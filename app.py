"""
app.py v2 — Flask web application for Plant IoT Dashboard.

Routes:
  GET  /                    → Dashboard
  GET  /portal              → Auth portal (login page)
  POST /portal/login        → Login handler
  GET  /portal/dashboard    → Authenticated download portal
  GET  /portal/logout       → Logout
  POST /api/portal/download → Download CSV or PDF report
  POST /api/reset/today     → Reset today's stats (admin)
  GET  /api/latest          → Latest sensor reading
  GET  /api/history/<h>     → History (hours)
  GET  /api/stats           → Today's motor stats
  GET  /api/stream          → SSE live feed
  GET  /api/health          → Health check
"""

import os
import io
import json
import time
import logging
import functools
from datetime import datetime, date

from flask import (
    Flask, render_template, jsonify, Response,
    request, redirect, url_for, session, send_file, abort
)

from config import (
    FLASK_HOST, FLASK_PORT, FLASK_DEBUG,
    LOG_DIR, CSV_LOG_DIR, REPORT_DIR,
    SENSOR_INTERVAL_SEC, PUMP_ML_PER_SEC,
    PORTAL_USERNAME, PORTAL_PASSWORD, SECRET_KEY
)
from database import (
    init_db, get_latest, get_history, get_hourly_summary,
    get_today_motor_stats, get_motor_log, reset_today_stats, get_last_reset
)
from report_generator import (
    generate_daily_report, generate_monthly_report, generate_yearly_report
)

# ─── App setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = SECRET_KEY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FLASK] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─── Auth helper ─────────────────────────────────────────────────────────────

def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("portal_login"))
        return f(*args, **kwargs)
    return wrapper


# ─── Main Dashboard ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ─── Portal ───────────────────────────────────────────────────────────────────

@app.route("/portal")
@app.route("/portal/login", methods=["GET"])
def portal_login():
    if session.get("logged_in"):
        return redirect(url_for("portal_dashboard"))
    return render_template("portal.html", error=None)


@app.route("/portal/login", methods=["POST"])
def portal_login_post():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    if username == PORTAL_USERNAME and password == PORTAL_PASSWORD:
        session["logged_in"] = True
        session["username"]  = username
        return redirect(url_for("portal_dashboard"))
    return render_template("portal.html", error="Invalid username or password.")


@app.route("/portal/dashboard")
@login_required
def portal_dashboard():
    return render_template("portal_dash.html", username=session.get("username"))


@app.route("/portal/logout")
def portal_logout():
    session.clear()
    return redirect(url_for("portal_login"))


# ─── Download API ─────────────────────────────────────────────────────────────

@app.route("/api/portal/download", methods=["POST"])
@login_required
def portal_download():
    data     = request.get_json()
    dl_type  = data.get("type")       # "log" or "report"
    fmt      = data.get("format")     # "daily"|"monthly"|"yearly"
    date_str = data.get("date")       # "YYYY-MM-DD"
    month    = data.get("month")      # int
    year_v   = data.get("year")       # int

    try:
        if dl_type == "log":
            # CSV log file for a specific day
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            fname = dt.strftime("Plant_IoT_%d%m%Y.csv")
            fpath = os.path.join(CSV_LOG_DIR, fname)
            if not os.path.exists(fpath):
                return jsonify({"error": f"Log file not found: {fname}"}), 404
            return send_file(fpath, as_attachment=True, download_name=fname,
                             mimetype="text/csv")

        elif dl_type == "report":
            if fmt == "daily":
                dt    = datetime.strptime(date_str, "%Y-%m-%d")
                fpath = generate_daily_report(date_str)
                fname = os.path.basename(fpath)
            elif fmt == "monthly":
                fpath = generate_monthly_report(int(year_v), int(month))
                fname = os.path.basename(fpath)
            elif fmt == "yearly":
                fpath = generate_yearly_report(int(year_v))
                fname = os.path.basename(fpath)
            else:
                return jsonify({"error": "Unknown format"}), 400

            return send_file(fpath, as_attachment=True, download_name=fname,
                             mimetype="application/pdf")

    except Exception as exc:
        log.exception("Download error: %s", exc)
        return jsonify({"error": str(exc)}), 500

    return jsonify({"error": "Invalid request"}), 400


# ─── Sensor Data APIs ─────────────────────────────────────────────────────────

@app.route("/api/latest")
def api_latest():
    data = get_latest(1)
    return jsonify(data[0] if data else {})


@app.route("/api/history")
@app.route("/api/history/<int:hours>")
def api_history(hours=24):
    hours = max(1, min(hours, 168))
    return jsonify(get_history(hours=hours))


@app.route("/api/hourly")
@app.route("/api/hourly/<int:hours>")
def api_hourly(hours=24):
    return jsonify(get_hourly_summary(hours=hours))


# ─── Today Stats ──────────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    stats    = get_today_motor_stats()
    total_s  = stats.get("total_s") or 0
    water_ml = round(total_s * PUMP_ML_PER_SEC)
    last_reset = get_last_reset()

    # Check if there was a reset today — if so, only count cycles after reset
    return jsonify({
        "cycles":    stats.get("cycles", 0),
        "total_s":   round(total_s, 1),
        "total_min": round(total_s / 60, 1),
        "water_ml":  water_ml,
        "water_l":   round(water_ml / 1000, 2),
        "last_reset": last_reset.get("reset_at") if last_reset else None,
    })


@app.route("/api/motor_log")
def api_motor_log():
    return jsonify(get_motor_log(limit=50))


# ─── Reset API ────────────────────────────────────────────────────────────────

@app.route("/api/reset/today", methods=["POST"])
@login_required
def api_reset_today():
    reset_today_stats(reset_by=session.get("username", "admin"))
    return jsonify({"status": "ok", "message": "Today's stats counter reset."})


# ─── SSE Live Stream ──────────────────────────────────────────────────────────

@app.route("/api/stream")
def api_stream():
    def generate():
        while True:
            try:
                data  = get_latest(1)
                row   = data[0] if data else {}
                stats = get_today_motor_stats()
                total_s  = stats.get("total_s") or 0
                row["today_water_ml"]  = round(total_s * PUMP_ML_PER_SEC)
                row["today_cycles"]    = stats.get("cycles", 0)
                row["today_total_s"]   = round(total_s, 1)
                row["today_total_min"] = round(total_s / 60, 1)
                yield f"data: {json.dumps(row)}\n\n"
            except Exception as exc:
                log.error("SSE error: %s", exc)
                yield "data: {}\n\n"
            time.sleep(SENSOR_INTERVAL_SEC)

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no",
                             "Connection": "keep-alive"})


# ─── Health ───────────────────────────────────────────────────────────────────

@app.route("/api/health")
def api_health():
    data = get_latest(1)
    return jsonify({
        "status": "ok",
        "last_ts": data[0]["timestamp"] if data else None,
    })


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    os.makedirs(CSV_LOG_DIR,  exist_ok=True)
    os.makedirs(REPORT_DIR,   exist_ok=True)
    log.info("Flask starting → http://%s:%d", FLASK_HOST, FLASK_PORT)
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG, threaded=True)