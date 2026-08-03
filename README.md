# 📞 GSM Assignment Alert System using Microsoft Graph API

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/framework-Flask-black.svg)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> An automated, multi-user assignment deadline notification system that runs 24/7 on a local Android phone via **Termux** (or PC). It monitors pending tasks from **Microsoft Teams** and **Outlook** via Microsoft Graph API and initiates direct **GSM cellular phone calls using a mobile SIM card** to speak deadlines aloud using Text-to-Speech (TTS).

---

## 👥 Project Team & Contributors
- **Sanskar Ghorpade** (`25108A0064`)
- **Aryan Chavan** (`25108A0066`)
- **Yash Mahto** (`25108A0067`)

---

## 🔐 Multi-User Authentication & Roles

The system features a **Unified Auth Landing Portal** (`/auth`) with 2 distinct user interfaces:

### 1. 👑 System Administrator Portal (`/admin`)
- **Pre-configured Admin Account:**
  - **Email:** `admin@sys.tem`
  - **Password:** `admin123`
  - **PIN:** `1234`
- **Admin Capabilities:**
  - View total registered students, active students, and pending task stats.
  - View all registered students directory with status toggles (`Active` / `Paused`).
  - Trigger individual test phone calls to any student.
  - **Trigger Batch Alert:** Immediately dials GSM calls sequentially to all active students with pending tasks.
  - View full system-wide call history, logs, and spoken voice transcripts.
  - Delete any student account & associated cached data.
  - Monitor host telephony status (Termux GSM vs PC Simulator, Local Network IP).

### 2. 🎓 Student Personal Portal (`/dashboard`)
- **Registration (`/auth` -> Sign Up Tab):**
  - Student Name
  - VIT Email Address (`@vitstudent.ac.in`)
  - Mobile Phone Number (SIM target for GSM calling)
  - Account Password & 4-Digit Security PIN (for quick PIN login)
  - Unique Student Identifier (`usr_xxxxxxxxxxxx`) generated automatically.
- **Student Dashboard Capabilities:**
  - View their personal upcoming deadlines (**🚨 Due Today**, **⚠️ Due Tomorrow**, **All Tasks**).
  - **Test Call My Phone:** Dials their registered phone immediately with their personal task alert.
  - **Pause / Resume Reminders:** Student can pause automated phone calls anytime.
  - View personal call history and spoken voice transcripts.
  - Link / Re-link Microsoft 365 student account.
  - **Delete My Account:** Wipe all personal data, phone number, and tokens.

---

## 🏗️ System Architecture

```
+-----------------------------------------------------------------------------------+
|                        Dedicated Host Android Phone                               |
|              (Running Termux + Python Flask Server + SIM Card)                    |
|                                                                                   |
|  [ Unified Auth Portal ] ---> Sign In (Pass/PIN) OR New Register (VIT Mail + PIN) |
|         |                                        |                                |
|         v (role: admin)                          v (role: student)                |
|  [ Admin Control Center ]                 [ Student Personal Portal ]             |
|  - All Students Directory                 - My Upcoming Tasks (Today/Tomorrow)    |
|  - Batch Alert Queue                      - "Call My Phone Now" Test Button       |
|  - System-wide Call Logs                  - Personal Call Transcripts             |
|  - Hardware & Host IP Diagnostics         - Pause / Resume / Delete Account       |
|         |                                        |                                |
|         +-------------------+--------------------+                                |
|                             |                                                     |
|                             v                                                     |
|                   [ SQLite Database ]                                             |
|        - Secure Password & PIN Hashes (Werkzeug)                                  |
|        - MS OAuth Refresh Tokens & Cached Tasks                                   |
|        - Call History Logs                                                        |
|                             |                                                     |
|                             v                                                     |
|  [ Scheduled Triggers ]     <--- Weekdays: 11:01 AM, 6:00 PM, 8:45 PM              |
|  (APScheduler in Python)    <--- Weekends: 10:00 AM, 6:00 PM, 8:45 PM              |
|                             |                                                     |
|                             v                                                     |
|  [ MS Graph API Worker ]    <--- Iterates through active users, refreshes tokens  |
|                                  fetches 'Due Today' & 'Due Tomorrow' tasks       |
|                             |                                                     |
|                             v                                                     |
|  [ GSM Batch Call Queue ]   <--- Dials Student 1 via SIM -> Speaks voice alert    |
|                                  waits -> Dials Student 2 -> Speaks alert...      |
+-----------------------------------------------------------------------------------+
```

---

## ⏰ Automated Alert Schedules
The system runs background cron tasks using `APScheduler`:
- **Weekdays (Mon–Fri)**: `11:01 AM`, `06:00 PM`, `08:45 PM`
- **Weekends (Sat–Sun)**: `10:00 AM`, `06:00 PM`, `08:45 PM`

### 🗣️ Voice Message Format:
> *"Alert for [Student Name]! Assignments due today: [Task 1, Task 2]. Assignments due tomorrow: [Task 3]. Please complete them on time."*

---

## 🚀 Quickstart Guide

### Option 1: Running on Android Phone (24/7 GSM Server via Termux)

1. Install **Termux** and **Termux:API** from [F-Droid](https://f-droid.org/).
2. Open Termux and clone this repository:
   ```bash
   pkg update -y && pkg install -y git python
   git clone https://github.com/mahtoyash/Assignment-Notes-Tracker.git
   cd Assignment-Notes-Tracker
   ```
3. Run the 1-click setup script:
   ```bash
   chmod +x termux_setup.sh
   ./termux_setup.sh
   ```
4. Open your phone's browser at `http://127.0.0.1:5000` (or `http://<phone-ip>:5000` from any device on the same WiFi network).

---

### Option 2: Running on Windows / PC (Development & Simulation Mode)

1. Clone the repository:
   ```bash
   git clone https://github.com/mahtoyash/Assignment-Notes-Tracker.git
   cd Assignment-Notes-Tracker
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` (runs in offline demo mode out of the box):
   ```bash
   cp .env.example .env
   ```
4. Start the server:
   ```bash
   python app.py
   ```
5. Open `http://127.0.0.1:5000` in your web browser:
   - **Admin Login:** `admin@sys.tem` / `admin123`
   - **Student Registration:** Click **"New Register"** tab.

---

## 🗂️ Project Structure

```
├── app.py                     # Main Flask web app, authentication & API endpoints
├── config.py                  # Environment config, schedules & platform detection
├── database.py                # Multi-user SQLite storage (users, tokens, logs, hashes)
├── ms_graph.py                # Microsoft Graph API & MSAL OAuth engine
├── scheduler.py               # APScheduler background cron daemon
├── telephony.py               # GSM dialing & TTS voice engine (Termux + PC simulator)
├── requirements.txt           # Python dependencies
├── termux_setup.sh            # 1-click Termux setup script with wake-lock
├── .env.example               # Configuration template
├── templates/                 # Jinja2 HTML templates
│   ├── base.html              # Dynamic navigation & role badges
│   ├── auth.html              # Unified Sign In / Register interface
│   ├── dashboard.html         # Student personal portal
│   ├── admin.html             # Admin control center
│   └── settings.html          # Azure & telephony configuration
└── static/                    # Frontend styling & JavaScript
    ├── css/
    │   └── style.css
    └── js/
        └── app.js
```

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).
