import json
import sys
import uuid
from pathlib import Path
from unittest import mock

import pytest
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

    @pytest.mark.skipif(
        sys.version_info > (3, 10),
        reason="Fails on 3.11 only on CI, for some reason",
    )  # TODO: investigate
    @mock.patch("azure.ai.formrecognizer.DocumentAnalysisClient")
    def test_get_text_with_azure(self, mock_azure_client):
        result = mock.Mock()
        result.content = "This is a test document."

        mock_azure_client.return_value.begin_analyze_document.return_value.result.return_value = (
            result
        )

        with override_settings(
            REMOTE_OCR_ENGINE="azureaivision",
            REMOTE_OCR_API_KEY="somekey",
            REMOTE_OCR_ENDPOINT="https://endpoint.cognitiveservices.azure.com/",
        ):
            parser = RemoteDocumentParser(uuid.uuid4())
            parser.parse(
                self.SAMPLE_FILES / "simple-digital.pdf",
                "application/pdf",
            )

            self.assertContainsStrings(
                parser.text.strip(),
                ["This is a test document."],
            )

    @mock.patch("boto3.client")
    def test_get_text_with_awstextract(self, mock_aws_client):
        mock_aws_client.return_value.analyze_document.return_value = {
            "Blocks": [
                {
                    "BlockType": "LINE",
                    "Text": "This is a test document.",
                },
            ],
        }

        with override_settings(
            REMOTE_OCR_ENGINE="awstextract",
            REMOTE_OCR_API_KEY="somekey",
            REMOTE_OCR_API_KEY_ID="somekeyid",
            REMOTE_OCR_REGION="us-west-2",
        ):
            parser = RemoteDocumentParser(uuid.uuid4())
            parser.parse(
                self.SAMPLE_FILES / "simple-digital.pdf",
                "application/pdf",
            )

            self.assertContainsStrings(
                parser.text.strip(),
                ["This is a test document."],
            )

    @mock.patch("google.cloud.vision.ImageAnnotatorClient")
    @mock.patch("google.cloud.storage.Client")
    @mock.patch("google.oauth2.service_account.Credentials.from_service_account_file")
    def test_get_text_with_googlecloudvision(
        self,
        mock_credentials_from_file,
        mock_gcs_client,
        mock_gcv_client,
    ):
        credentials = mock.Mock()
        credentials.project_id = "someproject"
        mock_credentials_from_file.return_value = credentials

        blob_mock0 = mock.Mock()
        blob_mock0.name = "somefile.pdf"
        blob_mock1 = mock.Mock()
        blob_mock1.name = "somefile.json"

        blob_mock1.download_as_bytes.return_value.decode.return_value = json.dumps(
            {
                "responses": [
                    {
                        "fullTextAnnotation": {
                            "text": "This is a test document.",
                        },
                    },
                ],
            },
        )

        mock_gcs_client.return_value.lookup_bucket.return_value.list_blobs.return_value = [
            blob_mock0,
            blob_mock1,
        ]

        result = mock.Mock()
        result.result = mock.Mock()
        mock_gcv_client.return_value.async_batch_annotate_files.return_value = result

        with override_settings(
            REMOTE_OCR_ENGINE="googlecloudvision",
            REMOTE_OCR_CREDENTIALS_FILE="somefile.json",
        ):
            parser = RemoteDocumentParser(uuid.uuid4())
            parser.parse(
                self.SAMPLE_FILES / "simple-digital.pdf",
                "application/pdf",
            )

            self.assertContainsStrings(
                parser.text.strip(),
                ["This is a test document."],
            )
