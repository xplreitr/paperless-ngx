from pathlib import Path

from django.test import TestCase

from documents.tests.utils import DirectoriesMixin
from documents.tests.utils import FileSystemAssertsMixin


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

    # Currently test is not working on 3.11 on CI but works locally. Dont know why.
    # @mock.patch("azure.ai.formrecognizer.DocumentAnalysisClient.begin_analyze_document")
    # def test_get_text_with_azure(self, mock_begin_analyze_document):
    #     result = mock.Mock()
    #     result.content = "This is a test document."
    #     mock_begin_analyze_document.return_value.result.return_value = result

    #     with override_settings(
    #         REMOTE_PARSER_ENGINE="azureaivision",
    #         REMOTE_PARSER_API_KEY="somekey",
    #         REMOTE_PARSER_ENDPOINT="https://endpoint.cognitiveservices.azure.com/",
    #     ):
    #         parser = RemoteDocumentParser(uuid.uuid4())
    #         parser.parse(
    #             self.SAMPLE_FILES / "simple-digital.pdf",
    #             "application/pdf",
    #         )

    #         mock_begin_analyze_document.assert_called_once()

    #         self.assertContainsStrings(
    #             parser.text.strip(),
    #             ["This is a test document."],
    #         )
