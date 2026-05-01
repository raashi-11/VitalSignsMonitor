"""
Adaptive Confidence-Weighted Fusion Engine
Person 3 (CSE Member 3) owns this file

What this does:
- Every 1 second reads rPPG output (HR + SNR)
- Every 1 second reads hardware output (HR + SNR)
- Computes adaptive weights based on SNR of each stream
- Produces fused HR output
- Handles graceful degradation when one sensor fails
- Logs all data to CSV
"""

import time
import csv
import os
import threading
from datetime import datetime

# Thresholds
SNR_THRESHOLD       = 1.0   # below this = sensor considered unreliable
DEGRADED_COUNT_LIMIT = 3    # consecutive cycles below threshold before flagging
HW_TIMEOUT_SECONDS  = 6.0  # if no ESP32 data for 6s, flag hardware as offline

# CSV log path
LOG_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'vitals_log.csv')
CSV_HEADERS = [
    'timestamp', 'datetime',
    'hr_rppg', 'snr_rppg',
    'hr_hw', 'snr_hw',
    'w_rppg', 'w_hw',
    'hr_fused', 'temperature_c', 'spo2_percent',
    'rppg_status', 'hw_status', 'system_status'
]

# ── Shared fused output (read by dashboard) ──────────────────────
fused_output = {
    "hr_fused":      0.0,
    "temperature_c": 0.0,
    "spo2_percent":  0.0,
    "w_rppg":        0.5,
    "w_hw":          0.5,
    "hr_rppg":       0.0,
    "hr_hw":         0.0,
    "snr_rppg":      0.0,
    "snr_hw":        0.0,
    "rppg_status":   "Initialising",
    "hw_status":     "Initialising",
    "system_status": "Starting up",
    "alert_hr_high": False,
    "alert_hr_low":  False,
    "alert_temp":    False,
    "alert_spo2":    False,
    "timestamp":     0
}
fusion_lock = threading.Lock()


def init_csv():
    """Create CSV file with headers if it doesn't exist."""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
        print(f"[Fusion] Log file created: {LOG_PATH}")


def log_to_csv(row: dict):
    """Append one row of fused data to the CSV log."""
    try:
        with open(LOG_PATH, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow({k: row.get(k, '') for k in CSV_HEADERS})
    except Exception as e:
        print(f"[Fusion] CSV write error: {e}")


def compute_fusion(hr_rppg, snr_rppg, hr_hw, snr_hw):
    """
    Compute adaptive confidence-weighted fusion.

    Formula:
        w_rppg = SNR_rppg / (SNR_rppg + SNR_hw)
        w_hw   = 1 - w_rppg
        HR_fused = (w_rppg * HR_rppg) + (w_hw * HR_hw)

    Returns: (hr_fused, w_rppg, w_hw)
    """
    total_snr = snr_rppg + snr_hw

    if total_snr == 0:
        # Both sensors unavailable — return 0 with equal weights
        return 0.0, 0.5, 0.5

    w_rppg = snr_rppg / total_snr
    w_hw   = 1.0 - w_rppg

    hr_fused = (w_rppg * hr_rppg) + (w_hw * hr_hw)
    return round(hr_fused, 1), round(w_rppg, 3), round(w_hw, 3)


def check_alerts(hr_fused, temperature_c, spo2_percent):
    """Check clinical thresholds and return alert flags."""
    return {
        "alert_hr_high": hr_fused > 120,
        "alert_hr_low":  0 < hr_fused < 45,
        "alert_temp":    temperature_c > 38.5,
        "alert_spo2":    0 < spo2_percent < 90
    }


def run_fusion_engine(rppg_module, hardware_module):
    """
    Main fusion loop. Runs every 1 second.

    Args:
        rppg_module:     the rppg.rppg_pipeline module (for rppg_output dict)
        hardware_module: the hardware.esp32_receiver module (for hardware_data dict)
    """
    global fused_output

    init_csv()
    print("[Fusion] Engine started. Running every 1 second...")

    # Counters for graceful degradation
    rppg_bad_count = 0
    hw_bad_count   = 0

    while True:
        cycle_start = time.time()

        # ── Read rPPG output ──────────────────────────────────────
        with rppg_module.rppg_lock:
            hr_rppg  = rppg_module.rppg_output["hr_bpm"]
            snr_rppg = rppg_module.rppg_output["snr"]
            face_ok  = rppg_module.rppg_output["face_detected"]

        # ── Read hardware output ──────────────────────────────────
        with hardware_module.hw_lock:
            hr_hw    = hardware_module.hardware_data["hw_hr_bpm"]
            snr_hw   = hardware_module.hardware_data["hw_snr"]
            temp     = hardware_module.hardware_data["temperature_c"]
            spo2     = hardware_module.hardware_data["spo2_percent"]
        hw_connected = hardware_module.is_hardware_connected()

        # ── Graceful degradation logic ────────────────────────────
        rppg_status = "OK"
        hw_status   = "OK"

        # rPPG degradation check
        if snr_rppg < SNR_THRESHOLD or not face_ok:
            rppg_bad_count += 1
        else:
            rppg_bad_count = 0

        if rppg_bad_count >= DEGRADED_COUNT_LIMIT:
            snr_rppg   = 0.0
            rppg_status = "Degraded — face not detected or poor lighting"

        # Hardware degradation check
        if not hw_connected:
            hw_bad_count += 1
        else:
            hw_bad_count = 0

        if hw_bad_count >= DEGRADED_COUNT_LIMIT:
            snr_hw   = 0.0
            hw_status = "Degraded — ESP32 not sending data"

        # ── Compute fused output ──────────────────────────────────
        hr_fused, w_rppg, w_hw = compute_fusion(hr_rppg, snr_rppg, hr_hw, snr_hw)

        # System status label
        if snr_rppg == 0 and snr_hw == 0:
            system_status = "Both sensors unavailable — check setup"
        elif snr_rppg == 0:
            system_status = "Hardware only — rPPG unavailable"
        elif snr_hw == 0:
            system_status = "rPPG only — hardware offline"
        else:
            system_status = "All sensors active"

        # ── Check alerts ──────────────────────────────────────────
        alerts = check_alerts(hr_fused, temp, spo2)

        # ── Update shared fused output ────────────────────────────
        now = time.time()
        with fusion_lock:
            fused_output.update({
                "hr_fused":      hr_fused,
                "temperature_c": round(temp, 1),
                "spo2_percent":  round(spo2, 1),
                "w_rppg":        w_rppg,
                "w_hw":          w_hw,
                "hr_rppg":       round(hr_rppg, 1),
                "hr_hw":         round(hr_hw, 1),
                "snr_rppg":      round(snr_rppg, 2),
                "snr_hw":        round(snr_hw, 2),
                "rppg_status":   rppg_status,
                "hw_status":     hw_status,
                "system_status": system_status,
                "timestamp":     now,
                **alerts
            })

        # ── Log to CSV ────────────────────────────────────────────
        log_to_csv({
            "timestamp":     now,
            "datetime":      datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S'),
            "hr_rppg":       hr_rppg,
            "snr_rppg":      snr_rppg,
            "hr_hw":         hr_hw,
            "snr_hw":        snr_hw,
            "w_rppg":        w_rppg,
            "w_hw":          w_hw,
            "hr_fused":      hr_fused,
            "temperature_c": temp,
            "spo2_percent":  spo2,
            "rppg_status":   rppg_status,
            "hw_status":     hw_status,
            "system_status": system_status
        })

        # Print summary every cycle
        print(f"[Fusion] HR: {hr_fused} bpm | Temp: {temp}°C | SpO2: {spo2}% | "
              f"Weights: rPPG={w_rppg:.0%} HW={w_hw:.0%} | {system_status}")

        # Sleep to maintain 1-second cycle
        elapsed = time.time() - cycle_start
        sleep_time = max(0, 1.0 - elapsed)
        time.sleep(sleep_time)