"""
run_all.py v2 — Launches all Plant IoT services:
  1. serial_reader.py  — Arduino USB → SQLite
  2. csv_logger.py     — 1-min CSV rows per day
  3. app.py            — Flask web app
"""

import subprocess, sys, time, signal, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON   = sys.executable
procs    = []

def start(script, label):
    p = subprocess.Popen(
        [PYTHON, os.path.join(BASE_DIR, script)],
        stdout=sys.stdout, stderr=sys.stderr, cwd=BASE_DIR
    )
    print(f"  ✔  {label:<35}  PID {p.pid}")
    procs.append((script, label, p))

def stop_all():
    print("\n  Stopping all services …")
    for _, label, p in procs:
        try: p.terminate(); p.wait(timeout=4)
        except Exception: p.kill()
        print(f"  ✔  {label} stopped")

signal.signal(signal.SIGINT,  lambda s,f: (stop_all(), sys.exit(0)))
signal.signal(signal.SIGTERM, lambda s,f: (stop_all(), sys.exit(0)))

print("\n"+"="*54)
print("   IoT Smart Plant Watering System v2")
print("="*54)

start("serial_reader.py", "Serial Reader (Arduino USB)")
time.sleep(2)
start("csv_logger.py",    "CSV Logger (1-min rows/day)")
time.sleep(1)
start("app.py",           "Flask Web Dashboard")
time.sleep(2)

print()
print("  All services running.")
print("  Dashboard → http://localhost:5000")
print("  Portal    → http://localhost:5000/portal")
print("  Press Ctrl+C to stop all.\n")
print("="*54+"\n")

while True:
    for i,(script,label,p) in enumerate(procs):
        if p.poll() is not None:
            print(f"  ⚠  {label} exited — restarting …")
            new_p = subprocess.Popen(
                [PYTHON, os.path.join(BASE_DIR, script)],
                stdout=sys.stdout, stderr=sys.stderr, cwd=BASE_DIR
            )
            procs[i] = (script, label, new_p)
    time.sleep(5)