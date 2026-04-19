# 🌱 IoT Smart Plant Watering System

Automated plant watering with Arduino UNO, DHT11, Soil Moisture Sensor,
0.96" OLED display, Relay, and a Python + Flask web dashboard.

---

## Hardware

| Component           | Arduino Pin  |
|---------------------|--------------|
| DHT11 DATA          | D2 (+ 10kΩ pull-up to 5V) |
| Moisture Sensor AOUT| A0           |
| OLED SDA            | A4           |
| OLED SCL            | A5           |
| Relay IN            | D7           |

---

## Quick Start

### 1 — Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2 — Flash Arduino
- Open `plant_watering/plant_watering.ino` in Arduino IDE
- Install libraries: DHT by Adafruit, Adafruit SSD1306, Adafruit GFX
- Select Board: Arduino UNO, Port: your COM port
- Upload

### 3 — Set serial port
Edit `config.py`:
```python
SERIAL_PORT = "COM3"        # Windows
SERIAL_PORT = "/dev/ttyUSB0"  # Linux
```

### 4 — Run (with Arduino)
```bash
python run_all.py
```

### 4b — Run (WITHOUT Arduino — simulator mode)
```bash
python run_sim.py
```

### 5 — Open Dashboard
```
http://localhost:5000
```

---

## Project Structure

```
plant_iot/
├── config.py           All constants (serial port, thresholds, etc.)
├── database.py         SQLite schema + query helpers
├── serial_reader.py    Arduino USB bridge → DB
├── simulate.py         Hardware simulator (no Arduino needed)
├── logger.py           10-minute report file generator
├── app.py              Flask web application + REST API
├── run_all.py          Launch all services (with Arduino)
├── run_sim.py          Launch all services (simulator mode)
├── requirements.txt    Python dependencies
├── plant_watering/
│   └── plant_watering.ino   Arduino firmware
├── data/
│   └── plant_iot.db    SQLite database (auto-created)
├── logs/
│   └── report_*.log    10-min monitoring reports
└── templates/
    └── index.html      Dashboard UI
```

---

## API Endpoints

| Endpoint              | Description                        |
|-----------------------|------------------------------------|
| GET /                 | Dashboard HTML                     |
| GET /api/latest       | Latest sensor reading (JSON)       |
| GET /api/history/24   | Last 24h of data (JSON array)      |
| GET /api/stats        | Motor cycle stats + water usage    |
| GET /api/motor_log    | Recent watering events             |
| GET /api/logs         | Log file list + content            |
| GET /api/stream       | Server-Sent Events (live, 5s)      |
| GET /api/health       | Health check                       |

---

## Thresholds (edit config.py)

| Setting        | Default | Meaning                    |
|----------------|---------|----------------------------|
| MOISTURE_LOW   | 30%     | Pump turns ON below this   |
| MOISTURE_HIGH  | 70%     | Pump turns OFF above this  |
| TEMP_HIGH      | 38°C    | Safety cutoff              |

---

## Deployment (Linux systemd)

```bash
sudo cp plant-iot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable plant-iot
sudo systemctl start  plant-iot
```

Edit `plant-iot.service` to match your username and project path.
