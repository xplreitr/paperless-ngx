import uuid
from pathlib import Path
from unittest import mock

from django.test import TestCase
from django.test import override_settings

from documents.tests.utils import DirectoriesMixin
from documents.tests.utils import FileSystemAssertsMixin
from paperless_remote.parsers import RemoteDocumentParser


class TestParser(DirectoriesMixin, FileSystemAssertsMixin, TestCase):
    SAMPLE_FILES = Path(__file__).resolve().parent / "samples"

    def assertContainsStrings(self, content, strings):
        # Asserts that all strings appear in content, in the given order.
        indices = []
        for s in strings:
            if s in content:
                indices.append(content.index(s))
            else:
                self.fail(f"'{s}' is not in '{content}'")
        self.assertListEqual(indices, sorted(indices))

    @mock.patch("azure.ai.formrecognizer.DocumentAnalysisClient.begin_analyze_document")
    def test_get_text_with_azure(self, mock_begin_analyze_document):
        result = mock.Mock()
        result.content = "This is a test document."
        mock_begin_analyze_document.return_value.result.return_value = result

        with override_settings(
            REMOTE_PARSER_ENGINE="azureaivision",
            REMOTE_PARSER_API_KEY="somekey",
            REMOTE_PARSER_ENDPOINT="https://endpoint.cognitiveservices.azure.com/",
        ):
            parser = RemoteDocumentParser(uuid.uuid4())
            parser.parse(
                self.SAMPLE_FILES / "simple-digital.pdf",
                "application/pdf",
            )

            mock_begin_analyze_document.assert_called_once()

            self.assertContainsStrings(
                parser.text.strip(),
                ["This is a test document."],
            )
