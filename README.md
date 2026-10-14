# HROne Employee Attendance & Analytics API

A REST API for employee attendance tracking and workforce analytics, built with **Python, FastAPI, and MongoDB**.

## Overview

This project provides APIs for managing employee records, recording attendance, calculating working hours, and generating attendance analytics. It includes validation, conflict handling, database indexes, and automated tests.

## Features

- Employee and attendance management
- Punch-in and punch-out workflows
- Shift-aware attendance dates, including overnight shifts
- Late-arrival and overtime calculations
- Work-hour and half-day calculations
- Employee monthly attendance reports
- Department-level attendance summaries and trends
- Late-arrival leaderboard with tie handling
- Paginated and filtered API responses
- MongoDB aggregation pipelines for analytics
- Database index analysis through explain endpoints
- Request validation and appropriate HTTP error responses

## Tech Stack

- **Language:** Python
- **API framework:** FastAPI
- **Database:** MongoDB Atlas
- **Validation:** Pydantic
- **Testing:** Pytest
- **API documentation:** OpenAPI / Swagger UI
- **Version control:** Git and GitHub

## Project Structure

```text
.
├── app/
│   ├── __init__.py
│   └── main.py
├── sample_data/
│   ├── attendance_logs.json
│   └── employees.json
├── tests/
│   ├── test_api.py
│   └── test_calculations.py
├── .gitignore
├── DATA_MODEL.md
├── DECISIONS.md
├── PROBLEM_STATEMENT.docx
├── REVIEW.md
├── openapi.yaml
├── requirements.txt
└── sample_seed.py
```

## Getting Started

### Prerequisites

- Python 3.11 or a compatible version supported by the dependencies
- MongoDB Atlas account or a reachable MongoDB instance
- Git

### 1. Clone the repository

```bash
git clone https://github.com/vishnuvardhanreddytavutu/hrone-employee-attendance-api.git
cd hrone-employee-attendance-api
```

### 2. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file in the project root and configure the MongoDB connection string and database name using the variable names expected by the application.

Example:

```env
MONGO_URI=your_mongodb_connection_string
MONGO_DB=your_database_name
```

Replace the example values with your own credentials. **Never commit `.env` or expose database credentials publicly.**

### 5. Run the API

```bash
uvicorn app.main:app --reload
```

Open the interactive API documentation:

- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

## Run Tests

```bash
python -m pytest -q
```

The current test suite passes **10 tests**.

## Engineering Decisions

See [DECISIONS.md](DECISIONS.md) for implementation choices and [DATA_MODEL.md](DATA_MODEL.md) for the data model. The review notes are available in [REVIEW.md](REVIEW.md).

## Security Notes

- Store database credentials in environment variables.
- Keep `.env` and virtual environment files out of version control.
- Use restricted database credentials and network access rules for deployment.
- Configure production secrets and access controls before exposing the API publicly.

## Future Improvements

- Automated CI test execution
- Production deployment and monitoring
- Expanded integration and concurrency tests
- Authentication and role-based access control, if required by the use case

## Author

**Vishnuvardhan Reddy Tavutu**

[GitHub Repository](https://github.com/vishnuvardhanreddytavutu/hrone-employee-attendance-api)
