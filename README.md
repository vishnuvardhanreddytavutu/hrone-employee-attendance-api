# HROne Employee Attendance & Analytics API

A FastAPI application for employee management, attendance tracking, manual attendance corrections, and MongoDB-based analytics.

## Requirements

- Python 3.10+
- MongoDB 6.0 or newer
- Dependencies listed in `requirements.txt`

## Setup

Create and activate a virtual environment, then install dependencies.

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file using `.env.example` as a reference, and configure `MONGO_URI` and `MONGO_DB`. Keep `.env` private; never commit credentials.

## Run

```powershell
uvicorn app.main:app --port 8000
```

API documentation: http://127.0.0.1:8000/docs

Health check: http://127.0.0.1:8000/health

## Sample Data

If MongoDB is running and `.env` is configured, load the provided sample records with:

```powershell
python sample_seed.py
```

## Tests

Run the available tests with:

```powershell
python -m pytest -v
```

## API Features

- Employee creation and paginated listing
- Attendance punch-in, punch-out, and listing
- Manual attendance regularization with audit history
- Monthly employee and department analytics
- Late-comers leaderboard
- Daily department attendance trends
- MongoDB execution-plan inspection

## Submission

Submit a public Git repository containing `app/main.py`, `requirements.txt`, `REVIEW.md`, `DECISIONS.md`, and this README.

Do not commit `.env`, credentials, or other secrets.
