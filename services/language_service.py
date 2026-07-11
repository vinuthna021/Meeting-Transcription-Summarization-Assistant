import time
from dataclasses import dataclass, field
from typing import List, Optional
from azure.core.credentials import AzureKeyCredential
from azure.ai.textanalytics import (
    TextAnalyticsClient,
    ExtractiveSummaryAction,
    AbstractiveSummaryAction
)
from config.settings import settings
from utils.logger import logger
from utils.error_handler import AzureLanguageError, LanguageValidationError

@dataclass
class LanguageResult:
    """
    Structured dataclass representing the standardized output
    of the Azure AI Language analysis process.
    """
    success: bool
    summary: str
    key_phrases: List[str]
    processing_time: float
    error_message: Optional[str] = None
    language: str = "en"
    status: str = "success"

class LanguageService:
    """
    Service wrapper for the Microsoft Azure AI Language SDK (TextAnalyticsClient).
    Performs input text validation, document summarization, and key phrase extraction.
    """

    def __init__(self):
        self.client: Optional[TextAnalyticsClient] = None
        self._is_initialized: bool = False

    def initialize(self) -> None:
        """
        Initializes the TextAnalyticsClient using configured endpoint and key.
        Fails fast if credentials or endpoints are malformed.
        """
        logger.debug("Initializing Azure AI Language client...")
        try:
            credential = AzureKeyCredential(settings.AZURE_LANGUAGE_KEY)
            self.client = TextAnalyticsClient(
                endpoint=settings.AZURE_LANGUAGE_ENDPOINT,
                credential=credential
            )
            self._is_initialized = True
            logger.info("Azure AI Language client initialized successfully.")
        except Exception as e:
            self._is_initialized = False
            logger.error(f"Failed to initialize Language client: {str(e)}")
            raise AzureLanguageError("SDK Initialization Failed", str(e))

    def validate_connection(self) -> bool:
        """
        Validates connection and credentials syntax by issuing a lightweight API check.

        Returns:
            bool: True if connection is authenticated and active.
        """
        if not self._is_initialized:
            self.initialize()

        logger.debug("Validating connection to Azure AI Language Service...")
        try:
            # Fire a fast key phrase check on a single word to verify auth
            response = self.client.extract_key_phrases(documents=["test"])
            if response and not response[0].is_error:
                logger.info("Azure AI Language Service connection verified successfully.")
                return True
            if response and response[0].is_error:
                logger.error(f"Language Service connection error: {response[0].error.message}")
                return False
            return False
        except Exception as e:
            logger.error(f"Exception encountered during Language connection verification: {str(e)}")
            return False

    def validate_transcript(self, text: Optional[str]) -> None:
        """
        Performs validation checks on incoming transcript text.

        Args:
            text (str): The transcript to validate.

        Raises:
            LanguageValidationError: If validations fail.
        """
        logger.debug("Validating input transcript content...")
        if text is None:
            raise LanguageValidationError("Transcript cannot be None.")
        
        cleaned_text = text.strip()
        if not cleaned_text:
            raise LanguageValidationError("Transcript cannot be empty or contain only whitespace.")

        # Azure AI Language limits documents by character count. Enforce a local 100,000 char threshold.
        max_chars = 100000
        if len(cleaned_text) > max_chars:
            raise LanguageValidationError(
                f"Transcript size ({len(cleaned_text)} chars) exceeds maximum supported length ({max_chars} chars)."
            )

    def _split_into_sentences(self, text: str) -> List[str]:
        """Helper to split unstructured text into clean sentences."""
        if not text:
            return []
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

    def build_meeting_overview(self, transcript: str, azure_summary: str) -> str:
        """Builds a concise meeting overview paragraph, combining Azure outputs with transcript context."""
        logger.debug("Building meeting overview...")
        sentences = self._split_into_sentences(azure_summary)
        if not sentences or len(azure_summary) < 15:
            transcript_sentences = self._split_into_sentences(transcript)
            sentences = transcript_sentences[:2]
        
        overview = " ".join(sentences).strip()
        if overview and not overview.endswith(('.', '?', '!')):
            overview += "."
        return overview if overview else "A team discussion was held to review ongoing tasks and sync on current milestones."

    def extract_topics(self, transcript: str, key_phrases: List[str]) -> List[str]:
        """Extracts the main discussion topics using key phrases and topic-introduction sentence patterns."""
        logger.debug("Extracting topics from transcript...")
        topics = []
        sentences = self._split_into_sentences(transcript)
        
        topic_keywords = ["discuss", "focus on", "agenda", "about", "today we are", "talking about", "project", "reviewing", "updates on", "milestone"]
        for s in sentences:
            s_lower = s.lower()
            if any(kw in s_lower for kw in topic_keywords):
                clean_s = s.strip()
                if 10 < len(clean_s) < 100:
                    clean_s = clean_s.rstrip(".!?")
                    topics.append(clean_s)
                    
        # Supplement using high-quality Azure Key Phrases if topics list is short
        if len(topics) < 3:
            for kp in key_phrases[:4]:
                topic_title = f"Discussion regarding {kp}"
                if topic_title not in topics:
                    topics.append(topic_title)
                    
        seen = set()
        deduped_topics = []
        for t in topics:
            if t.lower() not in seen:
                seen.add(t.lower())
                deduped_topics.append(t)
                
        return deduped_topics[:4]

    def extract_decisions(self, transcript: str) -> List[str]:
        """Heuristically extracts key decisions made during the meeting from the transcript."""
        logger.debug("Extracting decisions from transcript...")
        decisions = []
        sentences = self._split_into_sentences(transcript)
        decision_keywords = ["decided to", "we agreed", "agreed on", "consensus", "we will go with", "resolution", "confirmed that", "concluded"]
        
        for s in sentences:
            s_lower = s.lower()
            if any(kw in s_lower for kw in decision_keywords):
                clean_s = s.strip()
                if len(clean_s) > 10:
                    clean_s = clean_s.rstrip(".!?")
                    decisions.append(clean_s)
                    
        seen = set()
        deduped_decisions = []
        for d in decisions:
            if d.lower() not in seen:
                seen.add(d.lower())
                deduped_decisions.append(d)
                
        return deduped_decisions[:3]

    def extract_action_items(self, transcript: str) -> List[str]:
        """Heuristically extracts action items and tasks from the transcript."""
        logger.debug("Extracting action items from transcript...")
        actions = []
        sentences = self._split_into_sentences(transcript)
        action_keywords = ["action item", "todo", "to-do", "task", "we need to", "make sure to", "assigned to", "responsible for", "will handle", "will look into", "action point", "please do", "you should", "i will do", "i'll do"]
        
        for s in sentences:
            s_lower = s.lower()
            if any(kw in s_lower for kw in action_keywords):
                clean_s = s.strip()
                if len(clean_s) > 10:
                    clean_s = clean_s.rstrip(".!?")
                    actions.append(clean_s)
                    
        seen = set()
        deduped_actions = []
        for a in actions:
            if a.lower() not in seen:
                seen.add(a.lower())
                deduped_actions.append(a)
                
        return deduped_actions[:4]

    def generate_structured_summary(self, transcript: str, azure_summary: str, key_phrases: List[str]) -> str:
        """Orchestrates structured summary generation and formatting."""
        logger.debug("Generating structured summary block...")
        overview = self.build_meeting_overview(transcript, azure_summary)
        topics = self.extract_topics(transcript, key_phrases)
        decisions = self.extract_decisions(transcript)
        actions = self.extract_action_items(transcript)
        
        sentences = self._split_into_sentences(transcript)
        if len(sentences) >= 2:
            outcome = f"The meeting concluded with a clear understanding of the discussed items. The participants focused on coordinating next steps: {sentences[-1]}"
            if not outcome.endswith(('.', '?', '!')):
                outcome += "."
        else:
            outcome = "The meeting successfully concluded with all core agenda items addressed and next steps established."

        topics_str = "\n\n".join([f"• {t}" for t in topics]) if topics else "• Discussion of core meeting points."
        decisions_str = "\n\n".join([f"• {d}" for d in decisions]) if decisions else "No major decisions identified."
        actions_str = "\n\n".join([f"• {a}" for a in actions]) if actions else "No explicit action items identified."

        summary_lines = [
            "Meeting Summary",
            "----------------------------------------",
            "Meeting Overview",
            overview,
            "----------------------------------------",
            "Main Discussion Topics",
            topics_str,
            "----------------------------------------",
            "Important Decisions",
            decisions_str,
            "----------------------------------------",
            "Action Items",
            actions_str,
            "----------------------------------------",
            "Overall Outcome",
            outcome
        ]
        
        return "\n\n".join(summary_lines)

    def summarize_and_extract(self, transcript: str) -> LanguageResult:
        """
        Orchestrates summarization and key phrase extraction from the transcript.
        Implements a documented fallback mechanism if summarization is unavailable.

        Args:
            transcript (str): The raw meeting text transcript.

        Returns:
            LanguageResult: Aggregated summarization and extraction results.
        """
        start_time = time.time()
        
        try:
            self.validate_transcript(transcript)
        except LanguageValidationError as e:
            logger.error(f"Transcript validation failed: {str(e)}")
            return LanguageResult(
                success=False,
                summary="",
                key_phrases=[],
                processing_time=time.time() - start_time,
                error_message=str(e),
                status="failed"
            )

        if not self._is_initialized:
            self.initialize()

        # 2. Extract Key Phrases
        key_phrases: List[str] = []
        try:
            response = self.client.extract_key_phrases(documents=[transcript])
            if response and not response[0].is_error:
                seen_phrases = set()
                for kp in response[0].key_phrases:
                    kp_clean = kp.strip()
                    if kp_clean and kp_clean.lower() not in seen_phrases:
                        seen_phrases.add(kp_clean.lower())
                        key_phrases.append(kp_clean)
                logger.info(f"Extracted {len(key_phrases)} unique key phrases.")
            elif response and response[0].is_error:
                logger.warning(f"Key Phrase extraction returned API error: {response[0].error.message}")
        except Exception as e:
            logger.error(f"Failed during Key Phrase extraction: {str(e)}")
            return LanguageResult(
                success=False,
                summary="",
                key_phrases=[],
                processing_time=time.time() - start_time,
                error_message=f"Key Phrase Extraction failed: {str(e)}",
                status="failed"
            )

        # 3. Summarization with region/subscription fallback
        raw_summary = ""
        try:
            poller = self.client.begin_analyze_actions(
                documents=[transcript],
                actions=[ExtractiveSummaryAction(max_sentence_count=3)]
            )
            document_results = poller.result()
            
            sentences = []
            for doc_results in document_results:
                for action_result in doc_results:
                    if action_result.kind == "ExtractiveSummarization" and not action_result.is_error:
                        for sentence in action_result.sentences:
                            sentences.append(sentence.text.strip())
                    elif action_result.is_error:
                        logger.warning(f"Summarization action reported error: {action_result.error.message}")

            raw_summary = " ".join(sentences).strip()
            
        except Exception as e:
            logger.warning(
                f"Azure Summarization action is unsupported in this region/tier or failed: {str(e)}. "
                f"Applying local fallback summary."
            )
            raw_summary = ""

        # Construct the final structured summary block
        summary_text = self.generate_structured_summary(transcript, raw_summary, key_phrases)

        processing_duration = time.time() - start_time
        logger.info(f"Language analysis completed in {processing_duration:.2f}s.")
        
        return LanguageResult(
            success=True,
            summary=summary_text,
            key_phrases=key_phrases,
            processing_time=processing_duration,
            status="success"
        )
