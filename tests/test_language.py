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
from azure.core.exceptions import HttpResponseError
from services.language_service import LanguageService, LanguageResult
from utils.error_handler import LanguageValidationError, AzureLanguageError

class TestLanguageService(unittest.TestCase):
    """Unit tests for testing the LanguageService module and Azure AI Language SDK mocks."""

    def setUp(self):
        self.service = LanguageService()

    @patch("services.language_service.TextAnalyticsClient")
    def test_initialize_success(self, mock_client_class):
        self.service.initialize()
        self.assertTrue(self.service._is_initialized)
        mock_client_class.assert_called_once()

    def test_validate_transcript_none(self):
        with self.assertRaises(LanguageValidationError) as context:
            self.service.validate_transcript(None)
        self.assertIn("cannot be None", str(context.exception))

    def test_validate_transcript_empty(self):
        with self.assertRaises(LanguageValidationError) as context:
            self.service.validate_transcript("   ")
        self.assertIn("cannot be empty", str(context.exception))

    def test_validate_transcript_too_long(self):
        # 100,001 characters to trigger size limit validation
        long_text = "a" * 100001
        with self.assertRaises(LanguageValidationError) as context:
            self.service.validate_transcript(long_text)
        self.assertIn("exceeds maximum supported length", str(context.exception))

    @patch("services.language_service.TextAnalyticsClient")
    def test_validate_connection_success(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Mock key phrases connection response
        mock_resp = MagicMock()
        mock_resp.is_error = False
        mock_client.extract_key_phrases.return_value = [mock_resp]

        self.service.initialize()
        self.assertTrue(self.service.validate_connection())

    @patch("services.language_service.TextAnalyticsClient")
    def test_validate_connection_failure(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Simulate authentication error from Azure API
        mock_client.extract_key_phrases.side_effect = HttpResponseError("Access denied")

        self.service.initialize()
        self.assertFalse(self.service.validate_connection())

    @patch("services.language_service.TextAnalyticsClient")
    def test_summarize_and_extract_success(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # 1. Mock Key Phrases result
        mock_kp_doc = MagicMock()
        mock_kp_doc.is_error = False
        mock_kp_doc.key_phrases = ["Project Update", "Azure Speech", "Action Items", "Azure Speech"] # Contains duplicate
        mock_client.extract_key_phrases.return_value = [mock_kp_doc]

        # 2. Mock Extractive Summarization results
        sentence1 = MagicMock()
        sentence1.text = "This is summary sentence one."
        sentence2 = MagicMock()
        sentence2.text = "This is summary sentence two."

        action_result = MagicMock()
        action_result.kind = "ExtractiveSummarization"
        action_result.is_error = False
        action_result.sentences = [sentence1, sentence2]

        doc_results = [action_result]
        poller_result = [doc_results]

        mock_poller = MagicMock()
        mock_poller.result.return_value = poller_result
        mock_client.begin_analyze_actions.return_value = mock_poller

        self.service.initialize()
        result = self.service.summarize_and_extract("Hello. This is a transcript. This is summary sentence one. This is summary sentence two.")

        self.assertTrue(result.success)
        self.assertEqual(result.status, "success")
        
        # Verify structured summary format sections are generated
        self.assertIn("Meeting Summary", result.summary)
        self.assertIn("Meeting Overview", result.summary)
        self.assertIn("Main Discussion Topics", result.summary)
        self.assertIn("Important Decisions", result.summary)
        self.assertIn("Action Items", result.summary)
        self.assertIn("Overall Outcome", result.summary)
        self.assertIn("This is summary sentence one. This is summary sentence two.", result.summary)
        
        # Verify order and deduplication of key phrases
        self.assertEqual(result.key_phrases, ["Project Update", "Azure Speech", "Action Items"])
        self.assertIsNone(result.error_message)

    @patch("services.language_service.TextAnalyticsClient")
    def test_summarize_and_extract_summarization_fallback(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # 1. Mock Key Phrases success
        mock_kp_doc = MagicMock()
        mock_kp_doc.is_error = False
        mock_kp_doc.key_phrases = ["Action Items"]
        mock_client.extract_key_phrases.return_value = [mock_kp_doc]

        # 2. Mock Summarization raising an exception (e.g. Unsupported region / Free Tier restriction)
        mock_client.begin_analyze_actions.side_effect = HttpResponseError("Feature unsupported in this region")

        self.service.initialize()
        result = self.service.summarize_and_extract("Sentence one. Sentence two. Sentence three.")

        # Overall processing should still succeed by applying local fallback summarization
        self.assertTrue(result.success)
        self.assertEqual(result.status, "success")
        
        # Check that local fallback extracted the first two sentences inside Meeting Overview
        self.assertIn("Sentence one. Sentence two.", result.summary)
        self.assertEqual(result.key_phrases, ["Action Items"])

    @patch("services.language_service.TextAnalyticsClient")
    def test_summarize_and_extract_key_phrase_error_fails(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Simulate exception during key phrase extraction
        mock_client.extract_key_phrases.side_effect = Exception("Internal SDK Error")

        self.service.initialize()
        result = self.service.summarize_and_extract("Sentence one. Sentence two.")

        self.assertFalse(result.success)
        self.assertEqual(result.status, "failed")
        self.assertIn("Key Phrase Extraction failed", result.error_message)

    def test_heuristic_extractions(self):
        transcript = (
            "Today we will discuss project milestones. "
            "We decided to launch the product in September. "
            "Make sure to finish the code review before Friday. "
            "I will handle the deployment."
        )
        self.service.initialize()
        
        overview = self.service.build_meeting_overview(transcript, "Azure summary text")
        self.assertEqual(overview, "Azure summary text.")
        
        topics = self.service.extract_topics(transcript, ["milestones"])
        self.assertIn("Today we will discuss project milestones", topics)
        
        decisions = self.service.extract_decisions(transcript)
        self.assertIn("We decided to launch the product in September", decisions)
        
        actions = self.service.extract_action_items(transcript)
        self.assertIn("Make sure to finish the code review before Friday", actions)
        self.assertIn("I will handle the deployment", actions)

if __name__ == "__main__":
    unittest.main()
