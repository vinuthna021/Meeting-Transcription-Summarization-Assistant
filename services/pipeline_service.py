import time
import uuid
from dataclasses import dataclass
from typing import List, Optional
from config.settings import settings
from utils.logger import logger
from utils.error_handler import handle_exception, MeetingAssistantException, AzureSpeechError, AzureLanguageError, AzureStorageError
from utils.audio_validator import validate_audio_file
from services.speech_service import SpeechService, SpeechResult
from services.language_service import LanguageService, LanguageResult
from services.storage_service import StorageService, StorageResult

@dataclass
class PipelineResult:
    """
    Structured dataclass representing the final consolidated output
    of the entire meeting transcription and analysis pipeline.
    """
    success: bool
    meeting_id: str
    audio_blob: Optional[StorageResult] = None
    transcript_blob: Optional[StorageResult] = None
    summary_blob: Optional[StorageResult] = None
    transcript: str = ""
    summary: str = ""
    key_phrases: List[str] = None
    processing_time: float = 0.0
    status: str = "failed"
    error_message: Optional[str] = None
    upload_time: float = 0.0
    transcribe_time: float = 0.0
    language_time: float = 0.0
    blob_upload_time: float = 0.0
    confidence: Optional[float] = None
    audio_duration: float = 0.0
    original_filename: str = ""
    file_size_bytes: int = 0

    def __post_init__(self):
        if self.key_phrases is None:
            self.key_phrases = []

class PipelineService:
    """
    Orchestration service that chains together audio validation, storage archival,
    speech transcription, and language summarization services into a unified workflow.
    """

    def __init__(self):
        self.speech_service = SpeechService()
        self.language_service = LanguageService()
        self.storage_service = StorageService()
        self._is_initialized = False

    def initialize(self) -> None:
        """Initializes all underlying clients for Speech, Language, and Storage services."""
        logger.debug("Initializing pipeline service and sub-services...")
        self.speech_service.initialize()
        self.language_service.initialize()
        self.storage_service.initialize()
        self._is_initialized = True
        logger.info("Pipeline service and sub-services initialized successfully.")

    def validate_connections(self) -> bool:
        """
        Runs connection verification handshakes on all three integrated Azure services.

        Returns:
            bool: True if all services successfully authenticate and report active connections.
        """
        if not self._is_initialized:
            self.initialize()

        logger.debug("Executing pipeline-wide connection verification handshakes...")
        speech_ok = self.speech_service.validate_connection()
        lang_ok = self.language_service.validate_connection()
        storage_ok = self.storage_service.validate_connection()

        if speech_ok and lang_ok and storage_ok:
            logger.info("All Azure service connections are healthy and verified.")
            return True
        
        logger.error(
            f"Pipeline connection verification failed. "
            f"Speech: {'OK' if speech_ok else 'FAILED'}, "
            f"Language: {'OK' if lang_ok else 'FAILED'}, "
            f"Storage: {'OK' if storage_ok else 'FAILED'}"
        )
        return False

    def _generate_meeting_id(self) -> str:
        """Generates a unique chronological base identifier for the meeting."""
        random_suffix = uuid.uuid4().hex[:4]
        return f"meeting_{time.strftime('%Y%m%d_%H%M%S')}_{random_suffix}"

    def run_pipeline(self, local_audio_path: str) -> PipelineResult:
        """
        Orchestrates the end-to-end execution of the meeting assistant workflow.
        
        Args:
            local_audio_path (str): Filepath to the raw audio recording.
            
        Returns:
            PipelineResult: Struct containing status and outputs.
        """
        start_time = time.time()
        import os
        meeting_id = f"meeting_{time.strftime('%Y%m%d_%H%M%S')}_{os.urandom(2).hex()}"
        
        logger.info(f"Pipeline execution started for meeting: {meeting_id}")

        # Extract file size, original filename, and duration using PyAV
        file_size_bytes = 0
        original_filename = ""
        audio_duration = 0.0
        try:
            if os.path.exists(local_audio_path):
                file_size_bytes = os.path.getsize(local_audio_path)
                original_filename = os.path.basename(local_audio_path)
                try:
                    import av
                    with av.open(local_audio_path) as container:
                        if container.duration is not None:
                            audio_duration = float(container.duration) / 1000000.0
                except Exception as e:
                    logger.warning(f"Could not read audio duration: {str(e)}")
            else:
                original_filename = os.path.basename(local_audio_path)
        except Exception as e:
            logger.warning(f"Error reading file stats: {str(e)}")

        # 1. Local Audio Validation
        try:
            validate_audio_file(local_audio_path)
        except Exception as e:
            err_msg = handle_exception(e)
            logger.error(f"Pipeline aborted: audio file validation failed: {str(e)}")
            return PipelineResult(
                success=False,
                meeting_id=meeting_id,
                processing_time=time.time() - start_time,
                status="failed",
                error_message=err_msg,
                original_filename=original_filename,
                file_size_bytes=file_size_bytes,
                audio_duration=audio_duration
            )

        # Ensure clients are initialized
        if not self._is_initialized:
            self.initialize()

        # Extract file extension for upload mapping
        file_ext = os.path.splitext(local_audio_path)[-1].lower()
        audio_blob_name = f"{meeting_id}{file_ext}"
        
        # 2. Upload raw audio file to Blob Storage
        t_audio_upload_start = time.time()
        audio_upload_res = self.storage_service.upload_audio(local_audio_path, audio_blob_name)
        upload_time = time.time() - t_audio_upload_start
        
        if not audio_upload_res.success:
            logger.error(f"Pipeline aborted: audio upload to Blob Storage failed: {audio_upload_res.error_message}")
            return PipelineResult(
                success=False,
                meeting_id=meeting_id,
                audio_blob=audio_upload_res,
                processing_time=time.time() - start_time,
                status="failed",
                error_message=f"Storage upload failed: {audio_upload_res.error_message}",
                upload_time=upload_time,
                original_filename=original_filename,
                file_size_bytes=file_size_bytes,
                audio_duration=audio_duration
            )

        # 3. Speech-to-Text Transcription
        transcript_text = ""
        speech_result: Optional[SpeechResult] = None
        t_transcribe_start = time.time()
        try:
            speech_result = self.speech_service.transcribe(local_audio_path)
            transcribe_time = time.time() - t_transcribe_start
            if not speech_result.success:
                raise AzureSpeechError("Transcription failed.", speech_result.error_message)
            transcript_text = speech_result.transcript
            logger.info("Speech transcription completed successfully.")
        except Exception as e:
            err_msg = handle_exception(e)
            transcribe_time = time.time() - t_transcribe_start
            logger.error(f"Pipeline aborted: Speech transcription failed: {str(e)}")
            return PipelineResult(
                success=False,
                meeting_id=meeting_id,
                audio_blob=audio_upload_res,
                processing_time=time.time() - start_time,
                status="failed",
                error_message=err_msg,
                upload_time=upload_time,
                transcribe_time=transcribe_time,
                original_filename=original_filename,
                file_size_bytes=file_size_bytes,
                audio_duration=audio_duration
            )

        # 4. Upload transcript to Blob Storage
        transcript_blob_name = f"{meeting_id}.txt"
        t_blob_upload_start = time.time()
        transcript_upload_res = self.storage_service.upload_transcript(transcript_text, transcript_blob_name)
        blob_upload_time = time.time() - t_blob_upload_start
        
        if not transcript_upload_res.success:
            logger.error(f"Pipeline aborted: transcript upload to Blob Storage failed: {transcript_upload_res.error_message}")
            return PipelineResult(
                success=False,
                meeting_id=meeting_id,
                audio_blob=audio_upload_res,
                transcript_blob=transcript_upload_res,
                transcript=transcript_text,
                processing_time=time.time() - start_time,
                status="failed",
                error_message=f"Storage upload failed: {transcript_upload_res.error_message}",
                upload_time=upload_time,
                transcribe_time=transcribe_time,
                blob_upload_time=blob_upload_time,
                original_filename=original_filename,
                file_size_bytes=file_size_bytes,
                audio_duration=audio_duration,
                confidence=speech_result.confidence if speech_result else None
            )

        # 5. Language analysis (Summarization & Key Phrases)
        language_result: Optional[LanguageResult] = None
        summary_upload_res: Optional[StorageResult] = None
        summary_text = ""
        key_phrases: List[str] = []
        t_language_start = time.time()

        try:
            logger.info(f"DIAGNOSTIC: Full transcript before summarization:\n{transcript_text}")
            language_result = self.language_service.summarize_and_extract(transcript_text)
            language_time = time.time() - t_language_start
            if not language_result.success:
                raise AzureLanguageError("Language analysis failed.", language_result.error_message)
            
            summary_text = language_result.summary
            key_phrases = language_result.key_phrases
            logger.info("Language analysis completed successfully.")

            # 6. Upload summary to Blob Storage (only executed if Language succeeded)
            summary_blob_name = f"{meeting_id}_summary.txt"
            t_summary_upload_start = time.time()
            summary_upload_res = self.storage_service.upload_summary(summary_text, summary_blob_name)
            blob_upload_time += (time.time() - t_summary_upload_start)
            
            if not summary_upload_res.success:
                logger.error(f"Pipeline aborted: summary upload to Blob Storage failed: {summary_upload_res.error_message}")
                return PipelineResult(
                    success=False,
                    meeting_id=meeting_id,
                    audio_blob=audio_upload_res,
                    transcript_blob=transcript_upload_res,
                    summary_blob=summary_upload_res,
                    transcript=transcript_text,
                    processing_time=time.time() - start_time,
                    status="failed",
                    error_message=f"Storage upload failed: {summary_upload_res.error_message}",
                    upload_time=upload_time,
                    transcribe_time=transcribe_time,
                    language_time=language_time,
                    blob_upload_time=blob_upload_time,
                    original_filename=original_filename,
                    file_size_bytes=file_size_bytes,
                    audio_duration=audio_duration,
                    confidence=speech_result.confidence if speech_result else None
                )

        except Exception as e:
            err_msg = handle_exception(e)
            if 'language_time' not in locals():
                language_time = time.time() - t_language_start
            logger.warning(
                f"Language analysis failed. Returning transcript without summary. Details: {err_msg}"
            )
            duration = time.time() - start_time
            logger.info(f"Pipeline completed with warnings in {duration:.2f}s.")
            return PipelineResult(
                success=True,
                meeting_id=meeting_id,
                audio_blob=audio_upload_res,
                transcript_blob=transcript_upload_res,
                transcript=transcript_text,
                processing_time=duration,
                status="completed_with_warnings",
                error_message=f"Language Service failed: {err_msg}",
                upload_time=upload_time,
                transcribe_time=transcribe_time,
                language_time=language_time,
                blob_upload_time=blob_upload_time,
                original_filename=original_filename,
                file_size_bytes=file_size_bytes,
                audio_duration=audio_duration,
                confidence=speech_result.confidence if speech_result else None
            )

        # 7. Pipeline complete success
        duration = time.time() - start_time
        logger.info(f"Pipeline completed successfully in {duration:.2f}s.")
        return PipelineResult(
            success=True,
            meeting_id=meeting_id,
            audio_blob=audio_upload_res,
            transcript_blob=transcript_upload_res,
            summary_blob=summary_upload_res,
            transcript=transcript_text,
            summary=summary_text,
            key_phrases=key_phrases,
            processing_time=duration,
            status="success",
            upload_time=upload_time,
            transcribe_time=transcribe_time,
            language_time=language_time,
            blob_upload_time=blob_upload_time,
            original_filename=original_filename,
            file_size_bytes=file_size_bytes,
            audio_duration=audio_duration,
            confidence=speech_result.confidence if speech_result else None
        )

    def process_meeting(self, local_audio_path: str) -> PipelineResult:
        """
        Executes the complete transcription, analysis, and archiving pipeline.
        This method delegates to run_pipeline to maintain full backward compatibility.
        """
        return self.run_pipeline(local_audio_path)
