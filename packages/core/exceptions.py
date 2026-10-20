from typing import Optional, Dict, Any


class TranslationStudioException(Exception):
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class InvalidPDFError(TranslationStudioException):
    def __init__(self, message: str = "Invalid or corrupted PDF file", details: Optional[Dict[str, Any]] = None):
        super().__init__("INVALID_PDF", message, details)


class FileTooLargeError(TranslationStudioException):
    def __init__(self, message: str = "File size exceeds configured maximum limit", details: Optional[Dict[str, Any]] = None):
        super().__init__("FILE_TOO_LARGE", message, details)


class PageLimitExceededError(TranslationStudioException):
    def __init__(self, message: str = "Page count exceeds allowed limit", details: Optional[Dict[str, Any]] = None):
        super().__init__("PAGE_LIMIT_EXCEEDED", message, details)


class LanguageUndeterminedError(TranslationStudioException):
    def __init__(self, message: str = "Source language could not be determined with sufficient confidence", details: Optional[Dict[str, Any]] = None):
        super().__init__("LANGUAGE_UNDETERMINED", message, details)


class CostLimitExceededError(TranslationStudioException):
    def __init__(self, message: str = "Estimated translation cost exceeds configured budget limit", details: Optional[Dict[str, Any]] = None):
        super().__init__("COST_LIMIT_EXCEEDED", message, details)


class ProviderUnavailableError(TranslationStudioException):
    def __init__(self, provider: str, message: str = "Provider service is unavailable or circuit is open", details: Optional[Dict[str, Any]] = None):
        super().__init__("PROVIDER_UNAVAILABLE", f"{provider}: {message}", details)


class ValidationError(TranslationStudioException):
    def __init__(self, rule: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(rule, message, details)


class LayoutError(TranslationStudioException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__("LAYOUT_FAILED", message, details)
