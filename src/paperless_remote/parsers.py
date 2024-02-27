import json
from pathlib import Path
from typing import Optional

from django.conf import settings

from paperless_tesseract.parsers import RasterisedDocumentParser


class RemoteEngineConfig:
    def __init__(self, engine: str, api_key: str, endpoint: Optional[str] = None):
        self.engine = engine
        self.api_key = api_key
        self.endpoint = endpoint

    def engine_is_valid(self):
        valid = self.engine in ["chatgpt", "azureaivision"] and self.api_key is not None
        if self.engine == "azureaivision":
            valid = valid and self.endpoint is not None
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

    def chatgpt_parse(
        self,
        file: Path,
    ) -> Optional[str]:
        # does not work
        from openai import OpenAI

        client = OpenAI(
            api_key=self.settings.api_key,
        )
        assistants = client.beta.assistants.list()
        for assistant in assistants.data:
            if assistant.name == "Paperless-ngx Document Parser":
                assistant = assistant
                break
        if not assistant:
            assistant = client.beta.assistants.create(
                model="gpt-3.5-turbo",
                tools=[{"type": "code_interpreter"}],
                name="Paperless-ngx Document Parser",
            )

        self.log.info("Uploading document to OpenAI...")
        gpt_file = client.files.create(file=file, purpose="assistants")
        client.files.wait_for_processing(gpt_file.id)
        client.beta.assistants.update(assistant_id=assistant.id, files=[gpt_file.id])
        thread = client.beta.threads.create()
        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Output the text of the file",
        )
        client.beta.threads.runs.create(
            thread_id=thread,
            assistant_id=assistant.id,
        )
        response = client.beta.threads.messages.list(
            thread_id=thread.id,
        )
        self.text = response.data[0].content[0].text.value
        client.files.delete(gpt_file.id)

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
        elif self.settings.engine == "chatgpt":
            self.text = self.chatgpt_parse(document_path)
        elif self.settings.engine == "azureaivision":
            self.text = self.azure_ai_vision_parse(document_path)
        elif self.settings.engine == "googlecloudvision":
            self.text = self.google_cloud_vision_parse(document_path, mime_type)
        else:
            self.log.warning(
                "No valid remote parser engine is configured, content will be empty.",
            )
            self.text = ""
            return
