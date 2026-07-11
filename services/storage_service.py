import time
from dataclasses import dataclass
from typing import List, Optional
from azure.storage.blob import BlobServiceClient, ContainerClient, BlobClient
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
from config.settings import settings
from utils.logger import logger
from utils.error_handler import AzureStorageError, retry_on_failure

@dataclass
class StorageResult:
    """
    Structured dataclass representing the standardized output
    of the Storage service operations.
    """
    success: bool
    blob_name: str
    blob_path: str
    processing_time: float
    status: str
    blob_url: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

class StorageService:
    """
    Service wrapper for the Microsoft Azure Blob Storage SDK.
    Coordinates private container operations and uploads meeting assets using folder prefixes.
    """

    def __init__(self):
        self.blob_service_client: Optional[BlobServiceClient] = None
        self.container_client: Optional[ContainerClient] = None
        self._is_initialized: bool = False

    def initialize(self) -> None:
        """
        Initializes the BlobServiceClient and ContainerClient from configuration.
        Fails fast on malformed connection strings.
        """
        logger.debug("Initializing Azure Storage client interfaces...")
        try:
            self.blob_service_client = BlobServiceClient.from_connection_string(
                settings.AZURE_STORAGE_CONNECTION_STRING
            )
            self.container_client = self.blob_service_client.get_container_client(
                settings.BLOB_CONTAINER_NAME
            )
            self._is_initialized = True
            logger.info("Azure Storage Client initialized successfully.")
        except Exception as e:
            self._is_initialized = False
            logger.error(f"Failed to initialize BlobServiceClient: {str(e)}")
            raise AzureStorageError("Storage SDK Initialization Failed", str(e))

    def validate_connection(self) -> bool:
        """
        Validates container credentials, existence, private access configurations,
        and TLS/HTTPS connectivity state.

        Returns:
            bool: True if container exists, is private, and is fully authenticated.
        """
        if not self._is_initialized:
            self.initialize()

        logger.debug("Validating connection and checking storage container properties...")
        try:
            # 1. Check container existence
            if not self.container_client.exists():
                logger.error(f"Target container '{settings.BLOB_CONTAINER_NAME}' does not exist.")
                return False

            # 2. Check container properties (authentication check)
            properties = self.container_client.get_container_properties()

            # 3. Verify private access level (no anonymous access)
            # public_access should be None for private containers
            if properties.public_access is not None:
                logger.warning(
                    f"Security Warning: Container '{settings.BLOB_CONTAINER_NAME}' "
                    f"has public access set to '{properties.public_access}'. Private access (None) is required."
                )
                return False

            logger.info("Storage container validated successfully (Private access & HTTPS connection active).")
            return True
        except Exception as e:
            logger.error(f"Failed during Storage Service connection verification: {str(e)}")
            return False

    @retry_on_failure(retries=3, delay=1.0, backoff=2.0, exceptions=(HttpResponseError,))
    def _upload_data(self, data: bytes, blob_path: str) -> None:
        """Helper to upload raw byte data with retry decorators for transient errors."""
        blob_client = self.container_client.get_blob_client(blob_path)
        blob_client.upload_blob(data, overwrite=True)

    def upload_audio(self, local_file_path: str, blob_name: str) -> StorageResult:
        """
        Uploads a local meeting recording file into the 'audio/' folder prefix.

        Args:
            local_file_path (str): Path to the validated local audio recording.
            blob_name (str): Standardized filename (e.g. meeting_20260708_100000.wav).

        Returns:
            StorageResult: Standardized result mapping upload status.
        """
        if not self._is_initialized:
            self.initialize()

        start_time = time.time()
        blob_path = f"audio/{blob_name}"
        logger.info(f"Uploading audio file '{local_file_path}' to cloud location '{blob_path}'...")

        try:
            with open(local_file_path, "rb") as audio_file:
                audio_data = audio_file.read()
            
            self._upload_data(audio_data, blob_path)
            
            duration = time.time() - start_time
            blob_client = self.container_client.get_blob_client(blob_path)
            
            logger.info(f"Audio file uploaded successfully in {duration:.2f}s.")
            return StorageResult(
                success=True,
                blob_name=blob_name,
                blob_path=blob_path,
                blob_url=blob_client.url,
                processing_time=duration,
                status="success"
            )
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Failed to upload audio to storage: {str(e)}")
            return StorageResult(
                success=False,
                blob_name=blob_name,
                blob_path=blob_path,
                processing_time=duration,
                status="failed",
                error_message=str(e)
            )

    def upload_transcript(self, transcript_text: str, blob_name: str) -> StorageResult:
        """
        Uploads a plain text transcript into the 'transcripts/' folder prefix.

        Args:
            transcript_text (str): Raw transcription text string.
            blob_name (str): Standardized transcript filename (e.g. meeting_20260708_100000.txt).

        Returns:
            StorageResult: Standardized upload output status metrics.
        """
        if not self._is_initialized:
            self.initialize()

        start_time = time.time()
        blob_path = f"transcripts/{blob_name}"
        logger.info(f"Uploading transcript text to cloud location '{blob_path}'...")

        try:
            text_data = transcript_text.encode("utf-8")
            self._upload_data(text_data, blob_path)
            
            duration = time.time() - start_time
            blob_client = self.container_client.get_blob_client(blob_path)
            
            logger.info(f"Transcript uploaded successfully in {duration:.2f}s.")
            return StorageResult(
                success=True,
                blob_name=blob_name,
                blob_path=blob_path,
                blob_url=blob_client.url,
                processing_time=duration,
                status="success"
            )
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Failed to upload transcript to storage: {str(e)}")
            return StorageResult(
                success=False,
                blob_name=blob_name,
                blob_path=blob_path,
                processing_time=duration,
                status="failed",
                error_message=str(e)
            )

    def upload_summary(self, summary_text: str, blob_name: str) -> StorageResult:
        """
        Uploads plain text summary content into the 'summaries/' folder prefix.

        Args:
            summary_text (str): Meeting summary text content.
            blob_name (str): Standardized summary filename (e.g. meeting_20260708_100000_summary.txt).

        Returns:
            StorageResult: Standardized upload output status metrics.
        """
        if not self._is_initialized:
            self.initialize()

        start_time = time.time()
        blob_path = f"summaries/{blob_name}"
        logger.info(f"Uploading meeting summary to cloud location '{blob_path}'...")

        try:
            text_data = summary_text.encode("utf-8")
            self._upload_data(text_data, blob_path)
            
            duration = time.time() - start_time
            blob_client = self.container_client.get_blob_client(blob_path)
            
            logger.info(f"Summary uploaded successfully in {duration:.2f}s.")
            return StorageResult(
                success=True,
                blob_name=blob_name,
                blob_path=blob_path,
                blob_url=blob_client.url,
                processing_time=duration,
                status="success"
            )
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Failed to upload summary to storage: {str(e)}")
            return StorageResult(
                success=False,
                blob_name=blob_name,
                blob_path=blob_path,
                processing_time=duration,
                status="failed",
                error_message=str(e)
            )

    def download_blob(self, blob_path: str) -> str:
        """
        Downloads a text-based blob content and decodes it as string.

        Args:
            blob_path (str): Prefix path location (e.g. transcripts/meeting_01.txt).

        Returns:
            str: Decoded text contents of the blob.
        """
        if not self._is_initialized:
            self.initialize()

        logger.info(f"Downloading text content from storage blob '{blob_path}'...")
        try:
            blob_client = self.container_client.get_blob_client(blob_path)
            download_stream = blob_client.download_blob()
            content = download_stream.readall()
            return content.decode("utf-8")
        except ResourceNotFoundError as e:
            logger.error(f"Storage blob resource not found at path '{blob_path}': {str(e)}")
            raise AzureStorageError(f"Blob not found: {blob_path}", str(e))
        except Exception as e:
            logger.error(f"Failed to download blob contents: {str(e)}")
            raise AzureStorageError("Blob download failed", str(e))

    def list_meetings(self) -> List[str]:
        """
        Lists all meeting base names (timestamps) by scanning the 'transcripts/' prefix.

        Returns:
            List[str]: List of meeting timestamps available in archive.
        """
        if not self._is_initialized:
            self.initialize()

        logger.debug("Listing archived meetings in Storage container...")
        meetings = []
        try:
            # List all blobs with transcripts/ prefix
            blobs = self.container_client.list_blobs(name_starts_with="transcripts/")
            for blob in blobs:
                # Extract filename without transcripts/ prefix and without extension
                filename = blob.name.split("/")[-1]
                if filename.endswith(".txt"):
                    base_meeting_name = filename[:-4]  # Remove '.txt'
                    meetings.append(base_meeting_name)
            
            # Sort chronologically, latest first
            meetings.sort(reverse=True)
            return meetings
        except Exception as e:
            logger.error(f"Failed to list meeting archives from Storage: {str(e)}")
            raise AzureStorageError("Listing meeting archives failed", str(e))

    def cleanup(self) -> None:
        """Performs graceful client teardown and resource disposal."""
        logger.debug("Closing Storage client sessions...")
        if self.blob_service_client:
            try:
                self.blob_service_client.close()
                logger.debug("Storage connection closed.")
            except Exception as e:
                logger.warning(f"Error closing storage service client: {str(e)}")
