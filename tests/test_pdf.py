import unittest
import io
from services.pipeline_service import PipelineResult
from utils.pdf_generator import generate_meeting_pdf

class TestPDFGenerator(unittest.TestCase):
    def test_generate_pdf_success(self):
        # Create a mock result matching the pipeline result structure
        mock_result = PipelineResult(
            success=True,
            meeting_id="meeting_20260711_120000",
            transcript="Hello student success meeting John Smith guidance counselor John Smith wash hands",
            summary="Meeting Overview\n----------------------------------------\noverview content\n----------------------------------------\nMain Discussion Topics\n----------------------------------------\n• John Smith stress\n• Guidance counselor recommendation\n----------------------------------------\nDecisions\n----------------------------------------\n• John Smith speaks to guidance counselor\n----------------------------------------\nAction Items\n----------------------------------------\n• Ask John to visit office\n----------------------------------------\nOverall Outcome\n----------------------------------------\noutcome content",
            key_phrases=["student success", "guidance counselor", "John Smith"],
            processing_time=12.34,
            status="success",
            upload_time=1.2,
            transcribe_time=5.6,
            language_time=4.5,
            blob_upload_time=1.0,
            confidence=0.96,
            audio_duration=45.0,
            original_filename="meeting.wav",
            file_size_bytes=1024*1024
        )
        
        pdf_stream = generate_meeting_pdf(mock_result, manual_verification_text="guidance counselor", manual_accuracy=98.5)
        self.assertIsInstance(pdf_stream, io.BytesIO)
        pdf_bytes = pdf_stream.getvalue()
        self.assertTrue(len(pdf_bytes) > 0)
        
        # Verify standard PDF magic bytes signature (%PDF)
        self.assertEqual(pdf_bytes[:4], b'%PDF')

if __name__ == '__main__':
    unittest.main()
