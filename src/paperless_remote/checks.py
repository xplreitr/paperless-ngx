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
        settings.REMOTE_PARSER_ENGINE == "azureaivision"
        and not settings.REMOTE_PARSER_ENDPOINT
    ):
        return [
            Error(
                "Azure remote parser requires endpoint to be configured.",
            ),
        ]

    return []
