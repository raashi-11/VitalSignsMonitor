"""
ESP32 Data Receiver — Flask Server
Receives temperature from MLX90614 via ESP32 over WiFi.
MAX30102 removed — sensor damaged.
"""

from flask import Flask, request, jsonify
from datetime import datetime
import threading
import time

app = Flask(
    __name__,
    template_folder='../dashboard/templates'
)

hardware_data = {
    "temperature_c": 0.0,
    "ambient_c":     0.0,
    "sensor_ok":     False,
    "timestamp":     0,
    "connected":     False
}
hw_lock = threading.Lock()
last_received_time = 0


def is_hardware_connected():
    return (time.time() - last_received_time) < 6.0


@app.route('/sensor_data', methods=['POST'])
def receive_sensor_data():
    global last_received_time
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"status": "error", "message": "No JSON"}), 400

        last_received_time = time.time()

        with hw_lock:
            hardware_data["temperature_c"] = float(data.get("temperature_c", 0))
            hardware_data["ambient_c"]     = float(data.get("ambient_c", 0))
            hardware_data["sensor_ok"]     = bool(data.get("sensor_ok", True))
            hardware_data["timestamp"]     = last_received_time
            hardware_data["connected"]     = True

        print(f"[HW] Temp: {data.get('temperature_c')}°C  |  Ambient: {data.get('ambient_c')}°C")
        return jsonify({"status": "ok"})

    except Exception as e:
        print(f"[HW] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/hardware_status', methods=['GET'])
def get_hardware_status():
    with hw_lock:
        data_copy = hardware_data.copy()
    data_copy["connected"] = is_hardware_connected()
    return jsonify(data_copy)


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "running",
        "hardware_connected": is_hardware_connected(),
        "server_time": datetime.now().isoformat()
    })


def run_flask_server(host='0.0.0.0', port=5000):
    print(f"[HW] Flask server on http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    run_flask_server()