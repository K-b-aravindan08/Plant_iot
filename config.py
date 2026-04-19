"""
config.py — Centralized configuration for Plant IoT Watering System v2
"""

import os

# ── Serial Port ──────────────────────────────────────────────────────────────
SERIAL_PORT    = os.getenv("SERIAL_PORT", "COM15")
SERIAL_BAUD    = 115200
SERIAL_TIMEOUT = 2

# ── Database ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "data", "plant_iot.db")

# ── Log Directories ───────────────────────────────────────────────────────────
LOG_DIR        = os.path.join(BASE_DIR, "logs")
CSV_LOG_DIR    = os.path.join(BASE_DIR, "logs", "csv")
REPORT_DIR     = os.path.join(BASE_DIR, "logs", "reports")

# ── Log / Report Intervals ────────────────────────────────────────────────────
CSV_LOG_INTERVAL_SEC = 60      # CSV row written every 60 seconds

# ── Flask Web Server ─────────────────────────────────────────────────────────
FLASK_HOST  = "0.0.0.0"
FLASK_PORT  = int(os.getenv("PORT", 5000))   # Render uses PORT env var
FLASK_DEBUG = False

# ── Auth (portal login) ───────────────────────────────────────────────────────
# Override with environment variables in production
PORTAL_USERNAME = os.getenv("PORTAL_USER",     "admin")
PORTAL_PASSWORD = os.getenv("PORTAL_PASSWORD",  "plant2025")
SECRET_KEY      = os.getenv("SECRET_KEY",       "plant-iot-secret-key-change-me")

# ── Plant Thresholds ─────────────────────────────────────────────────────────
MOISTURE_LOW  = 15
MOISTURE_HIGH = 70
TEMP_HIGH     = 38.0

# ── Water Flow Estimate ──────────────────────────────────────────────────────
PUMP_ML_PER_SEC = 30

# ── Sensor Interval ──────────────────────────────────────────────────────────
SENSOR_INTERVAL_SEC = 5

# ── CSV Headers ───────────────────────────────────────────────────────────────
CSV_HEADERS = [
    "Date", "Time", "Temperature_C", "Humidity_pct",
    "Moisture_pct", "Motor_Status", "Amt_Water_Pumped_ml",
    "Time_Operated_s", "Operational_Mode", "Connection_Status"
]