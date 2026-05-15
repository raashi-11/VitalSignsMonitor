"""
main.py — Entry point for the entire system
Run this file to start everything:
    python main.py

What it starts (all simultaneously using threads):
    1. Flask server (receives ESP32 data + serves dashboard)
    2. rPPG pipeline (webcam heart rate detection)
    3. Fusion engine (combines both streams every 1 second)

Open browser at: http://localhost:5000
"""

import threading
import time
import sys

print("=" * 55)
print("  Smart Non-Contact Vital Signs Monitor")
print("  Starting all systems...")
print("=" * 55)

# ── Import modules ────────────────────────────────────────────
import rppg.rppg_pipeline       as rppg_module
import hardware.esp32_receiver  as hw_module
import fusion.fusion_engine     as fusion_module
from dashboard.app import flask_app


def start_flask():
    """Thread 1: Flask server + dashboard."""
    print("[Main] Starting Flask server on port 5000...")
    flask_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)


def start_rppg():
    """Thread 2: rPPG webcam pipeline (no window when running with main)."""
    print("[Main] Starting rPPG pipeline...")
    time.sleep(2)  # Wait for Flask to start first
    rppg_module.run_rppg(show_window=True)


def start_fusion():
    """Thread 3: Fusion engine."""
    print("[Main] Starting fusion engine...")
    time.sleep(3)  # Wait for rPPG and Flask to initialise
    fusion_module.run_fusion_engine(rppg_module, hw_module)


# ── Launch all threads ────────────────────────────────────────
threads = [
    threading.Thread(target=start_flask,  daemon=True, name="Flask"),
    threading.Thread(target=start_rppg,   daemon=True, name="rPPG"),
    threading.Thread(target=start_fusion, daemon=True, name="Fusion"),
]

for t in threads:
    t.start()

print()
print("[OK] All systems running!")
print()
print("[Dashboard] Open: http://localhost:5000")
print("[rPPG] Window: will open automatically")
print("[ESP32] Endpoint: http://[your-laptop-ip]:5000/sensor_data")
print()
print("Press Ctrl+C to stop everything.")
print()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n[Main] Shutting down. Goodbye.")
    sys.exit(0)