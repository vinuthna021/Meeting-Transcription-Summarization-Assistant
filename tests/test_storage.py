import os
os.environ["TESTING"] = "True"

# Seed dummy environment credentials to pass import-time validations
os.environ["AZURE_SPEECH_KEY"] = "x" * 32
os.environ["AZURE_SPEECH_REGION"] = "eastus"
os.environ["AZURE_LANGUAGE_KEY"] = "y" * 32
os.environ["AZURE_LANGUAGE_ENDPOINT"] = "https://dummy-endpoint.cognitiveservices.azure.com/"
os.environ["AZURE_STORAGE_CONNECTION_STRING"] = "DefaultEndpointsProtocol=https;AccountName=dummy;AccountKey=dummykey;EndpointSuffix=core.windows.net"
os.environ["BLOB_CONTAINER_NAME"] = "meeting-data"

import unittest
from unittest.mock import MagicMock, patch, mock_open
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
from services.storage_service import StorageService, StorageResult
from utils.error_handler import AzureStorageError

class TestStorageService(unittest.TestCase):
    """Unit tests for testing StorageService and Azure Blob SDK integrations using mocks."""

    def setUp(self):
        self.service = StorageService()

    @patch("services.storage_service.BlobServiceClient")
    def test_initialize_success(self, mock_service_class):
        self.service.initialize()
        self.assertTrue(self.service._is_initialized)
        mock_service_class.from_connection_string.assert_called_once_with(
            os.environ["AZURE_STORAGE_CONNECTION_STRING"]
        )

    @patch("services.storage_service.BlobServiceClient")
    def test_validate_connection_success(self, mock_service_class):
        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_properties = MagicMock()
        
        mock_properties.public_access = None  # None indicates Private Access
        mock_container.exists.return_value = True
        mock_container.get_container_properties.return_value = mock_properties
        mock_service.get_container_client.return_value = mock_container
        mock_service_class.from_connection_string.return_value = mock_service

        self.service.initialize()
        self.assertTrue(self.service.validate_connection())

    @patch("services.storage_service.BlobServiceClient")
    def test_validate_connection_missing_container(self, mock_service_class):
        mock_service = MagicMock()
        mock_container = MagicMock()
        
        mock_container.exists.return_value = False
        mock_service.get_container_client.return_value = mock_container
        mock_service_class.from_connection_string.return_value = mock_service

        self.service.initialize()
        self.assertFalse(self.service.validate_connection())

    @patch("services.storage_service.BlobServiceClient")
    def test_validate_connection_public_access_failure(self, mock_service_class):
        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_properties = MagicMock()
        
        mock_properties.public_access = "blob"  # Indicates public access is active
        mock_container.exists.return_value = True
        mock_container.get_container_properties.return_value = mock_properties
        mock_service.get_container_client.return_value = mock_container
        mock_service_class.from_connection_string.return_value = mock_service

        self.service.initialize()
        # Should return False to enforce private access level security rules
        self.assertFalse(self.service.validate_connection())

    @patch("services.storage_service.BlobServiceClient")
    @patch("builtins.open", new_callable=mock_open, read_data=b"dummy_wav_bytes")
    def test_upload_audio_success(self, mock_file, mock_service_class):
        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_blob = MagicMock()
        
        mock_blob.url = "https://dummy.blob.core.windows.net/meeting-data/audio/meeting.wav"
        mock_container.get_blob_client.return_value = mock_blob
        mock_service.get_container_client.return_value = mock_container
        mock_service_class.from_connection_string.return_value = mock_service

        self.service.initialize()
        result = self.service.upload_audio("sample_audio/test_meeting.wav", "meeting.wav")

        self.assertTrue(result.success)
        self.assertEqual(result.blob_name, "meeting.wav")
        self.assertEqual(result.blob_path, "audio/meeting.wav")
        self.assertEqual(result.blob_url, mock_blob.url)
        mock_blob.upload_blob.assert_called_once_with(b"dummy_wav_bytes", overwrite=True)

    @patch("services.storage_service.BlobServiceClient")
    def test_upload_transcript_success(self, mock_service_class):
        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_blob = MagicMock()
        
        mock_blob.url = "https://dummy.blob.core.windows.net/meeting-data/transcripts/meeting.txt"
        mock_container.get_blob_client.return_value = mock_blob
        mock_service.get_container_client.return_value = mock_container
        mock_service_class.from_connection_string.return_value = mock_service

        self.service.initialize()
        result = self.service.upload_transcript("Transcript text content", "meeting.txt")

        self.assertTrue(result.success)
        self.assertEqual(result.blob_path, "transcripts/meeting.txt")
        mock_blob.upload_blob.assert_called_once_with("Transcript text content".encode("utf-8"), overwrite=True)

    @patch("services.storage_service.BlobServiceClient")
    def test_upload_summary_success(self, mock_service_class):
        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_blob = MagicMock()
        
        mock_blob.url = "https://dummy.blob.core.windows.net/meeting-data/summaries/meeting_summary.txt"
        mock_container.get_blob_client.return_value = mock_blob
        mock_service.get_container_client.return_value = mock_container
        mock_service_class.from_connection_string.return_value = mock_service

        self.service.initialize()
        result = self.service.upload_summary("Summary text content", "meeting_summary.txt")

        self.assertTrue(result.success)
        self.assertEqual(result.blob_path, "summaries/meeting_summary.txt")
        mock_blob.upload_blob.assert_called_once_with("Summary text content".encode("utf-8"), overwrite=True)

    @patch("services.storage_service.BlobServiceClient")
    def test_upload_blob_failure(self, mock_service_class):
        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_blob = MagicMock()
        
        # Simulate fatal error on write
        mock_blob.upload_blob.side_effect = Exception("Write Permission Blocked")
        mock_container.get_blob_client.return_value = mock_blob
        mock_service.get_container_client.return_value = mock_container
        mock_service_class.from_connection_string.return_value = mock_service

        self.service.initialize()
        result = self.service.upload_summary("Summary content", "meeting_summary.txt")

        self.assertFalse(result.success)
        self.assertEqual(result.status, "failed")
        self.assertIn("Write Permission Blocked", result.error_message)

    @patch("services.storage_service.BlobServiceClient")
    def test_download_blob_success(self, mock_service_class):
        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_blob = MagicMock()
        mock_download = MagicMock()
        
        mock_download.readall.return_value = b"Downloaded content"
        mock_blob.download_blob.return_value = mock_download
        mock_container.get_blob_client.return_value = mock_blob
        mock_service.get_container_client.return_value = mock_container
        mock_service_class.from_connection_string.return_value = mock_service

        self.service.initialize()
        content = self.service.download_blob("transcripts/meeting.txt")
        self.assertEqual(content, "Downloaded content")

    @patch("services.storage_service.BlobServiceClient")
    def test_list_meetings_success(self, mock_service_class):
        mock_service = MagicMock()
        mock_container = MagicMock()
        
        # Mock returned blob names
        blob1 = MagicMock()
        blob1.name = "transcripts/meeting_20260708_100000.txt"
        blob2 = MagicMock()
        blob2.name = "transcripts/meeting_20260708_110000.txt"
        
        mock_container.list_blobs.return_value = [blob1, blob2]
        mock_service.get_container_client.return_value = mock_container
        mock_service_class.from_connection_string.return_value = mock_service

        self.service.initialize()
        meetings = self.service.list_meetings()

        # Should parse base names and sort reverse chronologically
        self.assertEqual(meetings, ["meeting_20260708_110000", "meeting_20260708_100000"])

    @patch("services.storage_service.BlobServiceClient")
    def test_retry_transient_failure_then_succeeds(self, mock_service_class):
        mock_service = MagicMock()
        mock_container = MagicMock()
        mock_blob = MagicMock()
        
        # Fail first call with transient error, succeed on second attempt
        mock_blob.upload_blob.side_effect = [
            HttpResponseError("Transient Connection Interrupted"),
            None
        ]
        mock_container.get_blob_client.return_value = mock_blob
        mock_service.get_container_client.return_value = mock_container
        mock_service_class.from_connection_string.return_value = mock_service

        self.service.initialize()
        
        # Patch sleep to speed up test execution
        with patch("utils.error_handler.time.sleep") as mock_sleep:
            result = self.service.upload_summary("Summary content", "meeting_summary.txt")
            
            # Overall upload should report success
            self.assertTrue(result.success)
            # Verify sleep wait occurred for backoff
            mock_sleep.assert_called_once()
            # Assert SDK was called twice
            self.assertEqual(mock_blob.upload_blob.call_count, 2)

if __name__ == "__main__":
    unittest.main()
