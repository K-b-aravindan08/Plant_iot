"""
run_sim.py v2 — Full stack with simulator (no Arduino needed).
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
    for _, label, p in procs:
        try: p.terminate(); p.wait(timeout=4)
        except Exception: p.kill()

signal.signal(signal.SIGINT,  lambda s,f: (stop_all(), sys.exit(0)))
signal.signal(signal.SIGTERM, lambda s,f: (stop_all(), sys.exit(0)))

print("\n"+"="*54)
print("  PlantIoT v2 — SIMULATOR MODE (no Arduino)")
print("="*54)

start("simulate.py",   "Sensor Simulator")
time.sleep(2)
start("csv_logger.py", "CSV Logger (1-min rows/day)")
time.sleep(1)
start("app.py",        "Flask Web Dashboard")
time.sleep(2)

print()
print("  Dashboard → http://localhost:5000")
print("  Portal    → http://localhost:5000/portal  (admin / plant2025)")
print("  Press Ctrl+C to stop.\n")
print("="*54+"\n")

while True: time.sleep(5)