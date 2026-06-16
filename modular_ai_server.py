"""
Modular Floating Microalgae Treatment Buoy
AI decision server + web dashboard

Run:
    pip install flask flask-cors
    python modular_ai_server.py

Open:
    http://localhost:5000

The server supports many connected buoy modules. Each ESP32 sends sensor data to
/analyze. The AI logic chooses controlled treatment flow, aeration, hold, or
safety lockout. Microalgae stays inside the closed photobioreactor/biofilm
module.
"""

from __future__ import annotations

import base64
from collections import deque
from datetime import datetime
from pathlib import Path
from time import time
from typing import Any

from flask import Flask, abort, jsonify, request, send_file
from flask_cors import CORS


app = Flask(__name__)
CORS(app)


# ------------------------------------------------------------
# Local icon CSS from the project folder first, then the old Downloads folder.
# ------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIR = BASE_DIR / "water_images"
TABLER_CSS_PATHS = [
    BASE_DIR / "Algae Bioreactor_files" / "tabler-icons.min.css",
    Path(r"C:\Users\User\Downloads\Algae Bioreactor_files\tabler-icons.min.css"),
]


# ------------------------------------------------------------
# AI thresholds
# ------------------------------------------------------------
PH_MIN = 6.2
PH_MAX = 8.8
DO_CRITICAL = 3.0
DO_LOW = 5.0
DO_GOOD = 6.5
SUN_MIN_FOR_ALGAE = 35.0
SUN_GOOD = 60.0
TURBIDITY_CAUTION = 60.0
TURBIDITY_CLOG_RISK = 90.0
TURBIDITY_LOCKOUT = 130.0
TEMP_MIN = 15.0
TEMP_MAX = 36.0
FILM_HARVEST_LEVEL = 85.0
ACTIVE_COMMAND_COOLDOWN = 45
HISTORY_LIMIT = 160
IMAGE_HISTORY_LIMIT = 60


modules: dict[str, dict[str, Any]] = {}
history: deque[dict[str, Any]] = deque(maxlen=HISTORY_LIMIT)
image_history: deque[dict[str, Any]] = deque(maxlen=IMAGE_HISTORY_LIMIT)
last_active_command_at: dict[str, float] = {}
manual_lockout = False
reading_counter = 0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def number(payload: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def metric_number(metrics: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(metrics.get(key, default))
    except (TypeError, ValueError):
        return default


def clean_id(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    cleaned = "".join(ch for ch in text if ch in allowed)
    return (cleaned or fallback)[:48]


def safe_image_filename(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
    cleaned = "".join(ch for ch in value if ch in allowed)
    return cleaned[:120]


def parse_reading(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "array_id": clean_id(payload.get("array_id"), "river-array-01"),
        "module_id": clean_id(payload.get("module_id"), "module-01"),
        "ph": number(payload, "ph", 7.0),
        "turbidity": number(payload, "turbidity", 999.0),
        "dissolved_o2": number(payload, "dissolved_o2", 0.0),
        "sunlight": number(payload, "sunlight", 0.0),
        "temperature_c": number(payload, "temperature_c", 25.0),
        "film_density": number(payload, "film_density", 0.0),
        "report_reason": str(payload.get("report_reason", "unknown"))[:64],
        "sensor_interval_seconds": number(payload, "sensor_interval_seconds", 10.0),
        "normal_report_interval_seconds": number(payload, "normal_report_interval_seconds", 60.0),
    }


def impossible_sensor_values(reading: dict[str, Any]) -> list[str]:
    problems = []
    if not 0.0 <= reading["ph"] <= 14.0:
        problems.append("pH sensor value is impossible")
    if not 0.0 <= reading["turbidity"] <= 3000.0:
        problems.append("turbidity sensor value is impossible")
    if not 0.0 <= reading["dissolved_o2"] <= 20.0:
        problems.append("DO sensor value is impossible")
    if not 0.0 <= reading["sunlight"] <= 100.0:
        problems.append("sunlight sensor value is impossible")
    if not -10.0 <= reading["temperature_c"] <= 60.0:
        problems.append("temperature sensor value is impossible")
    if not 0.0 <= reading["film_density"] <= 100.0:
        problems.append("film density sensor value is impossible")
    return problems


def analyze_image_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    brightness = metric_number(metrics, "brightness")
    contrast = metric_number(metrics, "contrast")
    green_ratio = metric_number(metrics, "green_ratio")
    brown_ratio = metric_number(metrics, "brown_ratio")
    dark_ratio = metric_number(metrics, "dark_ratio")
    avg_red = metric_number(metrics, "avg_red")
    avg_green = metric_number(metrics, "avg_green")
    avg_blue = metric_number(metrics, "avg_blue")

    reasons: list[str] = []
    score = 100.0
    status = "ภาพน้ำดูปกติ"
    recommendation = "ใช้ข้อมูลภาพร่วมกับค่า DO, pH และความขุ่นจากเซนเซอร์"

    if brightness < 45 or dark_ratio > 0.55:
        status = "ภาพมืดเกินไป"
        reasons.append("ภาพมืดหรือมีเงามาก อาจวิเคราะห์สีของน้ำได้ไม่แม่นยำ")
        recommendation = "ถ่ายภาพใหม่ในบริเวณที่มีแสงมากขึ้น"
        score -= 35

    if green_ratio > 0.18 and avg_green > avg_red * 1.08 and avg_green > avg_blue * 1.05:
        status = "น้ำมีโทนเขียวสูง"
        reasons.append("ภาพมีสัดส่วนสีเขียวสูง อาจมีสาหร่ายหรือพืชน้ำมาก")
        recommendation = "ตรวจร่วมกับค่า DO ช่วงกลางวัน/กลางคืน และพิจารณาเก็บตัวอย่างน้ำ"
        score -= 18

    if brown_ratio > 0.16:
        status = "น้ำมีโทนน้ำตาลหรือขุ่น"
        reasons.append("ภาพมีโทนน้ำตาลสูง อาจมาจากตะกอน ดิน หรือสารแขวนลอย")
        recommendation = "ตรวจร่วมกับเซนเซอร์ความขุ่น และลดอัตราการไหลถ้าเสี่ยงอุดตัน"
        score -= 22

    if contrast < 18 and brightness < 140:
        reasons.append("ภาพมี contrast ต่ำ น้ำอาจดูขุ่นหรือภาพอาจไม่ชัด")
        score -= 8

    if not reasons:
        reasons.append("สีและความสว่างของภาพอยู่ในช่วงที่ดูปกติ")

    risk = "ต่ำ"
    if score < 55:
        risk = "สูง"
    elif score < 78:
        risk = "ปานกลาง"

    return {
        "status": status,
        "risk": risk,
        "score": round(clamp(score, 0, 100)),
        "reason": "; ".join(reasons),
        "recommendation": recommendation,
    }


def water_quality_score(reading: dict[str, Any]) -> int:
    score = 100.0

    if reading["dissolved_o2"] < DO_GOOD:
        score -= (DO_GOOD - reading["dissolved_o2"]) * 12
    if reading["turbidity"] > TURBIDITY_CAUTION:
        score -= (reading["turbidity"] - TURBIDITY_CAUTION) * 0.45
    if reading["ph"] < PH_MIN:
        score -= (PH_MIN - reading["ph"]) * 18
    if reading["ph"] > PH_MAX:
        score -= (reading["ph"] - PH_MAX) * 18
    if reading["temperature_c"] < TEMP_MIN or reading["temperature_c"] > TEMP_MAX:
        score -= 10
    if reading["film_density"] > FILM_HARVEST_LEVEL:
        score -= 8

    return round(clamp(score, 0, 100))


def command_settings(command: str) -> dict[str, int]:
    if command == "TREAT":
        return {"pump_seconds": 10, "pump_pwm": 185, "aerate_seconds": 0}
    if command == "FLUSH":
        return {"pump_seconds": 6, "pump_pwm": 235, "aerate_seconds": 0}
    return {"pump_seconds": 0, "pump_pwm": 0, "aerate_seconds": 0}


def apply_cooldown(module_id: str, decision: dict[str, Any], reasons: list[str]) -> None:
    active_commands = {"TREAT", "FLUSH"}
    command = decision["command"]
    if command not in active_commands:
        decision["cooldown_remaining"] = 0
        return

    now = time()
    last = last_active_command_at.get(module_id)
    remaining = 0 if last is None else round(ACTIVE_COMMAND_COOLDOWN - (now - last))

    if remaining > 0:
        decision["command"] = "HOLD"
        decision["flow_level"] = "OFF"
        decision["cooldown_remaining"] = remaining
        reasons.append(f"cooldown active for {remaining}s")
        settings = command_settings("HOLD")
        decision.update(settings)
    else:
        last_active_command_at[module_id] = now
        decision["cooldown_remaining"] = 0


def decide(reading: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    alert = "NONE"
    command = "HOLD"
    flow_level = "OFF"
    growth_mode = "IDLE"
    safety_state = "OK"

    impossible = impossible_sensor_values(reading)
    if impossible:
        return {
            "command": "LOCKOUT",
            "flow_level": "OFF",
            "growth_mode": "IDLE",
            "alert": "SENSOR_CHECK",
            "safety_state": "LOCKOUT",
            "reason": "; ".join(impossible),
            "quality_score": 0,
            "cooldown_remaining": 0,
            **command_settings("LOCKOUT"),
        }

    ph_ok = PH_MIN <= reading["ph"] <= PH_MAX
    sun_ok = reading["sunlight"] >= SUN_MIN_FOR_ALGAE
    temp_ok = TEMP_MIN <= reading["temperature_c"] <= TEMP_MAX
    do_low = reading["dissolved_o2"] < DO_LOW
    do_critical = reading["dissolved_o2"] < DO_CRITICAL
    turbidity = reading["turbidity"]
    film_high = reading["film_density"] >= FILM_HARVEST_LEVEL

    if manual_lockout:
        command = "LOCKOUT"
        safety_state = "LOCKOUT"
        alert = "MANUAL_LOCKOUT"
        reasons.append("manual lockout is enabled")
    elif not ph_ok:
        command = "LOCKOUT"
        safety_state = "LOCKOUT"
        alert = "PH_ABNORMAL"
        reasons.append(f"pH {reading['ph']:.2f} is outside {PH_MIN}-{PH_MAX}")
    elif turbidity >= TURBIDITY_LOCKOUT:
        command = "LOCKOUT"
        safety_state = "LOCKOUT"
        alert = "CLEAN_INTAKE"
        reasons.append(f"turbidity {turbidity:.0f} NTU is too high")
    else:
        if film_high:
            alert = "HARVEST_BIOFILM"
            growth_mode = "MAINTENANCE"
            reasons.append("sealed algae cartridge is dense; maintain or replace biofilm soon")

        if turbidity >= TURBIDITY_CLOG_RISK:
            command = "FLUSH"
            flow_level = "FLUSH"
            alert = "CLEAN_INTAKE" if alert == "NONE" else alert
            reasons.append("intake screen may be clogged by turbid water; run short flush cycle")
        elif do_critical and not sun_ok:
            command = "TREAT"
            flow_level = "TREAT"
            alert = "LOW_DO"
            reasons.append("DO is critical and light is low; run closed treatment loop with backup aeration")
        elif do_low and not sun_ok:
            command = "TREAT"
            flow_level = "TREAT"
            alert = "LOW_DO"
            reasons.append("DO is low but light is weak; keep water moving through the treatment chamber")
        elif do_critical and sun_ok:
            command = "TREAT"
            flow_level = "TREAT"
            alert = "LOW_DO"
            reasons.append("DO is critical and sunlight supports the sealed microalgae chamber")
        elif do_low and sun_ok:
            command = "TREAT"
            flow_level = "TREAT"
            reasons.append("DO is low and sunlight is available; circulate water through the biofilter")
        elif turbidity >= TURBIDITY_CAUTION and ph_ok:
            command = "TREAT"
            flow_level = "TREAT"
            reasons.append("water is moderately turbid; pass water through the treatment chamber")
        elif reading["dissolved_o2"] < DO_GOOD and sun_ok:
            command = "TREAT"
            flow_level = "TREAT"
            reasons.append("DO is slightly low; run a normal treatment cycle")
        else:
            command = "HOLD"
            flow_level = "OFF"
            reasons.append("water quality is acceptable; keep the prototype in monitoring mode")

        if growth_mode != "MAINTENANCE":
            if sun_ok and temp_ok:
                growth_mode = "SEALED_GROW"
            elif not sun_ok and temp_ok and not do_low:
                growth_mode = "LOW_LIGHT_SUPPORT"
            else:
                growth_mode = "IDLE"

    decision = {
        "command": command,
        "flow_level": flow_level,
        "growth_mode": growth_mode,
        "alert": alert,
        "safety_state": safety_state,
        "reason": "; ".join(reasons),
        "quality_score": water_quality_score(reading),
    }
    decision.update(command_settings(command))
    if command == "TREAT" and do_low and not sun_ok:
        decision["aerate_seconds"] = 10
    apply_cooldown(reading["module_id"], decision, reasons)
    decision["reason"] = "; ".join(reasons)
    return decision


def process_payload(payload: dict[str, Any]) -> dict[str, Any]:
    global reading_counter

    reading = parse_reading(payload)
    decision = decide(reading)
    timestamp = datetime.now().strftime("%H:%M:%S")
    reading_counter += 1

    record = {
        **reading,
        **decision,
        "time": timestamp,
        "sequence": reading_counter,
    }
    modules[reading["module_id"]] = record
    history.appendleft(record.copy())
    return record


def wants_json(payload: dict[str, Any]) -> bool:
    return payload.get("response_format") == "json" or "application/json" in request.headers.get("Accept", "")


@app.route("/analyze", methods=["POST"])
def analyze():
    payload = request.get_json(silent=True) or {}
    if not payload:
        return "HOLD", 400

    record = process_payload(payload)
    print(
        f"[{record['time']}] {record['module_id']} "
        f"DO={record['dissolved_o2']:.1f} pH={record['ph']:.2f} "
        f"turb={record['turbidity']:.0f} sun={record['sunlight']:.0f}% "
        f"-> {record['command']}"
    )

    if wants_json(payload):
        return jsonify(record)
    return record["command"]


@app.route("/data", methods=["GET"])
def data():
    return jsonify(
        {
            "modules": list(modules.values()),
            "history": list(history),
            "images": list(image_history),
            "manual_lockout": manual_lockout,
            "thresholds": {
                "ph_min": PH_MIN,
                "ph_max": PH_MAX,
                "do_low": DO_LOW,
                "sun_min_for_algae": SUN_MIN_FOR_ALGAE,
                "turbidity_caution": TURBIDITY_CAUTION,
                "turbidity_clog_risk": TURBIDITY_CLOG_RISK,
                "film_harvest_level": FILM_HARVEST_LEVEL,
            },
        }
    )


@app.route("/manual_lock", methods=["POST"])
def manual_lock():
    global manual_lockout
    payload = request.get_json(silent=True) or {}
    manual_lockout = bool(payload.get("locked", True))
    return jsonify({"manual_lockout": manual_lockout})


@app.route("/capture-image", methods=["POST"])
def capture_image():
    payload = request.get_json(silent=True) or {}
    image_data = str(payload.get("image_data", ""))
    metrics = payload.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}

    if not image_data.startswith("data:image/") or ";base64," not in image_data:
        return jsonify({"error": "invalid image data"}), 400

    header, encoded = image_data.split(";base64,", 1)
    image_kind = header.replace("data:image/", "").split(";")[0].lower()
    ext = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp"}.get(image_kind, "jpg")

    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except Exception:
        return jsonify({"error": "invalid base64 image"}), 400

    if len(image_bytes) > 6 * 1024 * 1024:
        return jsonify({"error": "image too large"}), 413

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    module_id = clean_id(payload.get("module_id"), "web-camera")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = safe_image_filename(f"{timestamp}_{module_id}.{ext}")
    path = IMAGE_DIR / filename
    path.write_bytes(image_bytes)

    analysis = analyze_image_metrics(metrics)
    record = {
        "module_id": module_id,
        "time": datetime.now().strftime("%H:%M:%S"),
        "filename": filename,
        "url": f"/water_images/{filename}",
        "metrics": {
            "brightness": round(metric_number(metrics, "brightness"), 1),
            "contrast": round(metric_number(metrics, "contrast"), 1),
            "green_ratio": round(metric_number(metrics, "green_ratio"), 3),
            "brown_ratio": round(metric_number(metrics, "brown_ratio"), 3),
            "dark_ratio": round(metric_number(metrics, "dark_ratio"), 3),
            "avg_red": round(metric_number(metrics, "avg_red"), 1),
            "avg_green": round(metric_number(metrics, "avg_green"), 1),
            "avg_blue": round(metric_number(metrics, "avg_blue"), 1),
        },
        "analysis": analysis,
    }
    image_history.appendleft(record)
    return jsonify(record)


@app.route("/image_data", methods=["GET"])
def image_data():
    return jsonify({"images": list(image_history)})


@app.route("/water_images/<filename>", methods=["GET"])
def water_image(filename: str):
    safe_name = safe_image_filename(filename)
    if safe_name != filename:
        abort(404)
    path = IMAGE_DIR / safe_name
    if not path.exists():
        abort(404)
    return send_file(path)


@app.route("/simulate", methods=["POST"])
def simulate():
    payload = request.get_json(silent=True) or {}
    scenario = payload.get("scenario", "treat")

    samples = {
        "clear": {"dissolved_o2": 7.1, "ph": 7.4, "turbidity": 28, "sunlight": 75, "temperature_c": 28, "film_density": 35},
        "treat": {"dissolved_o2": 4.4, "ph": 7.2, "turbidity": 46, "sunlight": 72, "temperature_c": 29, "film_density": 42},
        "dark": {"dissolved_o2": 4.1, "ph": 7.1, "turbidity": 35, "sunlight": 12, "temperature_c": 27, "film_density": 40},
        "clog": {"dissolved_o2": 5.6, "ph": 7.4, "turbidity": 104, "sunlight": 64, "temperature_c": 28, "film_density": 50},
        "ph_bad": {"dissolved_o2": 5.5, "ph": 9.3, "turbidity": 30, "sunlight": 70, "temperature_c": 29, "film_density": 30},
        "maintenance": {"dissolved_o2": 6.0, "ph": 7.3, "turbidity": 42, "sunlight": 78, "temperature_c": 29, "film_density": 91},
    }

    sample = {
        "array_id": "demo-array",
        "module_id": f"demo-{scenario}",
        "report_reason": "web_demo",
        "sensor_interval_seconds": 10,
        "normal_report_interval_seconds": 60,
        "response_format": "json",
    }
    sample.update(samples.get(scenario, samples["treat"]))
    record = process_payload(sample)
    return jsonify(record)


@app.route("/tabler-icons.min.css", methods=["GET"])
def tabler_icons():
    for path in TABLER_CSS_PATHS:
        if path.exists():
            return send_file(path, mimetype="text/css")
    abort(404)


@app.route("/", methods=["GET"])
def dashboard():
    return r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Modular Algae Buoy</title>
<link rel="stylesheet" href="/tabler-icons.min.css">
<style>
* { box-sizing: border-box; }
:root {
  --bg: #dcefd2;
  --panel: #fbfff6;
  --panel2: #ecf8df;
  --panel3: #d7edc8;
  --line: #9fc889;
  --text: #102413;
  --muted: #587149;
  --green: #2f8a2f;
  --green-strong: #155c22;
  --green-bg: #d9f2d2;
  --leaf: #5faa35;
  --leaf-bg: #e8f7d9;
  --mint: #8ac85a;
  --mint-bg: #f0f9e8;
  --teal: #147c5e;
  --teal-bg: #dcf2e8;
  --blue: #1f7778;
  --blue-bg: #dff1eb;
  --amber: #9b6816;
  --amber-bg: #f8efd8;
  --red: #a23934;
  --red-bg: #fae5e2;
  --radius: 8px;
}
body {
  margin: 0;
  background:
    radial-gradient(circle at 12% 0%, rgba(143, 206, 95, .38), transparent 34%),
    radial-gradient(circle at 88% 8%, rgba(37, 126, 78, .18), transparent 32%),
    linear-gradient(180deg, #d7efc7 0%, #e9f7d9 46%, #f8fbef 100%);
  color: var(--text);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
button {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: linear-gradient(180deg, #fbfff6 0%, #e8f6d8 100%);
  color: var(--text);
  min-height: 36px;
  padding: 0 12px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font: inherit;
  box-shadow: 0 1px 0 rgba(16, 36, 23, .04);
}
button:hover { background: linear-gradient(180deg, #f3fde9 0%, #d8f0c5 100%); border-color: #78b85f; }
button:disabled {
  cursor: not-allowed;
  opacity: .55;
  background: #eef4e8;
}
.upload-button {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: linear-gradient(180deg, #fbfff6 0%, #e8f6d8 100%);
  color: var(--text);
  min-height: 36px;
  padding: 0 12px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font: inherit;
}
.upload-button:hover { background: linear-gradient(180deg, #f3fde9 0%, #d8f0c5 100%); border-color: #78b85f; }
.app { width: min(1180px, 100%); margin: 0 auto; padding: 18px; }
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 14px;
  padding: 14px;
  background: linear-gradient(180deg, rgba(251, 255, 246, .92), rgba(230, 246, 213, .86));
  border: 1px solid rgba(139, 190, 111, .9);
  border-radius: var(--radius);
  box-shadow: 0 12px 34px rgba(21, 92, 34, .10);
}
.brand { display: flex; align-items: center; gap: 10px; }
.brand i { color: var(--green-strong); font-size: 25px; }
.title { font-size: 20px; font-weight: 800; }
.sub { color: var(--muted); font-size: 12px; }
.actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
.button-help {
  flex: 1 0 100%;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}
.help-chip {
  border: 1px solid rgba(159, 200, 137, .85);
  background: rgba(251, 255, 246, .72);
  border-radius: var(--radius);
  padding: 8px 10px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.35;
}
.help-chip strong {
  color: var(--green-strong);
  margin-right: 4px;
}
.active-help {
  flex: 1 0 100%;
  border-left: 4px solid var(--green);
  background: rgba(223, 243, 210, .9);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 13px;
  line-height: 1.4;
  padding: 9px 11px;
  margin-top: 8px;
}
.active-help strong { color: var(--green-strong); }
.summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}
.tile, .module, .history {
  background: linear-gradient(180deg, var(--panel) 0%, #f0f9e7 100%);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: 0 10px 28px rgba(32, 122, 61, .08);
}
.tile {
  padding: 14px;
  min-height: 88px;
  background: linear-gradient(180deg, #fbfff5 0%, #dff2cc 100%);
}
.label {
  font-size: 11px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .06em;
  font-weight: 800;
}
.big { margin-top: 9px; font-size: 26px; font-weight: 850; line-height: 1; color: var(--green-strong); }
.module-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}
.module {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
  padding: 15px;
  background:
    linear-gradient(180deg, #fbfff6 0%, #e9f7dc 100%);
}
.module-step {
  min-height: 58px;
  border-radius: var(--radius);
  background: linear-gradient(180deg, var(--green), var(--green-strong));
  color: #ffffff;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 18px rgba(21, 92, 34, .18);
}
.module-step span { font-size: 24px; font-weight: 900; line-height: 1; }
.module-step small { font-size: 10px; font-weight: 800; margin-top: 4px; opacity: .86; }
.module-content { min-width: 0; }
.module-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.module-id { font-size: 16px; font-weight: 800; overflow-wrap: anywhere; }
.command {
  border-radius: var(--radius);
  padding: 5px 9px;
  font-size: 12px;
  font-weight: 850;
  white-space: nowrap;
}
.TREAT { background: var(--teal-bg); color: var(--teal); }
.FLUSH { background: var(--green-bg); color: var(--green-strong); }
.HOLD { background: var(--amber-bg); color: var(--amber); }
.LOCKOUT { background: var(--red-bg); color: var(--red); }
.metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}
.metric {
  background: linear-gradient(180deg, #f8fff2 0%, #e2f4d4 100%);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 10px;
}
.metric strong { display: block; margin-top: 6px; font-size: 18px; color: var(--green-strong); }
.reason { color: var(--muted); font-size: 13px; line-height: 1.45; margin-top: 12px; }
.reason.result {
  background: rgba(220, 242, 208, .78);
  border: 1px solid rgba(159, 200, 137, .85);
  border-radius: var(--radius);
  color: #234a21;
  padding: 9px 10px;
}
.state-line {
  color: #3f6732;
  font-size: 13px;
  line-height: 1.45;
  margin-top: 9px;
}
.state-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin-top: 9px;
}
.architecture {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0 18px;
}
.arch-card {
  background: linear-gradient(180deg, rgba(255,255,255,.82) 0%, rgba(233,247,217,.92) 100%);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px;
}
.arch-card strong { display: block; margin-bottom: 4px; color: var(--green-strong); }
.arch-card span { color: var(--muted); font-size: 13px; line-height: 1.45; }
.state-item {
  background: rgba(251, 255, 246, .68);
  border: 1px solid rgba(159, 200, 137, .72);
  border-radius: var(--radius);
  padding: 8px 10px;
}
.state-item span {
  display: block;
  color: var(--muted);
  font-size: 10px;
  font-weight: 850;
  letter-spacing: .05em;
  text-transform: uppercase;
}
.state-item strong {
  display: block;
  color: var(--green-strong);
  font-size: 13px;
  margin-top: 4px;
  overflow-wrap: anywhere;
}
.section-title {
  margin: 18px 0 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.section-title > div { min-width: 0; }
.section-hint {
  color: var(--muted);
  font-size: 12px;
  margin-top: 3px;
}
.section-title strong {
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .06em;
  font-size: 12px;
}
.history { overflow: hidden; }
.image-panel {
  background: linear-gradient(180deg, var(--panel) 0%, #edf8e2 100%);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: 0 10px 28px rgba(32, 122, 61, .08);
  padding: 14px;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, .95fr);
  gap: 14px;
  margin-bottom: 14px;
}
.camera-box video,
.camera-box canvas,
.image-result img {
  width: 100%;
  aspect-ratio: 16 / 9;
  display: block;
  border: 1px solid rgba(159, 200, 137, .85);
  border-radius: var(--radius);
  background: #102413;
  object-fit: cover;
}
.camera-box canvas { display: none; }
.capture-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}
.image-result {
  display: grid;
  gap: 10px;
}
.image-status {
  background: rgba(220, 242, 208, .78);
  border: 1px solid rgba(159, 200, 137, .85);
  border-radius: var(--radius);
  padding: 10px;
}
.image-status strong {
  display: block;
  color: var(--green-strong);
  font-size: 16px;
  margin-bottom: 5px;
}
.image-status p {
  color: var(--muted);
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.45;
}
.image-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.image-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}
.image-item {
  display: grid;
  grid-template-columns: 84px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  background: rgba(251, 255, 246, .68);
  border: 1px solid rgba(159, 200, 137, .72);
  border-radius: var(--radius);
  padding: 8px;
}
.image-item img {
  width: 84px;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--line);
}
.image-item strong {
  display: block;
  color: var(--green-strong);
  font-size: 13px;
}
.image-item span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  margin-top: 3px;
}
.row {
  display: grid;
  grid-template-columns: 170px 130px 1fr 90px 90px 90px;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  font-size: 13px;
}
.row:last-child { border-bottom: 0; }
.empty { padding: 28px; text-align: center; color: var(--muted); }
@media (max-width: 860px) {
  .topbar { align-items: flex-start; flex-direction: column; }
  .button-help { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .architecture { grid-template-columns: 1fr; }
  .summary, .module-grid { grid-template-columns: 1fr; }
  .image-panel { grid-template-columns: 1fr; }
  .metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .state-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .row { grid-template-columns: 1fr; align-items: start; }
  .row .command { justify-self: start; }
  .hide-sm { display: none; }
}
@media (max-width: 480px) {
  .app { padding: 12px; }
  .actions { width: 100%; }
  button { flex: 1; justify-content: center; }
  .button-help { grid-template-columns: 1fr; }
  .module { grid-template-columns: 1fr; }
  .module-step { flex-direction: row; gap: 6px; min-height: 40px; justify-content: flex-start; padding: 0 12px; }
  .metrics, .state-grid, .image-metrics { grid-template-columns: 1fr; }
  .image-item { grid-template-columns: 1fr; }
  .image-item img { width: 100%; }
}
</style>
</head>
<body>
<main class="app">
  <div class="topbar">
    <div class="brand">
      <i class="ti ti-circuit-bulb"></i>
      <div>
        <div class="title">AI-Controlled Modular Microalgae Biofilter</div>
        <div class="sub" id="connection">Waiting for module data</div>
      </div>
    </div>
    <div class="actions">
      <button data-sim="clear" title="จำลองน้ำคุณภาพดี ระบบจะ HOLD เพื่อประหยัดพลังงาน"><i class="ti ti-check"></i><span>Clear</span></button>
      <button data-sim="treat" title="จำลองออกซิเจนต่ำและแสงดี ระบบจะเพิ่มการไหลผ่านส่วนบำบัด"><i class="ti ti-activity-heartbeat"></i><span>Treat</span></button>
      <button data-sim="dark" title="จำลองออกซิเจนต่ำแต่แสงน้อย ระบบจะใช้โหมดเติมอากาศแทนการพึ่งสาหร่าย"><i class="ti ti-moon"></i><span>Dark</span></button>
      <button data-sim="clog" title="จำลองน้ำขุ่นมาก ระบบจะลด flow เพื่อป้องกันการอุดตัน"><i class="ti ti-filter"></i><span>Clog</span></button>
      <button data-sim="ph_bad" title="จำลอง pH ผิดปกติ ระบบจะ LOCKOUT เพื่อความปลอดภัย"><i class="ti ti-alert-triangle"></i><span>pH</span></button>
      <button data-sim="maintenance" title="จำลองฟิล์มสาหร่ายหนาแน่น ระบบจะแจ้งเตือนให้เก็บเกี่ยวหรือเปลี่ยนฟิล์ม"><i class="ti ti-tool"></i><span>Service</span></button>
      <button id="lock" title="ล็อกหรือปลดล็อกระบบ เพื่อหยุด actuator ทั้งหมดแบบ manual"><i class="ti ti-lock"></i><span>Lock</span></button>
      <div class="button-help" aria-label="คำอธิบายปุ่มจำลองสถานการณ์">
        <div class="help-chip"><strong>Clear</strong>clean water, stay on hold</div>
        <div class="help-chip"><strong>Treat</strong>run the treatment chamber</div>
        <div class="help-chip"><strong>Dark</strong>low light, add support air</div>
        <div class="help-chip"><strong>Clog</strong>flush intake and tubing</div>
        <div class="help-chip"><strong>pH</strong>unsafe water, stop the system</div>
        <div class="help-chip"><strong>Service</strong>maintenance alert</div>
        <div class="help-chip"><strong>Lock</strong>manual lockout</div>
      </div>
      <div class="active-help" id="active-help"><strong>Simulation buttons:</strong> test how the prototype chooses TREAT, FLUSH, HOLD, or LOCKOUT.</div>
    </div>
  </div>

  <section class="architecture">
    <div class="arch-card"><strong>Sealed Algae Cartridge</strong><span>Upper chamber for closed microalgae culture. It receives sunlight and keeps algae inside the module.</span></div>
    <div class="arch-card"><strong>Treatment Chamber</strong><span>Lower chamber for intake flow, filter media, and contact surfaces that improve water before release.</span></div>
    <div class="arch-card"><strong>Sensor + AI Control</strong><span>ESP32 reads water sensors and sends the data to the AI dashboard, which decides TREAT, FLUSH, HOLD, or LOCKOUT.</span></div>
  </section>

  <section class="summary">
    <div class="tile"><div class="label">โมดูลออนไลน์</div><div class="big" id="module-count">0</div></div>
    <div class="tile"><div class="label">ค่า DO เฉลี่ย</div><div class="big" id="avg-do">--</div></div>
    <div class="tile"><div class="label">กำลังบำบัด</div><div class="big" id="active-count">0</div></div>
    <div class="tile"><div class="label">การแจ้งเตือน</div><div class="big" id="alert-count">0</div></div>
  </section>

  <div class="section-title">
    <div>
      <strong>โมดูลทุ่นลอยน้ำ</strong>
      <div class="section-hint">เรียงจากข้อมูลล่าสุดลงไป เลข 1 คือโมดูลที่เพิ่งรายงานล่าสุด</div>
    </div>
    <span class="sub" id="updated">Updated --</span>
  </div>
  <section class="module-grid" id="modules">
    <div class="empty">ยังไม่มีข้อมูลจากโมดูล</div>
  </section>

  <div class="section-title">
    <div>
      <strong>วิเคราะห์ภาพแหล่งน้ำ</strong>
      <div class="section-hint">เปิดกล้องหรืออัปโหลดรูปเพื่อให้ระบบช่วยประเมินสี ความขุ่น และโอกาสพบสาหร่ายจากภาพ</div>
    </div>
    <span class="sub" id="image-count">0 รูป</span>
  </div>
  <section class="image-panel">
    <div class="camera-box">
      <video id="camera" autoplay playsinline muted></video>
      <canvas id="capture-canvas"></canvas>
      <div class="capture-actions">
        <button id="start-camera" type="button"><i class="ti ti-camera"></i><span>เปิดกล้อง</span></button>
        <button id="capture-photo" type="button"><i class="ti ti-photo"></i><span>ถ่ายและวิเคราะห์</span></button>
        <button id="stop-camera" type="button"><i class="ti ti-camera-off"></i><span>ปิดกล้อง</span></button>
        <label class="upload-button">
          <input id="image-upload" type="file" accept="image/*" capture="environment" hidden>
          <span><i class="ti ti-upload"></i> ถ่าย/อัปโหลดจากเครื่อง</span>
        </label>
      </div>
      <div class="section-hint">รูปจะถูกเก็บไว้ในโฟลเดอร์ D:\AlgaeBioreactor\water_images เมื่อรันจากไดรฟ์ D</div>
    </div>
    <div class="image-result">
      <div class="image-status" id="image-analysis">
        <strong>ยังไม่มีภาพให้วิเคราะห์</strong>
        <p>เมื่อถ่ายรูปแล้ว ระบบจะประเมินความสว่าง โทนเขียว โทนน้ำตาล และความเสี่ยงเบื้องต้นจากภาพ</p>
      </div>
      <div class="image-metrics" id="image-metrics"></div>
      <div class="image-list" id="image-list"></div>
    </div>
  </section>

  <div class="section-title">
    <strong>ประวัติการตัดสินใจ</strong>
    <span class="sub" id="history-count">0 รายการ</span>
  </div>
  <section class="history" id="history">
    <div class="empty">ยังไม่มีประวัติการตัดสินใจ</div>
  </section>
</main>

<script>
const $ = (id) => document.getElementById(id);
const activeCommands = new Set(['TREAT', 'FLUSH']);
const helpDescriptions = {
  clear: '<strong>Clear:</strong> clean water sample; the prototype should stay in HOLD mode.',
  treat: '<strong>Treat:</strong> water needs treatment; the pump should move water through the treatment chamber.',
  dark: '<strong>Dark:</strong> low light and low oxygen; the module still treats water and can use backup aeration.',
  clog: '<strong>Clog:</strong> intake or filter path is getting blocked; the system should run a short FLUSH cycle.',
  ph_bad: '<strong>pH:</strong> pH is unsafe; the system should enter LOCKOUT.',
  maintenance: '<strong>Service:</strong> algae cartridge is too dense; the system should raise a maintenance alert.',
  lock: '<strong>Lock:</strong> manual lockout disables the actuators for safety.'
};

function setActiveHelp(key) {
  const el = $('active-help');
  if (el && helpDescriptions[key]) {
    el.innerHTML = helpDescriptions[key];
  }
}

function n(value, digits = 1) {
  return Number(value || 0).toFixed(digits);
}

function commandClass(command) {
  return command || 'HOLD';
}

function commandText(command) {
  return {
    TREAT: 'Treat water',
    FLUSH: 'Flush intake',
    HOLD: 'Hold',
    LOCKOUT: 'Safety lockout'
  }[command] || command || 'Hold';
}

function flowText(value) {
  return {
    TREAT: 'Treatment flow',
    FLUSH: 'Flush cycle',
    OFF: 'Off'
  }[value] || value || '-';
}

function growthText(value) {
  return {
    SEALED_GROW: 'Closed algae growth',
    LOW_LIGHT_SUPPORT: 'Low-light support',
    MAINTENANCE: 'Maintenance required',
    IDLE: 'Idle'
  }[value] || value || '-';
}

function alertText(value) {
  return {
    NONE: 'None',
    SENSOR_CHECK: 'Check sensors',
    MANUAL_LOCKOUT: 'Manual lockout',
    PH_ABNORMAL: 'Unsafe pH',
    CLEAN_INTAKE: 'Clean intake',
    LOW_DO: 'Low oxygen',
    HARVEST_BIOFILM: 'Service algae cartridge'
  }[value] || value || 'None';
}

function reportReasonText(value) {
  const key = String(value || 'unknown').replace('_repeat', '');
  const suffix = String(value || '').endsWith('_repeat') ? ' (รายงานซ้ำเพราะยังอยู่ในภาวะเสี่ยง)' : '';
  return ({
    first_report: 'รายงานครั้งแรกหลังเปิดระบบ',
    scheduled_60s: 'รายงานตามรอบ 60 วินาที',
    web_demo: 'ข้อมูลจำลองจากปุ่มบนเว็บ',
    do_changed: 'ค่า DO เปลี่ยนเกิน 0.3 mg/L',
    ph_changed: 'ค่า pH เปลี่ยนเกิน 0.2',
    turbidity_changed: 'ความขุ่นเปลี่ยนเกิน 10 NTU',
    sunlight_changed: 'แสงเปลี่ยนเกิน 15%',
    temperature_changed: 'อุณหภูมิเปลี่ยนเกิน 1 C',
    film_changed: 'ฟิล์มสาหร่ายเปลี่ยนเกิน 5%',
    alert_do_critical: 'DO ต่ำวิกฤต',
    alert_do_low: 'DO ต่ำกว่าเกณฑ์',
    alert_ph_out_of_range: 'pH หลุดช่วงปลอดภัย',
    alert_turbidity_high: 'ความขุ่นสูง เสี่ยงอุดตัน',
    alert_film_dense: 'ฟิล์มสาหร่ายหนาแน่น'
  }[key] || value || 'ไม่ทราบสาเหตุ') + suffix;
}

function reasonText(reason) {
  if (!reason) return 'ยังไม่มีเหตุผลจากระบบ';
  return reason
    .split(';')
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      if (part.includes('cooldown active')) return part.replace(/cooldown active for (\d+)s/, 'ระบบกำลังพักปั๊มอีก $1 วินาที');
      if (part.includes('manual lockout is enabled')) return 'เปิดโหมดล็อกด้วยมืออยู่ ระบบจึงไม่สั่ง actuator';
      if (part.includes('pH') && part.includes('outside')) return part.replace(/pH ([0-9.]+) is outside ([0-9.]+)-([0-9.]+)/, 'ค่า pH $1 อยู่นอกช่วงปลอดภัย $2-$3');
      if (part.includes('turbidity') && part.includes('too high')) return part.replace(/turbidity ([0-9.]+) NTU is too high/, 'ความขุ่น $1 NTU สูงเกินไป ระบบหยุดเพื่อป้องกันความเสียหาย');
      if (part.includes('algae biofilm is dense')) return 'ฟิล์มสาหร่ายหนาแน่น ควรเก็บเกี่ยวหรือเปลี่ยนแผ่นฟิล์มเร็ว ๆ นี้';
      if (part.includes('water is very turbid')) return 'น้ำขุ่นมาก ระบบลดอัตราการไหลเพื่อป้องกันการอุดตัน';
      if (part.includes('DO is critical and sunlight is low')) return 'ออกซิเจนต่ำมากและแสงน้อย ระบบใช้การเติมอากาศเสริม';
      if (part.includes('DO is low but light is weak')) return 'ออกซิเจนต่ำแต่แสงไม่พอ ระบบลดการพึ่งพาไมโครแอลจีและใช้การเติมอากาศ';
      if (part.includes('DO is critical and sunlight can support')) return 'ออกซิเจนต่ำมากและมีแสงเพียงพอ ระบบเพิ่มการไหลผ่านส่วนบำบัด';
      if (part.includes('DO is low and sunlight is enough')) return 'ออกซิเจนต่ำและมีแสงพอ ระบบเพิ่มการไหลผ่านส่วนบำบัด';
      if (part.includes('DO is slightly low')) return 'ออกซิเจนต่ำเล็กน้อย ระบบเดิน flow ระดับปานกลาง';
      if (part.includes('water quality is acceptable')) return 'คุณภาพน้ำอยู่ในเกณฑ์ ระบบพักเพื่อประหยัดพลังงาน';
      if (part.includes('sensor value is impossible')) return 'ค่าจากเซนเซอร์ผิดปกติ ควรตรวจสอบสายไฟหรือการสอบเทียบ';
      return part;
    })
    .join('; ');
}

function metric(label, value, unit) {
  return `<div class="metric"><span class="label">${label}</span><strong>${value}${unit ? ' ' + unit : ''}</strong></div>`;
}

let cameraStream = null;

function cameraSupported() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
}

function setupCameraSupport() {
  if (cameraSupported()) {
    return;
  }
  $('start-camera').disabled = true;
  $('capture-photo').disabled = true;
  $('stop-camera').disabled = true;
  renderImageMessage(
    'Browser นี้ไม่รองรับกล้องโดยตรง',
    'ยังใช้งานได้โดยกด “ถ่าย/อัปโหลดจากเครื่อง” แทน ถ้าใช้มือถือปุ่มนี้มักจะเปิดกล้องให้ถ่ายรูปได้ หรือเปิดเว็บนี้ใน Chrome/Edge'
  );
}

async function startCamera() {
  const video = $('camera');
  if (!cameraSupported()) {
    setupCameraSupport();
    return;
  }
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } },
      audio: false
    });
    video.srcObject = cameraStream;
    renderImageMessage('เปิดกล้องแล้ว', 'เล็งไปที่ผิวน้ำหรือแหล่งน้ำ แล้วกด “ถ่ายและวิเคราะห์”');
  } catch (error) {
    renderImageMessage(
      'เปิดกล้องไม่ได้',
      'กรุณาอนุญาตการใช้กล้อง หรือใช้ปุ่ม “ถ่าย/อัปโหลดจากเครื่อง” แทน ถ้าเปิดผ่าน IP บนมือถือ กล้องอาจถูกบล็อกเพราะไม่ใช่ HTTPS'
    );
  }
}

function stopCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach((track) => track.stop());
    cameraStream = null;
  }
  $('camera').srcObject = null;
  renderImageMessage('ปิดกล้องแล้ว', 'สามารถเปิดกล้องใหม่หรืออัปโหลดรูปเพื่อวิเคราะห์ได้');
}

function drawVideoToCanvas() {
  const video = $('camera');
  const canvas = $('capture-canvas');
  const width = video.videoWidth || 1280;
  const height = video.videoHeight || 720;
  canvas.width = width;
  canvas.height = height;
  canvas.getContext('2d').drawImage(video, 0, 0, width, height);
  return canvas;
}

function analyzeCanvas(canvas) {
  const ctx = canvas.getContext('2d');
  const { data, width, height } = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const step = 16;
  let count = 0;
  let red = 0;
  let green = 0;
  let blue = 0;
  let brightness = 0;
  let brightnessSq = 0;
  let greenPixels = 0;
  let brownPixels = 0;
  let darkPixels = 0;

  for (let i = 0; i < data.length; i += 4 * step) {
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    const y = (r + g + b) / 3;
    red += r;
    green += g;
    blue += b;
    brightness += y;
    brightnessSq += y * y;
    if (g > r * 1.08 && g > b * 1.05 && g > 70) greenPixels++;
    if (r > 75 && g > 45 && b < 105 && r > b * 1.25) brownPixels++;
    if (y < 50) darkPixels++;
    count++;
  }

  const avgBrightness = brightness / count;
  const variance = Math.max(0, (brightnessSq / count) - (avgBrightness * avgBrightness));
  return {
    width,
    height,
    avg_red: red / count,
    avg_green: green / count,
    avg_blue: blue / count,
    brightness: avgBrightness,
    contrast: Math.sqrt(variance),
    green_ratio: greenPixels / count,
    brown_ratio: brownPixels / count,
    dark_ratio: darkPixels / count
  };
}

function renderImageMessage(title, body) {
  $('image-analysis').innerHTML = `<strong>${title}</strong><p>${body}</p>`;
}

function renderImageRecord(record) {
  const analysis = record.analysis || {};
  const metrics = record.metrics || {};
  $('image-analysis').innerHTML = `
    <strong>${analysis.status || 'วิเคราะห์ภาพแล้ว'} | ความเสี่ยง ${analysis.risk || '-'}</strong>
    <p>${analysis.reason || ''}</p>
    <p>${analysis.recommendation || ''}</p>
  `;
  $('image-metrics').innerHTML = `
    ${metric('คะแนนภาพ', analysis.score ?? '--', '')}
    ${metric('ความสว่าง', n(metrics.brightness), '')}
    ${metric('โทนเขียว', Math.round((metrics.green_ratio || 0) * 100), '%')}
    ${metric('โทนน้ำตาล', Math.round((metrics.brown_ratio || 0) * 100), '%')}
    ${metric('ภาพมืด', Math.round((metrics.dark_ratio || 0) * 100), '%')}
    ${metric('contrast', n(metrics.contrast), '')}
  `;
}

async function uploadCanvasImage(canvas) {
  const metrics = analyzeCanvas(canvas);
  const imageData = canvas.toDataURL('image/jpeg', 0.82);
  const res = await fetch('/capture-image', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      module_id: 'web-camera',
      image_data: imageData,
      metrics
    })
  });
  if (!res.ok) {
    renderImageMessage('บันทึกรูปไม่สำเร็จ', 'server ไม่สามารถรับรูปภาพนี้ได้');
    return;
  }
  const record = await res.json();
  renderImageRecord(record);
  poll();
}

async function capturePhoto() {
  const video = $('camera');
  if (!cameraStream || !video.videoWidth) {
    renderImageMessage('ยังไม่ได้เปิดกล้อง', 'กดเปิดกล้องก่อน หรือใช้อัปโหลดรูปแทน');
    return;
  }
  await uploadCanvasImage(drawVideoToCanvas());
}

function loadUploadFile(file) {
  if (!file) return;
  const img = new Image();
  img.onload = async () => {
    const canvas = $('capture-canvas');
    canvas.width = img.naturalWidth || img.width;
    canvas.height = img.naturalHeight || img.height;
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
    URL.revokeObjectURL(img.src);
    await uploadCanvasImage(canvas);
  };
  img.src = URL.createObjectURL(file);
}

function renderImageHistory(images) {
  $('image-count').textContent = (images || []).length + ' รูป';
  if (!images || !images.length) {
    $('image-list').innerHTML = '';
    return;
  }
  $('image-list').innerHTML = images.slice(0, 4).map((item) => `
    <div class="image-item">
      <img src="${item.url}" alt="water image">
      <div>
        <strong>${item.analysis?.status || 'ภาพแหล่งน้ำ'} | ${item.time}</strong>
        <span>ความเสี่ยง ${item.analysis?.risk || '-'} | คะแนน ${item.analysis?.score ?? '-'}</span>
        <span>${item.analysis?.reason || ''}</span>
      </div>
    </div>
  `).join('');
}

function timeValue(timeText) {
  const parts = String(timeText || '00:00:00').split(':').map((part) => Number(part) || 0);
  return (parts[0] * 3600) + (parts[1] * 60) + parts[2];
}

function latestFirst(items) {
  return [...(items || [])].sort((a, b) => {
    const seqDiff = Number(b.sequence || 0) - Number(a.sequence || 0);
    return seqDiff || (timeValue(b.time) - timeValue(a.time));
  });
}

function renderModules(items) {
  if (!items || !items.length) {
    $('modules').innerHTML = '<div class="empty">ยังไม่มีข้อมูลจากโมดูล</div>';
    return;
  }

  $('modules').innerHTML = latestFirst(items).map((m, index) => `
    <article class="module">
      <div class="module-step"><span>${index + 1}</span><small>ลำดับ</small></div>
      <div class="module-content">
        <div class="module-head">
          <div>
            <div class="module-id">${m.module_id}</div>
            <div class="sub">${m.array_id} | อัปเดต ${m.time}</div>
          </div>
          <span class="command ${commandClass(m.command)}">${commandText(m.command)}</span>
        </div>
        <div class="metrics">
          ${metric('DO', n(m.dissolved_o2), 'mg/L')}
          ${metric('pH', n(m.ph), '')}
          ${metric('ความขุ่น', Math.round(m.turbidity || 0), 'NTU')}
          ${metric('แสง', Math.round(m.sunlight || 0), '%')}
          ${metric('อุณหภูมิ', n(m.temperature_c), 'C')}
          ${metric('ฟิล์ม', Math.round(m.film_density || 0), '%')}
        </div>
        <div class="reason result">${reasonText(m.reason)}</div>
        <div class="state-grid">
          <div class="state-item"><span>การไหล</span><strong>${flowText(m.flow_level)}</strong></div>
          <div class="state-item"><span>โหมดสาหร่าย</span><strong>${growthText(m.growth_mode)}</strong></div>
          <div class="state-item"><span>แจ้งเตือน</span><strong>${alertText(m.alert)}</strong></div>
          <div class="state-item"><span>คะแนนน้ำ</span><strong>${m.quality_score}</strong></div>
          <div class="state-item"><span>รายงานเพราะ</span><strong>${reportReasonText(m.report_reason)}</strong></div>
        </div>
      </div>
    </article>
  `).join('');
}

function renderHistory(items) {
  $('history-count').textContent = (items || []).length + ' รายการ';
  if (!items || !items.length) {
    $('history').innerHTML = '<div class="empty">ยังไม่มีประวัติการตัดสินใจ</div>';
    return;
  }

  $('history').innerHTML = items.slice(0, 28).map((m) => `
    <div class="row">
      <span class="command ${commandClass(m.command)}">${commandText(m.command)}</span>
      <span>${m.module_id}</span>
      <span>${reasonText(m.reason)}</span>
      <span class="hide-sm">DO ${n(m.dissolved_o2)}</span>
      <span class="hide-sm">pH ${n(m.ph)}</span>
      <span class="hide-sm">${m.time}</span>
    </div>
  `).join('');
}

function renderSummary(data) {
  const modules = latestFirst(data.modules || []);
  const avgDo = modules.length
    ? modules.reduce((sum, m) => sum + Number(m.dissolved_o2 || 0), 0) / modules.length
    : null;
  const active = modules.filter((m) => activeCommands.has(m.command)).length;
  const alerts = modules.filter((m) => m.alert && m.alert !== 'NONE').length;

  $('module-count').textContent = modules.length;
  $('avg-do').textContent = avgDo === null ? '--' : avgDo.toFixed(1);
  $('active-count').textContent = active;
  $('alert-count').textContent = alerts;
  $('updated').textContent = modules[0] ? 'อัปเดตล่าสุด ' + modules[0].time : 'ยังไม่มีข้อมูล';
  $('connection').textContent = modules.length ? 'เชื่อมต่อกับ AI server แล้ว' : 'รอข้อมูลจากโมดูล';
  $('lock').innerHTML = data.manual_lockout
    ? '<i class="ti ti-lock-open"></i><span>Unlock</span>'
    : '<i class="ti ti-lock"></i><span>Lock</span>';
}

async function poll() {
  try {
    const res = await fetch('/data');
    const data = await res.json();
    renderSummary(data);
    renderModules(data.modules);
    renderHistory(data.history);
    renderImageHistory(data.images);
  } catch (error) {
    $('connection').textContent = 'Server offline';
  }
}

document.querySelectorAll('[data-sim]').forEach((button) => {
  button.addEventListener('mouseenter', () => setActiveHelp(button.dataset.sim));
  button.addEventListener('focus', () => setActiveHelp(button.dataset.sim));
  button.addEventListener('click', async () => {
    setActiveHelp(button.dataset.sim);
    await fetch('/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenario: button.dataset.sim })
    });
    poll();
  });
});

$('lock').addEventListener('mouseenter', () => setActiveHelp('lock'));
$('lock').addEventListener('focus', () => setActiveHelp('lock'));
$('lock').addEventListener('click', async () => {
  setActiveHelp('lock');
  const locked = $('lock').textContent.trim() === 'Unlock';
  await fetch('/manual_lock', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ locked: !locked })
  });
  poll();
});

$('start-camera').addEventListener('click', startCamera);
$('capture-photo').addEventListener('click', capturePhoto);
$('stop-camera').addEventListener('click', stopCamera);
$('image-upload').addEventListener('change', (event) => {
  loadUploadFile(event.target.files && event.target.files[0]);
  event.target.value = '';
});

setupCameraSupport();
poll();
setInterval(poll, 10000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    print("=" * 64)
    print("  Modular Floating Microalgae Treatment Buoy")
    print("=" * 64)
    print("  Dashboard: http://localhost:5000")
    print("  ESP32 API: http://YOUR_LAPTOP_IP:5000/analyze")
    print("  Concept: closed algae module + controlled water treatment flow")
    print("=" * 64)
    app.run(host="0.0.0.0", port=5000, debug=False)
