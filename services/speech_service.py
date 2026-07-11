import time
import threading
import os
import tempfile
import wave
import av
from typing import Optional, List
import azure.cognitiveservices.speech as speechsdk
from config.settings import settings
from utils.logger import logger
from utils.error_handler import AzureSpeechError, EmptyTranscriptError

class SpeechResult:
    """
    Reusable response model representing the standardized output
    of the Speech-to-Text transcription process.
    """
    def __init__(
        self,
        success: bool,
        status: str,
        transcript: str,
        processing_time: float,
        error_message: Optional[str] = None,
        confidence: Optional[float] = None
    ):
        self.success: bool = success
        self.status: str = status
        self.transcript: str = transcript
        self.processing_time: float = processing_time
        self.error_message: Optional[str] = error_message
        self.confidence: Optional[float] = confidence

    def __repr__(self) -> str:
        return (
            f"SpeechResult(success={self.success}, status='{self.status}', "
            f"transcript_len={len(self.transcript)}, time={self.processing_time:.2f}s)"
        )


class SpeechService:
    """
    Service wrapper for the Microsoft Azure AI Speech SDK.
    Handles continuous audio recognition, network connection checks, and clean resource destruction.
    """
    
    def __init__(self):
        self.speech_config: Optional[speechsdk.SpeechConfig] = None
        self._is_initialized: bool = False

    def initialize(self) -> None:
        """
        Initializes the Azure Speech Configuration using environment settings.
        Validates settings syntax and initializes the SDK configurations.
        """
        logger.debug("Initializing Azure Speech Configuration...")
        try:
            # Print diagnostic logs before creating SpeechConfig
            speech_key_len = len(settings.AZURE_SPEECH_KEY) if settings.AZURE_SPEECH_KEY else 0
            speech_region = settings.AZURE_SPEECH_REGION.strip() if settings.AZURE_SPEECH_REGION else ""
            logger.info(f"DIAGNOSTIC: Speech key length: {speech_key_len}")
            logger.info(f"DIAGNOSTIC: Speech region: '{speech_region}'")
            logger.info("DIAGNOSTIC: Whether endpoint is being used: False")
            logger.info(f"DIAGNOSTIC: SDK version: {speechsdk.__version__}")

            # Construct SpeechConfig using subscription key and regional location
            self.speech_config = speechsdk.SpeechConfig(
                subscription=settings.AZURE_SPEECH_KEY,
                region=speech_region
            )
            
            # Configure Speech SDK settings for detailed candidate analysis
            self.speech_config.output_format = speechsdk.OutputFormat.Detailed
            
            self._is_initialized = True
            logger.info("Speech SDK configurations initialized successfully.")
        except Exception as e:
            self._is_initialized = False
            logger.error(f"Failed to initialize SpeechConfig: {str(e)}")
            raise AzureSpeechError("SDK Initialization Failed", str(e))

    def validate_connection(self) -> bool:
        """
        Validates authentication and network connectivity with the Azure Speech endpoint
        prior to starting long transcriptions.
        
        Returns:
            bool: True if connection is active and credentials are authenticated.
        """
        if not self._is_initialized:
            self.initialize()
            
        logger.debug("Validating network connection to Azure Speech Service endpoint...")
        try:
            # We perform a tiny, mock-like recognition request to trigger a real API handshake.
            # Using a silent/empty push stream forces the SDK to establish socket contact.
            push_stream = speechsdk.audio.PushAudioInputStream()
            audio_config = speechsdk.audio.AudioConfig(stream=push_stream)
            
            # Temporary short recognizer
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=self.speech_config, 
                audio_config=audio_config
            )
            
            # Write a short chunk of silence (100ms of PCM data) to prevent server timeouts on new resources
            push_stream.write(b'\x00' * 3200)
            push_stream.close()
            
            # Synchronous check - returns immediately because stream is closed
            result = recognizer.recognize_once()
            
            # If the service rejected our credentials, it will trigger a Cancellation error
            if result.reason == speechsdk.ResultReason.Canceled:
                cancellation_details = speechsdk.CancellationDetails(result)
                if cancellation_details.reason == speechsdk.CancellationReason.Error:
                    err_text = str(cancellation_details.error_details)
                    if "auth" in err_text.lower() or "denied" in err_text.lower() or "401" in err_text:
                        logger.error("Azure Speech Connection validation failed: Authentication Error.")
                    else:
                        logger.error(f"Azure Speech Connection validation failed: {err_text}")
                    return False
            
            logger.info("Azure Speech Connection handshake validated successfully.")
            return True
        except Exception as e:
            logger.error(f"Exception during connection validation: {str(e)}")
            return False

    def _convert_to_wav(self, input_path: str, output_path: str) -> None:
        """Helper method to convert compressed audio formats to 16kHz, mono, 16-bit WAV using PyAV."""
        logger.info(f"Converting compressed audio {input_path} to WAV format: {output_path}...")
        container = av.open(input_path)
        stream = container.streams.audio[0]
        
        resampler = av.AudioResampler(
            format='s16',
            layout='mono',
            rate=16000
        )
        
        with wave.open(output_path, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2) # 16-bit = 2 bytes
            wav_file.setframerate(16000)
            
            for frame in container.decode(stream):
                resampled_frames = resampler.resample(frame)
                if resampled_frames:
                    for resampled_frame in resampled_frames:
                        data = resampled_frame.to_ndarray().tobytes()
                        wav_file.writeframes(data)
                        
            # Flush the resampler
            flushed_frames = resampler.resample(None)
            if flushed_frames:
                for resampled_frame in flushed_frames:
                    data = resampled_frame.to_ndarray().tobytes()
                    wav_file.writeframes(data)
                    
        container.close()
        logger.info("Audio conversion completed successfully.")

    def transcribe(self, audio_path: str) -> SpeechResult:
        """
        Transcribes a local audio file to text using continuous recognition.
        Handles files of arbitrary duration (short and long recordings).
        
        Args:
            audio_path (str): Path to the validated audio recording.
            
        Returns:
            SpeechResult: Structured result mapping transcription metrics and text.
            
        Raises:
            AzureSpeechError: If SDK raises errors or is canceled.
        """
        if not self._is_initialized:
            self.initialize()

        original_path = audio_path
        temp_wav_path: Optional[str] = None
        
        try:
            # Check if the file format requires conversion (non-wav to wav)
            _, ext = os.path.splitext(audio_path.lower())
            if ext != ".wav":
                try:
                    # Create a temporary file to store the converted wav audio
                    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                    temp_wav_path = temp_file.name
                    temp_file.close() # Close handle so PyAV can write to it
                    
                    # Perform the conversion
                    self._convert_to_wav(original_path, temp_wav_path)
                    audio_path = temp_wav_path
                except Exception as e:
                    logger.error(f"Failed to convert audio file {original_path} to WAV: {str(e)}")
                    raise AzureSpeechError("Failed to convert audio format for transcription.", str(e))

            logger.info(f"Starting continuous speech recognition for: {audio_path}")
            start_time = time.time()
            
            # Initialize thread-safe synchronization primitives and diagnostic counters
            done_event = threading.Event()
            transcript_segments: List[str] = []
            confidence_scores: List[float] = []
            error_details: List[str] = []
            recognition_events_count = 0

            try:
                # Setup file audio input configuration
                audio_config = speechsdk.audio.AudioConfig(filename=audio_path)
                recognizer = speechsdk.SpeechRecognizer(
                    speech_config=self.speech_config, 
                    audio_config=audio_config
                )
            except Exception as e:
                logger.error(f"Failed to create SpeechRecognizer: {str(e)}")
                raise AzureSpeechError("Failed to initialize recognizer interfaces.", str(e))

            # --- SDK Event Callbacks ---
            
            def handle_recognized(evt: speechsdk.SpeechRecognitionEventArgs):
                """Fires when a complete sentence has been recognized."""
                nonlocal recognition_events_count
                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    text = evt.result.text.strip()
                    if text:
                        recognition_events_count += 1
                        logger.debug(f"Recognized Segment: {text}")
                        transcript_segments.append(text)
                        
                        # Extract confidence scores from detailed json result if available
                        try:
                            detailed_json = evt.result.properties.get(
                                speechsdk.PropertyId.SpeechServiceResponse_JsonResult
                            )
                            import json
                            parsed = json.loads(detailed_json)
                            # Extract the confidence of the best NBest candidate
                            if "NBest" in parsed and len(parsed["NBest"]) > 0:
                                confidence_scores.append(parsed["NBest"][0]["Confidence"])
                        except Exception:
                            pass

            def handle_canceled(evt: speechsdk.SpeechRecognitionCanceledEventArgs):
                """Fires when service encounters error, key rotation, or stops."""
                logger.warning(f"Speech recognition canceled. Reason: {evt.reason}")
                if evt.reason == speechsdk.CancellationReason.Error:
                    err_msg = f"Error Code: {evt.error_code}. Details: {evt.error_details}"
                    logger.error(f"Speech Recognition Cancellation Details: {err_msg}")
                    error_details.append(err_msg)
                    done_event.set() # Only stop immediately on actual errors

            def handle_session_stopped(evt: speechsdk.SessionEventArgs):
                """Fires when audio file finishes streaming."""
                logger.info("Speech continuous recognition session stopped.")
                done_event.set()

            # Connect SDK Event listeners
            recognizer.recognized.connect(handle_recognized)
            recognizer.canceled.connect(handle_canceled)
            recognizer.session_stopped.connect(handle_session_stopped)

            # Trigger Continuous Recognition
            try:
                recognizer.start_continuous_recognition()
                # Wait for file to complete streaming (triggered by session_stopped or canceled events)
                done_event.wait()
                recognizer.stop_continuous_recognition()
            except Exception as e:
                logger.error(f"Error during active recognition process: {str(e)}")
                raise AzureSpeechError("Active transcription error.", str(e))
            finally:
                self.cleanup(recognizer)
                if 'audio_config' in locals():
                    del audio_config

            # Process Results
            processing_duration = time.time() - start_time
            
            if error_details:
                return SpeechResult(
                    success=False,
                    status="failed",
                    transcript="",
                    processing_time=processing_duration,
                    error_message=f"Azure Speech Error: {'; '.join(error_details)}"
                )

            full_transcript = " ".join(transcript_segments).strip()
            
            if not full_transcript:
                logger.warning("Transcription completed, but no words were parsed.")
                raise EmptyTranscriptError()

            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.85
            word_count = len(full_transcript.split())

            # Print diagnostic logs as required
            logger.info(f"DIAGNOSTIC: Total recognition events: {recognition_events_count}")
            logger.info(f"DIAGNOSTIC: Final transcript length: {len(full_transcript)} characters")
            logger.info(f"DIAGNOSTIC: Transcript word count: {word_count} words")

            logger.info(f"Completed speech recognition in {processing_duration:.2f}s.")
            return SpeechResult(
                success=True,
                status="success",
                transcript=full_transcript,
                processing_time=processing_duration,
                confidence=round(avg_confidence, 4)
            )
        finally:
            # Clean up the temporary WAV file if it was created
            if temp_wav_path and os.path.exists(temp_wav_path):
                try:
                    os.remove(temp_wav_path)
                    logger.debug(f"Temporary transcription file removed: {temp_wav_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete temporary file {temp_wav_path}: {str(e)}")

    def cleanup(self, recognizer: Optional[speechsdk.SpeechRecognizer] = None) -> None:
        """
        Performs explicit garbage collection and clean resource disposal of SpeechRecognizer.
        """
        logger.debug("Disposing of SpeechRecognizer resources...")
        if recognizer:
            try:
                # Disconnect event handlers to prevent memory leaks
                recognizer.recognized.disconnect_all()
                recognizer.canceled.disconnect_all()
                recognizer.session_stopped.disconnect_all()
                # Explicitly delete the C-level object wrapper
                del recognizer
                logger.debug("SDK recognizer instance successfully disposed.")
            except Exception as e:
                logger.warning(f"Error occurred during recognizer cleanup: {str(e)}")
