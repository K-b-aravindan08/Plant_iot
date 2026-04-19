"""
serial_reader.py — Reads JSON from Arduino via USB serial, writes to SQLite.

Runs as a long-lived background process.
Auto-reconnects if the Arduino is unplugged and re-plugged.

JSON format from Arduino:
  {"t":27.3,"h":65,"m":42,"p":0,"ms":18000}
  t  = temperature °C
  h  = humidity %
  m  = moisture %
  p  = pump state (0/1)
  ms = cumulative pump run time in milliseconds
"""

import serial
import json
import time
import logging
import os
from datetime import datetime

from config import SERIAL_PORT, SERIAL_BAUD, SERIAL_TIMEOUT
from database import init_db, insert_reading, insert_motor_log

# ─── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SERIAL] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Pump state tracking ──────────────────────────────────────────────────────
prev_pump_state = 0
pump_start_ts   = None


def handle_pump_transition(new_state: int, ts: str):
    """Detect pump ON→OFF and OFF→ON transitions, log completed cycles."""
    global prev_pump_state, pump_start_ts

    if new_state == 1 and prev_pump_state == 0:
        pump_start_ts = ts
        log.info("PUMP ON  — watering started at %s", ts)

    elif new_state == 0 and prev_pump_state == 1 and pump_start_ts:
        try:
            t_start = datetime.fromisoformat(pump_start_ts)
            t_stop  = datetime.fromisoformat(ts)
            dur     = (t_stop - t_start).total_seconds()
            insert_motor_log(pump_start_ts, ts, dur)
            log.info("PUMP OFF — ran for %.1f s (started %s)", dur, pump_start_ts)
        except Exception as exc:
            log.error("Motor log error: %s", exc)
        pump_start_ts = None

    prev_pump_state = new_state


def parse_and_store(line: str):
    """Parse one JSON line from Arduino and persist to DB."""
    line = line.strip()
    if not line or line in ("READY", "OLED_FAIL"):
        if line == "OLED_FAIL":
            log.warning("Arduino reports OLED failure — check wiring!")
        return

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        log.debug("Non-JSON line ignored: %s", line)
        return

    ts      = datetime.now().isoformat(timespec="seconds")
    temp    = float(data.get("t", 0))
    hum     = float(data.get("h", 0))
    moist   = int(data.get("m", 0))
    pump    = int(data.get("p", 0))
    pump_ms = int(data.get("ms", 0))

    insert_reading(ts, temp, hum, moist, pump, pump_ms)
    handle_pump_transition(pump, ts)

    log.info(
        "T=%.1f°C  H=%.0f%%  Moisture=%d%%  Pump=%s",
        temp, hum, moist, "ON" if pump else "OFF"
    )


def run():
    """Main loop — keeps trying to open serial port and read data."""
    init_db()
    log.info("Serial reader starting — port: %s @ %d baud", SERIAL_PORT, SERIAL_BAUD)

    while True:
        try:
            with serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=SERIAL_TIMEOUT) as ser:
                log.info("Connected to %s", SERIAL_PORT)
                ser.reset_input_buffer()

                while True:
                    raw = ser.readline()
                    if not raw:
                        continue                     # timeout — no data
                    line = raw.decode("utf-8", errors="ignore")
                    parse_and_store(line)

        except serial.SerialException as exc:
            log.error("Serial error: %s — retrying in 5 s", exc)
            time.sleep(5)

        except KeyboardInterrupt:
            log.info("Serial reader stopped by user.")
            break

        except Exception as exc:
            log.exception("Unexpected error: %s — retrying in 5 s", exc)
            time.sleep(5)


if __name__ == "__main__":
    run()
