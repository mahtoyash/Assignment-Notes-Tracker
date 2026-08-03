"""
Microsoft Graph API & OAuth Engine for GSM Assignment Alert System
Handles OAuth 2.0 authorization, multi-user token refresh, and fetching assignments from Teams / To-Do / Outlook.
"""

import time
import datetime
import logging
import requests
import msal
from typing import Dict, Any, List, Optional, Tuple

import config
import database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_msal_client() -> msal.ConfidentialClientApplication | msal.PublicClientApplication:
    """Instantiates the MSAL client (Confidential if client secret is provided, else Public)."""
    client_id = config.AZURE_CLIENT_ID or "mock-client-id"
    authority = config.AUTHORITY

    if config.AZURE_CLIENT_SECRET:
        return msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=config.AZURE_CLIENT_SECRET,
            authority=authority
        )
    return msal.PublicClientApplication(
        client_id=client_id,
        authority=authority
    )


def get_authorization_url(user_id: int, redirect_uri: str) -> Tuple[str, str]:
    """
    Generates Microsoft OAuth 2.0 authorization URL for a student.
    Returns (auth_url, state).
    """
    client = build_msal_client()
    state = f"user_{user_id}_{int(time.time())}"
    auth_url = client.get_authorization_request_url(
        scopes=config.SCOPES,
        redirect_uri=redirect_uri,
        state=state,
        prompt="select_account"
    )
    return auth_url, state


def exchange_code_for_tokens(code: str, redirect_uri: str) -> Dict[str, Any]:
    """Exchanges the authorization code returned by Microsoft for access & refresh tokens."""
    client = build_msal_client()
    result = client.acquire_token_by_authorization_code(
        code=code,
        scopes=config.SCOPES,
        redirect_uri=redirect_uri
    )
    return result


def refresh_access_token_if_needed(user_id: int) -> Optional[str]:
    """
    Retrieves and refreshes the user's Microsoft Graph access token using their stored refresh token.
    Updates the database with new token values.
    """
    tokens = database.get_user_tokens(user_id)
    if not tokens or not tokens.get("refresh_token"):
        logger.warning(f"No refresh token available for user_id={user_id}")
        return None

    expires_at = tokens.get("expires_at") or 0
    current_time = time.time()

    # If current access token is still valid for at least 5 more minutes, use it
    if tokens.get("access_token") and expires_at > (current_time + 300):
        return tokens["access_token"]

    # Acquire fresh token using refresh_token
    client = build_msal_client()
    result = client.acquire_token_by_refresh_token(
        refresh_token=tokens["refresh_token"],
        scopes=config.SCOPES
    )

    if "access_token" in result:
        new_access_token = result["access_token"]
        new_refresh_token = result.get("refresh_token", tokens["refresh_token"])
        expires_in = result.get("expires_in", 3600)
        new_expires_at = current_time + expires_in

        database.save_user_tokens(
            user_id=user_id,
            account_id=tokens.get("account_id"),
            account_email=tokens.get("account_email"),
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_at=new_expires_at
        )
        logger.info(f"Successfully refreshed Microsoft Graph token for user_id={user_id}")
        return new_access_token
    else:
        logger.error(f"Failed to refresh token for user_id={user_id}: {result.get('error_description')}")
        return None


def fetch_user_profile(access_token: str) -> Optional[Dict[str, Any]]:
    """Calls Microsoft Graph /me to fetch user profile info."""
    url = f"{config.GRAPH_ENDPOINT}/me"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.error(f"Error fetching Microsoft profile: {e}")
    return None


def fetch_pending_assignments(user_id: int) -> Dict[str, Any]:
    """
    Fetches pending tasks/assignments from Microsoft Graph (To Do, Teams Education, and Outlook).
    Filters them into:
      - 'due_today'
      - 'due_tomorrow'
      - 'all_pending'
    """
    if config.ENABLE_MOCK_DATA or not config.AZURE_CLIENT_ID:
        return get_mock_assignments(user_id)

    access_token = refresh_access_token_if_needed(user_id)
    if not access_token:
        # Fallback to cached assignments if network/token fails
        cached = database.get_cached_assignments(user_id)
        if cached:
            return categorize_assignments(cached)
        return {"due_today": [], "due_tomorrow": [], "all_pending": []}

    headers = {"Authorization": f"Bearer {access_token}"}
    raw_tasks = []

    # 1. Fetch from Microsoft To-Do / Tasks API
    try:
        todo_lists_res = requests.get(f"{config.GRAPH_ENDPOINT}/me/todo/lists", headers=headers, timeout=10)
        if todo_lists_res.status_code == 200:
            lists = todo_lists_res.json().get("value", [])
            for t_list in lists:
                list_id = t_list["id"]
                list_name = t_list.get("displayName", "Tasks")
                tasks_res = requests.get(
                    f"{config.GRAPH_ENDPOINT}/me/todo/lists/{list_id}/tasks?$filter=status ne 'completed'",
                    headers=headers,
                    timeout=10
                )
                if tasks_res.status_code == 200:
                    for item in tasks_res.json().get("value", []):
                        due_info = item.get("dueDateTime", {})
                        due_str = due_info.get("dateTime", "") if due_info else ""
                        raw_tasks.append({
                            "id": item.get("id"),
                            "title": item.get("title", "Untitled Assignment"),
                            "subject": list_name,
                            "due_date": due_str,
                            "is_completed": False
                        })
    except Exception as e:
        logger.warning(f"Error querying To-Do API: {e}")

    # 2. Fetch from Education Assignments API (for Teams School/College accounts)
    try:
        edu_res = requests.get(f"{config.GRAPH_ENDPOINT}/education/me/assignments", headers=headers, timeout=10)
        if edu_res.status_code == 200:
            for item in edu_res.json().get("value", []):
                if item.get("status") != "completed":
                    raw_tasks.append({
                        "id": item.get("id"),
                        "title": item.get("displayName", "Teams Assignment"),
                        "subject": item.get("classId", "Microsoft Teams"),
                        "due_date": item.get("dueDateTime", ""),
                        "is_completed": False
                    })
    except Exception as e:
        logger.debug(f"Education Assignments API not accessible on this account type: {e}")

    # 3. Cache the fetched assignments in SQLite
    if raw_tasks:
        database.cache_user_assignments(user_id, raw_tasks)

    return categorize_assignments(raw_tasks)


def categorize_assignments(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Categorizes tasks based on deadline:
      - Due Today
      - Due Tomorrow
      - All Pending
    """
    now = datetime.datetime.now()
    today_date = now.date()
    tomorrow_date = today_date + datetime.timedelta(days=1)

    due_today = []
    due_tomorrow = []
    all_pending = []

    for task in tasks:
        due_str = task.get("due_date") or ""
        parsed_date = None

        if due_str:
            # Handle ISO formats: 2026-08-03T18:00:00Z or 2026-08-03
            try:
                clean_due = due_str.replace("Z", "+00:00")
                if "T" in clean_due:
                    dt = datetime.datetime.fromisoformat(clean_due)
                    parsed_date = dt.date()
                else:
                    parsed_date = datetime.date.fromisoformat(clean_due[:10])
            except Exception:
                parsed_date = None

        item_formatted = {
            "id": task.get("id", ""),
            "title": task.get("title", "Assignment"),
            "subject": task.get("subject", "Course"),
            "due_date": due_str,
            "due_date_formatted": parsed_date.strftime("%d %b, %Y") if parsed_date else "No due date"
        }

        all_pending.append(item_formatted)

        if parsed_date == today_date:
            due_today.append(item_formatted)
        elif parsed_date == tomorrow_date:
            due_tomorrow.append(item_formatted)

    return {
        "due_today": due_today,
        "due_tomorrow": due_tomorrow,
        "all_pending": all_pending
    }


def get_mock_assignments(user_id: int) -> Dict[str, Any]:
    """
    Returns realistic mock assignment data for development & testing
    when Microsoft Azure App is not yet configured or in offline demo mode.
    """
    today_iso = datetime.datetime.now().strftime("%Y-%m-%dT23:59:00Z")
    tomorrow_iso = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%dT23:59:00Z")
    next_week_iso = (datetime.datetime.now() + datetime.timedelta(days=5)).strftime("%Y-%m-%dT23:59:00Z")

    mock_tasks = [
        {
            "id": f"mock_1_{user_id}",
            "title": "Computer Networks Lab Assignment 3",
            "subject": "Computer Networks",
            "due_date": today_iso,
            "is_completed": False
        },
        {
            "id": f"mock_2_{user_id}",
            "title": "Database Management Mini Project Report",
            "subject": "DBMS",
            "due_date": today_iso,
            "is_completed": False
        },
        {
            "id": f"mock_3_{user_id}",
            "title": "Software Engineering Case Study Submission",
            "subject": "Software Engg",
            "due_date": tomorrow_iso,
            "is_completed": False
        },
        {
            "id": f"mock_4_{user_id}",
            "title": "Microprocessor & Interfacing Quiz",
            "subject": "Microprocessors",
            "due_date": next_week_iso,
            "is_completed": False
        }
    ]

    # Cache the mock data in SQLite so it shows up in dashboard
    database.cache_user_assignments(user_id, mock_tasks)
    return categorize_assignments(mock_tasks)
