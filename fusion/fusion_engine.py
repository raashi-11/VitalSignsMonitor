"""
Fusion Engine — simplified for single hardware sensor (MLX90614 only).
HR comes entirely from rPPG webcam stream.
Temperature comes from MLX90614 via ESP32.
"""

import time
import csv
import os
import threading
from datetime import datetime

SNR_THRESHOLD        = 1.0
DEGRADED_COUNT_LIMIT = 3
HW_TIMEOUT_SECONDS   = 6.0

LOG_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'vitals_log.csv')
CSV_HEADERS = [
    'timestamp', 'datetime',
    'hr_bpm', 'snr_rppg',
    'temperature_c', 'ambient_c',
    'rppg_status', 'hw_status', 'system_status'
]

fused_output = {
    "hr_bpm":        0.0,
    "temperature_c": 0.0,
    "ambient_c":     0.0,
    "snr_rppg":      0.0,
    "face_detected": False,
    "signal_quality": "Initialising",
    "rppg_status":   "Initialising",
    "hw_status":     "Initialising",
    "system_status": "Starting up",
    "alert_hr_high": False,
    "alert_hr_low":  False,
    "alert_temp":    False,
    "timestamp":     0
}
fusion_lock = threading.Lock()


def init_csv():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'w', newline='') as f:
            csv.DictWriter(f, fieldnames=CSV_HEADERS).writeheader()
        print(f"[Fusion] Log file created: {LOG_PATH}")


def log_to_csv(row: dict):
    try:
        with open(LOG_PATH, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow({k: row.get(k, '') for k in CSV_HEADERS})
    except Exception as e:
        print(f"[Fusion] CSV write error: {e}")


def check_alerts(hr_bpm, temperature_c):
    return {
        "alert_hr_high": hr_bpm > 120,
        "alert_hr_low":  0 < hr_bpm < 45,
        "alert_temp":    temperature_c > 38.5
    }


def run_fusion_engine(rppg_module, hardware_module):
    global fused_output
    init_csv()
    print("[Fusion] Engine started.")

    rppg_bad_count = 0

    while True:
        cycle_start = time.time()

        # Read rPPG
        with rppg_module.rppg_lock:
            hr_bpm       = rppg_module.rppg_output["hr_bpm"]
            snr_rppg     = rppg_module.rppg_output["snr"]
            face_ok      = rppg_module.rppg_output["face_detected"]
            sig_quality  = rppg_module.rppg_output["signal_quality"]

        # Read hardware (temperature only)
        with hardware_module.hw_lock:
            temp     = hardware_module.hardware_data["temperature_c"]
            ambient  = hardware_module.hardware_data["ambient_c"]
        hw_connected = hardware_module.is_hardware_connected()

        # rPPG status
        rppg_status = "OK"
        if snr_rppg < SNR_THRESHOLD or not face_ok:
            rppg_bad_count += 1
        else:
            rppg_bad_count = 0
        if rppg_bad_count >= DEGRADED_COUNT_LIMIT:
            rppg_status = "Degraded — no face or poor lighting"

        # Hardware status
        hw_status = "OK — MLX90614 active" if hw_connected else "Offline — check ESP32"

        # System status
        if not hw_connected and rppg_bad_count >= DEGRADED_COUNT_LIMIT:
            system_status = "Both sensors degraded"
        elif not hw_connected:
            system_status = "Temperature sensor offline — HR only"
        elif rppg_bad_count >= DEGRADED_COUNT_LIMIT:
            system_status = "rPPG degraded — point camera at face"
        else:
            system_status = "All sensors active"

        alerts = check_alerts(hr_bpm, temp)
        now = time.time()

        with fusion_lock:
            fused_output.update({
                "hr_bpm":        round(hr_bpm, 1),
                "temperature_c": round(temp, 1),
                "ambient_c":     round(ambient, 1),
                "snr_rppg":      round(snr_rppg, 2),
                "face_detected": face_ok,
                "signal_quality": sig_quality,
                "rppg_status":   rppg_status,
                "hw_status":     hw_status,
                "system_status": system_status,
                "timestamp":     now,
                **alerts
            })

        log_to_csv({
            "timestamp":     now,
            "datetime":      datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S'),
            "hr_bpm":        hr_bpm,
            "snr_rppg":      snr_rppg,
            "temperature_c": temp,
            "ambient_c":     ambient,
            "rppg_status":   rppg_status,
            "hw_status":     hw_status,
            "system_status": system_status
        })

        print(f"[Fusion] HR: {hr_bpm} bpm | Temp: {temp}°C | {system_status}")

        elapsed = time.time() - cycle_start
        time.sleep(max(0, 1.0 - elapsed))