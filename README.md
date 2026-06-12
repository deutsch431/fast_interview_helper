# Interview Helper Suite

A dual-tool Windows application designed to assist candidates during technical and professional interviews. The suite captures system audio, transcribes conversation context in real time, and leverages the Gemini API to stream actionable hints and speech suggestions.

## Tools in the Suite

1. **Standard Interview Helper (`main.py`)**
   - Captures **both** microphone input (Candidate) and loopback speaker audio (Interviewer) into a mixed stereo channel.
   - Transcribes the conversation via the Gemini API.
   - Generates and displays verbatim transcripts and suggested responses in a comprehensive dark-themed desktop GUI.

2. **Fast Interview Helper (`fast_helper.py`)**
   - Captures loopback speaker audio (Interviewer) in a mono channel.
   - Supports **three Speech Recognition Providers** for transcribing the interviewer's speech:
     1. **Groq Cloud Whisper (whisper-large-v3)**: Requires a Groq API Key.
     2. **Google Cloud Speech-to-Text API**: Requires a Gemini/Google API Key.
     3. **Gemini API (gemini-3.5-flash)**: Runs transcription natively through the Gemini API.
   - Streams immediate quick strategy hints (<8 words) and full suggested responses character-by-character into a translucent overlay window designed to sit beside other applications.
   - Includes real-time system microphone mute/unmute status tracking and toggling using Windows Core Audio APIs.

---

## Key Features

- **Multi-Provider Speech Recognition**: Choice between Groq Cloud Whisper, Google Cloud STT, and native Gemini audio transcription in `fast_helper.py` to match speed/accuracy preferences.
- **Streamlined UI**: Configurable behaviors, context inputs (resume, role context), and system instructions.
- **Privacy Screen Sharing Protection**: Windows display affinity (`SetWindowDisplayAffinity` with `WDA_MONITOR`) is applied to all main and overlay windows. The application UI will appear as a **completely black box** on screen captures, screenshots, and screen-sharing platforms (e.g., Zoom, Teams, Discord), ensuring candidate privacy.
- **In-Memory Audio Processing**: Captured audio is buffered entirely in memory (`bytearray`) and sent securely over HTTPS. No speech records are written to local disk.
- **Audio Tester & Live Level Meters**: Features canvas-based active level indicators for testing audio device configuration before launching active session capture.

---

## Prerequisites

- **Operating System**: Windows 10/11 (required for WASAPI loopback device and Windows Core Audio integration).
- **Python**: Python 3.8+ installed.

---

## Installation & Setup

1. **Install Dependencies**:
   Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
   *Note: `PyAudioWPatch` is used to access Windows WASAPI loopback devices for speaker capture.*

2. **Configure API Keys**:
   Create a `.env` file in the root directory and configure your API Keys:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   GROQ_API_KEY=your_groq_api_key_here
   ```
   *Note: If no local `.env` is found, the launch scripts will attempt to check for a key in a neighboring `../ielts_speaking/.env` directory as a convenience.*

---

## How to Run

Use the provided batch launchers to quickly configure environment variables and run the application:

* **Fast Helper Launcher**: Double-click [run_fast_helper.bat](file:///d:/Games/yum/run_fast_helper.bat) or [run_helper.bat](file:///d:/Games/yum/run_helper.bat) to launch the `fast_helper.py` settings panel.

Or execute manually in your command prompt:
```bash
python fast_helper.py
```

---

## Usage Guide

1. **Calibrate Audio**:
   - Select your system loopback (speaker) device.
   - Click **TEST SPEAKER** to see levels change on the canvas bar as sound plays. Click again to stop testing.
2. **Select Provider & Configure Context**:
   - Choose your Speech Recognition Provider (Groq, Google Speech-to-Text, or Gemini).
   - Provide your background context, resume snippets, and the target role details.
   - Refine the **System Instructions** to specify model behavior (e.g., tone, language, response constraints).
3. **Start Session**:
   - Click **START ASSISTANT SESSION** to open the overlay panel.
4. **Use Click-to-Record**:
   - Click **START RECORDING** when the interviewer starts talking.
   - Click **STOP RECORDING** once the interviewer finishes. The status will update, the transcription will display, and Gemini suggestions will stream into the respective fields.
   - Click **MIC: ACTIVE** to mute/unmute your system microphone directly from the overlay.
