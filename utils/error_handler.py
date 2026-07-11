import time
import functools
from typing import Callable, Any, Type
from utils.logger import logger

class MeetingAssistantException(Exception):
    """Base exception class for the Meeting Assistant application."""
    def __init__(self, message: str, user_message: str = None):
        super().__init__(message)
        self.user_message = user_message or "An unexpected error occurred. Please try again."

class ConfigurationError(MeetingAssistantException):
    """Raised when application environment variables are missing or invalid."""
    def __init__(self, message: str):
        super().__init__(message, f"Configuration Error: {message}")

class AudioValidationError(MeetingAssistantException):
    """Raised when an uploaded audio file fails format, existence, or size checks."""
    def __init__(self, message: str):
        super().__init__(message, f"Audio File Error: {message}")

class AzureSpeechError(MeetingAssistantException):
    """Raised when the Azure AI Speech service returns error responses or fails synthesis."""
    def __init__(self, message: str, details: str = None):
        user_msg = "Transcription service failed. Please check network connection and API keys."
        if details:
            user_msg += f" (Details: {details})"
        super().__init__(f"Speech SDK error: {message}", user_msg)

class EmptyTranscriptError(MeetingAssistantException):
    """Raised when transcription finishes successfully but yields zero text content."""
    def __init__(self):
        super().__init__(
            "Azure Speech returned success but transcript was empty.",
            "No spoken language could be recognized in the uploaded audio recording."
        )

class AzureLanguageError(MeetingAssistantException):
    """Raised when the Azure AI Language service fails text analysis or summarization."""
    def __init__(self, message: str, details: str = None):
        user_msg = "Language processing failed. Please verify your Azure AI Language subscription and endpoint region."
        if details:
            user_msg += f" (Details: {details})"
        super().__init__(f"Language SDK error: {message}", user_msg)

class LanguageValidationError(MeetingAssistantException):
    """Raised when input text violates size, format, or content requirements."""
    def __init__(self, message: str):
        super().__init__(message, f"Language Input Validation Error: {message}")

class AzureStorageError(MeetingAssistantException):
    """Raised when the Azure Blob Storage service operations fail."""
    def __init__(self, message: str, details: str = None):
        user_msg = "Cloud storage archiving failed. Please verify storage credentials and connection status."
        if details:
            user_msg += f" (Details: {details})"
        super().__init__(f"Storage SDK error: {message}", user_msg)

def handle_exception(exc: Exception) -> str:
    """
    Parses any exception and returns a sanitized, graceful user-facing error message
    while ensuring the full traceback or technical details are persisted in logs.
    
    Args:
        exc (Exception): The caught exception.

    Returns:
        str: Graceful notification message for frontend display.
    """
    if isinstance(exc, MeetingAssistantException):
        logger.error(f"{exc.__class__.__name__} caught: {str(exc)}")
        return exc.user_message
    
    # Azure Core HttpResponseError
    if exc.__class__.__name__ == "HttpResponseError":
        logger.error(f"Azure HTTP Response Error: {str(exc)}", exc_info=True)
        return "Failed to communicate with Azure. Please verify your keys and network access."

    # General fallback
    logger.critical(f"Unhandled exception encountered: {str(exc)}", exc_info=True)
    return f"A system error occurred: {str(exc)}"

def retry_on_failure(retries: int = 3, delay: float = 1.0, backoff: float = 2.0, exceptions: tuple = (Exception,)):
    """
    Decorator for wrapping calls with exponential backoff retry logic.
    
    Args:
        retries (int): Total retry attempts before letting exception propagate.
        delay (float): Initial wait time in seconds.
        backoff (float): Multiplier for subsequent retry delays.
        exceptions (tuple): Tuple of exception types to trigger a retry.
    """
    def decorator(func: Callable[..., Any]):
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_delay = delay
            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    logger.warning(
                        f"Attempt {attempt}/{retries} for function '{func.__name__}' "
                        f"failed with error: {str(e)}. Retrying in {current_delay:.2f}s..."
                    )
                    if attempt == retries:
                        logger.error(f"Function '{func.__name__}' failed after {retries} attempts.")
                        raise e
                    time.sleep(current_delay)
                    current_delay *= backoff
            return None
        return wrapper
    return decorator
