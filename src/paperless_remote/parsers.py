import json
from pathlib import Path
from typing import Optional

from django.conf import settings

from paperless_tesseract.parsers import RasterisedDocumentParser


class RemoteEngineConfig:
    def __init__(
        self,
        engine: str,
        api_key: str,
        endpoint: Optional[str] = None,
        api_key_id: Optional[str] = None,
        region: Optional[str] = None,
    ):
        self.engine = engine
        self.api_key = api_key
        self.endpoint = endpoint
        self.api_key_id = api_key_id
        self.region = region

    def engine_is_valid(self):
        valid = (
            self.engine in ["azureaivision", "awstextract", "googlecloudvision"]
            and self.api_key is not None
        )
        if self.engine == "azureaivision":
            valid = valid and self.endpoint is not None
        if self.engine == "awstextract":
            valid = valid and self.region is not None and self.api_key_id is not None
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
            engine=settings.REMOTE_PARSER_ENGINE,
            api_key=settings.REMOTE_PARSER_API_KEY,
            endpoint=settings.REMOTE_PARSER_ENDPOINT,
            api_key_id=settings.REMOTE_PARSER_API_KEY_ID,
            region=settings.REMOTE_PARSER_REGION,
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
        # Does not work
        # https://cloud.google.com/vision/docs/pdf
        from google.cloud import storage
        from google.cloud import vision
        from google.oauth2 import service_account

        credentials_dict = {
            "type": "service_account",
            # 'client_id': os.environ['BACKUP_CLIENT_ID'],
            # 'client_email': os.environ['BACKUP_CLIENT_EMAIL'],
            # 'private_key_id': os.environ['BACKUP_PRIVATE_KEY_ID'],
            # 'private_key': os.environ['BACKUP_PRIVATE_KEY'],
        }
        credentials = service_account.Credentials.from_json_keyfile_dict(
            credentials_dict,
        )

        client = vision.ImageAnnotatorClient(credentials=credentials)
        storage_client = storage.Client()
        bucket_name = "paperless-ngx"
        bucket = storage_client.get_bucket(bucket_name)
        blob = bucket.blob(file.name)
        blob.upload_from_filename(file.name)
        gcs_destination_uri = f"gs://{bucket_name}/{file.name}.json"

        feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)

        gcs_source = vision.GcsSource(uri=blob.public_url)
        input_config = vision.InputConfig(gcs_source=gcs_source, mime_type=mime_type)

        gcs_destination = vision.GcsDestination(uri=gcs_destination_uri)
        output_config = vision.OutputConfig(
            gcs_destination=gcs_destination,
        )

        async_request = vision.AsyncAnnotateFileRequest(
            features=[feature],
            input_config=input_config,
            output_config=output_config,
        )

        operation = client.async_batch_annotate_files(requests=[async_request])

        self.log.info("Waiting for Google cloud operation to complete...")
        operation.result(timeout=420)

        # List objects with the given prefix, filtering out folders.
        blob_list = [
            blob for blob in list(bucket.list_blobs()) if not blob.name.endswith("/")
        ]
        # Process the first output file from GCS.
        output = blob_list[0]

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
