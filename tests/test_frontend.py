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
import streamlit as st

class MockSessionState(dict):
    """
    Custom dictionary wrapper that supports attribute access (dot notation),
    acting like Streamlit's st.session_state during unit testing.
    """
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(f"'MockSessionState' object has no attribute '{item}'")

    def __setattr__(self, key, value):
        self[key] = value

# Import frontend modules
import app.main as main_app
from services.pipeline_service import PipelineResult

class TestFrontendDashboard(unittest.TestCase):
    """Unit tests for the Streamlit frontend layout and session state helpers."""

    def setUp(self):
        # Prepare mock session state properties
        self.mock_state = MockSessionState()
        # Patch Streamlit's session_state proxy object
        self.patcher_state = patch("app.main.st.session_state", self.mock_state)
        self.patcher_state.start()

    def tearDown(self):
        self.patcher_state.stop()

    def test_session_state_initialization(self):
        # Trigger initialization function
        main_app.init_session_state()
        
        # Verify default key setups
        self.assertIn("history", self.mock_state)
        self.assertIn("current_result", self.mock_state)
        self.assertIn("processing", self.mock_state)
        self.assertEqual(self.mock_state.history, [])
        self.assertIsNone(self.mock_state.current_result)
        self.assertFalse(self.mock_state.processing)

    @patch("app.main.PipelineService")
    def test_get_pipeline_service_caches_instance(self, mock_pipeline_class):
        # Verify cache returns initialized pipeline
        mock_instance = MagicMock()
        mock_pipeline_class.return_value = mock_instance
        
        service = main_app.get_pipeline_service()
        
        self.assertEqual(service, mock_instance)

    @patch("app.main.st.markdown")
    def test_render_header_invokes_markdown(self, mock_markdown):
        main_app.render_header()
        mock_markdown.assert_called_once()
        # Verify header title keyword exists in markdown string
        args, _ = mock_markdown.call_args
        self.assertIn("Meeting Transcription", args[0])

    @patch("app.main.st.info")
    def test_render_results_empty_state(self, mock_info):
        self.mock_state.current_result = None
        main_app.render_results()
        mock_info.assert_called_once_with(
            "Upload audio and click 'Process Meeting' to view results."
        )

    @patch("app.main.st.tabs")
    @patch("app.main.st.metric")
    @patch("app.main.st.subheader")
    def test_render_results_populated_state(self, mock_subheader, mock_metric, mock_tabs):
        # Mock populated results structure
        mock_res = PipelineResult(
            success=True,
            meeting_id="meeting_20260708_120000",
            transcript="Mock transcript text",
            summary="Mock summary text",
            key_phrases=["test"],
            processing_time=1.5,
            status="success"
        )
        self.mock_state.current_result = mock_res
        
        # Mock tabs structure return values
        mock_tab1 = MagicMock()
        mock_tab2 = MagicMock()
        mock_tab3 = MagicMock()
        mock_tab4 = MagicMock()
        mock_tab5 = MagicMock()
        mock_tab6 = MagicMock()
        mock_tab7 = MagicMock()
        mock_tabs.return_value = [mock_tab1, mock_tab2, mock_tab3, mock_tab4, mock_tab5, mock_tab6, mock_tab7]

        main_app.render_results()

        mock_subheader.assert_called_once_with("📊 Results Dashboard: meeting_20260708_120000")
        mock_metric.assert_any_call("Processing Status", "SUCCESS")
        mock_metric.assert_any_call("Total Latency", "1.50 seconds")
        mock_tabs.assert_called_once()

if __name__ == "__main__":
    unittest.main()
