# Local Transcript Tool

A simple local Python browser app for transcribing audio/video files and capturing video screenshots at a chosen interval.

The app uses:

- Streamlit for the local browser UI
- faster-whisper for local transcription
- ffmpeg for audio extraction and screenshots

No cloud transcription or remote LLM service is used by the app. For fully offline operation, install dependencies and cache the selected Whisper model before disconnecting from the internet.

## Setup

Use Python 3.10 or newer. The current dependencies install on Python 3.13, but if a future binary wheel is unavailable, use Python 3.10-3.12.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install `ffmpeg` and make sure it is available on `PATH`:

```powershell
ffmpeg -version
```

On Windows, you can install ffmpeg with a package manager such as Winget:

```powershell
winget install Gyan.FFmpeg
```

Open a new terminal after installing ffmpeg so PATH changes are picked up.

## Run

```powershell
streamlit run app.py
```

Then open the local URL shown by Streamlit, usually:

```text
http://localhost:8501
```

## Offline Model Use

The sidebar option **Use local model files only** is enabled by default. With that enabled, transcription works only if the selected model already exists in the local model cache.

To cache a model once while online, run the app, uncheck **Use local model files only**, select the model, and process a small file. After the model is downloaded, turn the checkbox back on for offline use.

Default settings:

- Model: `small`
- Compute type: `int8`
- Device: CPU

You can select `tiny`, `base`, `small`, `medium`, or `large-v3` in the sidebar. Larger models need more RAM and disk space.

## Outputs

Each run is saved under:

```text
outputs/<job_id>/
```

The folder contains:

- the uploaded source file
- `audio.wav` for video inputs
- `transcript.txt`
- `segments.json`
- `screenshots/` for video inputs
- `screenshots.zip` when screenshots are captured

## Supported Files

The uploader accepts common formats handled by ffmpeg, including:

- Audio: `.mp3`, `.wav`, `.m4a`, `.aac`, `.flac`, `.ogg`, `.wma`
- Video: `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`, `.m4v`

## Notes

- If ffmpeg is missing, the app disables processing and shows setup guidance.
- If the selected model is missing while local-only mode is enabled, the app shows a clear error and keeps all processing local.
- If a binary dependency fails to install for your Python version, retry with Python 3.10-3.12.
