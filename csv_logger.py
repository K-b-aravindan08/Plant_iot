"""
csv_logger.py — Writes one CSV row per minute into a daily log file.

File naming : Plant_IoT_DDMMYYYY.csv
Location    : logs/csv/
Headers     : Date,Time,Temperature_C,Humidity_pct,Moisture_pct,
              Motor_Status,Amt_Water_Pumped_ml,Time_Operated_s,
              Operational_Mode,Connection_Status
"""

import os
import csv
import time
import logging
from datetime import datetime

from config import CSV_LOG_DIR, CSV_LOG_INTERVAL_SEC, CSV_HEADERS, PUMP_ML_PER_SEC
from database import get_latest, get_today_motor_stats

log = logging.getLogger(__name__)


def get_csv_path(dt: datetime) -> str:
    fname = dt.strftime("Plant_IoT_%d%m%Y.csv")
    return os.path.join(CSV_LOG_DIR, fname)


def ensure_header(path: str):
    """Write CSV header if file is new/empty."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)
        log.info("Created CSV log: %s", path)


def write_csv_row():
    """Read latest sensor data and append one row to today's CSV."""
    now  = datetime.now()
    path = get_csv_path(now)

    os.makedirs(CSV_LOG_DIR, exist_ok=True)
    ensure_header(path)

    latest = get_latest(1)
    if not latest:
        log.warning("No sensor data yet — skipping CSV row")
        return

    d      = latest[0]
    stats  = get_today_motor_stats()

    pump_on    = bool(d.get("pump_state", 0))
    motor_str  = "ON" if pump_on else "OFF"
    total_s    = stats.get("total_s", 0) or 0
    water_ml   = round(total_s * PUMP_ML_PER_SEC)
    conn_stat  = d.get("connection_status", "online")
    op_mode    = d.get("operational_mode", "auto")

    row = [
        now.strftime("%Y-%m-%d"),        # Date
        now.strftime("%H:%M:%S"),        # Time
        d.get("temperature", ""),        # Temperature_C
        d.get("humidity", ""),           # Humidity_pct
        d.get("moisture", ""),           # Moisture_pct
        motor_str,                       # Motor_Status
        water_ml,                        # Amt_Water_Pumped_ml
        round(total_s, 1),              # Time_Operated_s
        op_mode,                         # Operational_Mode
        conn_stat,                       # Connection_Status
    ]

    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)

    log.info("CSV row written → %s | T=%.1f H=%.0f M=%d Pump=%s",
             os.path.basename(path),
             d.get("temperature", 0), d.get("humidity", 0),
             d.get("moisture", 0), motor_str)


def run():
    log.info("CSV logger started — writing every %ds", CSV_LOG_INTERVAL_SEC)
    while True:
        try:
            write_csv_row()
        except Exception as exc:
            log.error("CSV write error: %s", exc)
        time.sleep(CSV_LOG_INTERVAL_SEC)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [CSV] %(message)s")
    run()