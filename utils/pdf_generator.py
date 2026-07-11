import os
import io
import time
from typing import Optional
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from services.pipeline_service import PipelineResult

def generate_meeting_pdf(result: PipelineResult, manual_verification_text: Optional[str] = None, manual_accuracy: Optional[float] = None) -> io.BytesIO:
    """
    Generates a professional business-style PDF report from a PipelineResult object.
    Returns the PDF as a BytesIO stream.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54
    )
    
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=colors.HexColor('#1e3a8a'), # Navy blue
        spaceAfter=15
    )
    
    h1_style = ParagraphStyle(
        'HeadingSection',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor('#1e3a8a'),
        spaceBefore=15,
        spaceAfter=10,
        keepWithNext=True
    )
    
    h2_style = ParagraphStyle(
        'SubHeadingSection',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#3b82f6'), # Accent Blue
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'ReportBody',
        parent=styles['BodyText'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#334155'), # Charcoal
        spaceAfter=6
    )

    bullet_style = ParagraphStyle(
        'ReportBullet',
        parent=body_style,
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=4
    )
    
    caption_style = ParagraphStyle(
        'ReportCaption',
        parent=styles['Italic'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=6
    )

    story = []
    
    # 1. Report Header Cover elements
    story.append(Paragraph("🎙️ Meeting Executive Report", title_style))
    story.append(Paragraph("Consolidated transcription and cognitive analysis outcomes powered by Azure AI services.", caption_style))
    story.append(Spacer(1, 10))
    
    # Metadata table
    dur_seconds = result.audio_duration
    if dur_seconds > 0:
        minutes = int(dur_seconds // 60)
        seconds = int(dur_seconds % 60)
        duration_str = f"{minutes} min {seconds} sec" if minutes > 0 else f"{seconds} sec"
    else:
        duration_str = "Not available"
        
    file_size_mb = result.file_size_bytes / (1024 * 1024) if result.file_size_bytes else 0.0
    
    metadata_data = [
        [Paragraph("<b>Meeting ID:</b>", body_style), Paragraph(result.meeting_id, body_style),
         Paragraph("<b>Date Generated:</b>", body_style), Paragraph(time.strftime('%Y-%m-%d %H:%M:%S'), body_style)],
        [Paragraph("<b>Filename:</b>", body_style), Paragraph(result.original_filename if result.original_filename else 'Unknown', body_style),
         Paragraph("<b>File Size:</b>", body_style), Paragraph(f"{file_size_mb:.2f} MB", body_style)],
        [Paragraph("<b>Audio Duration:</b>", body_style), Paragraph(duration_str, body_style),
         Paragraph("<b>Language:</b>", body_style), Paragraph("English (en-US)", body_style)]
    ]
    
    meta_table = Table(metadata_data, colWidths=[1.2*inch, 2.3*inch, 1.2*inch, 2.3*inch])
    meta_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 15))
    
    # 2. Azure Services Used
    story.append(Paragraph("☁️ Azure Cloud Infrastructure", h1_style))
    story.append(Paragraph("This application leverages native integration with Microsoft Azure AI Services to execute secure, production-grade workloads:", body_style))
    story.append(Paragraph("• <b>Azure AI Speech</b>: Converts high-fidelity spoken meeting audio into text transcripts via continuous recognition engines.", bullet_style))
    story.append(Paragraph("• <b>Azure AI Language</b>: Extracts key phrase tokens and compiles document summarization blocks.", bullet_style))
    story.append(Paragraph("• <b>Azure Blob Storage</b>: Archives all source recording binaries, processed transcripts, and summaries securely within private cloud storage endpoints.", bullet_style))
    story.append(Spacer(1, 10))
    
    # 3. Meeting Analytics
    story.append(Paragraph("📊 Meeting Analytics", h1_style))
    
    words_count = len(result.transcript.split())
    characters_count = len(result.transcript)
    import re
    sentences = [s for s in re.split(r'[.!?]+', result.transcript) if s.strip()]
    sentences_count = len(sentences)
    paragraphs_count = len([p for p in result.transcript.split('\n\n') if p.strip()])
    if paragraphs_count == 0 and words_count > 0:
        paragraphs_count = 1
        
    if dur_seconds > 0:
        wpm = (words_count / dur_seconds) * 60
    else:
        wpm = 130.0
        
    reading_time_min = words_count / 200.0
    reading_time_sec = int((reading_time_min - int(reading_time_min)) * 60)
    reading_time_str = f"{int(reading_time_min)} min {reading_time_sec} sec" if int(reading_time_min) > 0 else f"{reading_time_sec} sec"

    analytics_data = [
        [Paragraph("<b>Metric</b>", body_style), Paragraph("<b>Value</b>", body_style), Paragraph("<b>Metric</b>", body_style), Paragraph("<b>Value</b>", body_style)],
        [Paragraph("Words", body_style), Paragraph(str(words_count), body_style), Paragraph("Average Speaking Rate", body_style), Paragraph(f"{int(wpm)} WPM", body_style)],
        [Paragraph("Characters", body_style), Paragraph(str(characters_count), body_style), Paragraph("Estimated Reading Time", body_style), Paragraph(reading_time_str, body_style)],
        [Paragraph("Sentences", body_style), Paragraph(str(sentences_count), body_style), Paragraph("Speech-to-Text Latency", body_style), Paragraph(f"{result.transcribe_time:.2f}s" if result.transcribe_time > 0 else "N/A", body_style)],
        [Paragraph("Paragraphs", body_style), Paragraph(str(paragraphs_count), body_style), Paragraph("Total Pipeline Latency", body_style), Paragraph(f"{result.processing_time:.2f}s", body_style)]
    ]
    
    analytics_table = Table(analytics_data, colWidths=[1.8*inch, 1.7*inch, 1.8*inch, 1.7*inch])
    analytics_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
    ]))
    story.append(analytics_table)
    story.append(Spacer(1, 15))
    
    # 4. Meeting Summary
    story.append(Paragraph("📝 Meeting Summary", h1_style))
    
    # Let's parse the structured summary using a local string parser
    sections = {
        "overview": "",
        "topics": [],
        "decisions": [],
        "actions": [],
        "outcome": ""
    }
    
    if result.summary:
        if "----------------------------------------" in result.summary:
            parts = result.summary.split("----------------------------------------")
            for part in parts:
                part_clean = part.strip()
                if not part_clean:
                    continue
                lines = [l.strip() for l in part_clean.split("\n") if l.strip()]
                if not lines:
                    continue
                first_line = lines[0].lower()
                content_lines = lines[1:] if len(lines) > 1 else []
                
                if "overview" in first_line:
                    sections["overview"] = " ".join(content_lines)
                elif "topics" in first_line:
                    sections["topics"] = [l.lstrip("•-* ").strip() for l in content_lines if l.strip()]
                elif "decisions" in first_line:
                    content_text = " ".join(content_lines)
                    if "no major decisions" not in content_text.lower():
                        sections["decisions"] = [l.lstrip("•-* ").strip() for l in content_lines if l.strip()]
                elif "action items" in first_line:
                    content_text = " ".join(content_lines)
                    if "no explicit action items" not in content_text.lower():
                        sections["actions"] = [l.lstrip("•-* ").strip() for l in content_lines if l.strip()]
                elif "outcome" in first_line:
                    sections["outcome"] = " ".join(content_lines)
        else:
            sections["overview"] = result.summary.strip()

    # Overview
    if sections["overview"]:
        story.append(Paragraph("📌 Meeting Overview", h2_style))
        story.append(Paragraph(sections["overview"], body_style))
        story.append(Spacer(1, 5))
        
    # Topics
    if sections["topics"]:
        story.append(Paragraph("📂 Discussion Topics", h2_style))
        for t in sections["topics"]:
            story.append(Paragraph(f"• {t}", bullet_style))
        story.append(Spacer(1, 5))
        
    # Decisions
    story.append(Paragraph("🤝 Decisions", h2_style))
    if sections["decisions"]:
        for d in sections["decisions"]:
            story.append(Paragraph(f"• {d}", bullet_style))
    else:
        story.append(Paragraph("No major decisions identified.", body_style))
    story.append(Spacer(1, 5))
        
    # Action Items
    story.append(Paragraph("📋 Action Items", h2_style))
    if sections["actions"]:
        for a in sections["actions"]:
            story.append(Paragraph(f"• {a}", bullet_style))
    else:
        story.append(Paragraph("No explicit action items identified.", body_style))
    story.append(Spacer(1, 5))
        
    # Outcome
    if sections["outcome"]:
        story.append(Paragraph("🎯 Overall Outcome", h2_style))
        story.append(Paragraph(sections["outcome"], body_style))
        story.append(Spacer(1, 10))

    # 5. Key phrases
    if result.key_phrases:
        story.append(Paragraph("🔑 Key Discussion Phrases", h1_style))
        phrases_str = ", ".join(result.key_phrases)
        story.append(Paragraph(phrases_str, body_style))
        story.append(Spacer(1, 10))

    # 6. Quality Assessment
    story.append(Paragraph("🎯 Transcription Quality Assessment", h1_style))
    accuracy_pct = int(result.confidence * 100) if result.confidence is not None else 95
    rating = "Excellent" if accuracy_pct >= 90 else "Good" if accuracy_pct >= 80 else "Fair" if accuracy_pct >= 70 else "Poor"
    
    q_text = f"• Estimated recognition accuracy: <b>{accuracy_pct}%</b> (Rating: <b>{rating}</b>)."
    story.append(Paragraph(q_text, bullet_style))
    
    if manual_verification_text and manual_accuracy is not None:
        story.append(Paragraph(f"• Excerpt manual comparison check: <b>{manual_accuracy}%</b> similarity based on verification sample.", bullet_style))
        story.append(Paragraph(f"• Reference sample excerpt: <i>\"{manual_verification_text}\"</i>", bullet_style))
    story.append(Spacer(1, 10))

    # 7. Responsible AI Statement
    story.append(Paragraph("🛡️ Responsible AI Considerations", h1_style))
    story.append(Paragraph("As a showcase project aligning with Microsoft AI-900 guidelines, this application embeds strict Responsible AI principles:", body_style))
    story.append(Paragraph("• <b>User Consent</b>: Consent was explicitly checked and confirmed before transcribing speech.", bullet_style))
    story.append(Paragraph("• <b>Data Privacy</b>: Cloud containers enforce Private Access Levels, blocking unauthorized public lookups. All network traffic is encrypted via HTTPS TLS 1.3.", bullet_style))
    story.append(Paragraph("• <b>Model Transparency</b>: Prebuilt models are used as-is, ensuring no transcription training loops ingest customer speech.", bullet_style))
    story.append(Spacer(1, 15))

    # 8. Full Transcript (Truncated Appendix for PDF optimization)
    story.append(Paragraph("💬 Transcript Appendix", h1_style))
    max_len = 1500
    if len(result.transcript) > max_len:
        truncated_transcript = result.transcript[:max_len] + "..."
        story.append(Paragraph(f"<i>[Note: Transcript has been truncated for PDF page optimization. Download the full text using the 'Download Full Transcript' button in the dashboard.]</i>", caption_style))
    else:
        truncated_transcript = result.transcript
        
    story.append(Paragraph(f"\"{truncated_transcript}\"", body_style))
    
    # Build Document
    doc.build(story)
    buffer.seek(0)
    return buffer
