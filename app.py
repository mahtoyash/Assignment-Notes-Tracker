"""
Main Flask Web Application for GSM Assignment Alert System
Serves the multi-user web dashboard, manages Microsoft OAuth 2.0 logins,
and coordinates background scheduling and telephony alert triggers.
"""

import os
import socket
import logging
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


# Start APScheduler background engine
scheduler.start_scheduler()


# ----------------------------------------------------------------------
# Web Views / Pages
# ----------------------------------------------------------------------

@app.route("/")
def index():
    """Main Web Dashboard."""
    users = database.get_all_users()
    stats = database.get_system_stats()
    call_logs = database.get_recent_call_logs(limit=25)
    sched_status = scheduler.get_scheduler_status()

    # Get sample assignments summary from first active user if available
    assignments_summary = None
    if users:
        first_user_id = users[0]["id"]
        assignments_summary = ms_graph.fetch_pending_assignments(first_user_id)

    return render_template(
        "index.html",
        users=users,
        stats=stats,
        call_logs=call_logs,
        scheduler_status=sched_status,
        assignments_summary=assignments_summary,
        weekday_schedule=config.WEEKDAY_SCHEDULE,
        weekend_schedule=config.WEEKEND_SCHEDULE,
        is_termux=config.is_termux_environment(),
        azure_configured=bool(config.AZURE_CLIENT_ID and config.AZURE_CLIENT_ID != "mock-client-id"),
        host_ip=get_local_ip(),
        port=config.PORT
    )


@app.route("/settings")
def settings_view():
    """System and Hardware Settings View."""
    redirect_uri = url_for("oauth_callback", _external=True)
    return render_template(
        "settings.html",
        azure_client_id=config.AZURE_CLIENT_ID,
        azure_tenant=config.AZURE_TENANT_ID,
        redirect_uri=redirect_uri,
        is_termux=config.is_termux_environment()
    )


# ----------------------------------------------------------------------
# Student Registration & Microsoft OAuth Flow
# ----------------------------------------------------------------------

@app.route("/register", methods=["POST"])
def register_student():
    """Registers a student profile and initiates Microsoft OAuth 2.0 login."""
    name = request.form.get("name", "").strip()
    phone_number = request.form.get("phone_number", "").strip()

    if not name or not phone_number:
        flash("Please provide both student name and phone number.", "error")
        return redirect(url_for("index"))

    user_id = database.create_or_update_user(name, phone_number)
    session["pending_user_id"] = user_id

    # If Azure Client ID is not configured or mock mode is active, simulate instant MS connection
    if not config.AZURE_CLIENT_ID or config.AZURE_CLIENT_ID == "mock-client-id" or config.ENABLE_MOCK_DATA:
        # Mock token save for instant testing
        database.save_user_tokens(
            user_id=user_id,
            account_id=f"mock_acc_{user_id}",
            account_email=f"{name.lower().replace(' ', '')}@student.college.edu",
            access_token=f"mock_token_{user_id}",
            refresh_token=f"mock_refresh_{user_id}",
            expires_at=9999999999.0
        )
        # Pre-cache realistic assignments
        ms_graph.get_mock_assignments(user_id)
        flash(f"🎉 Student {name} registered and connected with Microsoft Account (Demo Mode)!", "success")
        return redirect(url_for("index"))

    # Live Microsoft OAuth 2.0 Flow
    redirect_uri = url_for("oauth_callback", _external=True)
    auth_url, state = ms_graph.get_authorization_url(user_id, redirect_uri)
    session["oauth_state"] = state

    return redirect(auth_url)


@app.route("/connect-ms/<int:user_id>")
def connect_ms(user_id: int):
    """Initiates Microsoft OAuth login for an existing registered student."""
    user = database.get_user_by_id(user_id)
    if not user:
        flash("Student not found.", "error")
        return redirect(url_for("index"))

    session["pending_user_id"] = user_id

    if not config.AZURE_CLIENT_ID or config.AZURE_CLIENT_ID == "mock-client-id" or config.ENABLE_MOCK_DATA:
        database.save_user_tokens(
            user_id=user_id,
            account_id=f"mock_acc_{user_id}",
            account_email=f"{user['name'].lower().replace(' ', '')}@student.college.edu",
            access_token=f"mock_token_{user_id}",
            refresh_token=f"mock_refresh_{user_id}",
            expires_at=9999999999.0
        )
        ms_graph.get_mock_assignments(user_id)
        flash(f"Microsoft Account linked for {user['name']}!", "success")
        return redirect(url_for("index"))

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

        # Fetch profile info
        profile = ms_graph.fetch_user_profile(access_token)
        account_email = profile.get("mail") or profile.get("userPrincipalName") if profile else "student@microsoft.com"
        account_id = profile.get("id") if profile else "ms_account"

        user_id = session.get("pending_user_id")
        if user_id:
            database.save_user_tokens(
                user_id=user_id,
                account_id=account_id,
                account_email=account_email,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at
            )
            # Fetch and cache initial assignments
            ms_graph.fetch_pending_assignments(user_id)
            flash("✅ Microsoft Account successfully connected! Alert system is active.", "success")
        else:
            flash("Logged in with Microsoft, but user session was lost. Please re-enter details.", "error")
    else:
        err_msg = token_response.get("error_description", "Unknown OAuth error")
        flash(f"Failed to acquire Microsoft tokens: {err_msg}", "error")

    return redirect(url_for("index"))


# ----------------------------------------------------------------------
# REST API Endpoints (AJAX Actions)
# ----------------------------------------------------------------------

@app.route("/api/users/<int:user_id>/call", methods=["POST"])
def api_test_call(user_id: int):
    """Triggers an immediate GSM call and voice alert for a single student."""
    user = database.get_user_by_id(user_id)
    if not user:
        return jsonify({"success": False, "error": "User not found"}), 404

    # Fetch live deadlines
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

    return jsonify({
        "success": True,
        "status": result["status"],
        "message": message,
        "phone_number": user["phone_number"]
    })


@app.route("/api/alerts/trigger-all", methods=["POST"])
def api_trigger_all():
    """Immediately processes the sequential batch alert queue for all active students."""
    results = telephony.process_batch_alert_queue(trigger_type="manual_batch")
    return jsonify({
        "success": True,
        "dispatched": len(results),
        "details": results
    })


@app.route("/api/users/<int:user_id>/toggle", methods=["POST"])
def api_toggle_user(user_id: int):
    """Toggles active/paused state for a student."""
    is_active = database.toggle_user_status(user_id)
    return jsonify({"success": True, "is_active": is_active})


@app.route("/api/users/<int:user_id>/delete", methods=["POST"])
def api_delete_user(user_id: int):
    """Deletes a student."""
    database.delete_user(user_id)
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
    import time
    print(f"""
    ================================================================
    📞 GSM Assignment Alert System Server Started!
    ----------------------------------------------------------------
    • Local Web UI:    http://127.0.0.1:{config.PORT}
    • Network Web UI:  http://{get_local_ip()}:{config.PORT}
    • Telephony Mode:  {'Android Termux (GSM SIM)' if config.is_termux_environment() else 'PC Audio Simulator'}
    • Daily Schedules: Mon-Fri (11:01 AM, 6:00 PM, 8:45 PM)
                       Sat-Sun (10:00 AM, 6:00 PM, 8:45 PM)
    ================================================================
    """)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
