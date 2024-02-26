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
            poller = document_analysis_client.begin_analyze_document(
                "prebuilt-layout",
                document=f,
            )
        result = poller.result()

        return result.content

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
