"""Language of the desktop interface. Stored user content stays verbatim."""

_language = "en"


def set_language(language):
    global _language
    _language = "ru" if language == "ru" else "en"


def tr(english, russian):
    return russian if _language == "ru" else english
