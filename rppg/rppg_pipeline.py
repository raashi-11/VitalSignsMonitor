"""
rPPG Pipeline — Heart Rate Detection from Webcam
Person 1 (CSE Member 1) owns this file

What this does:
- Opens webcam
- Detects face using OpenCV
- Extracts forehead region (top 30% of face)
- Reads green channel values per frame
- After 30 seconds of data: filters signal, runs FFT, extracts HR
- Calculates SNR (confidence score)
- Runs continuously, updating HR every second
"""

import cv2
import numpy as np
from scipy.signal import butter, filtfilt
from collections import deque
import time
import threading


# ── Configuration ──────────────────────────────────────────────
WEBCAM_INDEX   = 0          # 0 = built-in webcam, 1 = external
FPS            = 30         # frames per second
BUFFER_SECONDS = 30         # seconds of signal to buffer
BUFFER_SIZE    = FPS * BUFFER_SECONDS  # 900 samples
LOW_HZ         = 0.7        # 42 bpm — minimum possible heart rate
HIGH_HZ        = 3.5        # 210 bpm — maximum possible heart rate
MIN_SNR        = 1.0        # below this SNR, signal is considered unreliable


# ── Shared output (read by fusion engine) ───────────────────────
rppg_output = {
    "hr_bpm": 0,
    "snr": 0.0,
    "confidence": 0.0,   # 0.0 to 10.0
    "face_detected": False,
    "signal_quality": "No signal",
    "timestamp": 0
}
rppg_lock = threading.Lock()


def butter_bandpass(lowcut, highcut, fs, order=4):
    """Design a Butterworth bandpass filter."""
    nyq = 0.5 * fs
    low = lowcut / nyq
    high = highcut / nyq
    b, a = butter(order, [low, high], btype='band')
    return b, a


def apply_bandpass_filter(signal, lowcut=LOW_HZ, highcut=HIGH_HZ, fs=FPS):
    """Apply zero-phase bandpass filter to signal."""
    b, a = butter_bandpass(lowcut, highcut, fs)
    return filtfilt(b, a, signal)


def compute_hr_and_snr(signal, fs=FPS):
    """
    Run FFT on signal, find dominant frequency, compute HR and SNR.
    Returns: (heart_rate_bpm, snr_score_0_to_10)
    """
    # FFT
    n = len(signal)
    freqs = np.fft.rfftfreq(n, d=1.0/fs)
    fft_vals = np.abs(np.fft.rfft(signal))

    # Only look at physiological frequency range
    valid_mask = (freqs >= LOW_HZ) & (freqs <= HIGH_HZ)
    valid_freqs = freqs[valid_mask]
    valid_fft   = fft_vals[valid_mask]

    if len(valid_fft) == 0:
        return 0, 0.0

    # Find peak
    peak_idx  = np.argmax(valid_fft)
    peak_freq = valid_freqs[peak_idx]
    peak_power = valid_fft[peak_idx]

    # SNR = peak power / mean of all other bins
    other_bins = np.delete(valid_fft, peak_idx)
    mean_noise = np.mean(other_bins) if len(other_bins) > 0 else 1e-6
    raw_snr    = peak_power / (mean_noise + 1e-6)

    # Normalise SNR to 0–10 scale
    snr_normalised = min(raw_snr / 5.0, 10.0)

    heart_rate = peak_freq * 60.0
    return round(heart_rate, 1), round(snr_normalised, 2)


def get_signal_quality_label(snr):
    if snr >= 7.0:
        return "Excellent"
    elif snr >= 5.0:
        return "Good"
    elif snr >= 3.0:
        return "Fair"
    elif snr >= MIN_SNR:
        return "Poor"
    else:
        return "Unreliable"


def run_rppg(show_window=True):
    """
    Main rPPG loop. Call this to start the pipeline.
    Set show_window=False when running as part of main.py
    """
    global rppg_output

    cap = cv2.VideoCapture(WEBCAM_INDEX)
    cap.set(cv2.CAP_PROP_FPS, FPS)

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )

    # Rolling buffer for green channel values
    green_buffer = deque(maxlen=BUFFER_SIZE)

    # For display overlay
    current_hr  = 0
    current_snr = 0.0
    current_quality = "Collecting data..."

    print("[rPPG] Pipeline started. Opening webcam...")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[rPPG] Cannot read from webcam. Check connection.")
            break

        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80)
        )

        face_found = len(faces) > 0

        if face_found:
            # Use the largest detected face
            faces = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)
            x, y, w, h = faces[0]

            # Forehead ROI: top 30% height, middle 60% width
            roi_x1 = x + int(w * 0.20)
            roi_x2 = x + int(w * 0.80)
            roi_y1 = y
            roi_y2 = y + int(h * 0.30)

            forehead = frame[roi_y1:roi_y2, roi_x1:roi_x2]

            if forehead.size > 0:
                # Extract mean green channel value
                mean_green = np.mean(forehead[:, :, 1])  # index 1 = green in BGR
                green_buffer.append(mean_green)

                # Compute HR once buffer is full
                if len(green_buffer) == BUFFER_SIZE:
                    signal = np.array(green_buffer, dtype=np.float64)

                    # Normalise
                    signal = (signal - np.mean(signal)) / (np.std(signal) + 1e-6)

                    # Filter
                    filtered = apply_bandpass_filter(signal)

                    # HR + SNR
                    hr, snr = compute_hr_and_snr(filtered)
                    current_hr      = hr
                    current_snr     = snr
                    current_quality = get_signal_quality_label(snr)

                    # Update shared output
                    with rppg_lock:
                        rppg_output["hr_bpm"]         = hr
                        rppg_output["snr"]            = snr
                        rppg_output["confidence"]     = snr
                        rppg_output["face_detected"]  = True
                        rppg_output["signal_quality"] = current_quality
                        rppg_output["timestamp"]      = time.time()

            if show_window:
                # Draw face box (blue)
                cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)
                # Draw forehead ROI (green)
                cv2.rectangle(frame, (roi_x1, roi_y1), (roi_x2, roi_y2), (0, 255, 0), 2)
                cv2.putText(frame, 'Forehead ROI', (roi_x1, roi_y1 - 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        else:
            with rppg_lock:
                rppg_output["face_detected"]  = False
                rppg_output["signal_quality"] = "No face detected"

        if show_window:
            # Overlay HR info on frame
            status_color = (0, 200, 0) if face_found else (0, 0, 255)
            buffer_pct = int((len(green_buffer) / BUFFER_SIZE) * 100)

            cv2.putText(frame, f'HR: {current_hr} bpm',
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, status_color, 2)
            cv2.putText(frame, f'SNR: {current_snr:.1f}/10  Quality: {current_quality}',
                        (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.55, status_color, 1)
            cv2.putText(frame, f'Buffer: {buffer_pct}% ({len(green_buffer)}/{BUFFER_SIZE} samples)',
                        (10, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
            cv2.putText(frame, 'Press Q to quit',
                        (10, frame.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 150), 1)

            cv2.imshow('rPPG - Vital Signs Monitor', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    if show_window:
        cv2.destroyAllWindows()
    print("[rPPG] Pipeline stopped.")


# Run directly to test this file alone
if __name__ == "__main__":
    print("Running rPPG pipeline standalone test...")
    print("Sit in front of webcam. Keep face still. Good lighting.")
    print("HR will appear after 30 seconds of data collection.")
    run_rppg(show_window=True)