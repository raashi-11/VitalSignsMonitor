"""
Dashboard Flask Routes
Person 2 (CSE Member 2) owns this file

What this does:
- Serves the web dashboard HTML page
- Provides a /vitals API endpoint that the dashboard JS calls every second
- Returns all fused vital sign data as JSON
"""

from flask import render_template, jsonify
import sys
import os
import time

# So we can import from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hardware.esp32_receiver import app as flask_app
import hardware.esp32_receiver as hw_mod


@flask_app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('index.html')


def safe_float(val, default=0.0):
    """Convert any numeric type (including numpy) to plain Python float."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_bool(val, default=False):
    """Convert any bool-like type (including numpy.bool_) to plain Python bool."""
    try:
        return bool(val)
    except (TypeError, ValueError):
        return default


@flask_app.route('/vitals')
def get_vitals():
    """
    Called by dashboard JavaScript every 1 second via fetch().
    Returns all fused vital sign data as JSON.
    """
    # Try reading from the fusion engine (loaded by main.py into sys.modules)
    fusion_mod = sys.modules.get('fusion.fusion_engine')
    if fusion_mod and hasattr(fusion_mod, 'fused_output') and hasattr(fusion_mod, 'fusion_lock'):
        try:
            with fusion_mod.fusion_lock:
                raw = fusion_mod.fused_output.copy()
            # Convert all values to JSON-safe types
            data = {
                "hr_bpm": safe_float(raw.get("hr_bpm")),
                "temperature_c": safe_float(raw.get("temperature_c")),
                "ambient_c": safe_float(raw.get("ambient_c")),
                "snr_rppg": safe_float(raw.get("snr_rppg")),
                "face_detected": safe_bool(raw.get("face_detected")),
                "signal_quality": str(raw.get("signal_quality", "Initialising")),
                "rppg_status": str(raw.get("rppg_status", "Initialising")),
                "hw_status": str(raw.get("hw_status", "Initialising")),
                "system_status": str(raw.get("system_status", "Starting up")),
                "alert_hr_high": safe_bool(raw.get("alert_hr_high")),
                "alert_hr_low": safe_bool(raw.get("alert_hr_low")),
                "alert_temp": safe_bool(raw.get("alert_temp")),
                "timestamp": safe_float(raw.get("timestamp")),
            }
            return jsonify(data)
        except Exception as e:
            print(f"[Dashboard] Fusion read error: {e}")

    # Fallback: read directly from hardware + rppg modules
    try:
        with hw_mod.hw_lock:
            temp = safe_float(hw_mod.hardware_data.get("temperature_c"))
            ambient = safe_float(hw_mod.hardware_data.get("ambient_c"))
        hw_connected = bool(hw_mod.is_hardware_connected())

        hr_bpm = 0.0
        snr_rppg = 0.0
        face_detected = False
        signal_quality = "Initialising"

        rppg_mod = sys.modules.get('rppg.rppg_pipeline')
        if rppg_mod and hasattr(rppg_mod, 'rppg_output'):
            with rppg_mod.rppg_lock:
                hr_bpm = safe_float(rppg_mod.rppg_output.get("hr_bpm"))
                snr_rppg = safe_float(rppg_mod.rppg_output.get("snr"))
                face_detected = safe_bool(rppg_mod.rppg_output.get("face_detected"))
                signal_quality = str(rppg_mod.rppg_output.get("signal_quality", "Initialising"))

        hw_status = "OK -- MLX90614 active" if hw_connected else "Offline -- check ESP32"

        return jsonify({
            "hr_bpm": round(hr_bpm, 1),
            "temperature_c": round(temp, 1),
            "ambient_c": round(ambient, 1),
            "snr_rppg": round(snr_rppg, 2),
            "face_detected": face_detected,
            "signal_quality": signal_quality,
            "rppg_status": "OK" if face_detected else "Initialising",
            "hw_status": hw_status,
            "system_status": "Running" if hw_connected else "Temperature sensor offline",
            "alert_hr_high": hr_bpm > 120,
            "alert_hr_low": 0 < hr_bpm < 45,
            "alert_temp": temp > 38.5,
            "timestamp": time.time()
        })
    except Exception as e:
        print(f"[Dashboard] Error reading vitals: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "hr_bpm": 0.0, "temperature_c": 0.0, "ambient_c": 0.0, "snr_rppg": 0.0,
            "face_detected": False, "signal_quality": "Error",
            "rppg_status": "Error", "hw_status": "Error",
            "system_status": "Error",
            "alert_hr_high": False, "alert_hr_low": False, "alert_temp": False,
            "timestamp": 0.0
        })