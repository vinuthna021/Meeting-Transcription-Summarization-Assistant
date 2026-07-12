import os
from pathlib import Path
from dotenv import load_dotenv
from utils.logger import logger
from utils.error_handler import ConfigurationError

# Determine the absolute workspace root to safely resolve files
BASE_DIR = Path(__file__).resolve().parent.parent

# Load local environment variables from .env if present
env_path = BASE_DIR / ".env"
if env_path.exists() and os.getenv("TESTING") != "True":
    load_dotenv(dotenv_path=env_path, override=True)
    logger.info(f"Loaded configuration settings from local file: {env_path}")
else:
    logger.warning("No local .env file discovered. Relying on system environment variables.")

# Intercept Streamlit Secrets if running inside Streamlit Cloud/Local
try:
    import streamlit as st
    if hasattr(st, "secrets") and st.secrets:
        for key, val in st.secrets.items():
            if isinstance(val, str):
                os.environ[key] = val
except Exception:
    pass

class Settings:
    """
    Centralized configuration management class.
    Loads, parses, and validates required environment variables at application startup.
    Fails fast if any credentials or configurations are invalid.
    """
    
    def __init__(self):
        self.is_valid = False
        self.validation_error = "Configuration not loaded yet."
        self.AZURE_SPEECH_KEY = ""
        self.AZURE_SPEECH_REGION = ""
        self.AZURE_LANGUAGE_KEY = ""
        self.AZURE_LANGUAGE_ENDPOINT = ""
        self.AZURE_STORAGE_CONNECTION_STRING = ""
        self.BLOB_CONTAINER_NAME = "meeting-data"
        
        # Load once initially
        self.load()

    def load(self) -> None:
        """Loads and validates configuration from environment and streamlit secrets."""
        # Helper to get configuration from environment or streamlit secrets
        def get_config(key: str, default: str = "") -> str:
            val = os.getenv(key, "")
            if not val:
                try:
                    import streamlit as st
                    if hasattr(st, "secrets"):
                        # 1. Direct dictionary lookup
                        try:
                            val = st.secrets[key]
                        except Exception:
                            pass
                        
                        # 2. Direct attribute lookup
                        if not val:
                            try:
                                val = getattr(st.secrets, key)
                            except Exception:
                                pass
                                
                        # 3. Case-insensitive keys iteration lookup
                        if not val:
                            for k in st.secrets.keys():
                                if k.upper() == key.upper():
                                    try:
                                        val = st.secrets[k]
                                    except Exception:
                                        pass
                                    if not val:
                                        try:
                                            val = getattr(st.secrets, k)
                                        except Exception:
                                            pass
                                    if val:
                                        break
                except Exception as e:
                    logger.warning(f"Error reading secret {key}: {str(e)}")
            return str(val) if val else default

        # 1. Azure AI Speech Settings
        self.AZURE_SPEECH_KEY = get_config("AZURE_SPEECH_KEY", "").strip()
        self.AZURE_SPEECH_REGION = get_config("AZURE_SPEECH_REGION", "").strip()

        # 2. Azure AI Language Settings
        self.AZURE_LANGUAGE_KEY = get_config("AZURE_LANGUAGE_KEY", "").strip()
        self.AZURE_LANGUAGE_ENDPOINT = get_config("AZURE_LANGUAGE_ENDPOINT", "").strip()

        # 3. Azure Storage Settings
        self.AZURE_STORAGE_CONNECTION_STRING = get_config("AZURE_STORAGE_CONNECTION_STRING", "").strip()
        self.BLOB_CONTAINER_NAME = get_config("BLOB_CONTAINER_NAME", "meeting-data").strip()

        self.is_valid = True
        self.validation_error = None

        # Trigger configuration validation
        try:
            self.validate()
        except ConfigurationError as e:
            self.is_valid = False
            self.validation_error = str(e)

    def validate(self) -> None:
        """
        Validates all configuration attributes against business and cloud constraints.
        Raises ConfigurationError for missing keys or malformed URLs.
        """
        logger.debug("Executing startup configuration validations...")

        # A. Validate Speech config
        if not self.AZURE_SPEECH_KEY:
            raise ConfigurationError("AZURE_SPEECH_KEY environment variable is missing.")
            
        if not self.AZURE_SPEECH_REGION:
            raise ConfigurationError("AZURE_SPEECH_REGION environment variable is missing.")
        # Common region validation check (simple alphanumeric check)
        if not self.AZURE_SPEECH_REGION.isalnum():
            raise ConfigurationError(f"AZURE_SPEECH_REGION '{self.AZURE_SPEECH_REGION}' contains invalid characters.")

        # B. Validate Language config
        if not self.AZURE_LANGUAGE_KEY:
            raise ConfigurationError("AZURE_LANGUAGE_KEY environment variable is missing.")

        if not self.AZURE_LANGUAGE_ENDPOINT:
            raise ConfigurationError("AZURE_LANGUAGE_ENDPOINT environment variable is missing.")
        if not self.AZURE_LANGUAGE_ENDPOINT.startswith("https://"):
            raise ConfigurationError("AZURE_LANGUAGE_ENDPOINT must be a valid HTTPS URL (starting with 'https://').")

        # C. Validate Storage config
        if not self.AZURE_STORAGE_CONNECTION_STRING:
            raise ConfigurationError("AZURE_STORAGE_CONNECTION_STRING environment variable is missing.")
        # Ensure connection string looks valid
        if "DefaultEndpointsProtocol=https" not in self.AZURE_STORAGE_CONNECTION_STRING:
            raise ConfigurationError("AZURE_STORAGE_CONNECTION_STRING must enforce DefaultEndpointsProtocol=https.")
        if "AccountName=" not in self.AZURE_STORAGE_CONNECTION_STRING or "AccountKey=" not in self.AZURE_STORAGE_CONNECTION_STRING:
            raise ConfigurationError("AZURE_STORAGE_CONNECTION_STRING must contain 'AccountName' and 'AccountKey'.")

        if not self.BLOB_CONTAINER_NAME:
            raise ConfigurationError("BLOB_CONTAINER_NAME environment variable is missing.")
        
        # Enforce lowercase and naming guidelines for Blob containers
        if not self.BLOB_CONTAINER_NAME.islower() or not self.BLOB_CONTAINER_NAME.replace("-", "").isalnum():
            raise ConfigurationError(
                f"BLOB_CONTAINER_NAME '{self.BLOB_CONTAINER_NAME}' must contain only lowercase alphanumeric characters or hyphens."
            )

        logger.info("All configuration settings loaded and validated successfully.")

# Export a single global instance for application-wide importing
settings = Settings()
