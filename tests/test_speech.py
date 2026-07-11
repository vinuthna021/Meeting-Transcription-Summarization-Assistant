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
import azure.cognitiveservices.speech as speechsdk
from services.speech_service import SpeechService, SpeechResult
from utils.error_handler import ConfigurationError, AudioValidationError, AzureSpeechError, EmptyTranscriptError
from utils.audio_validator import validate_audio_file

class TestAudioValidator(unittest.TestCase):
    """Unit tests for testing local audio file validation checks."""

    @patch("utils.audio_validator.os.path.getsize")
    @patch("utils.audio_validator.Path.exists")
    @patch("utils.audio_validator.Path.is_file")
    @patch("builtins.open", new_callable=mock_open, read_data=b"mock_bytes")
    def test_valid_audio(self, mock_file, mock_is_file, mock_exists, mock_getsize):
        # Setup: Existing, standard wav file, under size limit
        mock_exists.return_value = True
        mock_is_file.return_value = True
        mock_getsize.return_value = 1024 * 1024  # 1MB
        
        self.assertTrue(validate_audio_file("sample_audio/test_meeting.wav"))

    @patch("utils.audio_validator.Path.exists")
    def test_file_not_found(self, mock_exists):
        mock_exists.return_value = False
        with self.assertRaises(AudioValidationError) as context:
            validate_audio_file("missing_file.wav")
        self.assertIn("does not exist", str(context.exception))

    @patch("utils.audio_validator.Path.exists")
    @patch("utils.audio_validator.Path.is_file")
    def test_unsupported_format(self, mock_is_file, mock_exists):
        mock_exists.return_value = True
        mock_is_file.return_value = True
        with self.assertRaises(AudioValidationError) as context:
            validate_audio_file("document.txt")
        self.assertIn("Unsupported audio format", str(context.exception))

    @patch("utils.audio_validator.os.path.getsize")
    @patch("utils.audio_validator.Path.exists")
    @patch("utils.audio_validator.Path.is_file")
    def test_file_too_large(self, mock_is_file, mock_exists, mock_getsize):
        mock_exists.return_value = True
        mock_is_file.return_value = True
        mock_getsize.return_value = 60 * 1024 * 1024  # 60MB (Limit is 50MB)
        
        with self.assertRaises(AudioValidationError) as context:
            validate_audio_file("large_meeting.wav")
        self.assertIn("exceeds maximum allowed size", str(context.exception))


class TestSpeechService(unittest.TestCase):
    """Unit tests for SpeechService and Azure SDK integration mocks."""

    def setUp(self):
        # Set up a fresh service instance for each test
        self.service = SpeechService()

    @patch("services.speech_service.speechsdk.SpeechConfig")
    def test_initialize_success(self, mock_speech_config):
        self.service.initialize()
        self.assertTrue(self.service._is_initialized)
        mock_speech_config.assert_called_once_with(
            subscription="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            region="eastus"
        )

    @patch("services.speech_service.speechsdk.SpeechRecognizer")
    @patch("services.speech_service.speechsdk.audio.PushAudioInputStream")
    @patch("services.speech_service.speechsdk.audio.AudioConfig")
    def test_validate_connection_success(self, mock_audio_config, mock_stream, mock_recognizer):
        # Setup mock connection check returns
        mock_result = MagicMock()
        mock_result.reason = speechsdk.ResultReason.NoMatch
        mock_recognizer.return_value.recognize_once.return_value = mock_result
        
        self.service.initialize()
        self.assertTrue(self.service.validate_connection())

    @patch("services.speech_service.speechsdk.SpeechRecognizer")
    @patch("services.speech_service.speechsdk.audio.PushAudioInputStream")
    @patch("services.speech_service.speechsdk.audio.AudioConfig")
    def test_validate_connection_auth_failure(self, mock_audio_config, mock_stream, mock_recognizer):
        # Setup authentication cancellation error
        mock_result = MagicMock()
        mock_result.reason = speechsdk.ResultReason.Canceled
        
        # Patch cancellation details
        with patch("services.speech_service.speechsdk.CancellationDetails") as mock_cancel_details:
            details = MagicMock()
            details.reason = speechsdk.CancellationReason.Error
            details.error_details = "Authentication Failure: Access Denied due to invalid key."
            mock_cancel_details.return_value = details
            
            mock_recognizer.return_value.recognize_once.return_value = mock_result
            
            self.service.initialize()
            self.assertFalse(self.service.validate_connection())

    @patch("services.speech_service.speechsdk.SpeechRecognizer")
    def test_transcribe_success(self, mock_recognizer_class):
        # Setup continuous recognition callbacks simulation
        mock_recognizer = MagicMock()
        mock_recognizer_class.return_value = mock_recognizer

        # Store callbacks registered by connect()
        callbacks = {}
        def mock_connect(event_name):
            def connect_fn(callback_fn):
                callbacks[event_name] = callback_fn
            return connect_fn

        mock_recognizer.recognized.connect = mock_connect("recognized")
        mock_recognizer.session_stopped.connect = mock_connect("session_stopped")
        mock_recognizer.canceled.connect = mock_connect("canceled")

        # Simulate start_continuous_recognition to trigger events
        def mock_start():
            # Create mock events to pass to callbacks
            mock_recognized_event = MagicMock()
            mock_recognized_event.result.reason = speechsdk.ResultReason.RecognizedSpeech
            mock_recognized_event.result.text = "Hello, welcome to our meeting."
            mock_recognized_event.result.properties.get.return_value = (
                '{"NBest": [{"Confidence": 0.985, "Lexical": "hello welcome to our meeting"}]}'
            )

            # Fire recognized segment
            callbacks["recognized"](mock_recognized_event)

            # Fire session stopped
            mock_stopped_event = MagicMock()
            callbacks["session_stopped"](mock_stopped_event)

        mock_recognizer.start_continuous_recognition.side_effect = mock_start

        self.service.initialize()
        result = self.service.transcribe("sample_audio/test_meeting.wav")

        self.assertTrue(result.success)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.transcript, "Hello, welcome to our meeting.")
        self.assertEqual(result.confidence, 0.985)
        self.assertIsNone(result.error_message)

    @patch("services.speech_service.speechsdk.SpeechRecognizer")
    def test_transcribe_empty_file_fails(self, mock_recognizer_class):
        # Setup continuous recognition callbacks returning no text
        mock_recognizer = MagicMock()
        mock_recognizer_class.return_value = mock_recognizer

        callbacks = {}
        mock_recognizer.recognized.connect = lambda fn: callbacks.update({"recognized": fn})
        mock_recognizer.session_stopped.connect = lambda fn: callbacks.update({"session_stopped": fn})
        mock_recognizer.canceled.connect = lambda fn: callbacks.update({"canceled": fn})

        def mock_start():
            # Fire session stopped immediately without firing recognized
            callbacks["session_stopped"](MagicMock())

        mock_recognizer.start_continuous_recognition.side_effect = mock_start

        self.service.initialize()
        with self.assertRaises(EmptyTranscriptError):
            self.service.transcribe("sample_audio/silent_meeting.wav")

if __name__ == "__main__":
    unittest.main()
