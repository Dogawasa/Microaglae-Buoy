# Chat Handoff Export

This is a project handoff summary created from the Codex working session.
It is not a platform-native export of the full chat thread, but it captures
the important decisions, files, setup steps, and current project state.

## Project name

Modular Algae Buoy Array  
AI-controlled floating microalgae biofilter prototype

## Main concept

The project evolved from an idea about releasing microalgae into water into a
safer and more realistic design:

- modular floating buoy system
- closed microalgae chamber on the upper section
- lower treatment chamber where water flows through the buoy
- ESP32 reads sensor values
- AI backend decides treatment action
- dashboard shows live module status
- GitHub Pages hosts the frontend only
- backend runs separately on a local machine or cloud server

## Final architecture

### Frontend

Hosted on GitHub Pages:

`https://dogawasa.github.io/Microaglae-Buoy/`

Purpose:

- static dashboard frontend
- user enters backend URL
- page polls backend API
- shows module status and summary
- includes 2D and 3D concept visuals

### Backend

Separate Flask backend:

- `backend_api_server.py` for clean API use with GitHub Pages
- `modular_ai_server.py` for older all-in-one local dashboard mode

Main API routes:

- `GET /health`
- `GET /data`
- `POST /analyze`
- `POST /simulate`
- `POST /manual_lock`
- `POST /capture-image`
- `GET /image_data`

### ESP32

Arduino sketch:

- `microsketch_/microsketch_.ino`

ESP32 responsibilities:

- read sensors
- send readings to backend
- receive command logic through backend response
- control pump / flow / optional aeration logic

## Main AI decisions

Commands used by the system:

- `HOLD`
- `TREAT`
- `FLUSH`
- `LOCKOUT`

The AI logic uses water quality conditions such as:

- dissolved oxygen
- pH
- turbidity
- sunlight
- temperature
- algae film density

## Adaptive reporting idea

The project was updated so it does not report noisy sensor data too often.

Final reporting concept:

- sensor read every 10 seconds
- normal report every 60 seconds
- immediate report when values change significantly
- immediate report for risky conditions

## GitHub repository

Repository:

`https://github.com/Dogawasa/Microaglae-Buoy`

Files added or updated in the repo:

- `README.md`
- `BACKEND_DEPLOYMENT.md`
- `PRODUCT_ARCHITECTURE.md`
- `PROTOTYPE_BUILD.md`
- `backend_api_server.py`
- `docs/index.html`
- `docs/styles.css`
- `docs/app.js`
- `docs/assets/model_2d.svg`
- `docs/assets/model_3d_isometric.svg`

## Important local paths

Project folder:

`D:\AlgaeBioreactor`

ZIP export:

`D:\AlgaeBioreactor.zip`

Quick-start guide:

`D:\AlgaeBioreactor\START_HERE.txt`

This handoff file:

`D:\AlgaeBioreactor\CHAT_HANDOFF_EXPORT.md`

## Model / visual files

Concept images included:

- `assets/model_2d.svg`
- `assets/model_3d_isometric.svg`
- `docs/assets/model_2d.svg`
- `docs/assets/model_3d_isometric.svg`

## Recommended way to run the system now

### GitHub Pages frontend mode

1. Run backend:

```powershell
cd D:\AlgaeBioreactor
pip install -r requirements.txt
python backend_api_server.py
```

2. Enable GitHub Pages in the repo:

- Settings
- Pages
- Deploy from a branch
- Branch: `main`
- Folder: `/docs`

3. Open:

`https://dogawasa.github.io/Microaglae-Buoy/`

4. Enter backend URL such as:

`http://192.168.1.103:5000`

### Local all-in-one mode

```powershell
cd D:\AlgaeBioreactor
python modular_ai_server.py
```

Then open:

`http://localhost:5000`

## ESP32 setup reminder

Edit:

`microsketch_/microsketch_.ino`

Update:

```cpp
const char* WIFI_SSID = "YourWiFiName";
const char* WIFI_PASSWORD = "YourWiFiPassword";
const char* SERVER_URL = "http://YOUR_COMPUTER_IP:5000/analyze";
```

## Extra documentation added

- `START_HERE.txt`
- `README.md`
- `BACKEND_DEPLOYMENT.md`
- `PRODUCT_ARCHITECTURE.md`
- `PROTOTYPE_BUILD.md`

## Project direction that was chosen

The chosen direction was:

- do not release live microalgae directly into the river
- keep microalgae in a closed system
- use AI as an intelligent control layer
- allow water to flow through treatment chambers
- use GitHub Pages only for frontend hosting
- keep backend separate for real sensor integration

## Notes about export

This file is a handoff summary, not an exact line-by-line platform export.
If needed, this can be copied into a new Codex account so work can continue
without losing the main technical context.
