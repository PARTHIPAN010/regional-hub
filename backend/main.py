import logging
import os
import smtplib
import tempfile
from contextlib import contextmanager
from datetime import date as dt_date, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from filelock import FileLock, Timeout
from pydantic import BaseModel, EmailStr, constr
from starlette.background import BackgroundTask

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = BASE_DIR / "index.html"
ADMIN_INDEX_FILE = BASE_DIR / "admin.html"
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

app = FastAPI(
    title="Digital Visitor Log Book API",
    docs_url=None,
    redoc_url=None,
)
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = BASE_DIR.parent / "visitors.xlsx"
LOCK_FILE = BASE_DIR.parent / "visitors.xlsx.lock"
DATA_FILE_BUSY_MESSAGE = (
    "The registration file is temporarily busy. Please wait a moment and submit again."
)

COLUMNS = [
    "S.No",
    "Date",
    "Visitor Name",
    "Organization Name",
    "Contact Number",
    "Mail ID",
    "Region",
    "Purpose",
    "Further Support",
    "E-Signature",
]

EMAIL_HOST = os.getenv("MAIL_SERVER", os.getenv("EMAIL_HOST"))
EMAIL_PORT = int(os.getenv("MAIL_PORT", os.getenv("EMAIL_PORT", "587")))
EMAIL_USERNAME = os.getenv("MAIL_USERNAME", os.getenv("EMAIL_USERNAME"))
EMAIL_PASSWORD = os.getenv("MAIL_PASSWORD", os.getenv("EMAIL_PASSWORD"))
EMAIL_FROM = os.getenv("MAIL_DEFAULT_SENDER", os.getenv("EMAIL_FROM", EMAIL_USERNAME))
EMAIL_USE_TLS = os.getenv("MAIL_USE_TLS", os.getenv("EMAIL_USE_TLS", "true")).lower() in {
    "1",
    "true",
    "yes",
    "on",
}
ADMIN_NOTIFICATION_EMAIL = os.getenv("ADMIN_NOTIFICATION_EMAIL", EMAIL_FROM or EMAIL_USERNAME)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin$321")
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "7010"))
APP_RELOAD = os.getenv("APP_RELOAD", "false").lower() in {"1", "true", "yes", "on"}


class VisitorInput(BaseModel):
    visitor_name: constr(strip_whitespace=True, min_length=1)
    organization_name: constr(strip_whitespace=True, min_length=1)
    contact_number: constr(strip_whitespace=True, min_length=5)
    mail_id: EmailStr
    region: Literal["Trichy", "Madurai", "Coimbatore"]
    purpose: constr(strip_whitespace=True, min_length=1)
    further_support: Optional[constr(strip_whitespace=True, max_length=500)] = ""
    signature: constr(strip_whitespace=True, min_length=20)
    date: Optional[dt_date] = None


class VisitorOutput(BaseModel):
    serial_number: int
    visitor_name: str
    organization_name: str
    contact_number: str
    mail_id: EmailStr
    region: str
    purpose: str
    further_support: str
    date: dt_date
    email_sent: bool
    admin_notified: bool
    message: str


class AdminLoginInput(BaseModel):
    password: constr(strip_whitespace=True, min_length=1)


def ensure_file_exists():
    if not DATA_FILE.exists():
        try:
            df = pd.DataFrame(columns=COLUMNS)
            df.to_excel(DATA_FILE, index=False, engine="openpyxl")
        except PermissionError as exc:
            raise HTTPException(
                status_code=503,
                detail=DATA_FILE_BUSY_MESSAGE,
            ) from exc


def normalize_date_value(value):
    if pd.isna(value):
        return ""

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, dt_date):
        return value.isoformat()

    text = str(value).strip()
    if not text:
        return ""

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text


def normalize_visitors_df(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for column in COLUMNS:
        if column not in normalized.columns:
            normalized[column] = ""
    normalized = normalized.loc[:, COLUMNS]
    normalized = normalized.where(pd.notna(normalized), "")
    normalized["Date"] = normalized["Date"].map(normalize_date_value)
    return normalized


@contextmanager
def data_file_lock():
    lock = FileLock(str(LOCK_FILE), timeout=10)
    try:
        with lock:
            ensure_file_exists()
            yield
    except Timeout as exc:
        raise HTTPException(status_code=503, detail=DATA_FILE_BUSY_MESSAGE) from exc


def load_visitors_df_unlocked() -> pd.DataFrame:
    try:
        df = pd.read_excel(DATA_FILE, engine="openpyxl")
        return normalize_visitors_df(df)
    except PermissionError as exc:
        raise HTTPException(
            status_code=503,
            detail=DATA_FILE_BUSY_MESSAGE,
        ) from exc


def save_visitors_df_unlocked(df: pd.DataFrame):
    try:
        normalized = normalize_visitors_df(df)
        normalized.to_excel(DATA_FILE, index=False, engine="openpyxl")
    except PermissionError as exc:
        raise HTTPException(
            status_code=503,
            detail=DATA_FILE_BUSY_MESSAGE,
        ) from exc


def sync_data_file_columns_unlocked():
    ensure_file_exists()
    try:
        raw_df = pd.read_excel(DATA_FILE, engine="openpyxl")
    except PermissionError as exc:
        raise HTTPException(
            status_code=503,
            detail=DATA_FILE_BUSY_MESSAGE,
        ) from exc

    raw_normalized_blanks = raw_df.copy()
    for column in COLUMNS:
        if column not in raw_normalized_blanks.columns:
            raw_normalized_blanks[column] = ""
    raw_normalized_blanks = raw_normalized_blanks.loc[:, COLUMNS].where(
        pd.notna(raw_normalized_blanks.loc[:, COLUMNS]), ""
    )

    normalized_df = normalize_visitors_df(raw_df)
    if list(raw_df.columns) != COLUMNS or not normalized_df.equals(raw_normalized_blanks):
        save_visitors_df_unlocked(normalized_df)


def read_visitors_df() -> pd.DataFrame:
    with data_file_lock():
        return load_visitors_df_unlocked()


def get_next_serial(df: pd.DataFrame) -> int:
    if df.empty:
        return 1
    values = pd.to_numeric(df["S.No"], errors="coerce")
    if values.isnull().all():
        return 1
    return int(values.max()) + 1


def verify_admin_password(password: Optional[str]):
    if not password or password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid admin password.")


def build_visitor_confirmation_email(
    visitor_name: str,
    to_email: str,
    organization_name: str,
    region: str,
    purpose: str,
    further_support: str,
    entry_date: dt_date,
):
    msg = EmailMessage()
    msg["Subject"] = "Your Regional Hub submission was received"
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    msg.set_content(
        f"""
Hello {visitor_name},

Your details have been received successfully by the Regional Hub team.

Submission summary:
- Date: {entry_date.strftime("%Y-%m-%d")}
- Organization: {organization_name}
- Region: {region}
- Purpose: {purpose}
- Further Support: {further_support or "None requested"}
- E-signature: received

We appreciate your interest and will be in touch if anything else is needed.

Regards,
Regional Hub Team
""".strip()
    )

    return msg


def build_admin_notification_email(
    visitor_name: str,
    visitor_email: str,
    contact_number: str,
    organization_name: str,
    region: str,
    purpose: str,
    further_support: str,
    entry_date: dt_date,
):
    msg = EmailMessage()
    msg["Subject"] = f"New Regional Hub registration: {visitor_name}"
    msg["From"] = EMAIL_FROM
    msg["To"] = ADMIN_NOTIFICATION_EMAIL
    msg.set_content(
        f"""
A new visitor registration was submitted.

Registration summary:
- Date: {entry_date.strftime("%Y-%m-%d")}
- Visitor Name: {visitor_name}
- Organization: {organization_name}
- Region: {region}
- Contact Number: {contact_number}
- Email: {visitor_email}
- Purpose: {purpose}
- Further Support: {further_support or "None requested"}
- E-signature: received.
""".strip()
    )
    return msg


def send_submission_notifications(
    visitor_name: str,
    visitor_email: str,
    contact_number: str,
    organization_name: str,
    region: str,
    purpose: str,
    further_support: str,
    entry_date: dt_date,
):
    if not all([EMAIL_HOST, EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_FROM]):
        raise RuntimeError("Email service is not configured.")

    visitor_message = build_visitor_confirmation_email(
        visitor_name=visitor_name,
        to_email=visitor_email,
        organization_name=organization_name,
        region=region,
        purpose=purpose,
        further_support=further_support,
        entry_date=entry_date,
    )

    admin_message = None
    if ADMIN_NOTIFICATION_EMAIL:
        admin_message = build_admin_notification_email(
            visitor_name=visitor_name,
            visitor_email=visitor_email,
            contact_number=contact_number,
            organization_name=organization_name,
            region=region,
            purpose=purpose,
            further_support=further_support,
            entry_date=entry_date,
        )

    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=20) as server:
            server.ehlo()
            if EMAIL_USE_TLS:
                server.starttls()
                server.ehlo()
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            server.send_message(visitor_message)
            if admin_message is not None:
                server.send_message(admin_message)
    except smtplib.SMTPAuthenticationError as exc:
        if EMAIL_HOST and "gmail" in EMAIL_HOST.lower():
            raise RuntimeError(
                "SMTP authentication failed. Gmail rejected the login. "
                "Use the Gmail address as MAIL_USERNAME and a Google App Password as MAIL_PASSWORD."
            ) from exc
        raise RuntimeError(
            "SMTP authentication failed. Check MAIL_USERNAME and MAIL_PASSWORD."
        ) from exc

    return {"email_sent": True, "admin_notified": admin_message is not None}


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def initialize_storage():
    with data_file_lock():
        sync_data_file_columns_unlocked()


@app.get("/", include_in_schema=False)
async def serve_landing_page():
    return FileResponse(INDEX_FILE)


@app.get("/admin", include_in_schema=False)
async def serve_admin_page():
    return FileResponse(ADMIN_INDEX_FILE)


@app.post("/admin/login")
async def admin_login(payload: AdminLoginInput):
    verify_admin_password(payload.password)
    return {"success": True, "message": "Admin access granted."}


@app.post("/add-visitor", response_model=VisitorOutput)
async def add_visitor(payload: VisitorInput):
    entry_date = payload.date or dt_date.today()
    row = {
        "Date": entry_date.strftime("%Y-%m-%d"),
        "Visitor Name": payload.visitor_name.strip(),
        "Organization Name": payload.organization_name.strip(),
        "Contact Number": payload.contact_number.strip(),
        "Mail ID": payload.mail_id.strip(),
        "Region": payload.region.strip(),
        "Purpose": payload.purpose.strip(),
        "Further Support": (payload.further_support or "").strip(),
        "E-Signature": payload.signature.strip(),
    }

    with data_file_lock():
        df = load_visitors_df_unlocked()
        serial = get_next_serial(df)
        row["S.No"] = serial
        new_row_df = pd.DataFrame([row], columns=COLUMNS)
        df = pd.concat([df, new_row_df], ignore_index=True)
        save_visitors_df_unlocked(df)

    email_sent = False
    admin_notified = False
    message = "Your details were submitted successfully."
    try:
        notification_result = send_submission_notifications(
            visitor_name=row["Visitor Name"],
            visitor_email=row["Mail ID"],
            contact_number=row["Contact Number"],
            organization_name=row["Organization Name"],
            region=row["Region"],
            purpose=row["Purpose"],
            further_support=row["Further Support"],
            entry_date=entry_date,
        )
        email_sent = notification_result["email_sent"]
        admin_notified = notification_result["admin_notified"]
        message = "Your details were submitted and the confirmation email has been sent."
    except Exception as exc:
        logger.exception("Email send failure for %s", payload.mail_id)
        message = f"Your details were saved, but the confirmation email could not be sent: {exc}"

    return VisitorOutput(
        serial_number=serial,
        visitor_name=row["Visitor Name"],
        date=entry_date,
        organization_name=row["Organization Name"],
        contact_number=row["Contact Number"],
        mail_id=row["Mail ID"],
        region=row["Region"],
        purpose=row["Purpose"],
        further_support=row["Further Support"],
        email_sent=email_sent,
        admin_notified=admin_notified,
        message=message,
    )


@app.get("/visitors")
async def get_visitors(date: Optional[str] = None, organization: Optional[str] = None):
    df = read_visitors_df()
    if date:
        try:
            parsed = datetime.strptime(date, "%Y-%m-%d").date()
            df = df[df["Date"] == parsed.strftime("%Y-%m-%d")]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

    if organization:
        df = df[df["Organization Name"].str.contains(organization, case=False, na=False)]

    df = df.sort_values(by="S.No", key=lambda values: pd.to_numeric(values, errors="coerce"))
    return df.to_dict(orient="records")


@app.get("/admin/registrations")
async def admin_registrations(admin_key: Optional[str] = Header(None, alias="X-Admin-Key")):
    verify_admin_password(admin_key)
    df = read_visitors_df()
    df = df.sort_values(by="S.No", key=lambda values: pd.to_numeric(values, errors="coerce"), ascending=False)
    return {"count": int(len(df.index)), "items": df.to_dict(orient="records")}


def create_export_snapshot() -> Path:
    with data_file_lock():
        ensure_file_exists()
        try:
            df = load_visitors_df_unlocked()
            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".xlsx",
                prefix="regional-hub-export-",
                dir=str(BASE_DIR),
            )
            temp_path = Path(temp_file.name)
            temp_file.close()
            df.to_excel(temp_path, index=False, engine="openpyxl")
        except PermissionError as exc:
            raise HTTPException(
                status_code=503,
                detail=DATA_FILE_BUSY_MESSAGE,
            ) from exc
    return temp_path


def remove_temp_file(path_str: str):
    Path(path_str).unlink(missing_ok=True)


@app.get("/admin/export")
async def admin_export(admin_key: Optional[str] = Header(None, alias="X-Admin-Key")):
    verify_admin_password(admin_key)
    snapshot_path = create_export_snapshot()
    return FileResponse(
        snapshot_path,
        filename=f"regional-hub-registrations-{dt_date.today().strftime('%Y-%m-%d')}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        background=BackgroundTask(remove_temp_file, str(snapshot_path)),
    )


@app.delete("/visitor/{serial_number}")
async def delete_visitor(serial_number: int):
    with data_file_lock():
        df = load_visitors_df_unlocked()
        serial_numbers = pd.to_numeric(df["S.No"], errors="coerce")
        if not (serial_numbers == serial_number).any():
            raise HTTPException(status_code=404, detail="Visitor entry not found")

        df = df.loc[serial_numbers != serial_number].copy()
        save_visitors_df_unlocked(df)

    return {"success": True, "deleted": serial_number}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=APP_HOST, port=APP_PORT, reload=APP_RELOAD)
