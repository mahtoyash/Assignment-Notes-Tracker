"""
Main Flask Web Application for GSM Assignment Alert System
Provides unified Authentication (Sign In & Register), Student Portal (/dashboard),
Admin Control Center (/admin), Microsoft OAuth 2.0 Integration, and Telephony Engine.
"""

import os
import time
import socket
import logging
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session

import config
import database
import ms_graph
import telephony
import scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask App
app = Flask(__name__)
app.secret_key = config.SECRET_KEY


def get_local_ip() -> str:
    """Detects local LAN IP address to display the accessible URL on Android / local WiFi."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# Start APScheduler background alert engine
scheduler.start_scheduler()


# ----------------------------------------------------------------------
# Authentication Decorators
# ----------------------------------------------------------------------

def login_required(f):
    """Requires user to be signed in."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to access your dashboard.", "info")
            return redirect(url_for("auth_view"))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Requires user to have 'admin' role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in as Administrator.", "info")
            return redirect(url_for("auth_view"))
        if session.get("role") != "admin":
            flash("Access restricted to System Administrators.", "error")
            return redirect(url_for("student_dashboard"))
        return f(*args, **kwargs)
    return decorated_function


@app.context_processor
def inject_global_template_vars():
    """Injects common variables into all Jinja2 templates."""
    return {
        "is_termux": config.is_termux_environment(),
        "host_ip": get_local_ip(),
        "port": config.PORT,
        "azure_configured": bool(config.AZURE_CLIENT_ID and config.AZURE_CLIENT_ID != "mock-client-id")
    }


# ----------------------------------------------------------------------
# Root & Authentication Routes
# ----------------------------------------------------------------------

@app.route("/")
def index():
    """Root redirect based on user role / session."""
    if "user_id" in session:
        if session.get("role") == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("student_dashboard"))
    return redirect(url_for("auth_view"))


@app.route("/auth")
def auth_view():
    """Unified Sign In / Register Landing Page."""
    if "user_id" in session:
        if session.get("role") == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("student_dashboard"))
    return render_template("auth.html")


@app.route("/auth/login", methods=["POST"])
def auth_login():
    """Authenticates student or admin using Email + Password or PIN."""
    email = request.form.get("email", "").strip()
    auth_type = request.form.get("auth_type", "password")
    password = request.form.get("password", "")
    pin = request.form.get("pin", "")

    if not email:
        flash("Please enter your email address.", "error")
        return redirect(url_for("auth_view"))

    user = None
    if auth_type == "pin":
        if not pin:
            flash("Please enter your 4-digit Security PIN.", "error")
            return redirect(url_for("auth_view"))
        user = database.authenticate_with_pin(email, pin)
    else:
        if not password:
            flash("Please enter your account password.", "error")
            return redirect(url_for("auth_view"))
        user = database.authenticate_user(email, password)

    if user:
        session["user_id"] = user["id"]
        session["uuid"] = user["uuid"]
        session["user_name"] = user["name"]
        session["email"] = user["email"]
        session["role"] = user["role"]

        flash(f"Welcome back, {user['name']}!", "success")
        if user["role"] == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("student_dashboard"))
    else:
        flash("Invalid email, password, or security PIN. Please try again.", "error")
        return redirect(url_for("auth_view"))


@app.route("/auth/register", methods=["POST"])
def auth_register():
    """Registers a new student profile and connects Microsoft account."""
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    phone_number = request.form.get("phone_number", "").strip()
    password = request.form.get("password", "")
    pin = request.form.get("pin", "")

    if not name or not email or not phone_number or not password or not pin:
        flash("All fields are required for registration.", "error")
        return redirect(url_for("auth_view"))

    user_id, err = database.register_user(
        name=name,
        email=email,
        password=password,
        pin=pin,
        phone_number=phone_number,
        role="student"
    )

    if err:
        flash(err, "error")
        return redirect(url_for("auth_view"))

    # Establish session
    user = database.get_user_by_id(user_id)
    session["user_id"] = user_id
    session["uuid"] = user["uuid"]
    session["user_name"] = user["name"]
    session["email"] = user["email"]
    session["role"] = "student"

    # Microsoft Account Connection
    if not config.AZURE_CLIENT_ID or config.AZURE_CLIENT_ID == "mock-client-id" or config.ENABLE_MOCK_DATA:
        # Pre-seed demo tokens and tasks for immediate testing
        database.save_user_tokens(
            user_id=user_id,
            account_id=f"mock_acc_{user_id}",
            account_email=email,
            access_token=f"mock_token_{user_id}",
            refresh_token=f"mock_refresh_{user_id}",
            expires_at=9999999999.0
        )
        ms_graph.get_mock_assignments(user_id)
        flash(f"Welcome to Assignment Alert System, {name}! Your portal is ready.", "success")
        return redirect(url_for("student_dashboard"))

    # Live Microsoft OAuth 2.0 Flow
    redirect_uri = url_for("oauth_callback", _external=True)
    auth_url, state = ms_graph.get_authorization_url(user_id, redirect_uri)
    session["oauth_state"] = state
    session["pending_user_id"] = user_id
    return redirect(auth_url)


@app.route("/logout")
def auth_logout():
    """Logs out current user and clears session."""
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth_view"))


# ----------------------------------------------------------------------
# Student Personal Dashboard
# ----------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def student_dashboard():
    """Personal Student Portal."""
    user_id = session["user_id"]
    current_user = database.get_user_by_id(user_id)
    if not current_user:
        session.clear()
        return redirect(url_for("auth_view"))

    # Fetch live deadlines
    assignments_summary = ms_graph.fetch_pending_assignments(user_id)

    # Fetch personal call history for this student
    personal_call_logs = database.get_recent_call_logs(limit=25, user_id=user_id)

    return render_template(
        "dashboard.html",
        current_user=current_user,
        assignments_summary=assignments_summary,
        call_logs=personal_call_logs
    )


# ----------------------------------------------------------------------
# Admin Control Center
# ----------------------------------------------------------------------

@app.route("/admin")
@admin_required
def admin_dashboard():
    """System Administrator Control Center."""
    students = database.get_all_students()
    stats = database.get_system_stats()
    call_logs = database.get_recent_call_logs(limit=50)
    sched_status = scheduler.get_scheduler_status()

    return render_template(
        "admin.html",
        students=students,
        stats=stats,
        call_logs=call_logs,
        scheduler_status=sched_status,
        weekday_schedule=config.WEEKDAY_SCHEDULE,
        weekend_schedule=config.WEEKEND_SCHEDULE
    )


@app.route("/settings")
@admin_required
def settings_view():
    """System and Hardware Settings View."""
    redirect_uri = url_for("oauth_callback", _external=True)
    return render_template(
        "settings.html",
        azure_client_id=config.AZURE_CLIENT_ID,
        azure_tenant=config.AZURE_TENANT_ID,
        redirect_uri=redirect_uri
    )


# ----------------------------------------------------------------------
# Microsoft OAuth 2.0 Connect & Callback
# ----------------------------------------------------------------------

@app.route("/connect-ms/<int:user_id>")
@login_required
def connect_ms(user_id: int):
    """Initiates Microsoft OAuth login for a student."""
    # Ensure students can only connect their own account unless admin
    if session.get("role") != "admin" and session.get("user_id") != user_id:
        flash("Unauthorized action.", "error")
        return redirect(url_for("student_dashboard"))

    user = database.get_user_by_id(user_id)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("index"))

    session["pending_user_id"] = user_id

    if not config.AZURE_CLIENT_ID or config.AZURE_CLIENT_ID == "mock-client-id" or config.ENABLE_MOCK_DATA:
        database.save_user_tokens(
            user_id=user_id,
            account_id=f"mock_acc_{user_id}",
            account_email=user["email"],
            access_token=f"mock_token_{user_id}",
            refresh_token=f"mock_refresh_{user_id}",
            expires_at=9999999999.0
        )
        ms_graph.get_mock_assignments(user_id)
        flash(f"Microsoft Account linked for {user['name']}!", "success")
        return redirect(url_for("student_dashboard"))

    redirect_uri = url_for("oauth_callback", _external=True)
    auth_url, state = ms_graph.get_authorization_url(user_id, redirect_uri)
    session["oauth_state"] = state
    return redirect(auth_url)


@app.route("/callback")
def oauth_callback():
    """OAuth 2.0 Redirect Callback handler from Microsoft."""
    code = request.args.get("code")
    error = request.args.get("error")
    error_desc = request.args.get("error_description")

    if error:
        flash(f"Microsoft Login Error: {error_desc or error}", "error")
        return redirect(url_for("index"))

    if not code:
        flash("Authorization code missing in callback.", "error")
        return redirect(url_for("index"))

    redirect_uri = url_for("oauth_callback", _external=True)
    token_response = ms_graph.exchange_code_for_tokens(code, redirect_uri)

    if "access_token" in token_response:
        access_token = token_response["access_token"]
        refresh_token = token_response.get("refresh_token")
        expires_in = token_response.get("expires_in", 3600)
        expires_at = time.time() + expires_in

        profile = ms_graph.fetch_user_profile(access_token)
        account_email = profile.get("mail") or profile.get("userPrincipalName") if profile else "student@vitstudent.ac.in"
        account_id = profile.get("id") if profile else "ms_account"

        user_id = session.get("pending_user_id") or session.get("user_id")
        if user_id:
            database.save_user_tokens(
                user_id=user_id,
                account_id=account_id,
                account_email=account_email,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at
            )
            ms_graph.fetch_pending_assignments(user_id)
            flash("Microsoft Account successfully connected! Alert system is active.", "success")
        else:
            flash("Microsoft login completed, but user session was lost.", "error")
    else:
        err_msg = token_response.get("error_description", "Unknown OAuth error")
        flash(f"Failed to acquire Microsoft tokens: {err_msg}", "error")

    return redirect(url_for("index"))


# ----------------------------------------------------------------------
# REST API Endpoints (AJAX Actions)
# ----------------------------------------------------------------------

@app.route("/api/users/<int:user_id>/call", methods=["POST"])
@login_required
def api_test_call(user_id: int):
    """Triggers an immediate GSM call and voice alert for a student."""
    # Authorization: Students can only call themselves, Admin can call anyone
    if session.get("role") != "admin" and session.get("user_id") != user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    user = database.get_user_by_id(user_id)
    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    data = ms_graph.fetch_pending_assignments(user_id)
    due_today = data.get("due_today", [])
    due_tomorrow = data.get("due_tomorrow", [])

    message = telephony.build_voice_message(user["name"], due_today, due_tomorrow)

    result = telephony.dial_and_speak(
        phone_number=user["phone_number"],
        message=message,
        user_name=user["name"],
        user_id=user_id,
        trigger_type="manual_test",
        tasks_due_today=len(due_today),
        tasks_due_tomorrow=len(due_tomorrow)
    )

    status_str = result.get("status", "")
    is_success = "SUCCESS" in status_str or "SIMULATED" in status_str

    return jsonify({
        "success": is_success,
        "status": status_str,
        "error": status_str if not is_success else None,
        "message": message,
        "phone_number": user["phone_number"]
    })


@app.route("/api/alerts/trigger-all", methods=["POST"])
@admin_required
def api_trigger_all():
    """Immediately processes the sequential batch alert queue for all active students (Admin only)."""
    results = telephony.process_batch_alert_queue(trigger_type="admin_batch")
    return jsonify({
        "success": True,
        "dispatched": len(results),
        "details": results
    })


@app.route("/api/users/<int:user_id>/toggle", methods=["POST"])
@login_required
def api_toggle_user(user_id: int):
    """Toggles active/paused state for a student."""
    if session.get("role") != "admin" and session.get("user_id") != user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    is_active = database.toggle_user_status(user_id)
    return jsonify({"success": True, "is_active": is_active})


@app.route("/api/users/<int:user_id>/delete", methods=["POST"])
@login_required
def api_delete_user(user_id: int):
    """Deletes a student account."""
    is_self = (session.get("user_id") == user_id)
    if session.get("role") != "admin" and not is_self:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    database.delete_user(user_id)
    if is_self:
        session.clear()

    return jsonify({"success": True})


@app.route("/api/status")
def api_status():
    """Returns server health, scheduler info, and stats."""
    return jsonify({
        "scheduler": scheduler.get_scheduler_status(),
        "stats": database.get_system_stats(),
        "is_termux": config.is_termux_environment(),
        "host_ip": get_local_ip()
    })


if __name__ == "__main__":
    print(f"""
    ================================================================
    GSM Assignment Alert System Server Running!
    ----------------------------------------------------------------
    * Local URL:      http://127.0.0.1:{config.PORT}
    * Network URL:    http://{get_local_ip()}:{config.PORT}
    * Admin Login:    admin@sys.tem  /  admin123
    * Telephony Mode: {'Android Termux (GSM SIM)' if config.is_termux_environment() else 'PC Audio Simulator'}
    ================================================================
    """)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
