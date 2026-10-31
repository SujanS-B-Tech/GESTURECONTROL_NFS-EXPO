# GESTUREDRIVE X 🏎️💨
### AI-Powered Touchless Control System for Need for Speed Heat
*Engineered for Windows 10/11 64-bit on ASUS TUF A15 (NVIDIA RTX 3050)*

---

## 1. Project Overview

**GESTUREDRIVE X** is a high-performance Windows desktop application that enables you to control your original **Need for Speed Heat** game installed through Steam using **only your webcam and real-time hand gestures**. 

There is **zero keyboard emulation**, no physical steering wheels, and no physical controllers required. The application uses Google MediaPipe Hand Landmarker to track 21 3D landmarks per hand at 30–60 FPS, computes steering wheel rotation and finger curl/extension geometry, and streams actual hardware-level **Xbox 360 XInput** signals to Windows via the **ViGEmBus** virtual controller bus driver.

---

## 2. Intuitive Gesture Control Mapping Reference

| Vehicle Function | Natural Steering Action | Mapped Xbox 360 Input | How It Works In-Game |
| :--- | :--- | :--- | :--- |
| **Drive Forward & Steer** | **Hands Gripped (Wheel Grip)** ✊ ✊ | **RT (Gas) + Left Stick X** | Gripping the virtual steering wheel drives forward automatically with full steering authority. Turning into corners is smooth and continuous with zero accidental drift stalls! |
| **Stop & Reverse** | **Both Palms Open** ✋ ✋ | **LT (Brake / Reverse) + Left Stick X** | Opening both palms flat brakes the car to a stop and engages Reverse. You can steer left/right while reversing! |
| **Nitrous Boost** | **Deliberate Thumbs Up (Straight Up)** 👍 | **Button A** | Point your thumb straight up in the air away from the fist to fire Nitrous (strict thumb protrusion filter prevents accidental triggers while driving). |
| **In-Game Overlay HUD** | **Press F10 or Click HUD Button** | **Floating PiP Window** | Floats a live mini-webcam and telemetry HUD over Need for Speed Heat without stealing game focus! Drag anywhere on your screen. |
| **Recenter Wheel** | **Press C Key or Click Button** | **Zero Calibrate** | Instantly sets your current natural arm rest angle as dead center (0.0°). |
| **Steering Sensitivity** | **Press S Key or Click Button** | **Cycle 0.8x / 1.0x / 1.2x / 1.4x** | Switch live between Smooth, Normal, Sport, and Ultra steering weights on the fly! |
| **Emergency Stop** | **UI Button or F12 Hotkey** | **Neutral Reset** | Immediately zeros all axes, brakes, and triggers. |

---

## 3. Technology Stack & Architecture

- **Computer Vision:** OpenCV + MediaPipe Hand Landmarker Task (TensorFlow Lite XNNPACK delegate).
- **Virtual Controller:** `vgamepad` + Nefarius `ViGEmBus` kernel driver.
- **Desktop GUI:** `PySide6` (Qt 6) with dark racing dashboard aesthetics, live 60 Hz HUD gauges, and real-time telemetry.
- **Process Watchdog:** `psutil` monitors `NeedForSpeedHeat.exe` status automatically.

### Modular Codebase Structure:
```
GESTURECONTROL-NFS/
├── main.py                     # Master application entrypoint
├── run_gesturedrive.bat        # One-click Windows desktop launcher
├── install_driver.bat          # Elevated ViGEmBus installer
├── requirements.txt            # Python dependencies
├── pytest.ini                  # Pytest configuration
├── config/
│   ├── settings.json           # Camera, deadzone, and sensitivity configuration
│   ├── gestures.json           # Gesture threshold mapping definitions
│   └── calibration.json        # User-calibrated physical neutral and lock angles
├── src/
│   ├── app.py                  # PySide6 application runtime
│   ├── camera/
│   │   ├── webcam.py           # Threaded capture with dropped stale frame queue
│   │   └── hand_tracker.py     # 21-point two-hand landmarker & HUD renderer
│   ├── gestures/
│   │   ├── steering.py         # Two-hand virtual steering math & curves
│   │   ├── recognizer.py       # 3D landmark gesture classifier & analog depths
│   │   └── calibration.py      # Guided calibration wizard profile manager
│   ├── controller/
│   │   ├── virtual_xbox.py     # Hardware XInput gamepad abstraction
│   │   ├── input_mapper.py     # Gesture-to-gamepad dispatcher & cooldowns
│   │   └── safety.py           # Tracking loss watchdog & frozen frame protection
│   ├── ui/
│   │   ├── main_window.py      # Central racing desktop interface
│   │   ├── dashboard.py        # Rotating steering wheel gauge & telemetry bars
│   │   ├── calibration_ui.py   # Guided multi-step calibration wizard
│   │   ├── controller_test_ui.py # Standalone controller visualizer & monitor
│   │   └── settings.py         # Runtime parameters dialog
│   └── utils/
│       ├── logger.py           # Centralized rotating file & console logger
│       └── performance.py      # FPS and loop latency monitors
└── tests/
    ├── test_steering.py        # Steering math, deadzone & decay tests
    ├── test_gestures.py        # Fist, palm, thumbs up, and handbrake tests
    ├── test_input_mapping.py   # Analog trigger & button pulse tests
    └── test_safety.py          # Watchdog & emergency stop tests
```

---

## 4. Setup and Installation

### Step 1: Install ViGEmBus Virtual Gamepad Driver (Required Once)
To enable Windows and Steam to recognize the virtual Xbox 360 controller:
1. Right-click `install_driver.bat` and select **"Run as administrator"**.
2. Click **"Yes"** on the Windows UAC elevation prompt and complete the setup wizard.
3. Once finished, Windows will have the Nefarius Virtual Gamepad Emulation Bus active.

### Step 2: Environment Setup (Automatic or Manual)
If running for the first time or if the virtual environment needs rebuilding:
- Double-click [`setup.bat`](file:///d:/PROJECTS/Projects/GESTURECONTROL-NFS/setup.bat) to automatically create the Python 3.12 virtual environment and install all dependencies.

### Step 3: Launch GESTUREDRIVE X
Double-click [`run_gesturedrive.bat`](file:///d:/PROJECTS/Projects/GESTURECONTROL-NFS/run_gesturedrive.bat) (which also automatically detects and triggers setup if `.venv` is missing) or run in terminal:
```bash
.\.venv\Scripts\python.exe main.py
```

---

## 5. Pre-Game Verification (Controller Monitor Mode)

Before launching Need for Speed Heat, you can verify every input independently:
1. Click **"CONTROLLER MONITOR"** in the top navigation bar.
2. An interactive 2D Xbox 360 gamepad diagram will appear.
3. Test your gestures:
   - Rotate hands: observe the **Left Stick X** moving smoothly left and right.
   - Clench fists / grip wheel: observe **RT (Throttle)** filling up to 255.
   - Open palms flat: observe **LT (Brake / Reverse)** filling up.
   - Thumbs up: observe **Button A** illuminate in green.
4. Once verified, close the monitor.

---

## 6. Guided Calibration Wizard

Every player has a slightly different natural arm rest position and camera angle:
1. Click **"CALIBRATE WIZARD"** on the main dashboard.
2. **Step 1:** Hold hands in your neutral rest position (at 9 and 3 o'clock). Click *Record Sample*.
3. **Step 2:** Turn the wheel to your maximum left lock. Click *Record Sample*.
4. **Step 3:** Turn the wheel to your maximum right lock. Click *Record Sample*.
5. **Step 4 & 5:** Clench right fist and open left palm to calibrate grip thresholds.
6. **Step 6:** Click *Save & Apply Calibration*.

---

## 7. Playing Need for Speed Heat via Steam

1. Start **GESTUREDRIVE X** and click **"START TRACKING"**.
2. Verify the **VIRTUAL XBOX 360** status badge is **CONNECTED (VIGEMBUS)**.
3. Launch **Need for Speed Heat** from your Steam library.
4. In Steam, ensure **Steam Input** is set to "Default Settings" (do not force disable Xbox controllers).
5. In NFS Heat Settings:
   - **Controls:** Gamepad / Xbox 360 Controller is detected automatically.
   - **Driving Options:** Ensure **Auto Reverse** is set to *Enabled* (Standard NFS Heat setting where holding brake when stopped reverses).
6. Drive with your hands held naturally in front of the webcam!

---

## 8. Safety & Watchdog Features

- **Tracking-Loss Watchdog:** If your hands temporarily leave the camera frame, GESTUREDRIVE X does **not** leave the car stuck turning or accelerating. It smoothly returns the steering to 0.0 and decays throttle/brake to neutral over 250ms.
- **Frozen-Camera Protection:** If the webcam feed freezes or drops, the watchdog zeroes all controller outputs immediately.
- **Emergency Stop:** Press **F12** at any moment or click the prominent hazard button on the dashboard to immediately disengage all virtual controller signals.

---

## 9. Running Automated Diagnostics

Execute the full 16-test suite:
```bash
.\.venv\Scripts\python.exe main.py --test
```
All unit tests cover:
- Steering geometry & deadzone bounds
- Gesture recognition classifications
- Controller input dispatches & pulse cooldowns
- Safety watchdogs & process watchers

---

## 10. Building Standalone Windows Executable (.exe)

To bundle GESTUREDRIVE X into a standalone Windows executable for distribution to machines without Python:
- Run [`build_executable.bat`](file:///d:/PROJECTS/Projects/GESTURECONTROL-NFS/build_executable.bat) or execute:
```bash
.\.venv\Scripts\pyinstaller.exe --noconsole --name="GESTUREDRIVE-X" --icon="assets/icon.ico" --add-data="assets;assets" --add-data="config;config" --collect-all=mediapipe --collect-all=vgamepad --collect-all=PySide6 --clean main.py
```
The compiled self-contained bundle will be located in the `dist/GESTUREDRIVE-X/` folder with driver installers included.

