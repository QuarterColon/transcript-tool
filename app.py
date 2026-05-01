from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Iterable

import streamlit as st
from faster_whisper import WhisperModel
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


APP_TITLE = "Local Transcript Tool"
OUTPUT_DIR = Path("outputs")
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
MODEL_OPTIONS = ("tiny", "base", "small", "medium", "large-v3")
COMPUTE_OPTIONS = ("int8", "float16", "float32")


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


def page_setup() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon=":material/graphic_eq:", layout="wide")
    st.title(APP_TITLE)
    st.caption("Transcribe audio/video locally and create PDF reports with transcript-based screenshots.")


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def safe_filename(filename: str) -> str:
    cleaned = Path(filename).name.replace("\x00", "")
    return cleaned or "uploaded_media"


def media_kind(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return None


def run_ffmpeg(args: list[str], action: str) -> None:
    command = ["ffmpeg", "-hide_banner", "-y", *args]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "ffmpeg failed without details."
        raise RuntimeError(f"{action} failed: {details}")


def extract_audio(video_path: Path, audio_path: Path) -> None:
    run_ffmpeg(
        [
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(audio_path),
        ],
        "Audio extraction",
    )


def select_screenshot_timestamps(
    segments: list[TranscriptSegment],
    minimum_gap_seconds: float = 15.0,
) -> list[float]:
    timestamps: list[float] = []
    last_timestamp: float | None = None
    for segment in segments:
        midpoint = max((segment.start + segment.end) / 2, 0)
        if last_timestamp is None or midpoint - last_timestamp >= minimum_gap_seconds:
            timestamps.append(midpoint)
            last_timestamp = midpoint
    return timestamps


def capture_screenshots_at_timestamps(
    video_path: Path,
    screenshot_dir: Path,
    timestamps: list[float],
) -> list[tuple[float, Path]]:
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    captures: list[tuple[float, Path]] = []
    for index, timestamp in enumerate(timestamps, start=1):
        screenshot_path = screenshot_dir / f"screenshot_{index:04d}.jpg"
        run_ffmpeg(
            [
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(screenshot_path),
            ],
            "Screenshot capture",
        )
        captures.append((timestamp, screenshot_path))
    return captures


@st.cache_resource(show_spinner=False)
def load_model(model_name: str, compute_type: str, local_files_only: bool) -> WhisperModel:
    return WhisperModel(
        model_name,
        device="cpu",
        compute_type=compute_type,
        local_files_only=local_files_only,
    )


def format_timestamp(seconds: float) -> str:
    total_milliseconds = int(seconds * 1000)
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def build_transcript_text(segments: Iterable[TranscriptSegment]) -> str:
    lines = []
    for segment in segments:
        lines.append(
            f"[{format_timestamp(segment.start)} - {format_timestamp(segment.end)}] "
            f"{segment.text.strip()}"
        )
    return "\n".join(lines).strip()


def transcribe_audio(
    audio_path: Path,
    model_name: str,
    compute_type: str,
    local_files_only: bool,
    language: str | None,
) -> tuple[str, list[TranscriptSegment]]:
    model = load_model(model_name, compute_type, local_files_only)
    segments_iter, _info = model.transcribe(
        str(audio_path),
        language=language or None,
        beam_size=5,
        vad_filter=True,
    )
    segments = [
        TranscriptSegment(start=segment.start, end=segment.end, text=segment.text)
        for segment in segments_iter
    ]
    return build_transcript_text(segments), segments


def save_uploaded_file(uploaded_file, destination: Path) -> None:
    with destination.open("wb") as file:
        file.write(uploaded_file.getbuffer())


def write_outputs(job_dir: Path, transcript_text: str, segments: list[TranscriptSegment]) -> tuple[Path, Path]:
    transcript_path = job_dir / "transcript.txt"
    segments_path = job_dir / "segments.json"
    transcript_path.write_text(transcript_text, encoding="utf-8")
    segments_path.write_text(
        json.dumps([asdict(segment) for segment in segments], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return transcript_path, segments_path


def add_screenshot_to_pdf(story: list, screenshot_path: Path, timestamp: float, styles) -> None:
    story.append(Spacer(1, 0.12 * inch))
    story.append(Paragraph(f"Screenshot at {format_timestamp(timestamp)}", styles["Heading3"]))

    image = PdfImage(str(screenshot_path))
    max_width = 6.8 * inch
    max_height = 3.8 * inch
    scale = min(max_width / image.imageWidth, max_height / image.imageHeight, 1)
    image.drawWidth = image.imageWidth * scale
    image.drawHeight = image.imageHeight * scale
    story.append(image)
    story.append(Spacer(1, 0.16 * inch))


def write_pdf_report(
    job_dir: Path,
    source_name: str,
    transcript_text: str,
    segments: list[TranscriptSegment],
    screenshot_items: list[tuple[float, Path]],
    model_name: str,
    compute_type: str,
) -> Path:
    pdf_path = job_dir / "transcript_report.pdf"
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=0.45 * inch,
        leftMargin=0.45 * inch,
        topMargin=0.45 * inch,
        bottomMargin=0.45 * inch,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Transcript Report", styles["Title"]),
        Spacer(1, 0.12 * inch),
        Paragraph(f"<b>Source:</b> {escape(source_name)}", styles["BodyText"]),
        Paragraph(f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles["BodyText"]),
        Paragraph(f"<b>Model:</b> {escape(model_name)} / {escape(compute_type)}", styles["BodyText"]),
        Spacer(1, 0.2 * inch),
    ]

    screenshot_items = sorted(screenshot_items, key=lambda item: item[0])
    next_screenshot = 0

    def add_due_screenshots(up_to_seconds: float) -> None:
        nonlocal next_screenshot
        while next_screenshot < len(screenshot_items) and screenshot_items[next_screenshot][0] <= up_to_seconds:
            timestamp, screenshot_path = screenshot_items[next_screenshot]
            add_screenshot_to_pdf(story, screenshot_path, timestamp, styles)
            next_screenshot += 1

    if segments:
        story.append(Paragraph("Transcript", styles["Heading2"]))
        for segment in segments:
            add_due_screenshots(segment.start)
            timestamp = f"{format_timestamp(segment.start)} - {format_timestamp(segment.end)}"
            text = escape(segment.text.strip())
            story.append(Paragraph(f"<b>{timestamp}</b><br/>{text}", styles["BodyText"]))
            story.append(Spacer(1, 0.08 * inch))
            add_due_screenshots(segment.end)
        add_due_screenshots(float("inf"))
    else:
        story.append(Paragraph("Transcript", styles["Heading2"]))
        story.append(Paragraph(escape(transcript_text or "No transcript text was generated."), styles["BodyText"]))

    doc.build(story)
    return pdf_path


def render_settings() -> tuple[str, str, bool, str | None]:
    with st.sidebar:
        st.header("Transcription")
        model_name = st.selectbox("Model", MODEL_OPTIONS, index=MODEL_OPTIONS.index("small"))
        compute_type = st.selectbox("Compute type", COMPUTE_OPTIONS, index=COMPUTE_OPTIONS.index("int8"))
        local_files_only = st.checkbox("Use local model files only", value=True)
        language_input = st.text_input("Language code", value="", placeholder="Optional, e.g. en or hi")
        st.divider()
        st.caption("Install ffmpeg and pre-download models for fully offline use.")
    return model_name, compute_type, local_files_only, language_input.strip() or None


def render_download(label: str, path: Path, mime: str) -> None:
    st.download_button(
        label,
        data=path.read_bytes(),
        file_name=path.name,
        mime=mime,
        use_container_width=True,
    )


def process_upload(
    uploaded_file,
    model_name: str,
    compute_type: str,
    local_files_only: bool,
    language: str | None,
) -> None:
    ensure_output_dir()
    job_id = uuid.uuid4().hex[:12]
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=False)

    source_path = job_dir / safe_filename(uploaded_file.name)
    save_uploaded_file(uploaded_file, source_path)
    kind = media_kind(source_path)
    if kind is None:
        st.error(f"Unsupported file type: {source_path.suffix or 'unknown'}")
        return

    audio_path = source_path
    screenshot_items: list[tuple[float, Path]] = []

    progress = st.progress(0, text="Preparing media")
    try:
        if kind == "video":
            audio_path = job_dir / "audio.wav"
            progress.progress(10, text="Extracting audio from video")
            extract_audio(source_path, audio_path)

        progress.progress(45, text="Loading local transcription model")
        progress.progress(60, text="Transcribing media")
        transcript_text, segments = transcribe_audio(
            audio_path=audio_path,
            model_name=model_name,
            compute_type=compute_type,
            local_files_only=local_files_only,
            language=language,
        )

        if kind == "video" and segments:
            progress.progress(80, text="Capturing transcript-based screenshots")
            screenshot_timestamps = select_screenshot_timestamps(segments)
            screenshot_items = capture_screenshots_at_timestamps(
                source_path,
                job_dir / "pdf_screenshots",
                screenshot_timestamps,
            )

        progress.progress(90, text="Saving outputs")
        transcript_path, segments_path = write_outputs(job_dir, transcript_text, segments)
        pdf_path = write_pdf_report(
            job_dir=job_dir,
            source_name=source_path.name,
            transcript_text=transcript_text,
            segments=segments,
            screenshot_items=screenshot_items,
            model_name=model_name,
            compute_type=compute_type,
        )
        shutil.rmtree(job_dir / "pdf_screenshots", ignore_errors=True)
        progress.progress(100, text="Done")
    except Exception as exc:
        progress.empty()
        st.error(str(exc))
        if "model" in str(exc).lower() or "huggingface" in str(exc).lower():
            st.info(
                "The selected model was not found locally. Uncheck 'Use local model files only' "
                "once while online, or pre-download the model into the faster-whisper cache."
            )
        return

    st.success(f"Finished. Outputs saved in `{job_dir}`.")
    st.subheader("Transcript")
    st.text_area("Transcript text", transcript_text, height=320)

    col1, col2, col3 = st.columns(3)
    with col1:
        render_download("Download transcript", transcript_path, "text/plain")
    with col2:
        render_download("Download segments JSON", segments_path, "application/json")
    with col3:
        render_download("Download PDF report", pdf_path, "application/pdf")


def main() -> None:
    page_setup()
    model_name, compute_type, local_files_only, language = render_settings()

    if not ffmpeg_available():
        st.warning(
            "ffmpeg is not available on PATH. Install ffmpeg before processing media. "
            "On Windows, install it and reopen the terminal so `ffmpeg` works from PowerShell."
        )

    uploaded_file = st.file_uploader(
        "Upload an audio or video file",
        type=sorted(extension.lstrip(".") for extension in SUPPORTED_EXTENSIONS),
    )

    process_clicked = st.button(
        "Generate transcript",
        type="primary",
        disabled=uploaded_file is None or not ffmpeg_available(),
        use_container_width=True,
    )

    if uploaded_file is not None:
        st.caption(f"Selected: `{uploaded_file.name}`")

    if process_clicked and uploaded_file is not None:
        process_upload(
            uploaded_file=uploaded_file,
            model_name=model_name,
            compute_type=compute_type,
            local_files_only=local_files_only,
            language=language,
        )


if __name__ == "__main__":
    main()
