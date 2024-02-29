import json
from pathlib import Path
from typing import Optional

from django.conf import settings

from paperless_tesseract.parsers import RasterisedDocumentParser


class RemoteEngineConfig:
    def __init__(
        self,
        engine: str,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_key_id: Optional[str] = None,
        region: Optional[str] = None,
        credentials_file: Optional[str] = None,
    ):
        self.engine = engine
        self.api_key = api_key
        self.endpoint = endpoint
        self.api_key_id = api_key_id
        self.region = region
        self.credentials_file = credentials_file

    def engine_is_valid(self):
        valid = (
            self.engine in ["azureaivision", "awstextract", "googlecloudvision"]
            and self.api_key is not None
        )
        if self.engine == "azureaivision":
            valid = valid and self.endpoint is not None
        if self.engine == "awstextract":
            valid = valid and self.region is not None and self.api_key_id is not None
        if self.engine == "googlecloudvision":
            valid = self.credentials_file is not None
        return valid


class RemoteDocumentParser(RasterisedDocumentParser):
    """
    This parser uses a remote ocr engine to parse documents
    """

    logging_name = "paperless.parsing.remote"

    def get_settings(self) -> RemoteEngineConfig:
        """
        This parser uses the OCR configuration settings to parse documents
        """
        return RemoteEngineConfig(
            engine=settings.REMOTE_OCR_ENGINE,
            api_key=settings.REMOTE_OCR_API_KEY,
            endpoint=settings.REMOTE_OCR_ENDPOINT,
            api_key_id=settings.REMOTE_OCR_API_KEY_ID,
            region=settings.REMOTE_OCR_REGION,
            credentials_file=settings.REMOTE_OCR_CREDENTIALS_FILE,
        )

    def supported_mime_types(self):
        if self.settings.engine_is_valid():
            if self.settings.engine == "googlecloudvision":
                return [
                    "application/pdf",
                    "image/tiff",
                ]
            else:
                return [
                    "application/pdf",
                    "image/png",
                    "image/jpeg",
                    "image/tiff",
                    "image/bmp",
                    "image/gif",
                    "image/webp",
                ]
        else:
            return []

    def aws_textract_parse(
        self,
        file: Path,
    ) -> Optional[str]:
        import boto3

        client = boto3.client(
            "textract",
            region_name=self.settings.region,
            aws_access_key_id=self.settings.api_key_id,
            aws_secret_access_key=self.settings.api_key,
        )

        lines = []
        with open(file, "rb") as f:
            file_bytes = f.read()
            file_bytearray = bytearray(file_bytes)

        self.log.info("Analyzing document with AWS Textract...")
        response = client.analyze_document(
            Document={"Bytes": file_bytearray},
            FeatureTypes=["TABLES"],
        )

        blocks = response["Blocks"]
        for block in blocks:
            if block["BlockType"] == "LINE":
                lines.append(block["Text"])

        return "\n".join(lines)

    def azure_ai_vision_parse(
        self,
        file: Path,
    ) -> Optional[str]:
        from azure.ai.formrecognizer import DocumentAnalysisClient
        from azure.core.credentials import AzureKeyCredential

        credential = AzureKeyCredential(self.settings.api_key)
        document_analysis_client = DocumentAnalysisClient(
            endpoint=self.settings.endpoint,
            credential=credential,
        )

        with open(file, "rb") as f:
            self.log.info("Analyzing document with Azure Vision AI...")
            poller = document_analysis_client.begin_analyze_document(
                "prebuilt-layout",
                document=f,
            )
        result = poller.result()

        return result.content

    def google_cloud_vision_parse(
        self,
        file: Path,
        mime_type: str,
    ) -> Optional[str]:
        # https://cloud.google.com/vision/docs/pdf
        from django.utils import timezone
        from google.cloud import storage
        from google.cloud import vision
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_file(
            self.settings.credentials_file,
        )

        client = vision.ImageAnnotatorClient(credentials=credentials)
        storage_client = storage.Client(credentials=credentials)

        self.log.info("Uploading document to Google Cloud Storage...")
        bucket_name = f"pngx_{credentials.project_id}_ocrstorage"
        bucket = storage_client.lookup_bucket(bucket_name)
        if bucket is None:
            bucket = storage_client.create_bucket(bucket_name)

        prefix = timezone.now().timestamp()
        blob = bucket.blob(f"{prefix}/{file.name}")
        blob.upload_from_filename(str(file))
        gcs_source_uri = f"gs://{bucket_name}/{prefix}/{file.name}"
        gcs_destination_uri = f"{gcs_source_uri}.json"

        gcs_source = vision.GcsSource(uri=gcs_source_uri)
        input_config = vision.InputConfig(gcs_source=gcs_source, mime_type=mime_type)

        gcs_destination = vision.GcsDestination(uri=gcs_destination_uri)
        output_config = vision.OutputConfig(
            gcs_destination=gcs_destination,
        )

        self.log.info("Analyzing document with Google Cloud Vision...")
        feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
        async_request = vision.AsyncAnnotateFileRequest(
            features=[feature],
            input_config=input_config,
            output_config=output_config,
        )

        operation = client.async_batch_annotate_files(requests=[async_request])

        self.log.info("Waiting for Google cloud operation to complete...")
        operation.result(timeout=180)

        # List objects with the given prefix, filtering out folders.
        blob_list = [
            blob
            for blob in list(bucket.list_blobs(prefix=prefix))
            if not blob.name.endswith("/")
        ]
        # second item is the json
        output = blob_list[1]

        json_string = output.download_as_bytes().decode("utf-8")
        response = json.loads(json_string)

        text = ""
        for response in response["responses"]:
            annotation = response["fullTextAnnotation"]
            text += annotation["text"]

        return text

    def parse(self, document_path: Path, mime_type, file_name=None):
        if not self.settings.engine_is_valid():
            self.log.warning(
                "No valid remote parser engine is configured, content will be empty.",
            )
            self.text = ""
            return
        elif self.settings.engine == "azureaivision":
            self.text = self.azure_ai_vision_parse(document_path)
        elif self.settings.engine == "awstextract":
            self.text = self.aws_textract_parse(document_path)
        elif self.settings.engine == "googlecloudvision":
            self.text = self.google_cloud_vision_parse(document_path, mime_type)
