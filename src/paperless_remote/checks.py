from django.conf import settings
from django.core.checks import Error
from django.core.checks import register


@register()
def check_remote_parser_configured(app_configs, **kwargs):
    if settings.REMOTE_PARSER_ENGINE and not settings.REMOTE_PARSER_API_KEY:
        return [
            Error(
                "No remote engine API key is configured.",
            ),
        ]

    if (
        settings.REMOTE_OCR_ENGINE == "azureaivision"
        and not settings.REMOTE_OCR_ENDPOINT
    ):
        return [
            Error(
                "Azure remote parser requires endpoint to be configured.",
            ),
        ]

    if settings.REMOTE_OCR_ENGINE == "awstextract" and (
        not settings.REMOTE_OCR_API_KEY_ID or not settings.REMOTE_OCR_REGION
    ):
        return [
            Error(
                "AWS Textract remote parser requires access key ID and region to be configured.",
            ),
        ]

    if settings.REMOTE_OCR_ENGINE == "googlecloudvision" and (
        not settings.REMOTE_OCR_CREDENTIALS_FILE
        or not settings.REMOTE_OCR_CREDENTIALS_FILE.exists()
    ):
        return [
            Error(
                "Google Cloud Vision remote parser requires a valid credentials file to be configured.",
            ),
        ]

    return []
