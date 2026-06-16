"""
Backend API server for the GitHub Pages frontend.

Run:
    pip install -r requirements.txt
    python backend_api_server.py

This backend receives ESP32 sensor readings, decides what the buoy module
should do next, and exposes JSON endpoints for the GitHub Pages dashboard.
"""

from __future__ import annotations

import base64
from collections import deque
from datetime import datetime
from pathlib import Path
from time import time
from typing import Any

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS


app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
IMAGE_DIR = BASE_DIR / "water_images"

PH_MIN = 6.2
PH_MAX = 8.8
DO_CRITICAL = 3.0
DO_LOW = 5.0
DO_GOOD = 6.5
SUN_MIN_FOR_ALGAE = 35.0
TURBIDITY_CAUTION = 60.0
TURBIDITY_CLOG_RISK = 90.0
TURBIDITY_LOCKOUT = 130.0
TEMP_MIN = 15.0
TEMP_MAX = 36.0
FILM_HARVEST_LEVEL = 85.0
ACTIVE_COMMAND_COOLDOWN = 45

modules: dict[str, dict[str, Any]] = {}
history: deque[dict[str, Any]] = deque(maxlen=160)
image_history: deque[dict[str, Any]] = deque(maxlen=60)
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


def safe_id(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    cleaned = "".join(ch for ch in text if ch in allowed)
    return (cleaned or fallback)[:48]


def parse_reading(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "array_id": safe_id(payload.get("array_id"), "river-array-01"),
        "module_id": safe_id(payload.get("module_id"), "module-01"),
        "ph": number(payload, "ph", 7.0),
        "turbidity": number(payload, "turbidity", 0.0),
        "dissolved_o2": number(payload, "dissolved_o2", 0.0),
        "sunlight": number(payload, "sunlight", 0.0),
        "temperature_c": number(payload, "temperature_c", 25.0),
        "film_density": number(payload, "film_density", 0.0),
        "report_reason": str(payload.get("report_reason", "unknown"))[:64],
        "sensor_interval_seconds": number(payload, "sensor_interval_seconds", 10.0),
        "normal_report_interval_seconds": number(payload, "normal_report_interval_seconds", 60.0),
    }


def impossible_sensor_values(reading: dict[str, Any]) -> list[str]:
    issues = []
    if not 0.0 <= reading["ph"] <= 14.0:
        issues.append("pH sensor value is impossible")
    if not 0.0 <= reading["turbidity"] <= 3000.0:
        issues.append("Turbidity sensor value is impossible")
    if not 0.0 <= reading["dissolved_o2"] <= 20.0:
        issues.append("DO sensor value is impossible")
    if not 0.0 <= reading["sunlight"] <= 100.0:
        issues.append("Sunlight sensor value is impossible")
    if not -10.0 <= reading["temperature_c"] <= 60.0:
        issues.append("Temperature sensor value is impossible")
    if not 0.0 <= reading["film_density"] <= 100.0:
        issues.append("Film density value is impossible")
    return issues


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
    if decision["command"] not in {"TREAT", "FLUSH"}:
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
        decision.update(command_settings("HOLD"))
    else:
        last_active_command_at[module_id] = now
        decision["cooldown_remaining"] = 0


def decide(reading: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    impossible = impossible_sensor_values(reading)
    if impossible:
        decision = {
            "command": "LOCKOUT",
            "flow_level": "OFF",
            "growth_mode": "IDLE",
            "alert": "SENSOR_CHECK",
            "safety_state": "LOCKOUT",
            "reason": "; ".join(impossible),
            "quality_score": 0,
            "cooldown_remaining": 0,
        }
        decision.update(command_settings("LOCKOUT"))
        return decision

    ph_ok = PH_MIN <= reading["ph"] <= PH_MAX
    sun_ok = reading["sunlight"] >= SUN_MIN_FOR_ALGAE
    temp_ok = TEMP_MIN <= reading["temperature_c"] <= TEMP_MAX
    do_low = reading["dissolved_o2"] < DO_LOW
    do_critical = reading["dissolved_o2"] < DO_CRITICAL
    turbidity = reading["turbidity"]
    film_high = reading["film_density"] >= FILM_HARVEST_LEVEL

    command = "HOLD"
    flow_level = "OFF"
    growth_mode = "IDLE"
    alert = "NONE"
    safety_state = "OK"

    if manual_lockout:
        command = "LOCKOUT"
        alert = "MANUAL_LOCKOUT"
        safety_state = "LOCKOUT"
        reasons.append("manual lockout is enabled")
    elif not ph_ok:
        command = "LOCKOUT"
        alert = "PH_ABNORMAL"
        safety_state = "LOCKOUT"
        reasons.append(f"pH {reading['ph']:.2f} is outside {PH_MIN}-{PH_MAX}")
    elif turbidity >= TURBIDITY_LOCKOUT:
        command = "LOCKOUT"
        alert = "CLEAN_INTAKE"
        safety_state = "LOCKOUT"
        reasons.append(f"turbidity {turbidity:.0f} NTU is too high")
    else:
        if film_high:
            alert = "HARVEST_BIOFILM"
            growth_mode = "MAINTENANCE"
            reasons.append("sealed algae cartridge is dense; maintain or replace biofilm soon")

        if turbidity >= TURBIDITY_CLOG_RISK:
            command = "FLUSH"
            flow_level = "FLUSH"
            if alert == "NONE":
                alert = "CLEAN_INTAKE"
            reasons.append("intake path may be clogged by turbid water; run short flush cycle")
        elif do_low:
            command = "TREAT"
            flow_level = "TREAT"
            if do_critical:
                alert = "LOW_DO"
            reasons.append(
                "low dissolved oxygen detected; circulate water through the treatment chamber"
                if sun_ok
                else "low dissolved oxygen with weak light; run treatment flow with aeration support"
            )
        elif turbidity >= TURBIDITY_CAUTION:
            command = "TREAT"
            flow_level = "TREAT"
            reasons.append("moderate turbidity detected; run a normal treatment cycle")
        elif reading["dissolved_o2"] < DO_GOOD and sun_ok:
            command = "TREAT"
            flow_level = "TREAT"
            reasons.append("dissolved oxygen is slightly low; run a normal treatment cycle")
        else:
            reasons.append("water quality is acceptable; keep the module in monitoring mode")

        if growth_mode != "MAINTENANCE":
            if sun_ok and temp_ok:
                growth_mode = "SEALED_GROW"
            elif not sun_ok and temp_ok:
                growth_mode = "LOW_LIGHT_SUPPORT"

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
    reading_counter += 1
    record = {
        **reading,
        **decision,
        "sequence": reading_counter,
        "time": datetime.now().strftime("%H:%M:%S"),
    }
    modules[reading["module_id"]] = record
    history.appendleft(record.copy())
    return record


def metric_number(metrics: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(metrics.get(key, default))
    except (TypeError, ValueError):
        return default


def analyze_image_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    brightness = metric_number(metrics, "brightness")
    contrast = metric_number(metrics, "contrast")
    green_ratio = metric_number(metrics, "green_ratio")
    brown_ratio = metric_number(metrics, "brown_ratio")
    dark_ratio = metric_number(metrics, "dark_ratio")

    reasons: list[str] = []
    score = 100.0
    status = "Image looks normal"
    recommendation = "Combine image analysis with live DO, pH, and turbidity sensor readings."

    if brightness < 45 or dark_ratio > 0.55:
        status = "Image is too dark"
        reasons.append("lighting is too low for reliable visual analysis")
        recommendation = "Take another photo in brighter light."
        score -= 35
    if green_ratio > 0.18:
        status = "Strong green tone detected"
        reasons.append("water may contain algae, plant material, or heavy green reflection")
        recommendation = "Compare with dissolved oxygen and turbidity before deciding on treatment."
        score -= 18
    if brown_ratio > 0.16:
        status = "Brown or turbid tone detected"
        reasons.append("water may carry sediment or suspended solids")
        recommendation = "Compare with the turbidity sensor and consider slower treatment flow."
        score -= 22
    if contrast < 18 and brightness < 140:
        reasons.append("low contrast suggests cloudy water or a weak photo")
        score -= 8
    if not reasons:
        reasons.append("color and brightness are within a normal range")

    risk = "Low"
    if score < 55:
        risk = "High"
    elif score < 78:
        risk = "Medium"

    return {
        "status": status,
        "risk": risk,
        "score": round(clamp(score, 0, 100)),
        "reason": "; ".join(reasons),
        "recommendation": recommendation,
    }


def save_image_record(payload: dict[str, Any]) -> dict[str, Any]:
    image_data = str(payload.get("image_data", ""))
    metrics = payload.get("metrics") or {}
    if not isinstance(metrics, dict):
        metrics = {}
    if not image_data.startswith("data:image/") or ";base64," not in image_data:
        raise ValueError("invalid image data")

    header, encoded = image_data.split(";base64,", 1)
    image_kind = header.replace("data:image/", "").split(";")[0].lower()
    ext = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "webp": "webp"}.get(image_kind, "jpg")
    image_bytes = base64.b64decode(encoded, validate=True)
    if len(image_bytes) > 6 * 1024 * 1024:
        raise ValueError("image too large")

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    module_id = safe_id(payload.get("module_id"), "web-camera")
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{module_id}.{ext}"
    (IMAGE_DIR / filename).write_bytes(image_bytes)

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
        },
        "analysis": analyze_image_metrics(metrics),
    }
    image_history.appendleft(record)
    return record


def simulate_payload(scenario: str) -> dict[str, Any]:
    base = {
        "array_id": "demo-array",
        "module_id": f"demo-{scenario}",
        "ph": 7.2,
        "turbidity": 24.0,
        "dissolved_o2": 7.1,
        "sunlight": 76.0,
        "temperature_c": 28.0,
        "film_density": 35.0,
        "report_reason": "web_demo",
        "sensor_interval_seconds": 10,
        "normal_report_interval_seconds": 60,
    }
    if scenario == "treat":
        base.update({"dissolved_o2": 4.3, "sunlight": 80.0, "turbidity": 38.0})
    elif scenario == "dark":
        base.update({"dissolved_o2": 4.0, "sunlight": 10.0})
    elif scenario == "clog":
        base.update({"turbidity": 108.0})
    elif scenario == "ph_bad":
        base.update({"ph": 9.7})
    elif scenario == "maintenance":
        base.update({"film_density": 91.0, "dissolved_o2": 5.8, "turbidity": 42.0})
    return base


@app.get("/health")
def health() -> Any:
    return jsonify({"ok": True, "service": "microalgae-backend-api"})


@app.post("/analyze")
def analyze() -> Any:
    payload = request.get_json(silent=True) or {}
    if not payload:
        return jsonify({"error": "missing payload"}), 400
    record = process_payload(payload)
    if payload.get("response_format") == "json" or "application/json" in request.headers.get("Accept", ""):
        return jsonify(record)
    return record["command"]


@app.get("/data")
def data() -> Any:
    return jsonify(
        {
            "modules": list(modules.values()),
            "history": list(history),
            "images": list(image_history),
            "manual_lockout": manual_lockout,
        }
    )


@app.post("/simulate")
def simulate() -> Any:
    payload = request.get_json(silent=True) or {}
    scenario = str(payload.get("scenario", "clear"))
    record = process_payload(simulate_payload(scenario))
    return jsonify(record)


@app.post("/manual_lock")
def manual_lock() -> Any:
    global manual_lockout
    payload = request.get_json(silent=True) or {}
    manual_lockout = bool(payload.get("locked", True))
    return jsonify({"manual_lockout": manual_lockout})


@app.post("/capture-image")
def capture_image() -> Any:
    try:
        return jsonify(save_image_record(request.get_json(silent=True) or {}))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/image_data")
def image_data() -> Any:
    return jsonify({"images": list(image_history)})


@app.get("/water_images/<path:filename>")
def water_image(filename: str) -> Any:
    return send_from_directory(IMAGE_DIR, filename)


if __name__ == "__main__":
    print("=" * 64)
    print("  Microalgae Buoy Backend API")
    print("=" * 64)
    print("  API: http://localhost:5000")
    print("  Health: http://localhost:5000/health")
    print("  ESP32 analyze: http://YOUR_LAPTOP_IP:5000/analyze")
    print("=" * 64)
    app.run(host="0.0.0.0", port=5000, debug=False)
