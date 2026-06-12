import os
import sys
import threading
import wave
import ctypes
import math
import array
import io
import asyncio
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from dotenv import load_dotenv
import pyaudiowpatch as pyaudio
import google.generativeai as genai

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
        self.root.title("Interview Helper [Protected]")
        self.root.geometry("620x900")
        self.root.configure(bg="#1e1e1e")
        
        # Audio state
        self.p = None
        self.mic_stream = None
        self.loopback_stream = None
        self.is_recording = False
        self.is_testing = False
        
        # In-memory audio buffers
        self.mic_buffer = bytearray()
        self.loopback_buffer = bytearray()
        
        # Live Volume Meter levels
        self.mic_level = 0.0
        self.loopback_level = 0.0
        
        # Devices list
        self.mic_devices = []
        self.loopback_devices = []
        
        # Load environment variables
        self.load_env_keys()
        
        # Start Async Background Thread
        self.async_thread = AsyncLoopThread()
        self.async_thread.start()
        
        # Setup GUI Components
        self.setup_ui()
        
        # Apply Screen Sharing Protection
        self.apply_protection()
        
        # Detect and Populate Audio Devices
        self.detect_devices()
        
    def load_env_keys(self):
        # Try loading from local directory
        load_dotenv(dotenv_path=".env")
        # Try loading from the neighboring ielts_speaking directory
        if not os.environ.get("GEMINI_API_KEY"):
            load_dotenv(dotenv_path="../ielts_speaking/.env")
            
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        
    def apply_protection(self):
        # Apply WDA_MONITOR (0x01) display affinity to render window as black box on screen capture
        WDA_MONITOR = 0x00000001
        try:
            self.root.update()
            hwnd = self.root.winfo_id()
            # Find the top-level parent HWND
            GA_ROOT = 2
            hwnd_root = ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT)
            
            result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd_root, WDA_MONITOR)
            if result:
                self.protection_status_label.config(text="Capture Protected: ACTIVE (Black Box)", fg="#4caf50")
            else:
                self.protection_status_label.config(text="Capture Protected: FAILED (Fallback)", fg="#f44336")
        except Exception as e:
            print(f"Error applying window protection: {e}")
            self.protection_status_label.config(text="Capture Protected: ERROR", fg="#f44336")

    def detect_devices(self):
        self.mic_devices = []
        self.loopback_devices = []
        
        try:
            self.p = pyaudio.PyAudio()
            
            # Find WASAPI Host API index
            wasapi_idx = None
            for i in range(self.p.get_host_api_count()):
                info = self.p.get_host_api_info_by_index(i)
                if info["type"] == pyaudio.paWASAPI:
                    wasapi_idx = i
                    break
            
            if wasapi_idx is None:
                self.status_label.config(text="Status: WASAPI Host API not found!", fg="#f44336")
                return
                
            # Scan devices for WASAPI inputs and loopbacks
            default_input_idx = -1
            default_output_idx = -1
            try:
                wasapi_info = self.p.get_host_api_info_by_index(wasapi_idx)
                default_input_idx = wasapi_info.get("defaultInputDevice", -1)
                default_output_idx = wasapi_info.get("defaultOutputDevice", -1)
            except Exception:
                pass
                
            for i in range(self.p.get_device_count()):
                dev_info = self.p.get_device_info_by_index(i)
                if dev_info["hostApi"] != wasapi_idx:
                    continue
                    
                if dev_info.get("isLoopbackDevice", False):
                    self.loopback_devices.append(dev_info)
                elif dev_info.get("maxInputChannels", 0) > 0:
                    self.mic_devices.append(dev_info)
                    
            # Fallback if generator needed
            if not self.loopback_devices:
                for dev_info in self.p.get_loopback_device_info_generator():
                    self.loopback_devices.append(dev_info)
                    
            # Populate Combobox values
            mic_names = [dev["name"] for dev in self.mic_devices]
            self.mic_combobox["values"] = mic_names
            
            loopback_names = [dev["name"] for dev in self.loopback_devices]
            self.loopback_combobox["values"] = loopback_names
            
            # Pre-select defaults
            if self.mic_devices:
                selected_idx = 0
                for idx, dev in enumerate(self.mic_devices):
                    if dev["index"] == default_input_idx:
                        selected_idx = idx
                        break
                self.mic_combobox.current(selected_idx)
                
            if self.loopback_devices:
                selected_idx = 0
                # Try to find corresponding loopback for default speaker
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
            self.status_label.config(text=f"Status: Device Detection Error: {e}", fg="#f44336")
        finally:
            if self.p:
                self.p.terminate()
                self.p = None

    def setup_ui(self):
        # Configure Style for dark Combobox dropdowns
        style = ttk.Style()
        style.theme_use('vista')
        style.configure("TCombobox", fieldbackground="#2d2d2d", background="#1e1e1e", foreground="#ffffff")
        
        # Main Frame with padding
        main_frame = tk.Frame(self.root, bg="#1e1e1e", padx=15, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header / Protection Status
        header_frame = tk.Frame(main_frame, bg="#1e1e1e")
        header_frame.pack(fill=tk.X, pady=(0, 5))
        
        title_label = tk.Label(header_frame, text="INTERVIEW HELPER", font=("Segoe UI", 15, "bold"), fg="#ffffff", bg="#1e1e1e")
        title_label.pack(side=tk.LEFT)
        
        self.protection_status_label = tk.Label(header_frame, text="Capture Protected: INITIALIZING", font=("Segoe UI", 9, "bold"), fg="#ff9800", bg="#1e1e1e")
        self.protection_status_label.pack(side=tk.RIGHT, pady=5)
        
        # API Key Input
        api_frame = tk.Frame(main_frame, bg="#1e1e1e")
        api_frame.pack(fill=tk.X, pady=(0, 5))
        
        api_label = tk.Label(api_frame, text="Gemini API Key:", font=("Segoe UI", 10), fg="#b0b0b0", bg="#1e1e1e")
        api_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.api_entry = tk.Entry(api_frame, font=("Segoe UI", 10), bg="#2d2d2d", fg="#ffffff", insertbackground="white", bd=0, highlightthickness=1, highlightbackground="#444444")
        self.api_entry.pack(fill=tk.X, side=tk.LEFT, expand=True)
        if self.api_key:
            self.api_entry.insert(0, self.api_key)
            
        # System Prompt / Context Area
        self.prompt_lbl = tk.Label(main_frame, text="System Instructions (Behavior/Tone):", font=("Segoe UI", 10, "bold"), fg="#ffffff", bg="#1e1e1e")
        self.prompt_lbl.pack(anchor=tk.W, pady=(2, 2))
        
        self.prompt_text = tk.Text(main_frame, height=3, font=("Segoe UI", 9), bg="#2d2d2d", fg="#ffffff", insertbackground="white", bd=0, highlightthickness=1, highlightbackground="#444444")
        self.prompt_text.pack(fill=tk.X, pady=(0, 5))
        self.prompt_text.insert("1.0", DEFAULT_SYSTEM_PROMPT)
        
        # Interview Context
        self.context_lbl = tk.Label(main_frame, text="Interview Context (About Me, Resume, Role Info):", font=("Segoe UI", 10, "bold"), fg="#ffffff", bg="#1e1e1e")
        self.context_lbl.pack(anchor=tk.W, pady=(2, 2))
        
        self.context_text = tk.Text(main_frame, height=3, font=("Segoe UI", 9), bg="#2d2d2d", fg="#ffffff", insertbackground="white", bd=0, highlightthickness=1, highlightbackground="#444444")
        self.context_text.pack(fill=tk.X, pady=(0, 5))
        self.context_text.insert("1.0", DEFAULT_INTERVIEW_CONTEXT)
        
        # Audio Devices Frame
        device_frame = tk.LabelFrame(main_frame, text=" Audio Source Selection ", font=("Segoe UI", 9, "bold"), bg="#1e1e1e", fg="#ffffff", bd=1, highlightthickness=0)
        device_frame.pack(fill=tk.X, pady=(0, 5), ipady=5, ipadx=5)
        
        tk.Label(device_frame, text="Microphone Input Device:", font=("Segoe UI", 9), fg="#b0b0b0", bg="#1e1e1e", anchor=tk.W).pack(fill=tk.X, padx=5, pady=(2, 0))
        self.mic_combobox = ttk.Combobox(device_frame, state="readonly")
        self.mic_combobox.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        tk.Label(device_frame, text="System Loopback Device (Speaker/Headphones):", font=("Segoe UI", 9), fg="#b0b0b0", bg="#1e1e1e", anchor=tk.W).pack(fill=tk.X, padx=5, pady=(2, 0))
        self.loopback_combobox = ttk.Combobox(device_frame, state="readonly")
        self.loopback_combobox.pack(fill=tk.X, padx=5, pady=(0, 2))
        
        # Live Audio Level Meter Frame
        meter_frame = tk.LabelFrame(main_frame, text=" Audio Tester & Live Levels ", font=("Segoe UI", 9, "bold"), bg="#1e1e1e", fg="#ffffff", bd=1, highlightthickness=0)
        meter_frame.pack(fill=tk.X, pady=(0, 5), ipady=5, ipadx=5)
        
        meter_control_frame = tk.Frame(meter_frame, bg="#1e1e1e")
        meter_control_frame.pack(fill=tk.X, padx=5, pady=(2, 5))
        
        self.test_button = tk.Button(meter_control_frame, text="TEST AUDIO", font=("Segoe UI", 9, "bold"), bg="#4caf50", fg="#ffffff", activebackground="#388e3c", activeforeground="#ffffff", bd=0, padx=10, pady=4, command=self.toggle_testing)
        self.test_button.pack(side=tk.LEFT)
        
        test_info_label = tk.Label(meter_control_frame, text="Select your devices above, then test active volume levels.", font=("Segoe UI", 9), fg="#888888", bg="#1e1e1e")
        test_info_label.pack(side=tk.LEFT, padx=10)
        
        # Mic level row
        mic_level_frame = tk.Frame(meter_frame, bg="#1e1e1e")
        mic_level_frame.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(mic_level_frame, text="Mic Level:    ", font=("Segoe UI", 9), fg="#b0b0b0", bg="#1e1e1e", width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.mic_canvas = tk.Canvas(mic_level_frame, width=250, height=10, bg="#2d2d2d", highlightthickness=0)
        self.mic_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.draw_meter(self.mic_canvas, 0, "#4caf50")
        
        # Speaker level row
        speaker_level_frame = tk.Frame(meter_frame, bg="#1e1e1e")
        speaker_level_frame.pack(fill=tk.X, padx=5, pady=2)
        tk.Label(speaker_level_frame, text="Speaker Level:", font=("Segoe UI", 9), fg="#b0b0b0", bg="#1e1e1e", width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.loopback_canvas = tk.Canvas(speaker_level_frame, width=250, height=10, bg="#2d2d2d", highlightthickness=0)
        self.loopback_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.draw_meter(self.loopback_canvas, 0, "#2196f3")
        
        # Recording Control Panel
        control_frame = tk.Frame(main_frame, bg="#1e1e1e")
        control_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.record_button = tk.Button(control_frame, text="START RECORDING", font=("Segoe UI", 11, "bold"), bg="#d32f2f", fg="#ffffff", activebackground="#b71c1c", activeforeground="#ffffff", bd=0, padx=20, pady=8, command=self.toggle_recording)
        self.record_button.pack(side=tk.LEFT)
        
        self.status_label = tk.Label(control_frame, text="Status: INITIALIZING DEVICES...", font=("Segoe UI", 10, "bold"), fg="#b0b0b0", bg="#1e1e1e")
        self.status_label.pack(side=tk.LEFT, padx=20)
        
        # Quick 1-Sentence Hint Box (Vibrant Highlights)
        quick_hint_label = tk.Label(main_frame, text="Key Strategy Hint:", font=("Segoe UI", 10, "bold"), fg="#ffb300", bg="#1e1e1e")
        quick_hint_label.pack(anchor=tk.W, pady=(2, 2))
        
        self.quick_hint_entry = tk.Entry(main_frame, font=("Segoe UI", 11, "bold"), bg="#2d2d2d", fg="#ffb300", insertbackground="white", bd=0, highlightthickness=1, highlightbackground="#ffb300")
        self.quick_hint_entry.pack(fill=tk.X, pady=(0, 5), ipady=5)
        self.quick_hint_entry.insert(0, "Key strategy hint will display here...")
        
        # Transcript & Main Hints Side-by-Side Frame
        results_frame = tk.Frame(main_frame, bg="#1e1e1e")
        results_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # Left Side: Transcript
        left_frame = tk.Frame(results_frame, bg="#1e1e1e")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        tk.Label(left_frame, text="Transcript (Speech-to-Text):", font=("Segoe UI", 10, "bold"), fg="#ffffff", bg="#1e1e1e").pack(anchor=tk.W, pady=2)
        self.transcript_area = scrolledtext.ScrolledText(left_frame, font=("Segoe UI", 9), bg="#2d2d2d", fg="#e0e0e0", bd=0, highlightthickness=1, highlightbackground="#444444")
        self.transcript_area.pack(fill=tk.BOTH, expand=True)
        self.transcript_area.insert("1.0", "Verbatim transcript of conversation...")
        
        # Right Side: Main Suggestions
        right_frame = tk.Frame(results_frame, bg="#1e1e1e")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        tk.Label(right_frame, text="Suggested Response (Speak This):", font=("Segoe UI", 10, "bold"), fg="#ffffff", bg="#1e1e1e").pack(anchor=tk.W, pady=2)
        self.response_area = scrolledtext.ScrolledText(right_frame, font=("Segoe UI", 9), bg="#2d2d2d", fg="#ffffff", bd=0, highlightthickness=1, highlightbackground="#444444")
        self.response_area.pack(fill=tk.BOTH, expand=True)
        self.response_area.insert("1.0", "Suggested response will display here...")
        
        # Bottom Buttons
        bottom_frame = tk.Frame(main_frame, bg="#1e1e1e")
        bottom_frame.pack(fill=tk.X, pady=(5, 0))
        
        copy_button = tk.Button(bottom_frame, text="Copy Hints", font=("Segoe UI", 9, "bold"), bg="#1976d2", fg="#ffffff", activebackground="#0d47a1", activeforeground="#ffffff", bd=0, padx=15, pady=5, command=self.copy_hints)
        copy_button.pack(side=tk.LEFT, padx=(0, 10))
        
        clear_button = tk.Button(bottom_frame, text="Clear", font=("Segoe UI", 9, "bold"), bg="#424242", fg="#ffffff", activebackground="#212121", activeforeground="#ffffff", bd=0, padx=15, pady=5, command=self.clear_fields)
        clear_button.pack(side=tk.LEFT)
        
        exit_button = tk.Button(bottom_frame, text="Exit", font=("Segoe UI", 9, "bold"), bg="#d32f2f", fg="#ffffff", activebackground="#b71c1c", activeforeground="#ffffff", bd=0, padx=15, pady=5, command=self.root.quit)
        exit_button.pack(side=tk.RIGHT)

    def draw_meter(self, canvas, percent, color):
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1:
            width = 250
        if height <= 1:
            height = 10
        # Draw background bar
        canvas.create_rectangle(0, 0, width, height, fill="#2d2d2d", outline="#444444", width=1)
        # Draw level bar
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
        mic_percent = min(100, int((self.mic_level / 3000.0) * 100))
        loopback_percent = min(100, int((self.loopback_level / 3000.0) * 100))
        
        self.draw_meter(self.mic_canvas, mic_percent, "#4caf50")
        self.draw_meter(self.loopback_canvas, loopback_percent, "#2196f3")
        
        # Decay levels
        self.mic_level *= 0.6
        self.loopback_level *= 0.6
        
        if self.is_recording or self.is_testing:
            self.root.after(50, self.update_meters)
        else:
            self.draw_meter(self.mic_canvas, 0, "#4caf50")
            self.draw_meter(self.loopback_canvas, 0, "#2196f3")

    def toggle_testing(self):
        if not self.is_testing:
            self.start_testing()
        else:
            self.stop_testing()
            
    def start_testing(self):
        if self.is_recording:
            return
            
        mic_idx = self.mic_combobox.current()
        loopback_idx = self.loopback_combobox.current()
        
        if mic_idx < 0 or loopback_idx < 0:
            messagebox.showerror("Error", "Please select valid audio devices.")
            return
            
        self.is_testing = True
        self.test_button.config(text="STOP TEST", bg="#ff9800", activebackground="#e65100")
        self.status_label.config(text="Status: TESTING DEVICES...", fg="#2196f3")
        self.record_button.config(state=tk.DISABLED)
        
        self.p = pyaudio.PyAudio()
        
        mic_info = self.mic_devices[mic_idx]
        loopback_info = self.loopback_devices[loopback_idx]
        
        mic_channels = int(mic_info.get("maxInputChannels", 1))
        # Match rate to loopback to avoid complex sample rate conversion
        rate = int(loopback_info.get("defaultSampleRate", 48000))
        loopback_channels = int(loopback_info.get("maxInputChannels", 2))
        
        def mic_callback(in_data, frame_count, time_info, status):
            self.mic_level = self.calculate_rms(in_data)
            return (None, pyaudio.paContinue)
            
        def loopback_callback(in_data, frame_count, time_info, status):
            self.loopback_level = self.calculate_rms(in_data)
            return (None, pyaudio.paContinue)
            
        self.mic_stream = self.p.open(
            format=pyaudio.paInt16,
            channels=mic_channels,
            rate=rate,
            input=True,
            input_device_index=mic_info["index"],
            stream_callback=mic_callback
        )
        
        self.loopback_stream = self.p.open(
            format=pyaudio.paInt16,
            channels=loopback_channels,
            rate=rate,
            input=True,
            input_device_index=loopback_info["index"],
            stream_callback=loopback_callback
        )
        
        self.mic_stream.start_stream()
        self.loopback_stream.start_stream()
        
        self.update_meters()
        
    def stop_testing(self):
        self.is_testing = False
        self.test_button.config(text="TEST AUDIO", bg="#4caf50", activebackground="#388e3c")
        self.status_label.config(text="Status: IDLE", fg="#b0b0b0")
        self.record_button.config(state=tk.NORMAL)
        
        if self.mic_stream:
            self.mic_stream.stop_stream()
            self.mic_stream.close()
            self.mic_stream = None
        if self.loopback_stream:
            self.loopback_stream.stop_stream()
            self.loopback_stream.close()
            self.loopback_stream = None
            
        if self.p:
            self.p.terminate()
            self.p = None

    def toggle_recording(self):
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()
            
    def start_recording(self):
        if self.is_testing:
            self.stop_testing()
            
        # Validate API Key
        key = self.api_entry.get().strip()
        if not key:
            messagebox.showerror("Error", "Please enter a Gemini API Key first.")
            return
            
        mic_idx = self.mic_combobox.current()
        loopback_idx = self.loopback_combobox.current()
        
        if mic_idx < 0 or loopback_idx < 0:
            messagebox.showerror("Error", "Please select valid audio devices.")
            return
            
        self.is_recording = True
        self.record_button.config(text="STOP RECORDING", bg="#ff9800", activebackground="#e65100")
        self.status_label.config(text="Status: RECORDING...", fg="#ff9800")
        self.test_button.config(state=tk.DISABLED)
        
        # Reset in-memory buffers
        self.mic_buffer = bytearray()
        self.loopback_buffer = bytearray()
        
        self.p = pyaudio.PyAudio()
        
        mic_info = self.mic_devices[mic_idx]
        loopback_info = self.loopback_devices[loopback_idx]
        
        mic_channels = int(mic_info.get("maxInputChannels", 1))
        rate = int(loopback_info.get("defaultSampleRate", 48000))
        loopback_channels = int(loopback_info.get("maxInputChannels", 2))
        
        # Callbacks to buffer in memory
        def mic_callback(in_data, frame_count, time_info, status):
            self.mic_level = self.calculate_rms(in_data)
            if self.is_recording:
                self.mic_buffer.extend(in_data)
            return (None, pyaudio.paContinue)
            
        def loopback_callback(in_data, frame_count, time_info, status):
            self.loopback_level = self.calculate_rms(in_data)
            if self.is_recording:
                self.loopback_buffer.extend(in_data)
            return (None, pyaudio.paContinue)
            
        self.mic_stream = self.p.open(
            format=pyaudio.paInt16,
            channels=mic_channels,
            rate=rate,
            input=True,
            input_device_index=mic_info["index"],
            stream_callback=mic_callback
        )
        
        self.loopback_stream = self.p.open(
            format=pyaudio.paInt16,
            channels=loopback_channels,
            rate=rate,
            input=True,
            input_device_index=loopback_info["index"],
            stream_callback=loopback_callback
        )
        
        self.mic_stream.start_stream()
        self.loopback_stream.start_stream()
        self.update_meters()

    def stop_recording(self):
        self.is_recording = False
        self.record_button.config(state=tk.DISABLED, text="PROCESSING...", bg="#424242")
        self.status_label.config(text="Status: PROCESSING...", fg="#2196f3")
        self.test_button.config(state=tk.NORMAL)
        
        if self.mic_stream:
            self.mic_stream.stop_stream()
            self.mic_stream.close()
        if self.loopback_stream:
            self.loopback_stream.stop_stream()
            self.loopback_stream.close()
            
        if self.p:
            self.p.terminate()
            self.p = None
            
        # Dispatch processing to the background asyncio event loop
        asyncio.run_coroutine_threadsafe(self.process_audio_async(), self.async_thread.loop)

    def make_stereo_wav(self, mic_buffer, loopback_buffer, mic_channels, loopback_channels, rate):
        if not mic_buffer and not loopback_buffer:
            return b""
            
        # Convert buffers to arrays of 16-bit signed integers
        mic_samples = array.array('h', mic_buffer)
        loop_samples = array.array('h', loopback_buffer)
        
        # Convert mic to mono if stereo
        if mic_channels == 2:
            mono_mic = array.array('h')
            for i in range(0, len(mic_samples), 2):
                if i + 1 < len(mic_samples):
                    mono_mic.append((mic_samples[i] + mic_samples[i+1]) // 2)
                else:
                    mono_mic.append(mic_samples[i])
            mic_samples = mono_mic
            
        # Convert loopback to mono if stereo
        if loopback_channels == 2:
            mono_loop = array.array('h')
            for i in range(0, len(loop_samples), 2):
                if i + 1 < len(loop_samples):
                    mono_loop.append((loop_samples[i] + loop_samples[i+1]) // 2)
                else:
                    mono_loop.append(loop_samples[i])
            loop_samples = mono_loop
            
        # Downsample both arrays to 16,000 Hz
        target_rate = 16000
        if rate != target_rate:
            ratio = rate / target_rate
            
            # Downsample mic
            resampled_mic = array.array('h')
            for i in range(int(len(mic_samples) / ratio)):
                idx = int(i * ratio)
                if idx < len(mic_samples):
                    resampled_mic.append(mic_samples[idx])
            mic_samples = resampled_mic
            
            # Downsample loopback
            resampled_loop = array.array('h')
            for i in range(int(len(loop_samples) / ratio)):
                idx = int(i * ratio)
                if idx < len(loop_samples):
                    resampled_loop.append(loop_samples[idx])
            loop_samples = resampled_loop
            
            rate = target_rate
            
        # Interleave samples as Stereo (Left Channel = Mic, Right Channel = Loopback)
        min_len = min(len(mic_samples), len(loop_samples))
        stereo_samples = array.array('h')
        for i in range(min_len):
            stereo_samples.append(mic_samples[i])   # Left (Mic)
            stereo_samples.append(loop_samples[i])  # Right (Loopback)
            
        # Pad remaining samples with silent samples (0)
        if len(mic_samples) > min_len:
            for i in range(min_len, len(mic_samples)):
                stereo_samples.append(mic_samples[i])
                stereo_samples.append(0)
        elif len(loop_samples) > min_len:
            for i in range(min_len, len(loop_samples)):
                stereo_samples.append(0)
                stereo_samples.append(loop_samples[i])
                
        # Generate WAV bytes
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(2) # Stereo
            wf.setsampwidth(2) # 16-bit PCM
            wf.setframerate(rate)
            wf.writeframes(stereo_samples.tobytes())
            
        return wav_io.getvalue()

    async def process_audio_async(self):
        try:
            api_key = self.api_entry.get().strip()
            system_prompt_raw = self.prompt_text.get("1.0", tk.END).strip()
            interview_context = self.context_text.get("1.0", tk.END).strip()
            system_prompt = f"{system_prompt_raw}\n\nCandidate / Interview Subject Context:\n{interview_context}"
            
            mic_idx = self.mic_combobox.current()
            loopback_idx = self.loopback_combobox.current()
            
            if mic_idx < 0 or loopback_idx < 0:
                self.root.after(0, lambda: messagebox.showerror("Error", "Please select valid audio devices."))
                return
                
            mic_info = self.mic_devices[mic_idx]
            loopback_info = self.loopback_devices[loopback_idx]
            
            rate = int(loopback_info.get("defaultSampleRate", 48000))
            mic_channels = int(mic_info.get("maxInputChannels", 1))
            loopback_channels = int(loopback_info.get("maxInputChannels", 2))
            
            # Mix to stereo bytes (takes ~5ms)
            wav_bytes = self.make_stereo_wav(
                self.mic_buffer, self.loopback_buffer,
                mic_channels, loopback_channels, rate
            )
            
            if not wav_bytes:
                self.root.after(0, lambda: self.update_transcript_ui("No audio captured."))
                self.status_label.config(text="Status: IDLE", fg="#b0b0b0")
                self.root.after(0, self.reset_record_button)
                return
                
            genai.configure(api_key=api_key)
            self.status_label.config(text="Status: STAGE 1: TRANSCRIBING AUDIO...", fg="#9c27b0")
            
            # 1. Run Stage 1: Async Transcription call
            model = genai.GenerativeModel(model_name=DEFAULT_MODEL)
            audio_part = {
                "mime_type": "audio/wav",
                "data": wav_bytes
            }
            
            transcribe_prompt = (
                "Analyze the attached stereo audio file (Channel 1 is candidate's voice, Channel 2 is interviewer's voice). "
                "Provide a clear, verbatim transcript of what was said. Structure it as: "
                "Interviewer: [what they said]\n"
                "Candidate: [what they said]\n"
                "If only one spoke, only list them. Focus on transcribing verbatim."
            )
            
            transcribe_response = await model.generate_content_async([audio_part, transcribe_prompt])
            transcript = transcribe_response.text
            
            # Update GUI with the transcript immediately
            self.root.after(0, lambda: self.update_transcript_ui(transcript))
            
            # 2. Run Stage 2: Parallel Async generation of Fast Hint & Main Hints
            self.status_label.config(text="Status: STAGE 2: PROCESSING RESPONSE...", fg="#00bcd4")
            
            fast_prompt = (
                f"Review this interview transcript:\n{transcript}\n\n"
                "Write a single, highly actionable strategy hint (under 8 words) giving the candidate the key concept or talking point to speak next.\n"
                "If the transcript is empty, silent, or incoherent, output exactly: 'Ask for repetition'"
            )
            
            main_prompt = (
                f"Review this interview transcript:\n{transcript}\n\n"
                f"System Context: {system_prompt}\n\n"
                "Generate a single, direct, professional response that the candidate can read aloud to the interviewer.\n\n"
                "RULES:\n"
                "- Do NOT provide bullet points, lists, options, or tips.\n"
                "- Do NOT use markdown symbols, bold text (**), asterisks, hashes (#), or headers.\n"
                "- Output only the exact text of the single response to be spoken.\n"
                "- Ensure maximum readability for speech.\n"
                "- If the transcript is empty, silent, or incoherent, output exactly: 'I\\'m sorry, the audio cut out slightly. Would you mind repeating that?'"
            )
            
            # Run both async calls in parallel
            task_fast = model.generate_content_async(
                fast_prompt,
                generation_config={
                    "temperature": 1.0,
                    "max_output_tokens": 300,
                    "thinking_config": {
                        "thinking_budget": 0
                    }
                }
            )
            task_main = model.generate_content_async(
                main_prompt,
                generation_config={
                    "temperature": 1.0,
                    "max_output_tokens": 300,
                    "thinking_config": {
                        "thinking_budget": 0
                    }
                }
            )
            
            fast_res, main_res = await asyncio.gather(task_fast, task_main)
            
            # Update UI fields
            self.root.after(0, lambda: self.update_fast_hint_ui(fast_res.text))
            self.root.after(0, lambda: self.update_main_hints_ui(main_res.text))
            
            self.status_label.config(text="Status: READY", fg="#4caf50")
            
        except Exception as e:
            error_msg = f"Error in async processing pipeline:\n{str(e)}"
            self.root.after(0, lambda: self.update_main_hints_ui(error_msg))
            self.status_label.config(text="Status: ERROR", fg="#f44336")
        finally:
            self.root.after(0, self.reset_record_button)

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
        self.transcript_area.insert("1.0", "Verbatim transcript of conversation...")
        self.quick_hint_entry.delete(0, tk.END)
        self.quick_hint_entry.insert(0, "Key strategy hint will display here...")
        self.response_area.delete("1.0", tk.END)
        self.response_area.insert("1.0", "Suggested response will display here...")
        self.status_label.config(text="Status: IDLE", fg="#b0b0b0")

if __name__ == "__main__":
    root = tk.Tk()
    app = InterviewHelperApp(root)
    root.mainloop()
