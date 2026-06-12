import os
import sys
import threading
import wave
import ctypes
from ctypes import wintypes
import math
import array
import io
import asyncio
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from dotenv import load_dotenv
import pyaudiowpatch as pyaudio
import google.generativeai as genai
import requests
import base64

# API Constants
DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_SYSTEM_PROMPT = (
    "Adopt a highly natural, human-like conversational persona and speak in the first person. "
    "Provide exactly one direct response as if you are the candidate answering a colleague. "
    "Begin the spoken response immediately. Never include preambles, meta-commentary, or introductory remarks. "
    "Use conversational, everyday professional language. Avoid dense technical jargon unless the interviewer's "
    "question specifically requires it or the context demands it."
)
DEFAULT_INTERVIEW_CONTEXT = (
    "Role: Senior Software Engineer\n"
    "Company: Target Company\n"
    "About Me: 5+ years of software development experience, specializing in clean code and scalable architectures."
)

# Windows Core Audio COM API helper functions for Microphone Mute/Unmute
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8)
    ]
    def __init__(self, l, w1, w2, b):
        self.Data1 = l
        self.Data2 = w1
        self.Data3 = w2
        for i in range(8):
            self.Data4[i] = b[i]

CLSID_MMDeviceEnumerator = GUID(0xBCDE0395, 0xE52F, 0x467C, [0x8E, 0x3D, 0xC4, 0x57, 0x92, 0x91, 0x69, 0x2E])
IID_IMMDeviceEnumerator = GUID(0xA95664D2, 0x9614, 0x4F35, [0xA7, 0x46, 0xDE, 0x8D, 0xB6, 0x36, 0x17, 0xE6])
IID_IAudioEndpointVolume = GUID(0x5CDF2C82, 0x841E, 0x4546, [0x97, 0x22, 0x0C, 0xF7, 0x40, 0x78, 0x22, 0x9A])

def get_microphone_mute() -> bool:
    try:
        ctypes.windll.ole32.CoInitialize(None)
        enumerator = ctypes.c_void_p()
        hr = ctypes.windll.ole32.CoCreateInstance(
            ctypes.byref(CLSID_MMDeviceEnumerator),
            None,
            23,
            ctypes.byref(IID_IMMDeviceEnumerator),
            ctypes.byref(enumerator)
        )
        if hr != 0:
            return False
            
        vtable = ctypes.cast(enumerator, ctypes.POINTER(ctypes.c_void_p))
        GetDefaultAudioEndpoint_func = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)
        )(ctypes.cast(vtable[0], ctypes.POINTER(ctypes.c_void_p))[4])
        
        device = ctypes.c_void_p()
        hr = GetDefaultAudioEndpoint_func(enumerator, 1, 0, ctypes.byref(device))
        if hr != 0:
            Release_func = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p)(ctypes.cast(vtable[0], ctypes.POINTER(ctypes.c_void_p))[2])
            Release_func(enumerator)
            return False
            
        device_vtable = ctypes.cast(device, ctypes.POINTER(ctypes.c_void_p))
        Activate_func = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
        )(ctypes.cast(device_vtable[0], ctypes.POINTER(ctypes.c_void_p))[3])
        
        volume = ctypes.c_void_p()
        hr = Activate_func(device, ctypes.byref(IID_IAudioEndpointVolume), 23, None, ctypes.byref(volume))
        if hr != 0:
            Release_device = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p)(ctypes.cast(device_vtable[0], ctypes.POINTER(ctypes.c_void_p))[2])
            Release_device(device)
            Release_enum = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p)(ctypes.cast(vtable[0], ctypes.POINTER(ctypes.c_void_p))[2])
            Release_enum(enumerator)
            return False
            
        volume_vtable = ctypes.cast(volume, ctypes.POINTER(ctypes.c_void_p))
        GetMute_func = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL)
        )(ctypes.cast(volume_vtable[0], ctypes.POINTER(ctypes.c_void_p))[15])
        
        is_muted = wintypes.BOOL()
        hr = GetMute_func(volume, ctypes.byref(is_muted))
        
        Release_volume = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p)(ctypes.cast(volume_vtable[0], ctypes.POINTER(ctypes.c_void_p))[2])
        Release_volume(volume)
        Release_device = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p)(ctypes.cast(device_vtable[0], ctypes.POINTER(ctypes.c_void_p))[2])
        Release_device(device)
        Release_enum = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p)(ctypes.cast(vtable[0], ctypes.POINTER(ctypes.c_void_p))[2])
        Release_enum(enumerator)
        
        if hr != 0:
            return False
        return bool(is_muted.value)
    except Exception:
        return False

def set_microphone_mute(mute: bool) -> bool:
    try:
        ctypes.windll.ole32.CoInitialize(None)
        enumerator = ctypes.c_void_p()
        hr = ctypes.windll.ole32.CoCreateInstance(
            ctypes.byref(CLSID_MMDeviceEnumerator),
            None,
            23,
            ctypes.byref(IID_IMMDeviceEnumerator),
            ctypes.byref(enumerator)
        )
        if hr != 0:
            return False
            
        vtable = ctypes.cast(enumerator, ctypes.POINTER(ctypes.c_void_p))
        GetDefaultAudioEndpoint_func = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)
        )(ctypes.cast(vtable[0], ctypes.POINTER(ctypes.c_void_p))[4])
        
        device = ctypes.c_void_p()
        hr = GetDefaultAudioEndpoint_func(enumerator, 1, 0, ctypes.byref(device))
        if hr != 0:
            Release_func = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p)(ctypes.cast(vtable[0], ctypes.POINTER(ctypes.c_void_p))[2])
            Release_func(enumerator)
            return False
            
        device_vtable = ctypes.cast(device, ctypes.POINTER(ctypes.c_void_p))
        Activate_func = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
        )(ctypes.cast(device_vtable[0], ctypes.POINTER(ctypes.c_void_p))[3])
        
        volume = ctypes.c_void_p()
        hr = Activate_func(device, ctypes.byref(IID_IAudioEndpointVolume), 23, None, ctypes.byref(volume))
        if hr != 0:
            Release_device = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p)(ctypes.cast(device_vtable[0], ctypes.POINTER(ctypes.c_void_p))[2])
            Release_device(device)
            Release_enum = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p)(ctypes.cast(vtable[0], ctypes.POINTER(ctypes.c_void_p))[2])
            Release_enum(enumerator)
            return False
            
        volume_vtable = ctypes.cast(volume, ctypes.POINTER(ctypes.c_void_p))
        SetMute_func = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, ctypes.c_void_p, wintypes.BOOL, ctypes.c_void_p
        )(ctypes.cast(volume_vtable[0], ctypes.POINTER(ctypes.c_void_p))[14])
        
        hr = SetMute_func(volume, mute, None)
        
        Release_volume = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p)(ctypes.cast(volume_vtable[0], ctypes.POINTER(ctypes.c_void_p))[2])
        Release_volume(volume)
        Release_device = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p)(ctypes.cast(device_vtable[0], ctypes.POINTER(ctypes.c_void_p))[2])
        Release_device(device)
        Release_enum = ctypes.WINFUNCTYPE(wintypes.DWORD, ctypes.c_void_p)(ctypes.cast(vtable[0], ctypes.POINTER(ctypes.c_void_p))[2])
        Release_enum(enumerator)
        
        return hr == 0
    except Exception:
        return False

# Speech-to-Text API Callers
def transcribe_via_groq(wav_bytes, api_key):
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    files = {
        "file": ("audio.wav", wav_bytes, "audio/wav")
    }
    data = {
        "model": "whisper-large-v3",
        "response_format": "json"
    }
    response = requests.post(url, headers=headers, files=files, data=data)
    response.raise_for_status()
    return response.json().get("text", "")

def transcribe_via_google_speech(wav_bytes, api_key, rate):
    url = f"https://speech.googleapis.com/v1/speech:recognize?key={api_key}"
    headers = {
        "Content-Type": "application/json"
    }
    audio_base64 = base64.b64encode(wav_bytes).decode('utf-8')
    payload = {
        "config": {
            "encoding": "LINEAR16",
            "sampleRateHertz": rate,
            "languageCode": "en-US"
        },
        "audio": {
            "content": audio_base64
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    results = response.json().get("results", [])
    transcript = ""
    for r in results:
        alternatives = r.get("alternatives", [])
        if alternatives:
            transcript += alternatives[0].get("transcript", "") + " "
    return transcript.strip()

def query_gemini_rest_sync(api_key, model_name, parts, callback):
    import json
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:streamGenerateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": parts
        }],
        "generationConfig": {
            "temperature": 1.0,
            "maxOutputTokens": 300,
            "thinkingConfig": {
                "thinkingBudget": 0
            }
        }
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json=payload, stream=True)
    response.raise_for_status()
    
    buffer = ""
    decoder = json.JSONDecoder()
    for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
        if chunk:
            buffer += chunk
            buffer = buffer.lstrip()
            if buffer.startswith('['):
                buffer = buffer[1:].lstrip()
            if buffer.startswith(','):
                buffer = buffer[1:].lstrip()
                
            while buffer:
                try:
                    obj, idx = decoder.raw_decode(buffer)
                    content_parts = obj.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    for part in content_parts:
                        if "text" in part:
                            callback(part["text"])
                    buffer = buffer[idx:].lstrip()
                    if buffer.startswith(','):
                        buffer = buffer[1:].lstrip()
                except json.JSONDecodeError:
                    break

class AsyncLoopThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.loop = asyncio.new_event_loop()
        
    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

class InterviewHelperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Interview Helper - Settings")
        self.root.geometry("520x630")
        self.root.configure(bg="#1e1e1e")
        
        # Audio state
        self.p = None
        self.loopback_stream = None
        self.is_recording = False
        self.is_testing = False
        
        # In-memory loopback buffer
        self.loopback_buffer = bytearray()
        self.loopback_level = 0.0
        self.loopback_devices = []
        
        # Overlay window reference
        self.overlay = None
        self.accumulated_text = ""
        
        self.load_env_keys()
        
        self.async_thread = AsyncLoopThread()
        self.async_thread.start()
        
        self.setup_settings_ui()
        self.detect_devices()
        
    def load_env_keys(self):
        load_dotenv(dotenv_path=".env")
        if not os.environ.get("GEMINI_API_KEY"):
            load_dotenv(dotenv_path="../ielts_speaking/.env")
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        
    def detect_devices(self):
        self.loopback_devices = []
        try:
            self.p = pyaudio.PyAudio()
            wasapi_idx = None
            for i in range(self.p.get_host_api_count()):
                info = self.p.get_host_api_info_by_index(i)
                if info["type"] == pyaudio.paWASAPI:
                    wasapi_idx = i
                    break
            
            if wasapi_idx is None:
                self.status_label.config(text="Status: WASAPI Host API not found!", fg="#f44336")
                return
                
            default_output_idx = -1
            try:
                wasapi_info = self.p.get_host_api_info_by_index(wasapi_idx)
                default_output_idx = wasapi_info.get("defaultOutputDevice", -1)
            except Exception:
                pass
                
            for i in range(self.p.get_device_count()):
                dev_info = self.p.get_device_info_by_index(i)
                if dev_info["hostApi"] != wasapi_idx:
                    continue
                if dev_info.get("isLoopbackDevice", False):
                    self.loopback_devices.append(dev_info)
                    
            if not self.loopback_devices:
                for dev_info in self.p.get_loopback_device_info_generator():
                    self.loopback_devices.append(dev_info)
                    
            loopback_names = [dev["name"] for dev in self.loopback_devices]
            self.loopback_combobox["values"] = loopback_names
            
            if self.loopback_devices:
                selected_idx = 0
                default_speakers = None
                try:
                    default_speakers = self.p.get_device_info_by_index(default_output_idx)
                except Exception:
                    pass
                if default_speakers:
                    for idx, dev in enumerate(self.loopback_devices):
                        if default_speakers["name"] in dev["name"]:
                            selected_idx = idx
                            break
                self.loopback_combobox.current(selected_idx)
                
            self.status_label.config(text="Status: IDLE", fg="#b0b0b0")
        except Exception as e:
            self.status_label.config(text=f"Status: Device Error: {e}", fg="#f44336")
        finally:
            if self.p:
                self.p.terminate()
                self.p = None

    def setup_settings_ui(self):
        style = ttk.Style()
        style.theme_use('vista')
        style.configure("TCombobox", fieldbackground="#2d2d2d", background="#1e1e1e", foreground="#ffffff")
        
        main_frame = tk.Frame(self.root, bg="#1e1e1e", padx=15, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = tk.Label(main_frame, text="INTERVIEW HELPER - SETTINGS", font=("Segoe UI", 13, "bold"), fg="#ffffff", bg="#1e1e1e")
        title_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Gemini/Google API Key
        self.api_frame = tk.Frame(main_frame, bg="#1e1e1e")
        self.api_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Label(self.api_frame, text="Gemini/Google Key:", font=("Segoe UI", 10), fg="#b0b0b0", bg="#1e1e1e").pack(side=tk.LEFT, padx=(0, 10))
        self.api_entry = tk.Entry(self.api_frame, font=("Segoe UI", 10), bg="#2d2d2d", fg="#ffffff", insertbackground="white", bd=0, highlightthickness=1, highlightbackground="#444444")
        self.api_entry.pack(fill=tk.X, side=tk.LEFT, expand=True)
        if self.api_key:
            self.api_entry.insert(0, self.api_key)
            
        # Groq API Key Frame (initially unpacked, packed dynamically)
        self.groq_frame = tk.Frame(main_frame, bg="#1e1e1e")
        self.groq_label = tk.Label(self.groq_frame, text="Groq API Key:       ", font=("Segoe UI", 10), fg="#b0b0b0", bg="#1e1e1e")
        self.groq_label.pack(side=tk.LEFT, padx=(0, 10))
        self.groq_api_entry = tk.Entry(self.groq_frame, font=("Segoe UI", 10), bg="#2d2d2d", fg="#ffffff", insertbackground="white", bd=0, highlightthickness=1, highlightbackground="#444444")
        self.groq_api_entry.pack(fill=tk.X, side=tk.LEFT, expand=True)
        if self.groq_api_key:
            self.groq_api_entry.insert(0, self.groq_api_key)
            
        # System Prompt
        self.prompt_lbl = tk.Label(main_frame, text="System Instructions (Behavior/Tone):", font=("Segoe UI", 10, "bold"), fg="#ffffff", bg="#1e1e1e")
        self.prompt_lbl.pack(anchor=tk.W, pady=(5, 2))
        self.prompt_text = tk.Text(main_frame, height=3, font=("Segoe UI", 9), bg="#2d2d2d", fg="#ffffff", insertbackground="white", bd=0, highlightthickness=1, highlightbackground="#444444")
        self.prompt_text.pack(fill=tk.X, pady=(0, 5))
        self.prompt_text.insert("1.0", DEFAULT_SYSTEM_PROMPT)
        
        # Interview Context
        self.context_lbl = tk.Label(main_frame, text="Interview Context (About Me, Resume, Role Info):", font=("Segoe UI", 10, "bold"), fg="#ffffff", bg="#1e1e1e")
        self.context_lbl.pack(anchor=tk.W, pady=(5, 2))
        self.context_text = tk.Text(main_frame, height=3, font=("Segoe UI", 9), bg="#2d2d2d", fg="#ffffff", insertbackground="white", bd=0, highlightthickness=1, highlightbackground="#444444")
        self.context_text.pack(fill=tk.X, pady=(0, 10))
        self.context_text.insert("1.0", DEFAULT_INTERVIEW_CONTEXT)
        
        # Provider selection frame
        provider_frame = tk.LabelFrame(main_frame, text=" Speech Recognition Provider ", font=("Segoe UI", 9, "bold"), bg="#1e1e1e", fg="#ffffff", bd=1, highlightthickness=0)
        provider_frame.pack(fill=tk.X, pady=(0, 10), ipady=5, ipadx=5)
        
        self.stt_provider_var = tk.StringVar(value="Groq Cloud Whisper (whisper-large-v3)")
        self.stt_combobox = ttk.Combobox(provider_frame, textvariable=self.stt_provider_var, state="readonly")
        self.stt_combobox["values"] = (
            "Groq Cloud Whisper (whisper-large-v3)",
            "Google Cloud Speech-to-Text API",
            "Gemini API (gemini-3.5-flash)"
        )
        self.stt_combobox.pack(fill=tk.X, padx=5, pady=5)
        self.stt_combobox.bind("<<ComboboxSelected>>", self.on_provider_change)
        
        # Audio Device Selector
        self.device_frame = tk.LabelFrame(main_frame, text=" Audio Selection ", font=("Segoe UI", 9, "bold"), bg="#1e1e1e", fg="#ffffff", bd=1, highlightthickness=0)
        self.device_frame.pack(fill=tk.X, pady=(0, 10), ipady=5, ipadx=5)
        
        tk.Label(self.device_frame, text="Interviewer Audio Device (Speaker/Headphone Loopback):", font=("Segoe UI", 9), fg="#b0b0b0", bg="#1e1e1e", anchor=tk.W).pack(fill=tk.X, padx=5, pady=(2, 2))
        self.loopback_combobox = ttk.Combobox(self.device_frame, state="readonly")
        self.loopback_combobox.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        # Speaker Tester / Volume meter
        meter_frame = tk.Frame(self.device_frame, bg="#1e1e1e")
        meter_frame.pack(fill=tk.X, padx=5, pady=2)
        
        self.test_button = tk.Button(meter_frame, text="TEST SPEAKER", font=("Segoe UI", 8, "bold"), bg="#4caf50", fg="#ffffff", activebackground="#388e3c", activeforeground="#ffffff", bd=0, padx=8, pady=3, command=self.toggle_testing)
        self.test_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.loopback_canvas = tk.Canvas(meter_frame, width=200, height=10, bg="#2d2d2d", highlightthickness=0)
        self.loopback_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.draw_meter(self.loopback_canvas, 0, "#2196f3")
        
        # Start button and status
        bottom_frame = tk.Frame(main_frame, bg="#1e1e1e")
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))
        
        start_session_button = tk.Button(bottom_frame, text="START ASSISTANT SESSION", font=("Segoe UI", 10, "bold"), bg="#1976d2", fg="#ffffff", activebackground="#0d47a1", activeforeground="#ffffff", bd=0, padx=15, pady=8, command=self.start_session)
        start_session_button.pack(side=tk.LEFT)
        
        self.status_label = tk.Label(bottom_frame, text="Status: IDLE", font=("Segoe UI", 9, "bold"), fg="#b0b0b0", bg="#1e1e1e")
        self.status_label.pack(side=tk.RIGHT)
        
        # Run change check once to sync initial setup
        self.on_provider_change()

    def on_provider_change(self, event=None):
        provider = self.stt_provider_var.get()
        if provider == "Groq Cloud Whisper (whisper-large-v3)":
            self.groq_frame.pack(fill=tk.X, pady=(0, 5), after=self.api_frame)
        else:
            self.groq_frame.pack_forget()

    def draw_meter(self, canvas, percent, color):
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1:
            width = 200
        if height <= 1:
            height = 10
        canvas.create_rectangle(0, 0, width, height, fill="#2d2d2d", outline="#444444", width=1)
        if percent > 0:
            fill_width = int((percent / 100.0) * width)
            canvas.create_rectangle(0, 0, fill_width, height, fill=color, outline="")

    def calculate_rms(self, in_data):
        count = len(in_data) // 2
        if count == 0:
            return 0.0
        samples = array.array('h', in_data)
        sum_squares = sum(s ** 2 for s in samples)
        return math.sqrt(sum_squares / count)

    def update_meters(self):
        loopback_percent = min(100, int((self.loopback_level / 3000.0) * 100))
        self.draw_meter(self.loopback_canvas, loopback_percent, "#2196f3")
        self.loopback_level *= 0.6
        if self.is_testing:
            self.root.after(50, self.update_meters)
        else:
            self.draw_meter(self.loopback_canvas, 0, "#2196f3")

    def toggle_testing(self):
        if not self.is_testing:
            self.start_testing()
        else:
            self.stop_testing()

    def start_testing(self):
        if self.is_recording:
            return
        loopback_idx = self.loopback_combobox.current()
        if loopback_idx < 0:
            messagebox.showerror("Error", "Please select a speaker loopback device.")
            return
            
        self.is_testing = True
        self.test_button.config(text="STOP TEST", bg="#ff9800")
        self.status_label.config(text="Status: TESTING...", fg="#2196f3")
        
        self.p = pyaudio.PyAudio()
        loopback_info = self.loopback_devices[loopback_idx]
        rate = int(loopback_info.get("defaultSampleRate", 48000))
        loopback_channels = int(loopback_info.get("maxInputChannels", 2))
        
        def loopback_callback(in_data, frame_count, time_info, status):
            self.loopback_level = self.calculate_rms(in_data)
            return (None, pyaudio.paContinue)
            
        self.loopback_stream = self.p.open(
            format=pyaudio.paInt16,
            channels=loopback_channels,
            rate=rate,
            input=True,
            input_device_index=loopback_info["index"],
            stream_callback=loopback_callback
        )
        self.loopback_stream.start_stream()
        self.update_meters()

    def stop_testing(self):
        self.is_testing = False
        self.test_button.config(text="TEST SPEAKER", bg="#4caf50")
        self.status_label.config(text="Status: IDLE", fg="#b0b0b0")
        if self.loopback_stream:
            self.loopback_stream.stop_stream()
            self.loopback_stream.close()
            self.loopback_stream = None
        if self.p:
            self.p.terminate()
            self.p = None

    def start_session(self):
        if self.is_testing:
            self.stop_testing()
            
        key = self.api_entry.get().strip()
        loopback_idx = self.loopback_combobox.current()
        provider = self.stt_provider_var.get()
        
        if not key:
            messagebox.showerror("Error", "Please enter a Gemini/Google API Key.")
            return
        if loopback_idx < 0:
            messagebox.showerror("Error", "Please select a speaker loopback device.")
            return
        if provider == "Groq Cloud Whisper (whisper-large-v3)":
            groq_key = self.groq_api_entry.get().strip()
            if not groq_key:
                messagebox.showerror("Error", "Please enter a Groq API Key first.")
                return
            
        # Hide settings window
        self.root.withdraw()
        
        # Open Overlay Window
        self.setup_overlay_ui()

    def setup_overlay_ui(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.title("Interview Helper [Overlay]")
        self.overlay.geometry("680x780")
        self.overlay.configure(bg="#121212")
        self.overlay.attributes("-transparentcolor", "#121212")
        
        self.apply_protection(self.overlay)
        self.overlay.protocol("WM_DELETE_WINDOW", self.close_session)
        
        overlay_frame = tk.Frame(self.overlay, bg="#121212", padx=10, pady=10)
        overlay_frame.pack(fill=tk.BOTH, expand=True)
        
        # Top Row: Control and Mic State
        top_row = tk.Frame(overlay_frame, bg="#121212")
        top_row.pack(fill=tk.X, pady=(0, 5))
        
        self.record_button = tk.Button(top_row, text="START RECORDING", font=("Segoe UI", 12, "bold"), bg="#d32f2f", fg="#ffffff", activebackground="#b71c1c", activeforeground="#ffffff", bd=0, padx=15, pady=6, command=self.toggle_recording)
        self.record_button.pack(side=tk.LEFT)
        
        self.mic_mute_button = tk.Button(top_row, text="CHECKING MIC...", font=("Segoe UI", 12, "bold"), bg="#757575", fg="#ffffff", bd=0, padx=15, pady=6, command=self.toggle_mic_mute)
        self.mic_mute_button.pack(side=tk.LEFT, padx=10)
        
        self.overlay_status_label = tk.Label(top_row, text="Status: IDLE", font=("Segoe UI", 11, "bold"), fg="#b0b0b0", bg="#121212")
        self.overlay_status_label.pack(side=tk.RIGHT)
        
        quick_lbl = tk.Label(overlay_frame, text="Key Strategy Hint:", font=("Segoe UI", 12, "bold"), fg="#ffb300", bg="#121212")
        quick_lbl.pack(anchor=tk.W, pady=(5, 2))
        
        self.quick_hint_entry = tk.Entry(overlay_frame, font=("Segoe UI", 15, "bold"), bg="#222222", fg="#ffb300", insertbackground="white", bd=0, highlightthickness=1, highlightbackground="#ffb300")
        self.quick_hint_entry.pack(fill=tk.X, pady=(0, 5), ipady=6)
        self.quick_hint_entry.insert(0, "Key strategy hint will display here...")
        
        # Transcript Section (Top - small)
        transcript_frame = tk.Frame(overlay_frame, bg="#121212")
        transcript_frame.pack(fill=tk.X, pady=(5, 5))
        tk.Label(transcript_frame, text="Interviewer Transcript:", font=("Segoe UI", 12, "bold"), fg="#ffffff", bg="#121212").pack(anchor=tk.W, pady=2)
        
        self.transcript_area = scrolledtext.ScrolledText(transcript_frame, height=4, font=("Segoe UI", 12), bg="#222222", fg="#e0e0e0", bd=0, highlightthickness=1, highlightbackground="#333333")
        self.transcript_area.pack(fill=tk.X, expand=True)
        self.transcript_area.insert("1.0", "Verbatim transcription...")
        
        # Detailed Hints Section (Bottom - fills remaining space)
        hints_frame = tk.Frame(overlay_frame, bg="#121212")
        hints_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 5))
        tk.Label(hints_frame, text="Suggested Response (Speak This):", font=("Segoe UI", 12, "bold"), fg="#ffffff", bg="#121212").pack(anchor=tk.W, pady=2)
        
        self.response_area = scrolledtext.ScrolledText(hints_frame, font=("Segoe UI", 13), bg="#222222", fg="#ffffff", bd=0, highlightthickness=1, highlightbackground="#333333")
        self.response_area.pack(fill=tk.BOTH, expand=True)
        self.response_area.insert("1.0", "Suggested response will display here...")
        
        # Bottom controls
        bottom_row = tk.Frame(overlay_frame, bg="#121212")
        bottom_row.pack(fill=tk.X, pady=(5, 0))
        
        copy_btn = tk.Button(bottom_row, text="Copy Hints", font=("Segoe UI", 11, "bold"), bg="#1976d2", fg="#ffffff", activebackground="#0d47a1", activeforeground="#ffffff", bd=0, padx=12, pady=4, command=self.copy_hints)
        copy_btn.pack(side=tk.LEFT)
        
        clear_btn = tk.Button(bottom_row, text="Clear", font=("Segoe UI", 11, "bold"), bg="#424242", fg="#ffffff", activebackground="#212121", activeforeground="#ffffff", bd=0, padx=12, pady=4, command=self.clear_fields)
        clear_btn.pack(side=tk.LEFT, padx=10)
        
        close_btn = tk.Button(bottom_row, text="Close & Settings", font=("Segoe UI", 11, "bold"), bg="#d32f2f", fg="#ffffff", activebackground="#b71c1c", activeforeground="#ffffff", bd=0, padx=12, pady=4, command=self.close_session)
        close_btn.pack(side=tk.RIGHT)
        
        self.poll_mic_status()

    def apply_protection(self, target_window):
        WDA_MONITOR = 0x00000001
        try:
            target_window.update()
            hwnd = target_window.winfo_id()
            GA_ROOT = 2
            hwnd_root = ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT)
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd_root, WDA_MONITOR)
        except Exception as e:
            print(f"Error applying display affinity: {e}")

    def toggle_mic_mute(self):
        muted = get_microphone_mute()
        success = set_microphone_mute(not muted)
        if success:
            self.update_mic_button_state(not muted)

    def poll_mic_status(self):
        if self.overlay and self.overlay.winfo_exists():
            muted = get_microphone_mute()
            self.update_mic_button_state(muted)
            self.overlay.after(500, self.poll_mic_status)

    def update_mic_button_state(self, is_muted):
        if is_muted:
            self.mic_mute_button.config(text="MIC: MUTED", bg="#f44336", activebackground="#d32f2f")
        else:
            self.mic_mute_button.config(text="MIC: ACTIVE", bg="#4caf50", activebackground="#388e3c")

    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        loopback_idx = self.loopback_combobox.current()
        if loopback_idx < 0:
            messagebox.showerror("Error", "Please select a speaker loopback device.")
            return
            
        self.is_recording = True
        self.record_button.config(text="STOP RECORDING", bg="#ff9800", activebackground="#e65100")
        self.overlay_status_label.config(text="Status: RECORDING...", fg="#ff9800")
        
        self.loopback_buffer = bytearray()
        self.p = pyaudio.PyAudio()
        
        loopback_info = self.loopback_devices[loopback_idx]
        rate = int(loopback_info.get("defaultSampleRate", 48000))
        loopback_channels = int(loopback_info.get("maxInputChannels", 2))
        
        def loopback_callback(in_data, frame_count, time_info, status):
            if self.is_recording:
                self.loopback_buffer.extend(in_data)
            return (None, pyaudio.paContinue)
            
        self.loopback_stream = self.p.open(
            format=pyaudio.paInt16,
            channels=loopback_channels,
            rate=rate,
            input=True,
            input_device_index=loopback_info["index"],
            stream_callback=loopback_callback
        )
        self.loopback_stream.start_stream()

    def stop_recording(self):
        self.is_recording = False
        self.record_button.config(state=tk.DISABLED, text="PROCESSING...", bg="#424242")
        self.overlay_status_label.config(text="Status: PROCESSING...", fg="#2196f3")
        
        if self.loopback_stream:
            self.loopback_stream.stop_stream()
            self.loopback_stream.close()
            self.loopback_stream = None
        if self.p:
            self.p.terminate()
            self.p = None
            
        asyncio.run_coroutine_threadsafe(self.process_audio_async(), self.async_thread.loop)

    def make_mono_wav(self, loopback_buffer, loopback_channels, rate):
        if not loopback_buffer:
            return b""
        samples = array.array('h', loopback_buffer)
        if loopback_channels == 2:
            mono_loop = array.array('h')
            for i in range(0, len(samples), 2):
                if i + 1 < len(samples):
                    mono_loop.append((samples[i] + samples[i+1]) // 2)
                else:
                    mono_loop.append(samples[i])
            samples = mono_loop
            
        target_rate = 16000
        if rate != target_rate:
            ratio = rate / target_rate
            resampled = array.array('h')
            for i in range(int(len(samples) / ratio)):
                idx = int(i * ratio)
                if idx < len(samples):
                    resampled.append(samples[idx])
            samples = resampled
            rate = target_rate
            
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(samples.tobytes())
            
        return wav_io.getvalue()

    async def process_audio_async(self):
        try:
            api_key = self.api_entry.get().strip()
            genai.configure(api_key=api_key)
            
            system_prompt_raw = self.prompt_text.get("1.0", tk.END).strip()
            interview_context = self.context_text.get("1.0", tk.END).strip()
            system_prompt = f"{system_prompt_raw}\n\nCandidate / Interview Subject Context:\n{interview_context}"
            loopback_idx = self.loopback_combobox.current()
            
            loopback_info = self.loopback_devices[loopback_idx]
            rate = int(loopback_info.get("defaultSampleRate", 48000))
            loopback_channels = int(loopback_info.get("maxInputChannels", 2))
            
            wav_bytes = self.make_mono_wav(self.loopback_buffer, loopback_channels, rate)
            if not wav_bytes:
                self.overlay.after(0, lambda: self.update_transcript_ui("No audio captured."))
                self.overlay_status_label.config(text="Status: IDLE", fg="#b0b0b0")
                self.overlay.after(0, self.reset_record_button)
                return
                
            provider = self.stt_provider_var.get()
            transcript = ""
            
            # 1. Run Speech Recognition (if cloud provider selected)
            if provider == "Groq Cloud Whisper (whisper-large-v3)":
                self.overlay_status_label.config(text="Status: TRANSCRIBING VIA GROQ...", fg="#9c27b0")
                groq_key = self.groq_api_entry.get().strip()
                if not groq_key:
                    raise Exception("Missing Groq API Key!")
                loop = asyncio.get_event_loop()
                transcript = await loop.run_in_executor(None, lambda: transcribe_via_groq(wav_bytes, groq_key))
                self.overlay.after(0, lambda val=transcript: self.update_transcript_ui(f"Interviewer: {val}"))
                
            elif provider == "Google Cloud Speech-to-Text API":
                self.overlay_status_label.config(text="Status: TRANSCRIBING VIA GOOGLE SPEECH...", fg="#9c27b0")
                google_stt_key = self.api_entry.get().strip()
                if not google_stt_key:
                    raise Exception("Missing Google/Gemini API Key!")
                loop = asyncio.get_event_loop()
                transcript = await loop.run_in_executor(None, lambda: transcribe_via_google_speech(wav_bytes, google_stt_key, rate))
                self.overlay.after(0, lambda val=transcript: self.update_transcript_ui(f"Interviewer: {val}"))
                
            elif provider == "Gemini API (gemini-3.5-flash)":
                self.overlay_status_label.config(text="Status: TRANSCRIBING VIA GEMINI...", fg="#9c27b0")
                model = genai.GenerativeModel(model_name=DEFAULT_MODEL)
                audio_part = {
                    "mime_type": "audio/wav",
                    "data": wav_bytes
                }
                transcribe_prompt = (
                    "Analyze the attached mono audio file containing the interviewer's audio. "
                    "Provide a clear, verbatim transcription of what was said. Output only the transcript "
                    "without any prefixes, names, or labels like 'Interviewer:'."
                )
                transcribe_response = await model.generate_content_async([audio_part, transcribe_prompt])
                transcript = transcribe_response.text.strip()
                self.overlay.after(0, lambda val=transcript: self.update_transcript_ui(f"Interviewer: {val}"))
            
            # 2. Query Gemini for Suggestions
            self.overlay_status_label.config(text="Status: GENERATING SUGGESTIONS...", fg="#00bcd4")
            loop = asyncio.get_event_loop()
            
            self.overlay.after(0, lambda: self.update_fast_hint_ui("Generating key strategy..."))
            self.overlay.after(0, lambda: self.update_main_hints_ui("Generating response..."))
            
            prompt = (
                f"Review this interview transcript containing the interviewer's question/comment:\nInterviewer: {transcript}\n\n"
                "First, generate a 1-sentence quick strategy hint (under 8 words) for the candidate.\n"
                "Second, generate a single, direct, professional response that the candidate can read aloud to the interviewer.\n\n"
                "RULES FOR THE RESPONSE:\n"
                "- Do NOT provide bullet points, lists, options, or tips.\n"
                "- Do NOT use markdown symbols, bold text (**), asterisks, hashes (#), or headers.\n"
                "- Output only the exact text of the single response to be spoken.\n"
                "- Ensure maximum readability for speech.\n"
                "- If the transcript is empty, silent, or incoherent, set the quick strategy hint to 'Ask for repetition' and the response to: 'I\\'m sorry, the audio cut out slightly. Would you mind repeating that?'\n\n"
                f"Context: {system_prompt}\n\n"
                "You MUST format your output exactly as follows:\n"
                "[QUICK]\n"
                "(Insert your 1-sentence quick strategy hint here)\n"
                "[DETAILED]\n"
                "(Insert the single direct spoken response here)\n"
            )
            
            parts = [
                {
                    "text": prompt
                }
            ]
            
            self.accumulated_text = ""
            await loop.run_in_executor(
                None,
                lambda: query_gemini_rest_sync(
                    api_key,
                    DEFAULT_MODEL,
                    parts,
                    lambda text: self.overlay.after(0, lambda: self.parse_and_update_text_only_stream(text))
                )
            )
                    
            self.overlay_status_label.config(text="Status: READY", fg="#4caf50")
        except Exception as e:
            error_msg = f"Error in async processing pipeline:\n{str(e)}"
            self.overlay.after(0, lambda: self.update_main_hints_ui(error_msg))
            self.overlay_status_label.config(text="Status: ERROR", fg="#f44336")
        finally:
            self.overlay.after(0, self.reset_record_button)

    def parse_and_update_text_only_stream(self, new_text):
        self.accumulated_text += new_text
        text = self.accumulated_text
        
        quick_start = text.find("[QUICK]")
        detailed_start = text.find("[DETAILED]")
        
        if quick_start != -1:
            end_idx = detailed_start if detailed_start != -1 else len(text)
            quick_content = text[quick_start + len("[QUICK]"):end_idx].strip()
            self.overlay.after(0, lambda val=quick_content: self.update_fast_hint_ui(val))
            
        if detailed_start != -1:
            detailed_content = text[detailed_start + len("[DETAILED]"):].strip()
            self.overlay.after(0, lambda val=detailed_content: self.update_main_hints_ui(val))

    def update_transcript_ui(self, text):
        self.transcript_area.delete("1.0", tk.END)
        self.transcript_area.insert("1.0", text)

    def update_fast_hint_ui(self, text):
        self.quick_hint_entry.delete(0, tk.END)
        self.quick_hint_entry.insert(0, text.strip())

    def update_main_hints_ui(self, text):
        self.response_area.delete("1.0", tk.END)
        self.response_area.insert("1.0", text)

    def reset_record_button(self):
        self.record_button.config(state=tk.NORMAL, text="START RECORDING", bg="#d32f2f", activebackground="#b71c1c")

    def copy_hints(self):
        text = self.response_area.get("1.0", tk.END).strip()
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Copied", "Hints copied to clipboard!")

    def clear_fields(self):
        self.transcript_area.delete("1.0", tk.END)
        self.transcript_area.insert("1.0", "Verbatim transcription...")
        self.quick_hint_entry.delete(0, tk.END)
        self.quick_hint_entry.insert(0, "Key strategy hint will display here...")
        self.response_area.delete("1.0", tk.END)
        self.response_area.insert("1.0", "Suggested response will display here...")
        self.overlay_status_label.config(text="Status: IDLE", fg="#b0b0b0")

    def close_session(self):
        if self.is_recording:
            self.stop_recording()
        if self.overlay:
            self.overlay.destroy()
            self.overlay = None
        self.root.deiconify()

if __name__ == "__main__":
    root = tk.Tk()
    app = InterviewHelperApp(root)
    root.mainloop()
