# Modular Algae Buoy Array

A high-school project for a modular floating water-treatment buoy that uses a closed microalgae chamber, ESP32 sensors, and an AI dashboard to decide how strongly the system should treat incoming water.

## Project idea

This system is designed as a chain of floating treatment modules. Water flows through each buoy, passes a controlled treatment section, and returns to the river or canal with improved dissolved oxygen and reduced nutrient stress.

The design is split into two controlled sections:

1. Upper algae production chamber  
   A closed transparent chamber where microalgae or algae biofilm receives sunlight and supports oxygen production.

2. Lower treatment chamber  
   The section where water passes through the buoy, interacts with the treatment surface, and is managed by pumps, aeration, and AI decisions.

The project does **not** automatically release live microalgae into natural water.

## Main features

- ESP32 sensor reporting
- AI-based decision logic for treatment flow and safety
- Thai-language web dashboard
- Manual test buttons for classroom/demo use
- Adaptive reporting:
  - sensor reads every 10 seconds
  - normal report every 60 seconds
  - immediate report for important changes or risky conditions
- Water image capture/upload and simple image analysis

## Project files

- `backend_api_server.py` - clean Flask backend API for the GitHub Pages frontend
- `modular_ai_server.py` - all-in-one local Flask AI server and dashboard
- `start_modular_ai_server.bat` - quick launcher for Windows
- `microsketch_/microsketch_.ino` - ESP32 / Arduino code
- `docs/index.html` - GitHub Pages frontend dashboard
- `docs/app.js` - frontend logic for remote backend polling
- `docs/styles.css` - GitHub Pages styling
- `BACKEND_DEPLOYMENT.md` - how to host the Flask backend separately
- `MICROALGAE_PROJECT_UPGRADE_PLAN.md` - concept and presentation notes
- `PRODUCT_ARCHITECTURE.md` - module architecture and control flow
- `PROTOTYPE_BUILD.md` - build order and prototype demo guide
- `Algae Bioreactor_files/tabler-icons.min.css` - local icon CSS
- `assets/model_2d.svg` - 2D concept image
- `assets/model_3d_isometric.svg` - 3D isometric concept image

## Concept images

### 2D model

![2D model](assets/model_2d.svg)

### 3D model

![3D model](assets/model_3d_isometric.svg)

## Run the dashboard

### Option 1: GitHub Pages frontend

After GitHub Pages is enabled for the `docs/` folder on the `main` branch, the dashboard URL should be:

```text
https://dogawasa.github.io/Microaglae-Buoy/
```

How to use the GitHub Pages dashboard:

1. Deploy or run the Flask backend somewhere reachable.
2. Open the GitHub Pages URL.
3. Paste the backend base URL into the `Backend URL` field.
4. Click `Save`.
5. The page will start loading live data from `/data`.

Examples of backend URLs:

```text
http://192.168.1.103:5000
https://your-backend-service.example.com
```

The frontend will call:

- `GET /data`
- `POST /simulate`
- `POST /manual_lock`

Recommended backend for GitHub Pages deployment:

```powershell
python backend_api_server.py
```

### Option 2: Local Flask dashboard

Install Python packages:

```powershell
pip install -r requirements.txt
```

Start the server:

```powershell
python modular_ai_server.py
```

Or on Windows, double-click:

```text
start_modular_ai_server.bat
```

Then open:

```text
http://localhost:5000
```

## Enable GitHub Pages

In the GitHub repository settings:

1. Open `Settings`
2. Open `Pages`
3. Under `Build and deployment`, choose:
   - `Source: Deploy from a branch`
   - `Branch: main`
   - `Folder: /docs`
4. Save

Then wait for GitHub Pages to publish the site.

## Arduino / ESP32 setup

Open:

```text
microsketch_\microsketch_.ino
```

Update these values:

```cpp
const char* WIFI_SSID = "YourWiFiName";
const char* WIFI_PASSWORD = "YourWiFiPassword";
const char* SERVER_URL = "http://YOUR_COMPUTER_IP:5000/analyze";
```

Your computer and ESP32 should be on the same WiFi network.

## Sensor inputs

The code is designed for these measurements:

- dissolved oxygen (DO)
- pH
- turbidity
- sunlight / light level
- temperature
- algae film density (optional)

## AI decisions

The dashboard and AI server can choose actions such as:

- `HOLD`
- `TREAT`
- `FLUSH`
- `LOCKOUT`

## Additional recommended hardware

- Waterproof electronics box
- Cable glands
- Intake screen
- Fine filter media
- Algae-retaining membrane
- Buck converter
- Fuse
- Leak sensor
- Manual power switch
- Ballast or anchor rope

## Suggested hardware

- ESP32 dev board
- DO sensor
- pH sensor
- turbidity sensor
- light sensor
- water temperature sensor
- small water pump
- relay or MOSFET driver
- aerator
- clear algae chamber
- floating body / buoy structure

## Notes

- `water_images/` stores captured or uploaded sample images.
- The dashboard includes demo buttons for testing when a real ESP32 is not connected.
- For real environmental deployment, use teacher/supervisor approval and follow local environmental rules.
- The GitHub Pages frontend is static and does not run Python. The AI backend must stay on a separate server.
