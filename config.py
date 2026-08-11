"""
Configuration Module for GSM Assignment Alert System
Handles environment loading, Azure OAuth endpoints, schedules, and platform detection.
"""

import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# Flask Server Config
SECRET_KEY = os.getenv("SECRET_KEY", "gsm-alert-system-default-secret-key-2026")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 5000))
DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")

# Database Path
DB_PATH = BASE_DIR / "alert_system.db"

# Microsoft Azure Active Directory / Entra ID Config
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "common")

AUTHORITY = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
GRAPH_ENDPOINT = "https://graph.microsoft.com/v1.0"

# OAuth 2.0 Scopes required for reading assignments & offline token refreshes
DEFAULT_SCOPES = [
    "User.Read",
    "Tasks.Read",
    "offline_access"
]
SCOPES_ENV = os.getenv("AZURE_SCOPES")
SCOPES = [s.strip() for s in SCOPES_ENV.split(",")] if SCOPES_ENV else DEFAULT_SCOPES

# Scheduled Alert Timestamps (24-hour format: hour, minute)
# Project Spec: Weekdays 11:01 AM, 6:00 PM, 8:45 PM | Weekends 10:00 AM, 6:00 PM, 8:45 PM
WEEKDAY_SCHEDULE = [
    {"hour": 11, "minute": 1, "label": "11:01 AM"},
    {"hour": 18, "minute": 0, "label": "06:00 PM"},
    {"hour": 20, "minute": 45, "label": "08:45 PM"}
]

WEEKEND_SCHEDULE = [
    {"hour": 10, "minute": 0, "label": "10:00 AM"},
    {"hour": 18, "minute": 0, "label": "06:00 PM"},
    {"hour": 20, "minute": 45, "label": "08:45 PM"}
]

# Telephony Provider & Twilio Config
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "+17372212163")
TELEPHONY_PROVIDER = os.getenv("TELEPHONY_PROVIDER", "auto").lower()

def is_twilio_enabled() -> bool:
    """Returns True if Twilio credentials are fully configured."""
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER)

# Telephony Mode Detection for Termux
def is_termux_environment() -> bool:
    mode = os.getenv("TELEPHONY_MODE", "auto").lower()
    if mode == "termux":
        return True
    if mode == "simulate":
        return False
    
    # Auto-detection check
    is_android_termux = "TERMUX_VERSION" in os.environ or "PREFIX" in os.environ
    has_termux_call = shutil.which("termux-telephony-call") is not None
    return is_android_termux and has_termux_call

ENABLE_MOCK_DATA = os.getenv("ENABLE_MOCK_DATA", "false").lower() in ("true", "1", "yes")

