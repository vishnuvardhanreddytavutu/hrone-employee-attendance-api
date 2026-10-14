
"""
HROne Employee Attendance & Analytics API
Run: uvicorn app.main:app --port 8000
Environment: MONGO_URI, MONGO_DB
"""
import os
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Literal
import json
import bson.json_util

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Path
from pydantic import BaseModel, ConfigDict, Field, EmailStr, field_validator, StrictInt
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.read_concern import ReadConcern

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "hrone_attendance")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is required")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[MONGO_DB]
employees = db["employees"]
attendance = db["attendance_logs"]

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc
PRESENT_STATUSES = ("PRESENT", "WFH", "ON_DUTY")
ALL_STATUSES = ("PRESENT", "WFH", "ON_DUTY", "ABSENT", "LEAVE")

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")


# ------------------------------- Helpers ----------------------------------

def now_utc():
    return datetime.now(UTC).replace(microsecond=0)


def as_utc(dt: datetime) -> datetime:
    """Treat MongoDB's naive datetimes as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def epoch_ms(dt):
    if dt is None:
        return None
    return int(as_utc(dt).timestamp() * 1000)


def api_time(dt):
    return epoch_ms(dt)


def from_epoch_ms(value: int) -> datetime:
    # Millisecond input; discard fractional seconds before calculations.
    return datetime.fromtimestamp(value / 1000, UTC).replace(microsecond=0)


def local_datetime(dt: datetime) -> datetime:
    return as_utc(dt).astimezone(IST)


def local_date(dt: datetime) -> str:
    return local_datetime(dt).date().isoformat()


def round_half_up(value, places=2):
    quantum = Decimal("1").scaleb(-places)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))




def compute_late_minutes(punch_in: datetime, shift_start: str) -> int:
    local = local_datetime(punch_in)

    h, m = map(int, shift_start.split(":"))
    shift_start_minutes = h * 60 + m
    punch_minutes = local.hour * 60 + local.minute
    seconds_after_start = (
        punch_minutes - shift_start_minutes
    ) * 60 + local.second

    # Handle overnight shifts.
    if seconds_after_start < -12 * 60 * 60:
        seconds_after_start += 24 * 60 * 60
    elif seconds_after_start > 12 * 60 * 60:
        seconds_after_start -= 24 * 60 * 60

    # More than 10 minutes late; report whole elapsed minutes.
    if seconds_after_start > 10 * 60:
        return seconds_after_start // 60

    return 0




def shift_end_datetime(punch_in: datetime, shift_start: str, shift_end: str):
    local_in = local_datetime(punch_in)
    sh, sm = map(int, shift_start.split(":"))
    eh, em = map(int, shift_end.split(":"))
    start = local_in.replace(hour=sh, minute=sm, second=0, microsecond=0)
    if local_in < start:
        start -= timedelta(days=1)
    end = start.replace(hour=eh, minute=em)
    if (eh, em) <= (sh, sm):
        end += timedelta(days=1)
    return end


def compute_overtime(punch_out: datetime, shift_start: str,
                     shift_end: str, punch_in: datetime) -> int:
    end_local = shift_end_datetime(punch_in, shift_start, shift_end)
    out_local = local_datetime(punch_out)
    minutes = int((out_local - end_local).total_seconds() // 60)
    return minutes if minutes >= 30 else 0


def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
    seconds = (as_utc(punch_out) - as_utc(punch_in)).total_seconds()
    return round_half_up(seconds / 3600, 2)


def validate_date(value: str) -> str:
    try:
         if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", value
        ):
            raise ValueError()
         return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise HTTPException(422, "Date must be YYYY-MM-DD")


def validate_month(value: str) -> tuple[str, date, date]:
    try:
        start = date.fromisoformat(value + "-01")
        if len(value) != 7:
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "Month must be YYYY-MM")
    next_month = date(start.year + (start.month == 12),
                      1 if start.month == 12 else start.month + 1, 1)
    return value, start, next_month


def public_employee(doc):
    doc = dict(doc)
    doc.pop("_id", None)
    if "created_at" in doc:
        doc["created_at"] = epoch_ms(doc["created_at"])
    return doc


def public_attendance(doc):
    doc = dict(doc)
    doc.pop("_id", None)
    for field in ("punch_in", "punch_out"):
        if field in doc:
            doc[field] = epoch_ms(doc[field])
    history = []
    for entry in doc.get("history", []) or []:
        entry = dict(entry)
        if entry.get("at") is not None:
            entry["at"] = epoch_ms(entry["at"])
        history.append(entry)
    doc["history"] = history
    doc.setdefault("half_day", False)
    return doc


def make_indexes():
    employees.create_index([("emp_code", ASCENDING)], unique=True,
                           name="uq_employees_emp_code")
    employees.create_index([("department", ASCENDING), ("emp_code", ASCENDING)],
                           name="ix_employees_department_code")
    employees.create_index([("department", ASCENDING), ("joined_on", ASCENDING)],
                           name="ix_employees_department_joined")
    attendance.create_index([("emp_code", ASCENDING), ("date", ASCENDING)],
                            unique=True, name="uq_attendance_employee_date")
    attendance.create_index([("date", DESCENDING), ("emp_code", ASCENDING)],
                            name="ix_attendance_date_employee")
    attendance.create_index([("emp_code", ASCENDING), ("date", DESCENDING),
                             ("status", ASCENDING)],
                            name="ix_attendance_employee_date_status")
    attendance.create_index([("status", ASCENDING), ("date", DESCENDING)],
                            name="ix_attendance_status_date")
    attendance.create_index([("date", ASCENDING), ("late_minutes", DESCENDING),
                             ("emp_code", ASCENDING)],
                            name="ix_attendance_date_late")


@app.on_event("startup")
def startup():
    make_indexes()


# -------------------------------- Models -----------------------------------

class EmployeeIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    emp_code: str = Field(pattern=r"^EMP\d{4,6}$")
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=120)
    department: str = Field(min_length=1, max_length=50)
    shift_start: str = Field(default="09:30", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    shift_end: str = Field(default="18:30", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    joined_on: str

    
    @field_validator("joined_on")
    @classmethod
    def valid_join_date(cls, value):
        try:
            if not isinstance(value, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", value
            ):
                raise ValueError()
            date.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError("joined_on must be YYYY-MM-DD")
        return value


    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Invalid email")
        return value

    @field_validator("shift_end")
    @classmethod
    def valid_shift_end(cls, value, info):
        start = info.data.get("shift_start")
        if start and value == start:
            raise ValueError("shift_start and shift_end must differ")
        return value


class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[StrictInt] = Field(default=None, ge=100000000000,
                                       le=4102444800000)
    status: Literal["PRESENT", "WFH", "ON_DUTY"] = "PRESENT"


class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: Optional[StrictInt] = Field(default=None, ge=100000000000,
                                         le=4102444800000)


class RegularizationIn(BaseModel):
    status: Optional[Literal["PRESENT", "WFH", "ON_DUTY", "ABSENT", "LEAVE"]] = None
    punch_in: Optional[StrictInt] = Field(default=None, ge=100000000000,
                                    le=4102444800000)
    punch_out: Optional[StrictInt] = Field(default=None, ge=100000000000,
                                     le=4102444800000)
    reason: str = Field(min_length=5, max_length=200)
    regularized_by: str = Field(min_length=1, max_length=50)


# ------------------------------- Health -----------------------------------

@app.get("/health")
def health():
    try:
        client.admin.command("ping")
        return {"status": "ok"}
    except PyMongoError:
        raise HTTPException(503, "MongoDB unavailable")


# ------------------------------ Employees ---------------------------------

@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    doc = body.model_dump()
    doc["created_at"] = now_utc()
    try:
        employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "emp_code already exists")
    return public_employee(doc)


@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q = {}
    if department:
        q["department"] = department
    total = employees.count_documents(q)
    items = list(employees.find(q, {"_id": 0})
                 .sort("emp_code", ASCENDING)
                 .skip((page - 1) * page_size).limit(page_size))
    for item in items:
        if "created_at" in item:
            item["created_at"] = epoch_ms(item["created_at"])
    return {"items": items, "total": total, "page": page, "page_size": page_size}


# ------------------------------ Punch In ----------------------------------

@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    emp = employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(404, "Employee not found")

    
    ts = from_epoch_ms(body.punched_at) if body.punched_at is not None else now_utc()
    local = local_datetime(ts)
    sh, sm = map(int, emp["shift_start"].split(":"))
    eh, em = map(int, emp["shift_end"].split(":"))

    is_overnight = (eh, em) <= (sh, sm)
    before_shift_end = (local.hour, local.minute) < (eh, em)

    if is_overnight and before_shift_end:
        day = (local.date() - timedelta(days=1)).isoformat()
    else:
        day = local.date().isoformat()

    doc = {
        "emp_code": body.emp_code,
        "date": day,
        "status": body.status,
        "punch_in": ts,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": compute_late_minutes(ts, emp["shift_start"]),
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }
    try:
        attendance.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "already punched in for this date")
    return public_attendance(doc)


# ------------------------------ Punch Out ---------------------------------

@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
    emp = employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(404, "Employee not found")

    ts = from_epoch_ms(body.punched_at) if body.punched_at is not None else now_utc()
    local_day = local_date(ts)
    # Search the most recent unclosed punch whose start is not after the requested time.
    candidates = list(attendance.find({
        "emp_code": body.emp_code,
        "punch_in": {"$lte": ts},
    }).sort("punch_in", DESCENDING).limit(2))
    if not candidates:
        raise HTTPException(404, "No punch-in found")
    record = candidates[0]
    if record.get("punch_out") is not None:
        raise HTTPException(409, "Already punched out")
    if ts <= as_utc(record["punch_in"]):
        raise HTTPException(422, "punch_out must be after punch_in")
    if ts - as_utc(record["punch_in"]) > timedelta(hours=24):
        raise HTTPException(422, "punch_out cannot be more than 24 hours after punch_in")

    hours = compute_work_hours(record["punch_in"], ts)
    overtime = compute_overtime(ts, emp["shift_start"], emp["shift_end"],
                                record["punch_in"])
    half_day = hours < 4.50
    result = attendance.update_one(
        {"_id": record["_id"], "punch_out": None},
        {"$set": {"punch_out": ts, "work_hours": hours,
                  "overtime_minutes": overtime, "half_day": half_day}},
    )
    if result.modified_count != 1:
        raise HTTPException(409, "Already punched out")
    record.update({"punch_out": ts, "work_hours": hours,
                   "overtime_minutes": overtime, "half_day": half_day})
    return public_attendance(record)


# ---------------------------- Attendance List -----------------------------

@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    q = {}
    if emp_code:
        q["emp_code"] = emp_code
    if date_from:
        validate_date(date_from)
    if date_to:
        validate_date(date_to)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must not be after date_to")
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    if status:
        if status not in ALL_STATUSES:
            raise HTTPException(422, "Invalid status")
        q["status"] = status

    total = attendance.count_documents(q)
    docs = list(attendance.find(q).sort(
        [("date", DESCENDING), ("emp_code", ASCENDING)]
    ).skip((page - 1) * page_size).limit(page_size))
    return {"items": [public_attendance(d) for d in docs],
            "total": total, "page": page, "page_size": page_size}


# --------------------------- Regularization -------------------------------

@app.patch("/attendance/{emp_code}/{date_str}")
def regularize(emp_code: str, date_str: str, body: RegularizationIn):
    validate_date(date_str)
    emp = employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(404, "Employee not found")
    record = attendance.find_one({"emp_code": emp_code, "date": date_str})
    if not record:
        raise HTTPException(404, "Attendance record not found")

    updates = {}
    supplied = body.model_dump(exclude_unset=True)
    for key in ("status", "punch_in", "punch_out"):
        if key in supplied:
            updates[key] = from_epoch_ms(supplied[key]) if key in ("punch_in", "punch_out") and supplied[key] is not None else supplied[key]

    final_status = updates.get("status", record.get("status"))
    final_in = updates.get("punch_in", record.get("punch_in"))
    final_out = updates.get("punch_out", record.get("punch_out"))

    
    if final_status in ("ABSENT", "LEAVE"):
        if "punch_in" in supplied or "punch_out" in supplied:
            raise HTTPException(
                422, "ABSENT and LEAVE cannot include punch times"
            )

        updates["punch_in"] = None
        updates["punch_out"] = None
        updates["work_hours"] = None
        updates["late_minutes"] = 0
        updates["overtime_minutes"] = 0
        updates["half_day"] = False
    else:
        if final_in is None:
            raise HTTPException(422, "Presence status requires punch_in")

        if local_date(final_in) != date_str:
            raise HTTPException(422, "punch_in must be on the attendance date")
        if final_out is not None:
            if final_out <= final_in:
                raise HTTPException(422, "punch_out must be after punch_in")
            if final_out - final_in > timedelta(hours=24):
                raise HTTPException(422, "punch_out must be within 24 hours")
            hours = compute_work_hours(final_in, final_out)
            updates["work_hours"] = hours
            updates["half_day"] = hours < 4.50
            updates["overtime_minutes"] = compute_overtime(
                final_out, emp["shift_start"], emp["shift_end"], final_in)
        else:
            updates["work_hours"] = None
            updates["half_day"] = False
            updates["overtime_minutes"] = 0
        updates["late_minutes"] = compute_late_minutes(final_in, emp["shift_start"])

    changes = {}
    for key, new_value in updates.items():
        old_value = record.get(key)
        if old_value != new_value:
            changes[key] = {"before": old_value, "after": new_value}
    if not changes:
        raise HTTPException(422, "No changes to regularize")

    history_entry = {
        "at": now_utc(),
        "regularized_by": body.regularized_by,
        "reason": body.reason,
        "changes": changes,
    }
    # Atomic append and update; history entries from concurrent requests are not overwritten.
    update_doc = {"$set": updates, "$push": {"history": history_entry}}
    result = attendance.update_one(
        {"_id": record["_id"]}, update_doc
    )
    if result.modified_count != 1:
        raise HTTPException(409, "Concurrent regularization conflict")
    updated = attendance.find_one({"_id": record["_id"]})
    return public_attendance(updated)


# ------------------------------ Aggregations ------------------------------

def monthly_match(month):
    month, start, end = validate_month(month)
    return month, start, end


@app.get("/analytics/employees/{emp_code}/monthly")

def employee_monthly(emp_code: str, month: str):
    month, start, end = monthly_match(month)

    emp = employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(404, "Employee not found")

    pipeline = [
        {
            "$match": {
                "emp_code": emp_code,
                "date": {
                    "$gte": start.isoformat(),
                    "$lt": end.isoformat(),
                },
            }
        },
        {
            "$addFields": {
                "day_date": {
                    "$dateFromString": {"dateString": "$date"}
                },
                "is_present": {
                    "$in": ["$status", list(PRESENT_STATUSES)]
                },
            }
        },
        {
            "$group": {
                "_id": None,
                "present_days_raw": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    "$is_present",
                                    {
                                        "$gte": [
                                            {"$dayOfWeek": "$day_date"},
                                            2,
                                        ]
                                    },
                                    {
                                        "$lte": [
                                            {"$dayOfWeek": "$day_date"},
                                            6,
                                        ]
                                    },
                                    {
                                        "$gte": [
                                            "$date",
                                            emp["joined_on"],
                                        ]
                                    },
                                ]
                            },
                            {
                                "$cond": [
                                    {"$eq": ["$half_day", True]},
                                    0.5,
                                    1,
                                ]
                            },
                            0,
                        ]
                    }
                },
                "leave_days": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$status", "LEAVE"]},
                            1,
                            0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$late_minutes", 0]},
                            1,
                            0,
                        ]
                    }
                },
                "late_minutes": {"$sum": "$late_minutes"},
                "total_overtime_minutes": {
                    "$sum": "$overtime_minutes"
                },
                "work_hours_total": {
                    "$sum": {"$ifNull": ["$work_hours", 0]}
                },
                "work_hours_count": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {
                                        "$in": [
                                            "$status",
                                            list(PRESENT_STATUSES),
                                        ]
                                    },
                                    {"$ne": ["$work_hours", None]},
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
            }
        },
    ]

    rows = list(attendance.aggregate(pipeline))
    stats = rows[0] if rows else {}

    join_date = date.fromisoformat(emp["joined_on"])
    cursor = max(start, join_date)
    working_days = 0

    while cursor < end:
        if cursor.weekday() < 5:
            working_days += 1
        cursor += timedelta(days=1)

    present_days = round_half_up(
        stats.get("present_days_raw", 0), 2
    )
    pct = (
        round_half_up(present_days / working_days * 100, 4)
        if working_days
        else None
    )

    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working_days,
        "present_days": present_days,
        "leave_days": stats.get("leave_days", 0),
        "late_count": stats.get("late_count", 0),
        "total_late_minutes": stats.get("late_minutes", 0),
        "total_overtime_minutes": stats.get(
            "total_overtime_minutes", 0
        ),
        "attendance_pct": pct,
    }



@app.get("/analytics/departments/summary")
def department_summary(month: str, department: Optional[str] = None):
    month, start, end = monthly_match(month)
    match_emp = {"$expr": {"$lte": ["$joined_on", end.isoformat()[:-3] + "31"]}}
    # Compute the true month-end date rather than assuming every month has 31 days.
    last_day = (end - timedelta(days=1)).isoformat()
    match_emp = {"joined_on": {"$lte": last_day}}
    if department:
        match_emp["department"] = department

    pipeline = [
        {"$match": match_emp},
        {"$lookup": {
            "from": "attendance_logs",
            "let": {"code": "$emp_code"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$emp_code", "$$code"]},
                    {"$gte": ["$date", start.isoformat()]},
                    {"$lt": ["$date", end.isoformat()]},
                ]}}},
                {"$project": {"status": 1, "late_minutes": 1, "work_hours": 1,
                              "half_day": 1}},
            ],
            "as": "logs",
        }},
        {"$unwind": {"path": "$logs", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": "$department",
            "headcount": {"$addToSet": "$emp_code"},
            "present_days": {"$sum": {"$cond": [
                {"$in": ["$logs.status", list(PRESENT_STATUSES)]},
                {"$cond": [{"$eq": ["$logs.half_day", True]}, 0.5, 1]}, 0]}},
            "late_count": {"$sum": {"$cond": [
                {"$gt": ["$logs.late_minutes", 0]}, 1, 0]}},
            "total_late_minutes": {"$sum": {"$ifNull": ["$logs.late_minutes", 0]}},
            "leave_count": {"$sum": {"$cond": [{"$eq": ["$logs.status", "LEAVE"]}, 1, 0]}},
            "on_duty_count": {"$sum": {"$cond": [{"$eq": ["$logs.status", "ON_DUTY"]}, 1, 0]}},
            "hours": {"$push": {"$cond": [
                {"$and": [{"$in": ["$logs.status", list(PRESENT_STATUSES)]},
                          {"$ne": ["$logs.work_hours", None]}]},
                "$logs.work_hours", None]}},
        }},
        {"$project": {
            "_id": 0, "department": "$_id",
            "headcount": {"$size": "$headcount"},
            "present_days": 1, "late_count": 1,
            "total_late_minutes": 1, "leave_count": 1, "on_duty_count": 1,
            "hours": {"$filter": {"input": "$hours", "as": "h",
                                  "cond": {"$ne": ["$$h", None]}}},
        }},
        {"$addFields": {
            "avg_work_hours": {"$cond": [
                {"$gt": [{"$size": "$hours"}, 0]},
                {"$round": [{"$avg": "$hours"}, 2]}, None]},
        }},
        {"$project": {"hours": 0}},
        {"$sort": {"department": 1}},
    ]
    return {"month": month, "items": list(employees.aggregate(pipeline))}


@app.get("/analytics/leaderboard/late")
def late_leaderboard(
    month: str,
    limit: int = Query(10, ge=1, le=100),
    department: Optional[str] = None,
):
    month, start, end = monthly_match(month)
    pipeline = [
        {"$match": {"date": {"$gte": start.isoformat(), "$lt": end.isoformat()},
                    "late_minutes": {"$gt": 0}}},
        {"$group": {"_id": "$emp_code", "total_late_minutes": {"$sum": "$late_minutes"},
                    "late_count": {"$sum": 1}}},
        {"$lookup": {"from": "employees", "localField": "_id",
                     "foreignField": "emp_code", "as": "employee"}},
        {"$unwind": "$employee"},
    ]
    if department:
        pipeline.append({"$match": {"employee.department": department}})
    pipeline += [
        {"$setWindowFields": {
            "sortBy": {"total_late_minutes": -1},
            "output": {"rank": {"$rank": {}}},
        }},
        {"$match": {"rank": {"$lte": limit}}},
        {"$sort": {"total_late_minutes": -1, "_id": 1}},
        {"$project": {"_id": 0, "emp_code": "$_id",
                      "name": "$employee.name", "department": "$employee.department",
                      "total_late_minutes": 1, "late_count": 1, "rank": 1}},
    ]
    return {"month": month, "items": list(attendance.aggregate(pipeline))}




@app.get("/analytics/departments/{department}/trend")
def department_trend(department: str, date_from: str, date_to: str):
    validate_date(date_from)
    validate_date(date_to)

    first = date.fromisoformat(date_from)
    last = date.fromisoformat(date_to)

    if last < first:
        raise HTTPException(422, "date_to must not precede date_from")
    if (last - first).days > 91:
        raise HTTPException(422, "Date range cannot exceed 92 days")
    if not employees.find_one({"department": department}):
        raise HTTPException(404, "Department not found")

    pipeline = [
        {
            "$match": {
                "date": {
                    "$gte": first.isoformat(),
                    "$lte": last.isoformat(),
                }
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "emp_code",
                "foreignField": "emp_code",
                "as": "employee",
            }
        },
        {"$unwind": "$employee"},
        {"$match": {"employee.department": department}},
        {
            "$group": {
                "_id": "$date",
                "present_count": {
                    "$sum": {
                        "$cond": [
                            {"$in": ["$status", list(PRESENT_STATUSES)]},
                            {
                                "$cond": [
                                    {"$eq": ["$half_day", True]},
                                    0.5,
                                    1,
                                ]
                            },
                            0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$late_minutes", 0]},
                            1,
                            0,
                        ]
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": "$_id",
                "present_count": 1,
                "late_count": 1,
            }
        },
        {
            "$set": {
                "day": {
                    "$dateFromString": {"dateString": "$date"}
                }
            }
        },
        {
            "$densify": {
                "field": "day",
                "range": {
                    "step": 1,
                    "unit": "day",
                    "bounds": [
                        datetime.combine(first, time.min),
                        datetime.combine(last + timedelta(days=1), time.min),
                    ],
                },
            }
        },
        {
            "$set": {
                "date": {
                    "$dateToString": {
                        "date": "$day",
                        "format": "%Y-%m-%d",
                    }
                },
                "present_count": {"$ifNull": ["$present_count", 0]},
                "late_count": {"$ifNull": ["$late_count", 0]},
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "let": {"day_string": "$date"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$department", department]},
                                    {"$lte": ["$joined_on", "$$day_string"]},
                                ]
                            }
                        }
                    },
                    {"$count": "count"},
                ],
                "as": "hc",
            }
        },
        {
            "$set": {
                "headcount": {
                    "$ifNull": [{"$arrayElemAt": ["$hc.count", 0]}, 0]
                },
                "is_working_day": {
                    "$and": [
                        {"$gte": [{"$dayOfWeek": "$day"}, 2]},
                        {"$lte": [{"$dayOfWeek": "$day"}, 6]},
                    ]
                },
            }
        },
        {
            "$set": {
                "attendance_rate": {
                    "$cond": [
                        {
                            "$and": [
                                "$is_working_day",
                                {"$gt": ["$headcount", 0]},
                            ]
                        },
                        {
                            "$round": [
                                {
                                    "$multiply": [
                                        {
                                            "$divide": [
                                                "$present_count",
                                                "$headcount",
                                            ]
                                        },
                                        100,
                                    ]
                                },
                                4,
                            ]
                        },
                        None,
                    ]
                }
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"day": 1},
                "output": {
                    "moving_avg_7d": {
                        "$avg": "$attendance_rate",
                        "window": {"range": [-6, 0], "unit": "day"},
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": 1,
                "is_working_day": 1,
                "headcount": 1,
                "present_count": 1,
                "late_count": 1,
                "attendance_rate": 1,
                "moving_avg_7d": {"$round": ["$moving_avg_7d", 4]},
            }
        },
        {"$sort": {"date": 1}},
    ]

    items = list(attendance.aggregate(pipeline, allowDiskUse=True))
    return {
        "department": department,
        "from": date_from,
        "to": date_to,
        "items": items,
    }



# ------------------------------ Explain -----------------------------------



@app.get("/admin/explain/{endpoint}")
def explain_endpoint(
    endpoint: Literal[
        "attendance_list",
        "employee_monthly",
        "department_summary",
        "late_leaderboard",
        "department_trend",
    ],
    emp_code: Optional[str] = None,
    month: Optional[str] = None,
    department: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    limit: int = Query(10, ge=1, le=50),
):
    if endpoint == "attendance_list":
        query = {}
        if emp_code:
            query["emp_code"] = emp_code
        if status:
            query["status"] = status

        if month:
            _, start, end = monthly_match(month)
            query["date"] = {
                "$gte": start.isoformat(),
                "$lt": end.isoformat(),
            }
        elif date_from or date_to:
            query["date"] = {}
            if date_from:
                query["date"]["$gte"] = validate_date(date_from)
            if date_to:
                query["date"]["$lte"] = validate_date(date_to)

        command = {
            "find": "attendance_logs",
            "filter": query,
            "sort": {"date": -1, "emp_code": 1},
            "skip": (page - 1) * page_size,
            "limit": page_size,
        }
        result = db.command({
            "explain": command,
            "verbosity": "executionStats",
        })

    elif endpoint == "employee_monthly":
        if not emp_code or not month:
            raise HTTPException(
                status_code=422,
                detail="emp_code and month are required",
            )
        _, start, end = monthly_match(month)
        if not employees.find_one({"emp_code": emp_code}):
            raise HTTPException(status_code=404, detail="Employee not found")

        pipeline = [{
            "$match": {
                "emp_code": emp_code,
                "date": {
                    "$gte": start.isoformat(),
                    "$lt": end.isoformat(),
                },
            }
        }]
        result = db.command({
            "explain": {
                "aggregate": "attendance_logs",
                "pipeline": pipeline,
                "cursor": {},
            },
            "verbosity": "executionStats",
        })

    elif endpoint == "department_summary":
        if not month:
            raise HTTPException(status_code=422, detail="month is required")
        _, start, end = monthly_match(month)
        query = {"joined_on": {"$lte": (end - timedelta(days=1)).isoformat()}}
        if department:
            query["department"] = department

        result = db.command({
            "explain": {
                "aggregate": "employees",
                "pipeline": [{"$match": query}],
                "cursor": {},
            },
            "verbosity": "executionStats",
        })

    elif endpoint == "late_leaderboard":
        if not month:
            raise HTTPException(status_code=422, detail="month is required")
        _, start, end = monthly_match(month)
        pipeline = [{
            "$match": {
                "date": {
                    "$gte": start.isoformat(),
                    "$lt": end.isoformat(),
                },
                "late_minutes": {"$gt": 0},
            }
        }]
        result = db.command({
            "explain": {
                "aggregate": "attendance_logs",
                "pipeline": pipeline,
                "cursor": {},
            },
            "verbosity": "executionStats",
        })

    else:
        if not department or not date_from or not date_to:
            raise HTTPException(
                status_code=422,
                detail="department, date_from and date_to are required",
            )

        start_date = validate_date(date_from)
        end_date = validate_date(date_to)
        if start_date > end_date:
            raise HTTPException(
                status_code=422,
                detail="date_from must be on or before date_to",
            )

        pipeline = [
            {
                "$match": {
                    "date": {"$gte": start_date, "$lte": end_date},
                }
            },
            {
                "$lookup": {
                    "from": "employees",
                    "localField": "emp_code",
                    "foreignField": "emp_code",
                    "as": "employee",
                }
            },
            {"$unwind": "$employee"},
            {"$match": {"employee.department": department}},
            {
                "$addFields": {
                    "day_date": {
                        "$dateFromString": {"dateString": "$date"}
                    }
                }
            },
            {
                "$setWindowFields": {
                    "sortBy": {"day_date": 1},
                    "output": {
                        "explain_window_count": {
                            "$sum": 1,
                            "window": {
                                "range": [-6, 0],
                                "unit": "day",
                            },
                        }
                    },
                }
            },
        ]
        result = db.command({
            "explain": {
                "aggregate": "attendance_logs",
                "pipeline": pipeline,
                "cursor": {},
            },
            "verbosity": "executionStats",
        })

    return json.loads(
        bson.json_util.dumps({
            "endpoint": endpoint,
            "collection": (
                "employees"
                if endpoint == "department_summary"
                else "attendance_logs"
            ),
            "explain": result,
        })
    )
