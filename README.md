# Smart Non-Contact Vital Signs Monitor

**Non-contact heart rate, temperature and SpO2 monitoring using rPPG + IR sensor fusion**

## Team
- Person 1 (CSE) — rPPG signal processing
- Person 2 (CSE) — Dashboard and visualization
- Person 3 (CSE) — Fusion engine and Flask server
- Person 4 (ECE) — ESP32 hardware integration

## How to run
```bash
pip install -r requirements.txt
python main.py
```
Open browser at http://localhost:5000

## Hardware required
- ESP32 DevKit V1
- MLX90614 IR thermometer
- MAX30102 pulse oximeter
- SSD1306 OLED display