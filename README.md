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

## 💡 Problem Statement
Students frequently miss assignment deadlines on platforms like Microsoft Teams and Outlook because emails and app push notifications often get overlooked. Paid automated calling services (like Twilio) are expensive for student projects. 

This project provides a **free, self-hosted multi-user solution** running on a local Android device to check pending assignments and make direct phone calls via the phone's physical SIM card at scheduled reminder times.

---

## 🏗️ System Architecture

```
+-------------------------------------------------------------------------------+
|                       Dedicated Host Android Phone                            |
|             (Running Termux + Python Flask Server + SIM Card)                 |
|                                                                               |
|  [ Web Registration Portal ] <--- Students Register (Name, Phone, MS Login)  |
|            |                                                                  |
|            v                                                                  |
|  [ SQLite Database ]        <--- Stores User Profiles & Refresh Tokens        |
|            |                                                                  |
|            v                                                                  |
|  [ Scheduled Triggers ]     <--- Weekdays: 11:01 AM, 6:00 PM, 8:45 PM         |
|  (APScheduler in Python)    <--- Weekends: 10:00 AM, 6:00 PM, 8:45 PM         |
|            |                                                                  |
|            v                                                                  |
|  [ MS Graph API Worker ]    <--- Iterates through all users, refreshes token, |
|                                  fetches 'Due Today' & 'Due Tomorrow' tasks   |
|            |                                                                  |
|            v                                                                  |
|  [ GSM Batch Call Queue ]   <--- Dials Student 1 via SIM -> Speaks voice alert|
|                                  waits -> Dials Student 2 -> Speaks alert...  |
+-------------------------------------------------------------------------------+
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
4. Open your phone's browser and go to `http://127.0.0.1:5000` (or `http://<phone-ip>:5000` from any device on the same WiFi).

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
3. Copy `.env.example` to `.env` (optional, runs in offline/demo mode out of the box):
   ```bash
   cp .env.example .env
   ```
4. Start the server:
   ```bash
   python app.py
   ```
5. Open `http://127.0.0.1:5000` in your web browser. 
   *(In PC mode, calls are simulated in the console and spoken aloud using desktop TTS).*

---

## 🔐 Microsoft Azure App Registration (Free)

To connect live Microsoft Teams and Outlook accounts:
1. Go to [Azure Portal App Registrations](https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).
2. Click **New registration**:
   - Name: `GSM Assignment Alert System`
   - Supported Account Types: *Accounts in any organizational directory and personal Microsoft accounts*
   - Redirect URI: `Web` -> `http://localhost:5000/callback` (or your public IP / ngrok URL)
3. Copy your **Application (client) ID** and add it to your `.env` file:
   ```env
   AZURE_CLIENT_ID=your-client-id-here
   AZURE_TENANT_ID=common
   ```

---

## 🗂️ Project Structure

```
├── app.py                     # Main Flask web app & API endpoints
├── config.py                  # Environment config, schedules & platform detection
├── database.py                # Multi-user SQLite storage (users, tokens, logs)
├── ms_graph.py                # Microsoft Graph API & MSAL OAuth engine
├── scheduler.py               # APScheduler background cron daemon
├── telephony.py               # GSM dialing & TTS voice engine (Termux + PC simulator)
├── requirements.txt           # Python dependencies
├── termux_setup.sh            # 1-click Termux setup script
├── .env.example               # Configuration template
├── templates/                 # Jinja2 HTML templates (Dashboard, Settings, Layout)
│   ├── base.html
│   ├── index.html
│   └── settings.html
└── static/                    # Frontend styling & JavaScript
    ├── css/
    │   └── style.css
    └── js/
        └── app.js
```

---

## 📄 License
This project is open-source under the [MIT License](LICENSE).
