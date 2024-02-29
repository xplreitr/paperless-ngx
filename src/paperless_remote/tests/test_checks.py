from django.test import TestCase
from django.test import override_settings

from paperless_remote import check_remote_parser_configured


class TestChecks(TestCase):
    @override_settings(REMOTE_OCR_ENGINE=None)
    def test_no_engine(self):
        msgs = check_remote_parser_configured(None)
        self.assertEqual(len(msgs), 0)

    @override_settings(REMOTE_OCR_ENGINE="azureaivision")
    @override_settings(REMOTE_OCR_API_KEY="somekey")
    @override_settings(REMOTE_OCR_ENDPOINT=None)
    def test_azure_no_endpoint(self):
        msgs = check_remote_parser_configured(None)
        self.assertEqual(len(msgs), 1)
        self.assertTrue(
            msgs[0].msg.startswith(
                "Azure remote parser requires endpoint to be configured.",
            ),
        )

    @override_settings(REMOTE_OCR_ENGINE="awstextract")
    @override_settings(REMOTE_OCR_API_KEY="somekey")
    @override_settings(REMOTE_OCR_API_KEY_ID=None)
    @override_settings(REMOTE_OCR_REGION=None)
    def test_aws_no_id_or_region(self):
        msgs = check_remote_parser_configured(None)
        self.assertEqual(len(msgs), 1)
        self.assertTrue(
            msgs[0].msg.startswith(
                "AWS Textract remote parser requires access key ID and region to be configured.",
            ),
        )

    @override_settings(REMOTE_OCR_ENGINE="googlecloudvision")
    @override_settings(REMOTE_OCR_CREDENTIALS_FILE=None)
    def test_gcv_no_creds_file(self):
        msgs = check_remote_parser_configured(None)
        self.assertEqual(len(msgs), 1)
        self.assertTrue(
            msgs[0].msg.startswith(
                "Google Cloud Vision remote parser requires a valid credentials file to be configured.",
            ),
        )

    @override_settings(REMOTE_OCR_ENGINE="something")
    @override_settings(REMOTE_OCR_API_KEY="somekey")
    def test_valid_configuration(self):
        msgs = check_remote_parser_configured(None)
        self.assertEqual(len(msgs), 0)
