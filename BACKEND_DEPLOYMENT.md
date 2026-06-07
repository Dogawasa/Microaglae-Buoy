# Backend Deployment

## Purpose

The GitHub Pages dashboard is static, so the Flask AI backend must run separately.

## Minimum backend requirements

- Python 3.10+
- `flask`
- `flask-cors`
- Public or reachable URL

## Local network option

Run on your computer:

```powershell
pip install -r requirements.txt
python modular_ai_server.py
```

Then use your computer IP as the backend URL in GitHub Pages:

```text
http://192.168.x.x:5000
```

## Cloud option

Deploy the backend to a service such as:

- Render
- Railway
- Replit
- VPS / cloud VM

## Required API routes

The frontend expects these routes:

- `GET /data`
- `POST /simulate`
- `POST /manual_lock`

Optional:

- `POST /capture-image`
- `GET /image_data`

## CORS

The backend must allow cross-origin requests from GitHub Pages. This project already uses:

```python
from flask_cors import CORS
CORS(app)
```
