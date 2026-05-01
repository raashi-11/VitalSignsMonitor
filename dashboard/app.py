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

# So we can import from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hardware.esp32_receiver import app as flask_app


@flask_app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('index.html')


@flask_app.route('/vitals')
def get_vitals():
    """
    Called by dashboard JavaScript every 1 second via fetch().
    Returns all fused vital sign data as JSON.
    """
    try:
        from fusion.fusion_engine import fused_output, fusion_lock
        import threading
        with fusion_lock:
            data = fused_output.copy()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "hr_fused": 0, "temperature_c": 0,
                        "spo2_percent": 0, "system_status": "Error"})