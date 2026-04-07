# Digital Visitor Log Book

## Overview
Lightweight visitor intake system with:
- Backend: FastAPI (Python)
- Storage: Excel (`visitors.xlsx`) using `pandas` + `openpyxl`
- Frontend: Landing page served by FastAPI
- Notifications: Confirmation email via SMTP after submission

## Project Structure

```
/project
  /backend
    main.py
    requirements.txt
    .env.example
  /frontend
    index.html
    app.js
    styles.css
  visitors.xlsx (generated automatically)
  README.md
```

## Backend Setup

1. Create a Python virtual environment and activate.
   - Windows (PowerShell): `python -m venv .venv; .\.venv\Scripts\Activate`

2. Install dependencies:
   - `pip install -r backend/requirements.txt`

3. Copy `.env.example` to `.env` and fill credentials:
   - Preferred location: `backend\.env`
   - Also supported: `.env` at the project root
   - Supported keys: `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USE_TLS`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`
   - Backward-compatible keys: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USERNAME`, `EMAIL_PASSWORD`, `EMAIL_FROM`

4. Start server:
   - From `/backend`: `python main.py`
   - Or for local development: `uvicorn main:app --reload --host 127.0.0.1 --port 8000`
   - Or for production: `uvicorn main:app --host 0.0.0.0 --port 8000`

Optional runtime environment variables:
- `APP_HOST` default `127.0.0.1`
- `APP_PORT` default `8000`
- `APP_RELOAD` default `false`

## Open The App

1. Make sure the backend server is running.
2. Open `http://127.0.0.1:8000` in the browser.

## Available APIs

- `POST /add-visitor`
- `GET /visitors` with optional query `date=YYYY-MM-DD` and `organization=substring`
- `DELETE /visitor/{id}`

`POST /add-visitor` expects the usual visitor details plus:
- `region`: one of `Trichy`, `Madurai`, or `Coimbatore`
- `further_support`: optional free-text note for any extra help requested

## Excel behavior

- File `visitors.xlsx` auto-created with headers.
- New rows appended; `S.No` auto-increment.
- Existing files are normalized automatically if new columns are added.

## Notes

- `.xlsx` is protected with lock file `visitors.xlsx.lock` to avoid concurrent corruption.
- Visitor writes and deletes are performed while the file lock is held to avoid duplicate serial numbers during concurrent updates.
- The landing page is served from `/` and static assets are served from `/static`.
- Validation happens in both the frontend and backend.
