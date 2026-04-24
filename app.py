from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from typing import Iterable

import streamlit as st
from faster_whisper import WhisperModel


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
    st.caption("Transcribe audio/video locally and capture video screenshots at a chosen interval.")


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


def capture_screenshots(video_path: Path, screenshot_dir: Path, interval_seconds: int) -> list[Path]:
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    pattern = screenshot_dir / "screenshot_%04d.jpg"
    run_ffmpeg(
        [
            "-i",
            str(video_path),
            "-vf",
            f"fps=1/{interval_seconds}",
            "-q:v",
            "2",
            str(pattern),
        ],
        "Screenshot capture",
    )
    return sorted(screenshot_dir.glob("*.jpg"))


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


def zip_screenshots(job_dir: Path, screenshot_paths: list[Path]) -> Path | None:
    if not screenshot_paths:
        return None
    archive_base = job_dir / "screenshots"
    archive_path = shutil.make_archive(str(archive_base), "zip", screenshot_paths[0].parent)
    return Path(archive_path)


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
    screenshot_interval: int,
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
    screenshot_paths: list[Path] = []

    progress = st.progress(0, text="Preparing media")
    try:
        if kind == "video":
            audio_path = job_dir / "audio.wav"
            progress.progress(10, text="Extracting audio from video")
            extract_audio(source_path, audio_path)

            progress.progress(25, text="Capturing screenshots")
            screenshot_paths = capture_screenshots(source_path, job_dir / "screenshots", screenshot_interval)

        progress.progress(45, text="Loading local transcription model")
        progress.progress(60, text="Transcribing media")
        transcript_text, segments = transcribe_audio(
            audio_path=audio_path,
            model_name=model_name,
            compute_type=compute_type,
            local_files_only=local_files_only,
            language=language,
        )

        progress.progress(90, text="Saving outputs")
        transcript_path, segments_path = write_outputs(job_dir, transcript_text, segments)
        screenshots_zip = zip_screenshots(job_dir, screenshot_paths)
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
        if screenshots_zip:
            render_download("Download screenshots ZIP", screenshots_zip, "application/zip")

    if screenshot_paths:
        st.subheader("Screenshots")
        st.caption(f"{len(screenshot_paths)} screenshots captured every {timedelta(seconds=screenshot_interval)}.")
        preview_columns = st.columns(4)
        for index, screenshot_path in enumerate(screenshot_paths[:12]):
            with preview_columns[index % 4]:
                st.image(str(screenshot_path), caption=screenshot_path.name, use_container_width=True)


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

    screenshot_interval = 10
    if uploaded_file is not None and Path(uploaded_file.name).suffix.lower() in VIDEO_EXTENSIONS:
        screenshot_interval = st.number_input(
            "Screenshot interval in seconds",
            min_value=1,
            max_value=3600,
            value=10,
            step=1,
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
            screenshot_interval=int(screenshot_interval),
            model_name=model_name,
            compute_type=compute_type,
            local_files_only=local_files_only,
            language=language,
        )


if __name__ == "__main__":
    main()
