import logging
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential

from config import AZURE

logger = logging.getLogger(__name__)

# ISO 639-1 code -> human-readable name, used in the generation prompt.
# Extend this as new regional languages are needed.
SUPPORTED_LANGUAGES = {
    "en": "English",
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "ur": "Urdu",
}

DEFAULT_LANGUAGE = "en"


class LanguageDetector:
    def __init__(self, config=AZURE):
        self.client = TextAnalyticsClient(
            endpoint=config.language_endpoint,
            credential=AzureKeyCredential(config.language_key),
        )

    def detect(self, text: str) -> str:
        """Returns an ISO 639-1 code, falling back to English on any failure
        or on a language we don't have a prompt-friendly name for."""
        try:
            result = self.client.detect_language(documents=[text])[0]
            code = result.primary_language.iso6391_name
            if code in SUPPORTED_LANGUAGES:
                return code
            logger.info("Detected unsupported language '%s', falling back to English", code)
            return DEFAULT_LANGUAGE
        except Exception as e:  # noqa: BLE001 - detection must never break the request
            logger.warning("Language detection failed (%s), defaulting to English", e)
            return DEFAULT_LANGUAGE

    @staticmethod
    def language_name(code: str) -> str:
        return SUPPORTED_LANGUAGES.get(code, "English")
