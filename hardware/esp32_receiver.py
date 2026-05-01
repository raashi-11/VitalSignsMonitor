"""
ESP32 Data Receiver — Flask Server
Person 3 (CSE Member 3) owns this file

What this does:
- Runs a Flask server on port 5000
- Waits for JSON data from the ESP32 hardware device
- Stores the latest sensor readings in memory
- Exposes an endpoint the fusion engine reads from
- Can be tested WITHOUT hardware using the test function at the bottom
"""

from flask import Flask, request, jsonify
from datetime import datetime
import threading
import time

app = Flask(__name__)

# ── Shared latest hardware data ─────────────────────────────────
# This gets updated every time ESP32 sends a packet
hardware_data = {
    "temperature_c": 0.0,
    "spo2_percent": 0.0,
    "hw_hr_bpm": 0.0,
    "hw_snr": 0.0,        # quality flag from MAX30102 (0–10)
    "timestamp": 0,
    "connected": False     # True if data received in last 6 seconds
}
hw_lock = threading.Lock()

# Track last received time for connection timeout
last_received_time = 0


def is_hardware_connected():
    """Returns True if ESP32 sent data in the last 6 seconds."""
    return (time.time() - last_received_time) < 6.0


# ── Flask Routes ────────────────────────────────────────────────

@app.route('/sensor_data', methods=['POST'])
def receive_sensor_data():
    """
    ESP32 sends JSON here every 2 seconds.
    Expected format:
    {
        "temperature_c": 36.8,
        "spo2_percent": 98.0,
        "hw_hr_bpm": 74.0,
        "hw_snr": 8.0
    }
    """
    global last_received_time

    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "error", "message": "No JSON received"}), 400

        # Validate required fields
        required = ["temperature_c", "spo2_percent", "hw_hr_bpm"]
        for field in required:
            if field not in data:
                return jsonify({"status": "error", "message": f"Missing: {field}"}), 400

        last_received_time = time.time()

        with hw_lock:
            hardware_data["temperature_c"] = float(data.get("temperature_c", 0))
            hardware_data["spo2_percent"]  = float(data.get("spo2_percent", 0))
            hardware_data["hw_hr_bpm"]     = float(data.get("hw_hr_bpm", 0))
            hardware_data["hw_snr"]        = float(data.get("hw_snr", 8.0))
            hardware_data["timestamp"]     = last_received_time
            hardware_data["connected"]     = True

        print(f"[HW] Received → Temp: {data['temperature_c']}°C | "
              f"SpO2: {data['spo2_percent']}% | HR: {data['hw_hr_bpm']} bpm")

        return jsonify({"status": "ok", "received_at": datetime.now().isoformat()})

    except Exception as e:
        print(f"[HW] Error receiving data: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/hardware_status', methods=['GET'])
def get_hardware_status():
    """Dashboard calls this to get latest hardware readings."""
    with hw_lock:
        data_copy = hardware_data.copy()
    data_copy["connected"] = is_hardware_connected()
    return jsonify(data_copy)


@app.route('/health', methods=['GET'])
def health_check():
    """Simple check to confirm server is running."""
    return jsonify({
        "status": "running",
        "hardware_connected": is_hardware_connected(),
        "server_time": datetime.now().isoformat()
    })


def run_flask_server(host='0.0.0.0', port=5000):
    """Start the Flask server. Called from main.py in a thread."""
    print(f"[HW] Flask server starting on http://{host}:{port}")
    print(f"[HW] ESP32 should POST to: http://[laptop-ip]:{port}/sensor_data")
    app.run(host=host, port=port, debug=False, use_reloader=False)


# ── Test WITHOUT hardware ────────────────────────────────────────
def send_test_data():
    """
    Call this to simulate ESP32 sending data.
    Use this to test before hardware arrives.
    Run this in a separate terminal:
    python -c "from hardware.esp32_receiver import send_test_data; send_test_data()"
    """
    import urllib.request
    import json

    test_payload = json.dumps({
        "temperature_c": 36.8,
        "spo2_percent":  98.0,
        "hw_hr_bpm":     74.0,
        "hw_snr":        8.0
    }).encode('utf-8')

    req = urllib.request.Request(
        'http://localhost:5000/sensor_data',
        data=test_payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req) as response:
            print("Test data sent. Response:", response.read().decode())
    except Exception as e:
        print(f"Error — is the server running? {e}")


if __name__ == "__main__":
    print("Starting Flask server for ESP32 data...")
    print("Open another terminal and run:")
    print("  python -c \"from hardware.esp32_receiver import send_test_data; send_test_data()\"")
    print("to simulate ESP32 sending data without real hardware.")
    run_flask_server()