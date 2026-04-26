# Audio/Video Transcript Tool Proposal

## Overview

This proposal is for a browser-based tool that can generate transcripts from uploaded audio or video files. For video files, the tool can also capture screenshots at a selected time interval, such as every 30 or 60 seconds.

The tool is intended to run inside the organization's OpenStack environment on a Windows machine. This keeps processing within approved infrastructure and avoids sending media files to external transcription services.

## What The Tool Does

- Allows a user to upload an audio or video file through a simple browser interface.
- Generates a transcript from the uploaded file.
- Summarizes the transcript using an approved local LLM.
- Generates a structured report from the transcript, such as meeting notes, action items, or a review summary.
- Extracts screenshots from video files based on a user-selected interval.
- Saves transcript files, screenshot files, and structured transcript data.
- Runs transcription using locally available Whisper model files.
- Runs summarization and report generation using locally hosted LLM files or an approved internal LLM service.
- Keeps media processing within the OpenStack-hosted Windows environment.

## Why This Is Useful

Many teams need transcripts from meetings, interviews, demos, training videos, support calls, or operational recordings. Using external services may not be acceptable when the content is confidential or internal.

This tool provides a controlled alternative:

- Media files stay within internal infrastructure.
- Users get transcripts, summaries, reports, and screenshots from one interface.
- Processing can work without internet access after setup.
- The solution can start small and later be expanded for team use.

## Proposed Deployment

The tool should be deployed on a Windows machine hosted in OpenStack.

Recommended setup:

- Windows Server or Windows desktop image on OpenStack.
- Python installed on the Windows machine.
- ffmpeg installed for video and audio processing.
- The transcript tool installed from the GitHub repository.
- Whisper model files downloaded and placed on the machine during setup.
- Local LLM model files downloaded and placed on the machine during setup, or access configured to an approved internal LLM endpoint.
- A persistent storage location for uploaded files and generated outputs.
- Access limited to approved users through the internal network, VPN, or remote desktop.

The app can be run as a Streamlit browser application. Users open the tool in a browser and interact with it through a simple upload form.

## Suggested Resources

For a proof of concept:

- 4 vCPU
- 16 GB RAM
- 100 GB storage
- CPU processing
- Whisper `small` model
- Lightweight local LLM for summary/report testing

For longer videos and better accuracy:

- 8 to 16 vCPU
- 32 to 64 GB RAM
- 250 GB or more storage
- CPU processing
- Whisper `medium` model
- Medium-sized local LLM, depending on available memory

For highest accuracy:

- 16+ vCPU
- 64 GB+ RAM
- 500 GB or more storage
- Whisper `large-v3` model
- Larger local LLM if report quality is a priority
- Expect slower processing if no supported GPU is available

## Basic Technical Components

- Python: application runtime.
- Streamlit: browser-based user interface.
- faster-whisper: transcription engine.
- ffmpeg: audio extraction and screenshot capture.
- Local model files: used for offline/private transcription.
- Local LLM: used for transcript summarization and report generation.
- OpenStack Windows machine: hosting environment.

## Output Files

Each processed file can generate:

- Transcript text file.
- Transcript segment JSON file.
- Transcript summary.
- Generated report.
- Extracted screenshots for videos.
- Screenshot ZIP file for download.

## Security Considerations

- Do not expose the tool publicly.
- Limit access to approved internal users.
- Store uploads and outputs on approved storage.
- Use a cleanup policy for old uploads and transcripts.
- Preload transcription and LLM model files so internet access is not required during normal use.
- Avoid sending audio, video, transcript, summary, or report content to external services.

## Future Enhancements

- Add a field to select a specific model folder.
- Add job history and processing status.
- Add automatic cleanup of old files.
- Add user authentication if accessed by multiple teams.
- Add background processing for multiple large files.
- Add configurable report templates for different use cases.
- Add approval workflow for generated reports if needed.

## Success Criteria

The proposal is successful if:

- The tool runs on a Windows machine in OpenStack.
- Users can upload supported audio and video files.
- Transcripts are generated without using external transcription APIs.
- Summaries and reports are generated without using external LLM APIs.
- Screenshots are generated for video files at the selected interval.
- Outputs can be downloaded from the browser.
- Processing remains within approved infrastructure.
