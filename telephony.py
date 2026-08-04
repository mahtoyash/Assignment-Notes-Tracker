"""
Telephony & Voice TTS Alert Module for GSM Assignment Alert System
Handles GSM phone dialing and Text-to-Speech playback via Termux API on Android,
with an automatic desktop simulator (pyttsx3) for development & testing on PC.
"""

import time
import subprocess
import logging
from typing import Dict, Any, List, Optional

import config
import database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_voice_message(user_name: str, due_today: List[Dict[str, Any]], due_tomorrow: List[Dict[str, Any]]) -> str:
    """
    Constructs the exact voice message according to the project specification.
    Format:
      "Alert for [Student Name]! Assignments due today: [Task 1, Task 2].
       Assignments due tomorrow: [Task 3]. Please complete them on time."
    """
    if not due_today and not due_tomorrow:
        return f"Hello {user_name}! This is a notification from your GSM Assignment Alert System. You have no pending assignments due today or tomorrow. Keep up the great work!"

    parts = [f"Alert for {user_name}!"]

    if due_today:
        today_titles = [f"{t.get('title')} in {t.get('subject')}" if t.get('subject') and t.get('subject') != 'General' else t.get('title') for t in due_today]
        parts.append(f"Assignments due today: {', '.join(today_titles)}.")

    if due_tomorrow:
        tomorrow_titles = [f"{t.get('title')} in {t.get('subject')}" if t.get('subject') and t.get('subject') != 'General' else t.get('title') for t in due_tomorrow]
        parts.append(f"Assignments due tomorrow: {', '.join(tomorrow_titles)}.")

    parts.append("Please complete them on time.")
    return " ".join(parts)


def speak_desktop_tts(message: str):
    """Fallback TTS engine for PC / Windows development testing using pyttsx3."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 160)  # Moderate speaking speed
        engine.say(message)
        engine.runAndWait()
    except Exception as e:
        logger.warning(f"Desktop TTS playback error (non-critical): {e}")


def dial_and_speak(
    phone_number: str,
    message: str,
    user_name: str = "Student",
    user_id: Optional[int] = None,
    trigger_type: str = "manual_test",
    tasks_due_today: int = 0,
    tasks_due_tomorrow: int = 0
) -> Dict[str, Any]:
    """
    Executes a GSM telephone call and reads out the voice alert message.
    - If Twilio credentials exist: Uses Twilio Cloud Voice API (0 popups, auto-hangup).
    - On Android / Termux: Uses `termux-telephony-call` and `termux-tts-speak`.
    - On PC / Windows: Simulates the call in console and uses desktop TTS.
    """
    logger.info(f"Initiating alert call to {user_name} ({phone_number}) | Trigger: {trigger_type}")
    
    use_twilio = config.is_twilio_enabled() or config.TELEPHONY_PROVIDER == "twilio"
    is_termux = config.is_termux_environment()

    if use_twilio:
        try:
            from twilio.rest import Client
            from twilio.twiml.voice_response import VoiceResponse

            logger.info(f"Executing Twilio Voice Call to {phone_number} from {config.TWILIO_PHONE_NUMBER}")
            client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
            
            # Construct TwiML: Speaks message and immediately hangs up when done
            response = VoiceResponse()
            response.say(message, voice='Polly.Aditi', language='en-IN')
            response.hangup()

            call = client.calls.create(
                twiml=str(response),
                to=phone_number,
                from_=config.TWILIO_PHONE_NUMBER
            )
            logger.info(f"Twilio Call successfully dispatched. Call SID: {call.sid}")
            status = f"TWILIO_SUCCESS ({call.sid[:12]})"
        except Exception as e:
            logger.error(f"Twilio Telephony execution error: {e}")
            status = f"TWILIO_FAILED: {str(e)[:50]}"

    elif is_termux:
        try:
            # 1. Dial phone number via Termux Telephony API
            logger.info(f"Executing Termux GSM call: termux-telephony-call {phone_number}")
            subprocess.run(["termux-telephony-call", phone_number], check=True, timeout=10)

            # Wait 7 seconds for the phone to establish connection / user to answer
            time.sleep(7)

            # 2. Speak message via Termux Text-to-Speech API
            logger.info(f"Speaking TTS alert via Termux: '{message}'")
            subprocess.run(["termux-tts-speak", "-r", "0.9", message], check=True, timeout=30)

            # Wait additional time for speech to finish before returning
            speech_duration = max(len(message.split()) * 0.45, 4.0)
            time.sleep(speech_duration)

            status = "SUCCESS"
        except Exception as e:
            logger.error(f"Termux telephony execution error: {e}")
            status = f"FAILED: {str(e)[:50]}"
    else:
        # PC Development / Simulator Mode
        print("\n" + "=" * 60)
        print(f"[GSM CALL SIMULATOR] Dialing SIM -> {phone_number} ({user_name})")
        print(f"[VOICE ALERT TTS] \"{message}\"")
        print("=" * 60 + "\n")

        # Play audio locally so the developer can hear the exact alert
        speak_desktop_tts(message)
        status = "SIMULATED"


    # Record log in SQLite database
    log_id = database.log_call(
        user_id=user_id,
        user_name=user_name,
        phone_number=phone_number,
        trigger_type=trigger_type,
        tasks_due_today=tasks_due_today,
        tasks_due_tomorrow=tasks_due_tomorrow,
        message_spoken=message,
        status=status
    )

    return {
        "log_id": log_id,
        "status": status,
        "phone_number": phone_number,
        "message": message,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }


def process_batch_alert_queue(trigger_type: str = "scheduled", specific_user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Iterates through registered students, checks their deadlines from Microsoft Graph,
    and makes sequential calls for each user with pending deadlines.
    """
    import ms_graph  # Lazy import to avoid circular dependencies

    results = []

    if specific_user_id:
        user = database.get_user_by_id(specific_user_id)
        users = [user] if user else []
    else:
        # All active users
        users = database.get_all_users()
        users = [u for u in users if u.get("is_active")]

    logger.info(f"Processing alert queue for {len(users)} active user(s)...")

    for index, user in enumerate(users):
        user_id = user["id"]
        user_name = user["name"]
        phone_number = user["phone_number"]

        try:
            # 1. Fetch pending assignments for this specific user
            data = ms_graph.fetch_pending_assignments(user_id)
            due_today = data.get("due_today", [])
            due_tomorrow = data.get("due_tomorrow", [])

            # For scheduled runs, only call if there is at least 1 task due today or tomorrow
            # For manual test calls, call regardless to confirm setup
            if not due_today and not due_tomorrow and trigger_type == "scheduled":
                logger.info(f"Skipping call for {user_name}: No assignments due today or tomorrow.")
                continue

            # 2. Build voice script
            message = build_voice_message(user_name, due_today, due_tomorrow)

            # 3. Dial and speak
            call_res = dial_and_speak(
                phone_number=phone_number,
                message=message,
                user_name=user_name,
                user_id=user_id,
                trigger_type=trigger_type,
                tasks_due_today=len(due_today),
                tasks_due_tomorrow=len(due_tomorrow)
            )
            results.append(call_res)

            # 4. Sequential delay between calls if more than 1 user is in queue
            if index < len(users) - 1:
                logger.info("Waiting 5 seconds before dialing next student in queue...")
                time.sleep(5)

        except Exception as e:
            logger.error(f"Error processing alert for user_id={user_id}: {e}")
            results.append({
                "status": f"ERROR: {str(e)}",
                "phone_number": phone_number,
                "user_name": user_name
            })

    return results
