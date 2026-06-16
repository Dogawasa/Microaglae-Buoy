/*
  Modular Floating Microalgae Treatment Buoy
  Board: ESP32

  Project concept:
  - Each buoy is one small treatment module.
  - River/canal water is pumped through the treatment section.
  - Microalgae stays in a closed photobioreactor or biofilm chamber.
  - The system improves water by controlled flow, oxygen transfer, and nutrient uptake.
  - It does not automatically release microalgae into the river.

  AI decisions from the server:
  - TREAT: run water through the lower treatment chamber.
  - FLUSH: run a short high-speed cleaning cycle for the intake path.
  - HOLD: save power and keep monitoring.
  - LOCKOUT: stop everything for safety.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <Arduino.h>

// ------------------------------------------------------------
// WiFi and AI server settings
// ------------------------------------------------------------
const char* WIFI_SSID = "YourWiFiName";
const char* WIFI_PASSWORD = "YourWiFiPassword";

// Example: "http://192.168.1.103:5000/analyze"
const char* SERVER_URL = "http://YOUR_COMPUTER_IP:5000/analyze";

const char* MODULE_ID = "module-01";
const char* ARRAY_ID = "river-array-01";

// ------------------------------------------------------------
// Sensor pins
// ------------------------------------------------------------
#define PIN_PH              34
#define PIN_TURBIDITY       35
#define PIN_DO              32
#define PIN_LIGHT           33
#define PIN_TEMP            39   // Optional analog temperature sensor
#define PIN_FILM_DENSITY    36   // Optional light sensor inside algae film chamber

// ------------------------------------------------------------
// Actuator pins
// ------------------------------------------------------------
#define PIN_FLOW_RELAY      26   // Main water flow pump or valve
#define PIN_FLOW_PWM        27   // Optional motor driver PWM pin
#define PIN_AERATOR_RELAY   14   // Optional air pump
#define PIN_GROW_LIGHT      25   // Optional grow LEDs
#define PIN_MIXER_RELAY     12   // Optional chamber mixer
#define PIN_STATUS_LED      2

// ------------------------------------------------------------
// Hardware options
// ------------------------------------------------------------
#define FLOW_PWM_ENABLED    0    // Set 1 if using a MOSFET/motor driver with PWM
#define TEMP_SENSOR_ENABLED 0    // Set 1 if PIN_TEMP has an LM35-like analog sensor
#define FILM_SENSOR_ENABLED 0    // Set 1 if PIN_FILM_DENSITY is installed

const bool RELAY_ACTIVE_HIGH = true;

// ------------------------------------------------------------
// Timing
// ------------------------------------------------------------
const unsigned long SENSOR_INTERVAL_MS = 10000UL;        // Read sensors every 10 seconds
const unsigned long REPORT_INTERVAL_MS = 60000UL;        // Normal dashboard/AI report every 60 seconds
const unsigned long ALERT_REPORT_INTERVAL_MS = 30000UL;  // Repeat active alert reports every 30 seconds
const unsigned long HTTP_TIMEOUT_MS = 3500UL;
const unsigned long FLOW_COOLDOWN_MS = 30000UL;
const unsigned long AERATOR_COOLDOWN_MS = 45000UL;
const unsigned long GROW_LIGHT_MAX_MS = 120000UL;
const unsigned long MIXER_PULSE_MS = 15000UL;

// ------------------------------------------------------------
// PWM settings
// ------------------------------------------------------------
#if FLOW_PWM_ENABLED
const int FLOW_PWM_CHANNEL = 0;
const int FLOW_PWM_FREQ = 5000;
const int FLOW_PWM_BITS = 8;
#endif

// ------------------------------------------------------------
// Calibration values
// ------------------------------------------------------------
const float ADC_REF_VOLTAGE = 3.3;
const float ADC_MAX_VALUE = 4095.0;
const int SENSOR_SAMPLES = 12;

float PH_VOLTAGE_AT_PH7 = 2.50;
float PH_SLOPE = -0.18;

float TURBIDITY_CLEAR_VOLTAGE = 3.00;
float TURBIDITY_MUDDY_VOLTAGE = 1.20;
float TURBIDITY_MAX_NTU = 120.0;

float DO_SATURATED_VOLTAGE = 3.30;
float DO_SATURATED_MG_L = 8.00;

// ------------------------------------------------------------
// Adaptive reporting thresholds
// ------------------------------------------------------------
const float REPORT_DELTA_PH = 0.20;
const float REPORT_DELTA_TURBIDITY = 10.0;
const float REPORT_DELTA_DO = 0.30;
const float REPORT_DELTA_SUNLIGHT = 15.0;
const float REPORT_DELTA_TEMPERATURE = 1.0;
const float REPORT_DELTA_FILM = 5.0;

const float ALERT_DO_CRITICAL = 3.0;
const float ALERT_DO_LOW = 5.0;
const float ALERT_PH_MIN = 6.2;
const float ALERT_PH_MAX = 8.8;
const float ALERT_TURBIDITY_HIGH = 90.0;
const float ALERT_FILM_DENSE = 85.0;

// ------------------------------------------------------------
// Runtime state
// ------------------------------------------------------------
unsigned long lastSensorRead = 0;
unsigned long lastReportAt = 0;
unsigned long flowStopAt = 0;
unsigned long flowCooldownUntil = 0;
unsigned long aeratorStopAt = 0;
unsigned long aeratorCooldownUntil = 0;
unsigned long growLightStopAt = 0;
unsigned long mixerStopAt = 0;

bool flowRunning = false;
bool aeratorRunning = false;
bool growLightRunning = false;
bool mixerRunning = false;
bool hasLastReportedReading = false;

struct SensorReading {
  float ph;
  float turbidity;
  float dissolvedO2;
  float sunlight;
  float temperatureC;
  float filmDensity;
  int rawPh;
  int rawTurbidity;
  int rawDo;
  int rawLight;
  int rawTemp;
  int rawFilm;
};

SensorReading lastReportedReading;

struct ServerDecision {
  String command;
  String flowLevel;
  String growthMode;
  String alert;
  String reason;
  int pumpSeconds;
  int pumpPwm;
  int aerateSeconds;
};

// ------------------------------------------------------------
// Setup and loop
// ------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println();
  Serial.println("Modular microalgae treatment buoy starting...");

  analogReadResolution(12);
  analogSetPinAttenuation(PIN_PH, ADC_11db);
  analogSetPinAttenuation(PIN_TURBIDITY, ADC_11db);
  analogSetPinAttenuation(PIN_DO, ADC_11db);
  analogSetPinAttenuation(PIN_LIGHT, ADC_11db);
  analogSetPinAttenuation(PIN_TEMP, ADC_11db);
  analogSetPinAttenuation(PIN_FILM_DENSITY, ADC_11db);

  pinMode(PIN_FLOW_RELAY, OUTPUT);
  pinMode(PIN_AERATOR_RELAY, OUTPUT);
  pinMode(PIN_GROW_LIGHT, OUTPUT);
  pinMode(PIN_MIXER_RELAY, OUTPUT);
  pinMode(PIN_STATUS_LED, OUTPUT);

#if FLOW_PWM_ENABLED
  ledcSetup(FLOW_PWM_CHANNEL, FLOW_PWM_FREQ, FLOW_PWM_BITS);
  ledcAttachPin(PIN_FLOW_PWM, FLOW_PWM_CHANNEL);
#endif

  stopAllActuators();
  connectWiFi();
}

void loop() {
  unsigned long now = millis();
  updateActuators(now);

  if (now - lastSensorRead >= SENSOR_INTERVAL_MS) {
    lastSensorRead = now;

    SensorReading reading = readSensors();
    printReading(reading);

    String reportReason = getReportReason(reading, now);
    if (reportReason.length() > 0) {
      if (WiFi.status() == WL_CONNECTED) {
        ServerDecision decision = sendToAI(reading, reportReason);
        printDecision(decision);
        applyDecision(decision);

        lastReportedReading = reading;
        hasLastReportedReading = true;
        lastReportAt = now;
      } else {
        Serial.println("WiFi disconnected. Reconnecting...");
        connectWiFi();
      }
    } else {
      Serial.println("No significant change. Sensor reading kept local.");
    }
  }
}

// ------------------------------------------------------------
// Sensor reading
// ------------------------------------------------------------
SensorReading readSensors() {
  SensorReading r;

  r.rawPh = readAnalogAverage(PIN_PH);
  r.rawTurbidity = readAnalogAverage(PIN_TURBIDITY);
  r.rawDo = readAnalogAverage(PIN_DO);
  r.rawLight = readAnalogAverage(PIN_LIGHT);
  r.rawTemp = readAnalogAverage(PIN_TEMP);
  r.rawFilm = readAnalogAverage(PIN_FILM_DENSITY);

  r.ph = convertPH(r.rawPh);
  r.turbidity = convertTurbidity(r.rawTurbidity);
  r.dissolvedO2 = convertDissolvedOxygen(r.rawDo);
  r.sunlight = convertLightPercent(r.rawLight);
  r.temperatureC = convertTemperatureC(r.rawTemp);
  r.filmDensity = convertFilmDensityPercent(r.rawFilm);

  return r;
}

int readAnalogAverage(uint8_t pin) {
  long total = 0;
  for (int i = 0; i < SENSOR_SAMPLES; i++) {
    total += analogRead(pin);
    delay(3);
  }
  return (int)(total / SENSOR_SAMPLES);
}

float adcToVoltage(int raw) {
  return raw * (ADC_REF_VOLTAGE / ADC_MAX_VALUE);
}

float convertPH(int raw) {
  float voltage = adcToVoltage(raw);
  float ph = 7.0 + ((voltage - PH_VOLTAGE_AT_PH7) / PH_SLOPE);
  return constrain(ph, 0.0, 14.0);
}

float convertTurbidity(int raw) {
  float voltage = adcToVoltage(raw);
  float span = TURBIDITY_CLEAR_VOLTAGE - TURBIDITY_MUDDY_VOLTAGE;
  if (span == 0.0) {
    return 0.0;
  }
  float cloudyRatio = (TURBIDITY_CLEAR_VOLTAGE - voltage) / span;
  cloudyRatio = constrain(cloudyRatio, 0.0, 1.0);
  return cloudyRatio * TURBIDITY_MAX_NTU;
}

float convertDissolvedOxygen(int raw) {
  float voltage = adcToVoltage(raw);
  float mgL = (voltage / DO_SATURATED_VOLTAGE) * DO_SATURATED_MG_L;
  return constrain(mgL, 0.0, 20.0);
}

float convertLightPercent(int raw) {
  return constrain((raw / ADC_MAX_VALUE) * 100.0, 0.0, 100.0);
}

float convertTemperatureC(int raw) {
#if TEMP_SENSOR_ENABLED
  // LM35-style sensor: 10 mV per degree Celsius.
  return adcToVoltage(raw) * 100.0;
#else
  (void)raw;
  return 25.0;
#endif
}

float convertFilmDensityPercent(int raw) {
#if FILM_SENSOR_ENABLED
  // More blocked light means denser algae/biofilm.
  float lightThroughFilm = convertLightPercent(raw);
  return constrain(100.0 - lightThroughFilm, 0.0, 100.0);
#else
  (void)raw;
  return 0.0;
#endif
}

// ------------------------------------------------------------
// Adaptive reporting
// ------------------------------------------------------------
String getReportReason(const SensorReading& r, unsigned long now) {
  if (!hasLastReportedReading) {
    return "first_report";
  }

  String alertNow = alertReason(r);
  String alertLast = alertReason(lastReportedReading);

  if (alertNow.length() > 0 && alertNow != alertLast) {
    return alertNow;
  }

  String changeReason = significantChangeReason(r, lastReportedReading);
  if (changeReason.length() > 0) {
    return changeReason;
  }

  if (alertNow.length() > 0 && now - lastReportAt >= ALERT_REPORT_INTERVAL_MS) {
    return alertNow + "_repeat";
  }

  if (now - lastReportAt >= REPORT_INTERVAL_MS) {
    return "scheduled_60s";
  }

  return "";
}

String alertReason(const SensorReading& r) {
  if (r.dissolvedO2 < ALERT_DO_CRITICAL) {
    return "alert_do_critical";
  }
  if (r.dissolvedO2 < ALERT_DO_LOW) {
    return "alert_do_low";
  }
  if (r.ph < ALERT_PH_MIN || r.ph > ALERT_PH_MAX) {
    return "alert_ph_out_of_range";
  }
  if (r.turbidity >= ALERT_TURBIDITY_HIGH) {
    return "alert_turbidity_high";
  }
  if (r.filmDensity >= ALERT_FILM_DENSE) {
    return "alert_film_dense";
  }
  return "";
}

String significantChangeReason(const SensorReading& current, const SensorReading& previous) {
  if (abs(current.dissolvedO2 - previous.dissolvedO2) >= REPORT_DELTA_DO) {
    return "do_changed";
  }
  if (abs(current.ph - previous.ph) >= REPORT_DELTA_PH) {
    return "ph_changed";
  }
  if (abs(current.turbidity - previous.turbidity) >= REPORT_DELTA_TURBIDITY) {
    return "turbidity_changed";
  }
  if (abs(current.sunlight - previous.sunlight) >= REPORT_DELTA_SUNLIGHT) {
    return "sunlight_changed";
  }
  if (abs(current.temperatureC - previous.temperatureC) >= REPORT_DELTA_TEMPERATURE) {
    return "temperature_changed";
  }
  if (abs(current.filmDensity - previous.filmDensity) >= REPORT_DELTA_FILM) {
    return "film_changed";
  }
  return "";
}

// ------------------------------------------------------------
// AI communication
// ------------------------------------------------------------
ServerDecision sendToAI(const SensorReading& r, const String& reportReason) {
  ServerDecision fallback = defaultDecision();

  HTTPClient http;
  http.begin(SERVER_URL);
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Accept", "application/json");

  String payload = "{";
  payload += "\"array_id\":\"" + String(ARRAY_ID) + "\",";
  payload += "\"module_id\":\"" + String(MODULE_ID) + "\",";
  payload += "\"ph\":" + String(r.ph, 2) + ",";
  payload += "\"turbidity\":" + String(r.turbidity, 1) + ",";
  payload += "\"dissolved_o2\":" + String(r.dissolvedO2, 2) + ",";
  payload += "\"sunlight\":" + String(r.sunlight, 1) + ",";
  payload += "\"temperature_c\":" + String(r.temperatureC, 1) + ",";
  payload += "\"film_density\":" + String(r.filmDensity, 1) + ",";
  payload += "\"report_reason\":\"" + reportReason + "\",";
  payload += "\"sensor_interval_seconds\":" + String(SENSOR_INTERVAL_MS / 1000UL) + ",";
  payload += "\"normal_report_interval_seconds\":" + String(REPORT_INTERVAL_MS / 1000UL) + ",";
  payload += "\"flow_running\":" + String(flowRunning ? "true" : "false") + ",";
  payload += "\"aerator_running\":" + String(aeratorRunning ? "true" : "false") + ",";
  payload += "\"response_format\":\"json\"";
  payload += "}";

  int httpCode = http.POST(payload);
  if (httpCode != 200) {
    Serial.print("AI server HTTP error: ");
    Serial.println(httpCode);
    http.end();
    return fallback;
  }

  String body = http.getString();
  http.end();
  return parseDecision(body);
}

ServerDecision defaultDecision() {
  ServerDecision d;
  d.command = "HOLD";
  d.flowLevel = "OFF";
  d.growthMode = "IDLE";
  d.alert = "";
  d.reason = "No valid AI response";
  d.pumpSeconds = 0;
  d.pumpPwm = 0;
  d.aerateSeconds = 0;
  return d;
}

ServerDecision parseDecision(String body) {
  ServerDecision d = defaultDecision();
  body.trim();

  if (body.startsWith("{")) {
    d.command = normalizeText(extractJsonString(body, "command"));
    d.flowLevel = normalizeText(extractJsonString(body, "flow_level"));
    d.growthMode = normalizeText(extractJsonString(body, "growth_mode"));
    d.alert = normalizeText(extractJsonString(body, "alert"));
    d.reason = extractJsonString(body, "reason");
    d.pumpSeconds = extractJsonInt(body, "pump_seconds", 0);
    d.pumpPwm = extractJsonInt(body, "pump_pwm", 0);
    d.aerateSeconds = extractJsonInt(body, "aerate_seconds", 0);
  } else {
    d.command = normalizeText(body);
  }

  if (d.command.length() == 0) d.command = "HOLD";
  if (d.flowLevel.length() == 0) d.flowLevel = "OFF";
  if (d.growthMode.length() == 0) d.growthMode = "IDLE";
  if (d.reason.length() == 0) d.reason = "AI command received";

  return d;
}

String normalizeText(String value) {
  value.trim();
  value.toUpperCase();
  return value;
}

String extractJsonString(const String& body, const String& key) {
  String needle = "\"" + key + "\"";
  int keyPos = body.indexOf(needle);
  if (keyPos < 0) return "";

  int colon = body.indexOf(':', keyPos + needle.length());
  if (colon < 0) return "";

  int start = colon + 1;
  while (start < body.length() && (body[start] == ' ' || body[start] == '\t')) start++;
  if (start >= body.length()) return "";

  if (body[start] == '"') {
    int endQuote = body.indexOf('"', start + 1);
    if (endQuote < 0) return "";
    return body.substring(start + 1, endQuote);
  }

  int end = start;
  while (end < body.length() && body[end] != ',' && body[end] != '}') end++;
  String value = body.substring(start, end);
  value.trim();
  return value;
}

int extractJsonInt(const String& body, const String& key, int fallback) {
  String value = extractJsonString(body, key);
  if (value.length() == 0) return fallback;
  return value.toInt();
}

// ------------------------------------------------------------
// Decision handling
// ------------------------------------------------------------
void applyDecision(const ServerDecision& d) {
  if (d.command == "LOCKOUT") {
    stopAllActuators();
    blinkStatus(4, 120);
    return;
  }

  if (d.command == "TREAT" || d.command == "FLUSH") {
    startTreatmentFlow(d);
  } else if (d.command == "HOLD") {
    // Keep currently timed outputs running, but do not start a new cycle.
  }

  if (d.aerateSeconds > 0) {
    startAeration(d.aerateSeconds);
  }

  if (d.growthMode == "SEALED_GROW") {
    startMixerPulse();
    stopGrowLight();
  } else if (d.growthMode == "LOW_LIGHT_SUPPORT") {
    startGrowLight();
  } else if (d.growthMode == "MAINTENANCE") {
    stopGrowLight();
    startMixerPulse();
  } else {
    stopGrowLight();
  }

  if (d.alert == "HARVEST_BIOFILM") {
    blinkStatus(3, 250);
  }
}

void startTreatmentFlow(const ServerDecision& d) {
  unsigned long now = millis();
  if (flowRunning) return;
  if (!timeReached(now, flowCooldownUntil)) {
    Serial.println("Flow cooldown active.");
    return;
  }

  int seconds = d.pumpSeconds;
  int pwm = d.pumpPwm;

  if (seconds <= 0) {
    if (d.command == "FLUSH") seconds = 6;
    else seconds = 10;
  }
  if (pwm <= 0) {
    if (d.command == "FLUSH") pwm = 235;
    else pwm = 185;
  }

  flowRunning = true;
  flowStopAt = now + ((unsigned long)seconds * 1000UL);
  setRelay(PIN_FLOW_RELAY, true);
  setFlowPwm(pwm);
  digitalWrite(PIN_STATUS_LED, HIGH);
}

void startAeration(int seconds) {
  unsigned long now = millis();
  if (aeratorRunning) return;
  if (!timeReached(now, aeratorCooldownUntil)) {
    Serial.println("Aerator cooldown active.");
    return;
  }

  if (seconds <= 0) seconds = 10;
  aeratorRunning = true;
  aeratorStopAt = now + ((unsigned long)seconds * 1000UL);
  setRelay(PIN_AERATOR_RELAY, true);
  digitalWrite(PIN_STATUS_LED, HIGH);
}

void startGrowLight() {
  growLightRunning = true;
  growLightStopAt = millis() + GROW_LIGHT_MAX_MS;
  setRelay(PIN_GROW_LIGHT, true);
}

void stopGrowLight() {
  growLightRunning = false;
  setRelay(PIN_GROW_LIGHT, false);
}

void startMixerPulse() {
  mixerRunning = true;
  mixerStopAt = millis() + MIXER_PULSE_MS;
  setRelay(PIN_MIXER_RELAY, true);
}

void updateActuators(unsigned long now) {
  if (flowRunning && timeReached(now, flowStopAt)) {
    flowRunning = false;
    flowCooldownUntil = now + FLOW_COOLDOWN_MS;
    setRelay(PIN_FLOW_RELAY, false);
    setFlowPwm(0);
  }

  if (aeratorRunning && timeReached(now, aeratorStopAt)) {
    aeratorRunning = false;
    aeratorCooldownUntil = now + AERATOR_COOLDOWN_MS;
    setRelay(PIN_AERATOR_RELAY, false);
  }

  if (growLightRunning && timeReached(now, growLightStopAt)) {
    stopGrowLight();
  }

  if (mixerRunning && timeReached(now, mixerStopAt)) {
    mixerRunning = false;
    setRelay(PIN_MIXER_RELAY, false);
  }

  if (!flowRunning && !aeratorRunning && !growLightRunning && !mixerRunning) {
    digitalWrite(PIN_STATUS_LED, LOW);
  }
}

void stopAllActuators() {
  flowRunning = false;
  aeratorRunning = false;
  growLightRunning = false;
  mixerRunning = false;

  setRelay(PIN_FLOW_RELAY, false);
  setRelay(PIN_AERATOR_RELAY, false);
  setRelay(PIN_GROW_LIGHT, false);
  setRelay(PIN_MIXER_RELAY, false);
  setFlowPwm(0);
  digitalWrite(PIN_STATUS_LED, LOW);
}

void setRelay(uint8_t pin, bool on) {
  bool level = RELAY_ACTIVE_HIGH ? on : !on;
  digitalWrite(pin, level ? HIGH : LOW);
}

void setFlowPwm(int pwm) {
  pwm = constrain(pwm, 0, 255);
#if FLOW_PWM_ENABLED
  ledcWrite(FLOW_PWM_CHANNEL, pwm);
#else
  (void)pwm;
#endif
}

bool timeReached(unsigned long now, unsigned long target) {
  return (long)(now - target) >= 0;
}

// ------------------------------------------------------------
// WiFi and logging
// ------------------------------------------------------------
void connectWiFi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 24) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Connected. IP: ");
    Serial.println(WiFi.localIP());
    blinkStatus(2, 120);
  } else {
    Serial.println("WiFi failed. Will retry later.");
  }
}

void blinkStatus(int count, int delayMs) {
  for (int i = 0; i < count; i++) {
    digitalWrite(PIN_STATUS_LED, HIGH);
    delay(delayMs);
    digitalWrite(PIN_STATUS_LED, LOW);
    delay(delayMs);
  }
}

void printReading(const SensorReading& r) {
  Serial.println("--------------------------------");
  Serial.print("Module: ");
  Serial.println(MODULE_ID);
  Serial.print("pH: ");
  Serial.println(r.ph, 2);
  Serial.print("Turbidity: ");
  Serial.print(r.turbidity, 1);
  Serial.println(" NTU");
  Serial.print("Dissolved O2: ");
  Serial.print(r.dissolvedO2, 2);
  Serial.println(" mg/L");
  Serial.print("Sunlight: ");
  Serial.print(r.sunlight, 1);
  Serial.println("%");
  Serial.print("Temperature: ");
  Serial.print(r.temperatureC, 1);
  Serial.println(" C");
  Serial.print("Film density: ");
  Serial.print(r.filmDensity, 1);
  Serial.println("%");
}

void printDecision(const ServerDecision& d) {
  Serial.print("AI command: ");
  Serial.println(d.command);
  Serial.print("Flow level: ");
  Serial.println(d.flowLevel);
  Serial.print("Growth mode: ");
  Serial.println(d.growthMode);
  Serial.print("Alert: ");
  Serial.println(d.alert);
  Serial.print("Reason: ");
  Serial.println(d.reason);
}
