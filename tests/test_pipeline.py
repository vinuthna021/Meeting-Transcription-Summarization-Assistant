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
from unittest.mock import MagicMock, patch
from services.pipeline_service import PipelineService, PipelineResult
from services.speech_service import SpeechResult
from services.language_service import LanguageResult
from services.storage_service import StorageResult
from utils.error_handler import AudioValidationError

class TestPipelineService(unittest.TestCase):
    """Unit tests validating the PipelineService orchestrator workflow and error recovery bounds."""

    def setUp(self):
        self.service = PipelineService()
        self.service.initialize()

    @patch("services.pipeline_service.validate_audio_file")
    def test_pipeline_success(self, mock_validate):
        mock_validate.return_value = True

        # Mock sub-service results
        audio_res = StorageResult(success=True, blob_name="m.wav", blob_path="audio/m.wav", blob_url="url1", processing_time=0.1, status="success")
        speech_res = SpeechResult(success=True, status="success", transcript="Hello world.", processing_time=0.1, confidence=0.99)
        transcript_res = StorageResult(success=True, blob_name="m.txt", blob_path="transcripts/m.txt", blob_url="url2", processing_time=0.1, status="success")
        lang_res = LanguageResult(success=True, summary="Hello summary.", key_phrases=["world"], processing_time=0.1, status="success")
        summary_res = StorageResult(success=True, blob_name="m_summary.txt", blob_path="summaries/m_summary.txt", blob_url="url3", processing_time=0.1, status="success")

        with patch.object(self.service.storage_service, "upload_audio", return_value=audio_res), \
             patch.object(self.service.speech_service, "transcribe", return_value=speech_res), \
             patch.object(self.service.storage_service, "upload_transcript", return_value=transcript_res), \
             patch.object(self.service.language_service, "summarize_and_extract", return_value=lang_res), \
             patch.object(self.service.storage_service, "upload_summary", return_value=summary_res):
             
             result = self.service.process_meeting("sample_audio/test_meeting.wav")

             self.assertTrue(result.success)
             self.assertEqual(result.status, "success")
             self.assertEqual(result.transcript, "Hello world.")
             self.assertEqual(result.summary, "Hello summary.")
             self.assertEqual(result.key_phrases, ["world"])
             self.assertEqual(result.audio_blob.blob_url, "url1")
             self.assertEqual(result.transcript_blob.blob_url, "url2")
             self.assertEqual(result.summary_blob.blob_url, "url3")
             self.assertIsNone(result.error_message)

    @patch("services.pipeline_service.validate_audio_file")
    def test_pipeline_invalid_audio(self, mock_validate):
        # Setup: Audio validation throws exception
        mock_validate.side_effect = AudioValidationError("File size exceeds limit.")

        result = self.service.process_meeting("sample_audio/test_meeting.wav")

        self.assertFalse(result.success)
        self.assertEqual(result.status, "failed")
        self.assertIn("Audio File Error: File size exceeds limit", result.error_message)

    @patch("services.pipeline_service.validate_audio_file")
    def test_pipeline_audio_upload_failure(self, mock_validate):
        mock_validate.return_value = True
        
        # Audio upload fails
        audio_res = StorageResult(success=False, blob_name="m.wav", blob_path="audio/m.wav", processing_time=0.1, status="failed", error_message="Write Timeout")
        
        with patch.object(self.service.storage_service, "upload_audio", return_value=audio_res):
            result = self.service.process_meeting("sample_audio/test_meeting.wav")

            self.assertFalse(result.success)
            self.assertEqual(result.status, "failed")
            self.assertIn("Storage upload failed: Write Timeout", result.error_message)
            self.assertIsNone(result.transcript_blob)

    @patch("services.pipeline_service.validate_audio_file")
    def test_pipeline_speech_transcription_failure(self, mock_validate):
        mock_validate.return_value = True

        audio_res = StorageResult(success=True, blob_name="m.wav", blob_path="audio/m.wav", blob_url="url1", processing_time=0.1, status="success")
        # Speech transcription fails
        speech_res = SpeechResult(success=False, status="failed", transcript="", processing_time=0.1, error_message="Acoustic Noise")

        with patch.object(self.service.storage_service, "upload_audio", return_value=audio_res), \
             patch.object(self.service.speech_service, "transcribe", return_value=speech_res):
             
             result = self.service.process_meeting("sample_audio/test_meeting.wav")

             self.assertFalse(result.success)
             self.assertEqual(result.status, "failed")
             self.assertIn("(Details: Acoustic Noise)", result.error_message)

    @patch("services.pipeline_service.validate_audio_file")
    def test_pipeline_transcript_upload_failure(self, mock_validate):
        mock_validate.return_value = True

        audio_res = StorageResult(success=True, blob_name="m.wav", blob_path="audio/m.wav", blob_url="url1", processing_time=0.1, status="success")
        speech_res = SpeechResult(success=True, status="success", transcript="Hello world.", processing_time=0.1, confidence=0.99)
        # Transcript upload fails
        transcript_res = StorageResult(success=False, blob_name="m.txt", blob_path="transcripts/m.txt", processing_time=0.1, status="failed", error_message="Disk Full")

        with patch.object(self.service.storage_service, "upload_audio", return_value=audio_res), \
             patch.object(self.service.speech_service, "transcribe", return_value=speech_res), \
             patch.object(self.service.storage_service, "upload_transcript", return_value=transcript_res):
             
             result = self.service.process_meeting("sample_audio/test_meeting.wav")

             self.assertFalse(result.success)
             self.assertEqual(result.status, "failed")
             self.assertIn("Storage upload failed: Disk Full", result.error_message)

    @patch("services.pipeline_service.validate_audio_file")
    def test_pipeline_language_service_failure_recovers_transcript(self, mock_validate):
        mock_validate.return_value = True

        audio_res = StorageResult(success=True, blob_name="m.wav", blob_path="audio/m.wav", blob_url="url1", processing_time=0.1, status="success")
        speech_res = SpeechResult(success=True, status="success", transcript="Hello world.", processing_time=0.1, confidence=0.99)
        transcript_res = StorageResult(success=True, blob_name="m.txt", blob_path="transcripts/m.txt", blob_url="url2", processing_time=0.1, status="success")
        # Language summarization service fails
        lang_res = LanguageResult(success=False, summary="", key_phrases=[], processing_time=0.1, error_message="Endpoint Offline", status="failed")

        with patch.object(self.service.storage_service, "upload_audio", return_value=audio_res), \
             patch.object(self.service.speech_service, "transcribe", return_value=speech_res), \
             patch.object(self.service.storage_service, "upload_transcript", return_value=transcript_res), \
             patch.object(self.service.language_service, "summarize_and_extract", return_value=lang_res):
             
             result = self.service.process_meeting("sample_audio/test_meeting.wav")

             # Recovery verification: Pipeline reports success but with warnings
             # We should recover the text transcript and skip writing the summary
             self.assertTrue(result.success)
             self.assertEqual(result.status, "completed_with_warnings")
             self.assertEqual(result.transcript, "Hello world.")
             self.assertEqual(result.summary, "")
             self.assertIsNone(result.summary_blob)
             self.assertIn("Language Service failed", result.error_message)

    @patch("services.pipeline_service.validate_audio_file")
    def test_pipeline_summary_upload_failure(self, mock_validate):
        mock_validate.return_value = True

        audio_res = StorageResult(success=True, blob_name="m.wav", blob_path="audio/m.wav", blob_url="url1", processing_time=0.1, status="success")
        speech_res = SpeechResult(success=True, status="success", transcript="Hello world.", processing_time=0.1, confidence=0.99)
        transcript_res = StorageResult(success=True, blob_name="m.txt", blob_path="transcripts/m.txt", blob_url="url2", processing_time=0.1, status="success")
        lang_res = LanguageResult(success=True, summary="Hello summary.", key_phrases=["world"], processing_time=0.1, status="success")
        # Summary upload fails
        summary_res = StorageResult(success=False, blob_name="m_summary.txt", blob_path="summaries/m_summary.txt", processing_time=0.1, status="failed", error_message="Container locked")

        with patch.object(self.service.storage_service, "upload_audio", return_value=audio_res), \
             patch.object(self.service.speech_service, "transcribe", return_value=speech_res), \
             patch.object(self.service.storage_service, "upload_transcript", return_value=transcript_res), \
             patch.object(self.service.language_service, "summarize_and_extract", return_value=lang_res), \
             patch.object(self.service.storage_service, "upload_summary", return_value=summary_res):
             
             result = self.service.process_meeting("sample_audio/test_meeting.wav")

             self.assertFalse(result.success)
             self.assertEqual(result.status, "failed")
             self.assertIn("Storage upload failed: Container locked", result.error_message)

if __name__ == "__main__":
    unittest.main()
