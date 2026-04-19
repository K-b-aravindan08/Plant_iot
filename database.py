"""
database.py — SQLite schema + all query helpers for Plant IoT v2
"""

import sqlite3
import os
import logging
from config import DB_PATH

log = logging.getLogger(__name__)


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS sensor_data (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp        TEXT    NOT NULL,
            temperature      REAL,
            humidity         REAL,
            moisture         INTEGER,
            pump_state       INTEGER DEFAULT 0,
            pump_total_ms    INTEGER DEFAULT 0,
            operational_mode TEXT    DEFAULT 'auto',
            connection_status TEXT   DEFAULT 'online'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS motor_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at  TEXT,
            stopped_at  TEXT,
            duration_s  REAL,
            reason      TEXT DEFAULT 'auto_moisture',
            water_ml    REAL DEFAULT 0
        )
    """)

    # Daily stats reset log
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_reset_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            reset_date  TEXT,
            reset_by    TEXT,
            reset_at    TEXT
        )
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_sensor_ts ON sensor_data (timestamp)")
    conn.commit()
    conn.close()
    log.info("Database initialized: %s", DB_PATH)


# ── Writes ────────────────────────────────────────────────────────────────────

def insert_reading(ts, temp, hum, moist, pump, pump_ms,
                   mode="auto", conn_status="online"):
    conn = get_conn()
    conn.execute(
        """INSERT INTO sensor_data
           (timestamp,temperature,humidity,moisture,pump_state,
            pump_total_ms,operational_mode,connection_status)
           VALUES (?,?,?,?,?,?,?,?)""",
        (ts, temp, hum, moist, pump, pump_ms, mode, conn_status)
    )
    conn.commit()
    conn.close()


def insert_motor_log(started_at, stopped_at, duration_s,
                     reason="auto_moisture", water_ml=0):
    conn = get_conn()
    conn.execute(
        "INSERT INTO motor_log (started_at,stopped_at,duration_s,reason,water_ml) VALUES (?,?,?,?,?)",
        (started_at, stopped_at, duration_s, reason, water_ml)
    )
    conn.commit()
    conn.close()


# ── Reads ─────────────────────────────────────────────────────────────────────

def get_latest(n=1):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM sensor_data ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_history(hours=24):
    conn = get_conn()
    rows = conn.execute(
        """SELECT timestamp,temperature,humidity,moisture,
                  pump_state,pump_total_ms,operational_mode,connection_status
           FROM sensor_data
           WHERE timestamp >= datetime('now', ? || ' hours')
           ORDER BY id ASC""",
        (f"-{hours}",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_history_range(start_dt, end_dt):
    """Return rows between two ISO datetime strings."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT timestamp,temperature,humidity,moisture,
                  pump_state,pump_total_ms,operational_mode,connection_status
           FROM sensor_data
           WHERE timestamp >= ? AND timestamp <= ?
           ORDER BY id ASC""",
        (start_dt, end_dt)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_today_motor_stats():
    """Cycles and total runtime for TODAY only (resets at midnight)."""
    conn = get_conn()
    row = conn.execute(
        """SELECT COUNT(*) AS cycles,
                  COALESCE(SUM(duration_s),0) AS total_s,
                  COALESCE(SUM(water_ml),0)   AS water_ml
           FROM motor_log
           WHERE date(started_at) = date('now')"""
    ).fetchone()
    conn.close()
    return dict(row) if row else {"cycles": 0, "total_s": 0, "water_ml": 0}


def get_motor_stats_range(start_date, end_date):
    conn = get_conn()
    row = conn.execute(
        """SELECT COUNT(*) AS cycles,
                  COALESCE(SUM(duration_s),0) AS total_s,
                  COALESCE(SUM(water_ml),0)   AS water_ml
           FROM motor_log
           WHERE date(started_at) >= ? AND date(started_at) <= ?""",
        (start_date, end_date)
    ).fetchone()
    conn.close()
    return dict(row) if row else {"cycles": 0, "total_s": 0, "water_ml": 0}


def get_motor_log(limit=50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM motor_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_hourly_summary(hours=24):
    conn = get_conn()
    rows = conn.execute(
        """SELECT strftime('%Y-%m-%d %H:00', timestamp) AS hour,
                  ROUND(AVG(temperature),1) AS avg_temp,
                  ROUND(AVG(humidity),1)    AS avg_hum,
                  ROUND(AVG(moisture),0)    AS avg_moist,
                  MAX(pump_state)           AS pump_on
           FROM sensor_data
           WHERE timestamp >= datetime('now', ? || ' hours')
           GROUP BY hour
           ORDER BY hour ASC""",
        (f"-{hours}",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_daily_summary(date_str):
    """date_str: 'YYYY-MM-DD'"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT timestamp,temperature,humidity,moisture,pump_state,pump_total_ms
           FROM sensor_data
           WHERE date(timestamp)=?
           ORDER BY id ASC""",
        (date_str,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monthly_summary(year, month):
    conn = get_conn()
    rows = conn.execute(
        """SELECT strftime('%Y-%m-%d',timestamp) AS day,
                  ROUND(AVG(temperature),1) AS avg_temp,
                  ROUND(AVG(humidity),1)    AS avg_hum,
                  ROUND(AVG(moisture),0)    AS avg_moist,
                  MAX(pump_state)           AS pump_on
           FROM sensor_data
           WHERE strftime('%Y-%m',timestamp)=?
           GROUP BY day ORDER BY day ASC""",
        (f"{year:04d}-{month:02d}",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_yearly_summary(year):
    conn = get_conn()
    rows = conn.execute(
        """SELECT strftime('%Y-%m',timestamp) AS month,
                  ROUND(AVG(temperature),1) AS avg_temp,
                  ROUND(AVG(humidity),1)    AS avg_hum,
                  ROUND(AVG(moisture),0)    AS avg_moist,
                  MAX(pump_state)           AS pump_on
           FROM sensor_data
           WHERE strftime('%Y',timestamp)=?
           GROUP BY month ORDER BY month ASC""",
        (str(year),)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def reset_today_stats(reset_by="admin"):
    """Log a daily reset event (does not delete data)."""
    from datetime import datetime
    conn = get_conn()
    now = datetime.now().isoformat(timespec="seconds")
    today = datetime.now().strftime("%Y-%m-%d")
    conn.execute(
        "INSERT INTO daily_reset_log (reset_date,reset_by,reset_at) VALUES (?,?,?)",
        (today, reset_by, now)
    )
    conn.commit()
    conn.close()
    log.info("Daily stats reset by %s at %s", reset_by, now)


def get_last_reset():
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM daily_reset_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    print("DB ready:", DB_PATH)