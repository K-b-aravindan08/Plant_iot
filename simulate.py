"""
simulate.py — Simulates Arduino sensor data for testing WITHOUT hardware.

Run this INSTEAD of serial_reader.py when Arduino is not connected.
It generates realistic sensor readings and pump cycles directly into the DB.

Usage:
  python simulate.py
"""

import time
import math
import random
import logging
from datetime import datetime

from database import init_db, insert_reading, insert_motor_log
from config import SENSOR_INTERVAL_SEC, MOISTURE_LOW, MOISTURE_HIGH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SIM] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Simulation state ─────────────────────────────────────────────
moisture     = 55.0         # start mid-range
pump_on      = False
pump_start   = None
total_pump_ms = 0
tick         = 0

def simulate_dht11(tick):
    """Gentle sine wave for temp and humidity."""
    temp = 26.0 + 3.0 * math.sin(tick / 60) + random.uniform(-0.3, 0.3)
    hum  = 60.0 + 8.0 * math.sin(tick / 90 + 1) + random.uniform(-1, 1)
    return round(temp, 1), round(max(20, min(95, hum)), 0)

def run():
    global moisture, pump_on, pump_start, total_pump_ms, tick

    init_db()
    log.info("Simulator started — inserting readings every %ds", SENSOR_INTERVAL_SEC)
    log.info("Open http://localhost:5000 to see the dashboard")

    while True:
        tick += 1
        ts   = datetime.now().isoformat(timespec="seconds")
        temp, hum = simulate_dht11(tick)

        # Moisture drifts down slowly; pump fills it back up
        if pump_on:
            moisture += 3.0 + random.uniform(0, 1)    # pump raises moisture
        else:
            moisture -= 0.4 + random.uniform(0, 0.3)  # evaporation

        moisture = max(0, min(100, moisture))

        # Pump control (mirrors Arduino logic)
        if not pump_on and moisture < MOISTURE_LOW:
            pump_on    = True
            pump_start = time.time()
            log.info("SIM PUMP ON  (moisture %.0f%%)", moisture)

        elif pump_on and moisture >= MOISTURE_HIGH:
            dur = time.time() - pump_start
            total_pump_ms += int(dur * 1000)
            insert_motor_log(
                (datetime.fromtimestamp(pump_start)).isoformat(timespec="seconds"),
                ts, dur
            )
            pump_on = False
            log.info("SIM PUMP OFF (moisture %.0f%%, ran %.1fs)", moisture, dur)

        current_pump_ms = total_pump_ms
        if pump_on and pump_start:
            current_pump_ms += int((time.time() - pump_start) * 1000)

        insert_reading(ts, temp, hum, int(moisture),
                       1 if pump_on else 0, current_pump_ms)

        log.info("T=%.1f°C  H=%.0f%%  Moisture=%.0f%%  Pump=%s",
                 temp, hum, moisture, "ON" if pump_on else "OFF")

        time.sleep(SENSOR_INTERVAL_SEC)

if __name__ == "__main__":
    run()
