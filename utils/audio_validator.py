import os
from pathlib import Path
from utils.logger import logger
from utils.error_handler import AudioValidationError

# Define global configuration constraints
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 Megabytes
SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a"}

def validate_audio_file(file_path: str) -> bool:
    """
    Performs comprehensive local checks on the target audio file:
    - Path existence
    - File readability
    - Supported extensions (.wav, .mp3, .m4a)
    - Maximum size constraints (<= 50MB)
    
    Args:
        file_path (str): Absolute or relative local path to the audio file.

    Returns:
        bool: True if the file successfully meets all validation checks.
        
    Raises:
        AudioValidationError: If any of the checks fail.
    """
    logger.debug(f"Initiating validation checks for target file: {file_path}")

    # 1. Check path type and existence
    if not file_path:
        raise AudioValidationError("Audio file path cannot be empty or null.")
    
    path_obj = Path(file_path)
    if not path_obj.exists():
        raise AudioValidationError(f"Audio file does not exist at location: {file_path}")
        
    if not path_obj.is_file():
        raise AudioValidationError(f"Target path exists but is not a valid file: {file_path}")

    # 2. Check file extension
    suffix = path_obj.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise AudioValidationError(
            f"Unsupported audio format '{suffix}'. Supported formats are: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    # 3. Check file size limits
    try:
        file_size = os.path.getsize(file_path)
    except OSError as e:
        raise AudioValidationError(f"Failed to read file metadata: {str(e)}")

    if file_size > MAX_FILE_SIZE_BYTES:
        max_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
        actual_mb = file_size / (1024 * 1024)
        raise AudioValidationError(
            f"File size ({actual_mb:.2f} MB) exceeds maximum allowed size ({max_mb:.0f} MB)."
        )

    if file_size == 0:
        raise AudioValidationError("Audio file is completely empty (0 bytes).")

    # 4. Check file readability
    try:
        with open(file_path, "rb") as f:
            # Try reading a tiny chunk (e.g. 1024 bytes) to verify filesystem permission
            f.read(1024)
    except (IOError, PermissionError) as e:
        raise AudioValidationError(f"File exists but is not readable due to permissions: {str(e)}")

    logger.info(f"Audio file '{path_obj.name}' ({file_size / (1024*1024):.2f} MB) validated successfully.")
    return True
