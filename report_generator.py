"""
report_generator.py — Generates PDF monitoring reports.

Types & naming:
  Daily   : Monitoring_Report_DDMMYYYY.pdf
  Monthly : Monitoring_Report_MMYYYY.pdf
  Yearly  : Monitoring_Report_YYYY.pdf

Location  : logs/reports/
"""

import os
import io
import logging
from datetime import datetime, date, timedelta

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics import renderPDF
from reportlab.graphics.widgets.markers import makeMarker

from config import REPORT_DIR, PUMP_ML_PER_SEC
from database import (
    get_daily_summary, get_monthly_summary, get_yearly_summary,
    get_motor_stats_range, get_latest
)

log = logging.getLogger(__name__)

# ── Colour palette ────────────────────────────────────────────────────────────
GREEN   = colors.HexColor("#238636")
DKGREEN = colors.HexColor("#1a5c15")
LTGREEN = colors.HexColor("#e8f5e9")
BLUE    = colors.HexColor("#1565C0")
LTBLUE  = colors.HexColor("#E3F2FD")
RED     = colors.HexColor("#C62828")
LTRED   = colors.HexColor("#FFEBEE")
YELLOW  = colors.HexColor("#F9A825")
GRAY    = colors.HexColor("#455A64")
LTGRAY  = colors.HexColor("#F5F5F5")
WHITE   = colors.white
BLACK   = colors.black


def _styles():
    ss = getSampleStyleSheet()
    base = dict(fontName="Helvetica", fontSize=10, leading=14)
    bold = dict(fontName="Helvetica-Bold")

    def ps(name, **kw):
        merged = {**base, **kw}
        return ParagraphStyle(name, **merged)

    return {
        "title":    ps("title",   fontName="Helvetica-Bold", fontSize=20, textColor=DKGREEN, alignment=TA_CENTER, spaceAfter=4),
        "subtitle": ps("sub",     fontName="Helvetica",      fontSize=11, textColor=GRAY,    alignment=TA_CENTER, spaceAfter=12),
        "h2":       ps("h2",      fontName="Helvetica-Bold", fontSize=13, textColor=BLUE,    spaceBefore=14, spaceAfter=4),
        "h3":       ps("h3",      fontName="Helvetica-Bold", fontSize=11, textColor=DKGREEN, spaceBefore=8,  spaceAfter=3),
        "body":     ps("body",    fontSize=9,  textColor=BLACK, spaceAfter=3),
        "kv":       ps("kv",      fontSize=9,  textColor=GRAY,  spaceAfter=2),
        "footer":   ps("footer",  fontSize=7,  textColor=GRAY,  alignment=TA_CENTER),
        "center":   ps("center",  fontSize=9,  alignment=TA_CENTER),
        "bold":     ps("bold",    fontName="Helvetica-Bold", fontSize=9),
    }


def _hr():
    return HRFlowable(width="100%", thickness=1, color=colors.HexColor("#DDDDDD"), spaceAfter=6, spaceBefore=4)


def _section_bar(title, st):
    return KeepTogether([
        Paragraph(title, st["h2"]),
        HRFlowable(width="100%", thickness=2, color=GREEN, spaceAfter=6),
    ])


def _kv_table(pairs, col_w=(6*cm, 10*cm)):
    data = [[Paragraph(f"<b>{k}</b>", ParagraphStyle("kk", fontName="Helvetica-Bold", fontSize=9)),
             Paragraph(str(v),        ParagraphStyle("vv", fontName="Helvetica",      fontSize=9))]
            for k, v in pairs]
    t = Table(data, colWidths=list(col_w))
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0,0), (-1,-1), [LTGRAY, WHITE]),
        ("GRID",           (0,0), (-1,-1), 0.3, colors.HexColor("#DDDDDD")),
        ("LEFTPADDING",    (0,0), (-1,-1), 8),
        ("RIGHTPADDING",   (0,0), (-1,-1), 8),
        ("TOPPADDING",     (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 5),
    ]))
    return t


def _stat_box_table(items):
    """items = list of (label, value, unit, color)"""
    cells = []
    for label, value, unit, col in items:
        inner = Table([
            [Paragraph(label, ParagraphStyle("sl", fontName="Helvetica", fontSize=7, textColor=GRAY))],
            [Paragraph(str(value), ParagraphStyle("sv", fontName="Helvetica-Bold", fontSize=16, textColor=col))],
            [Paragraph(unit,  ParagraphStyle("su", fontName="Helvetica", fontSize=7, textColor=GRAY))],
        ], colWidths=[4.4*cm])
        inner.setStyle(TableStyle([
            ("ALIGN",         (0,0),(-1,-1), "CENTER"),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
            ("BACKGROUND",    (0,0),(-1,-1), LTGRAY),
            ("BOX",           (0,0),(-1,-1), 1, colors.HexColor("#CCCCCC")),
            ("TOPPADDING",    (0,0),(-1,-1), 8),
            ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ]))
        cells.append(inner)
    row_table = Table([cells], colWidths=[4.6*cm]*len(cells))
    row_table.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER")]))
    return row_table


def _simple_line_chart(data_series, labels, width=480, height=160,
                       series_colors=None, y_label="", title=""):
    """
    data_series: list of lists of (x_index, y_value)
    labels: x axis labels (strings)
    """
    if not data_series or not any(data_series):
        d = Drawing(width, height)
        d.add(String(width/2, height/2, "No data available",
                     textAnchor="middle", fontSize=9, fillColor=GRAY))
        return d

    d  = Drawing(width, height)
    lc = HorizontalLineChart()
    lc.x      = 50
    lc.y      = 30
    lc.width  = width - 70
    lc.height = height - 50

    lc.data = [[pt[1] for pt in s] for s in data_series]

    all_vals = [v for s in lc.data for v in s if v is not None]
    if all_vals:
        mn, mx = min(all_vals), max(all_vals)
        pad    = max((mx - mn) * 0.15, 2)
        lc.valueAxis.valueMin = mn - pad
        lc.valueAxis.valueMax = mx + pad
    lc.valueAxis.valueStep    = None
    lc.valueAxis.labels.fontSize   = 7
    lc.valueAxis.labelTextFormat   = "%.1f"

    lc.categoryAxis.categoryNames  = labels[::max(1, len(labels)//10)]
    lc.categoryAxis.labels.fontSize = 7
    lc.categoryAxis.labels.angle   = 30
    lc.categoryAxis.labels.dy      = -8

    palette = series_colors or [colors.HexColor("#f85149"), colors.HexColor("#58a6ff"),
                                 colors.HexColor("#3fb950"), colors.HexColor("#d29922")]
    for i, s in enumerate(lc.lines):
        s.strokeColor = palette[i % len(palette)]
        s.strokeWidth = 1.5

    if title:
        d.add(String(width/2, height-8, title, textAnchor="middle",
                     fontSize=8, fillColor=GRAY, fontName="Helvetica-Bold"))
    d.add(lc)
    return d


def _build_common_content(story, st, rows, stats, period_label,
                           report_name, generated_at):
    """Build the shared content blocks used in all report types."""

    # ── Header ────────────────────────────────────────────────────
    story.append(Paragraph("🌱 IoT Smart Plant Watering System", st["title"]))
    story.append(Paragraph("Monitoring Report", st["subtitle"]))
    story.append(Paragraph(f"Period: {period_label}", st["subtitle"]))
    story.append(_hr())
    story.append(Paragraph(f"Generated : {generated_at}     |     Report : {report_name}",
                           st["center"]))
    story.append(Spacer(1, 10))

    # ── Current / Latest snapshot ─────────────────────────────────
    latest = get_latest(1)
    story.append(_section_bar("📡  Current Sensor Readings", st))
    if latest:
        d = latest[0]
        pump_label = "ON  (WATERING)" if d.get("pump_state") else "OFF  (STANDBY)"
        pump_min   = round((d.get("pump_total_ms") or 0) / 60000, 1)
        story.append(_kv_table([
            ("Temperature",   f"{d.get('temperature', '--')} °C"),
            ("Humidity",      f"{d.get('humidity', '--')} %"),
            ("Soil Moisture", f"{d.get('moisture', '--')} %"),
            ("Pump Status",   pump_label),
            ("Session Pump",  f"{pump_min} min (cumulative this session)"),
            ("Last Update",   d.get("timestamp", "--")),
            ("Op. Mode",      d.get("operational_mode", "auto").capitalize()),
            ("Connection",    d.get("connection_status", "online").capitalize()),
        ]))
    else:
        story.append(Paragraph("No current data available.", st["body"]))
    story.append(Spacer(1, 10))

    # ── Period Summary stats ───────────────────────────────────────
    story.append(_section_bar("📊  Period Summary", st))
    if rows:
        temps  = [r.get("temperature") or r.get("avg_temp") for r in rows if (r.get("temperature") or r.get("avg_temp")) is not None]
        hums   = [r.get("humidity")    or r.get("avg_hum")  for r in rows if (r.get("humidity")    or r.get("avg_hum"))  is not None]
        moists = [r.get("moisture")    or r.get("avg_moist")for r in rows if (r.get("moisture")    or r.get("avg_moist"))is not None]

        pairs = [("Readings / Data Points", len(rows))]
        if temps:
            pairs += [
                ("Avg Temperature",    f"{round(sum(temps)/len(temps),1)} °C"),
                ("Min / Max Temp",     f"{min(temps):.1f} / {max(temps):.1f} °C"),
            ]
        if hums:
            pairs += [("Avg Humidity", f"{round(sum(hums)/len(hums),1)} %")]
        if moists:
            pairs += [("Avg Soil Moisture", f"{round(sum(moists)/len(moists),0):.0f} %")]

        # Pump active %
        pump_rows = [r for r in rows if r.get("pump_state") == 1]
        if pump_rows and rows:
            pairs.append(("Pump Active", f"{round(len(pump_rows)/len(rows)*100,1)} % of period"))

        story.append(_kv_table(pairs))
    else:
        story.append(Paragraph("No data for this period.", st["body"]))
    story.append(Spacer(1, 10))

    # ── Motor / Water stats ───────────────────────────────────────
    story.append(_section_bar("⚙️  Motor & Water Statistics", st))
    total_s  = stats.get("total_s") or 0
    total_min = round(total_s / 60, 1)
    water_ml  = round(total_s * PUMP_ML_PER_SEC)
    water_l   = round(water_ml / 1000, 2)
    story.append(_stat_box_table([
        ("Watering Cycles", stats.get("cycles",0), "completed events", BLUE),
        ("Total Pump Runtime", f"{total_min} min", f"{total_s:.0f} seconds", GREEN),
        ("Est. Water Used", f"{water_ml} ml", f"{water_l} L total", colors.HexColor("#0288D1")),
    ]))
    story.append(Spacer(1, 10))

    # ── Charts ────────────────────────────────────────────────────
    story.append(_section_bar("📈  Temperature & Humidity Chart", st))
    if rows:
        # Use timestamp or 'hour' or 'day' or 'month' field
        label_key = "timestamp" if "timestamp" in rows[0] else (
                    "hour" if "hour" in rows[0] else (
                    "day"  if "day"  in rows[0] else "month"))
        labels = [str(r.get(label_key,""))[-8:] for r in rows]
        step   = max(1, len(labels)//12)
        disp_labels = [labels[i] if i % step == 0 else "" for i in range(len(labels))]

        temp_pts  = [(i, r.get("temperature") or r.get("avg_temp")) for i,r in enumerate(rows)
                     if (r.get("temperature") or r.get("avg_temp")) is not None]
        hum_pts   = [(i, r.get("humidity")    or r.get("avg_hum"))  for i,r in enumerate(rows)
                     if (r.get("humidity")    or r.get("avg_hum"))  is not None]

        chart = _simple_line_chart(
            [temp_pts, hum_pts], disp_labels,
            width=480, height=150,
            series_colors=[colors.HexColor("#f85149"), colors.HexColor("#58a6ff")],
        )
        story.append(chart)

        legend = Table([[
            Rect(0,2,10,10,fillColor=colors.HexColor("#f85149"),strokeColor=None),
            Paragraph(" Temperature (°C)", ParagraphStyle("l1",fontSize=8)),
            Spacer(1,0),
            Rect(0,2,10,10,fillColor=colors.HexColor("#58a6ff"),strokeColor=None),
            Paragraph(" Humidity (%)", ParagraphStyle("l2",fontSize=8)),
        ]], colWidths=[14,80,20,14,80])
        story.append(legend)
    story.append(Spacer(1, 8))

    story.append(_section_bar("🌱  Soil Moisture & Pump State Chart", st))
    if rows:
        moist_pts = [(i, r.get("moisture") or r.get("avg_moist")) for i,r in enumerate(rows)
                     if (r.get("moisture") or r.get("avg_moist")) is not None]
        pump_pts  = [(i, (r.get("pump_state") or r.get("pump_on") or 0)*100)
                     for i,r in enumerate(rows)]

        chart2 = _simple_line_chart(
            [moist_pts, pump_pts], disp_labels,
            width=480, height=150,
            series_colors=[colors.HexColor("#3fb950"), colors.HexColor("#d29922")],
        )
        story.append(chart2)

        legend2 = Table([[
            Rect(0,2,10,10,fillColor=colors.HexColor("#3fb950"),strokeColor=None),
            Paragraph(" Moisture (%)", ParagraphStyle("l3",fontSize=8)),
            Spacer(1,0),
            Rect(0,2,10,10,fillColor=colors.HexColor("#d29922"),strokeColor=None),
            Paragraph(" Pump State (×100)", ParagraphStyle("l4",fontSize=8)),
        ]], colWidths=[14,80,20,14,100])
        story.append(legend2)
    story.append(Spacer(1, 10))

    # ── Observations & Recommendations ───────────────────────────
    story.append(_section_bar("💡  Observations & Recommendations", st))
    obs = []
    if rows:
        temps  = [r.get("temperature") or r.get("avg_temp") for r in rows if (r.get("temperature") or r.get("avg_temp")) is not None]
        moists = [r.get("moisture")    or r.get("avg_moist")for r in rows if (r.get("moisture")    or r.get("avg_moist"))is not None]

        if temps:
            avg_t = sum(temps)/len(temps)
            if avg_t > 35:
                obs.append("⚠️  High average temperature detected (>35°C). Consider shading the plant.")
            elif avg_t < 15:
                obs.append("⚠️  Low temperature detected (<15°C). Frost risk — consider moving the plant indoors.")
            else:
                obs.append("✅  Temperature within normal range.")

        if moists:
            avg_m = sum(moists)/len(moists)
            if avg_m < 25:
                obs.append("⚠️  Average soil moisture critically low (<25%). Check pump operation and water supply.")
            elif avg_m > 85:
                obs.append("⚠️  Soil consistently over-watered (>85%). Reduce watering threshold.")
            else:
                obs.append("✅  Soil moisture maintained within healthy range.")

        if stats.get("cycles", 0) > 20:
            obs.append("⚠️  High number of watering cycles — possible sensor drift or soil drainage issue.")

        obs.append(f"ℹ️  Total estimated water consumption for this period: {water_l} L.")
        obs.append("ℹ️  System operating in AUTO mode based on sensor thresholds (30% ON / 70% OFF).")
        obs.append("ℹ️  Calibrate moisture sensor every 30 days for best accuracy.")

    for o in obs:
        story.append(Paragraph(o, st["body"]))
    story.append(Spacer(1, 10))

    # ── System Info ───────────────────────────────────────────────
    story.append(_section_bar("🔧  System Information", st))
    story.append(_kv_table([
        ("Controller",         "Arduino UNO (ATmega328P)"),
        ("Temp / Humidity",    "DHT11 Sensor — Pin D2"),
        ("Soil Moisture",      "Analog Resistive Sensor — Pin A0"),
        ("Display",            "0.96\" SSD1306 OLED I2C — A4/A5"),
        ("Relay",              "1-Channel 5V Relay — Pin D7"),
        ("Backend",            "Python 3 + Flask + SQLite"),
        ("Moisture Threshold", "ON < 30%  |  OFF ≥ 70%"),
        ("Temp Safety Cutoff", "38 °C — pump forced OFF"),
        ("Pump Flow Rate",     "~30 ml/sec (configurable)"),
        ("Data Interval",      "5 seconds (sensor) / 60 seconds (CSV log)"),
    ]))
    story.append(Spacer(1, 10))

    # ── Footer ────────────────────────────────────────────────────
    story.append(_hr())
    story.append(Paragraph(
        f"Plant IoT Monitoring System  |  {report_name}  |  Generated: {generated_at}",
        st["footer"]
    ))


def generate_daily_report(date_str: str = None) -> str:
    """
    date_str: 'YYYY-MM-DD' or None for today.
    Returns path to generated PDF.
    """
    if date_str is None:
        date_str = date.today().strftime("%Y-%m-%d")

    dt       = datetime.strptime(date_str, "%Y-%m-%d")
    ddmmyyyy = dt.strftime("%d%m%Y")
    fname    = f"Monitoring_Report_{ddmmyyyy}.pdf"
    os.makedirs(REPORT_DIR, exist_ok=True)
    fpath    = os.path.join(REPORT_DIR, fname)

    rows   = get_daily_summary(date_str)
    stats  = get_motor_stats_range(date_str, date_str)
    gen_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    story = []
    st    = _styles()
    _build_common_content(story, st, rows, stats,
                          f"Daily — {dt.strftime('%d %B %Y')}",
                          fname, gen_at)

    doc = SimpleDocTemplate(fpath, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    doc.build(story)
    log.info("Daily report → %s", fpath)
    return fpath


def generate_monthly_report(year: int, month: int) -> str:
    mmyyyy = f"{month:02d}{year:04d}"
    fname  = f"Monitoring_Report_{mmyyyy}.pdf"
    os.makedirs(REPORT_DIR, exist_ok=True)
    fpath  = os.path.join(REPORT_DIR, fname)

    rows   = get_monthly_summary(year, month)
    start  = f"{year:04d}-{month:02d}-01"
    end    = f"{year:04d}-{month:02d}-31"
    stats  = get_motor_stats_range(start, end)
    gen_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    month_name = datetime(year, month, 1).strftime("%B %Y")

    story = []
    st    = _styles()
    _build_common_content(story, st, rows, stats,
                          f"Monthly — {month_name}",
                          fname, gen_at)

    doc = SimpleDocTemplate(fpath, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    doc.build(story)
    log.info("Monthly report → %s", fpath)
    return fpath


def generate_yearly_report(year: int) -> str:
    fname  = f"Monitoring_Report_{year:04d}.pdf"
    os.makedirs(REPORT_DIR, exist_ok=True)
    fpath  = os.path.join(REPORT_DIR, fname)

    rows   = get_yearly_summary(year)
    stats  = get_motor_stats_range(f"{year}-01-01", f"{year}-12-31")
    gen_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    story = []
    st    = _styles()
    _build_common_content(story, st, rows, stats,
                          f"Yearly — {year}",
                          fname, gen_at)

    doc = SimpleDocTemplate(fpath, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    doc.build(story)
    log.info("Yearly report → %s", fpath)
    return fpath


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from database import init_db
    init_db()
    p = generate_daily_report()
    print("Generated:", p)