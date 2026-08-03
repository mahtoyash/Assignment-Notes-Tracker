#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# 24/7 Background Server Launcher for Android Phone
# Keeps the server running even when the phone screen is locked & laptop is off!
# ==============================================================================

echo "================================================================"
echo "🔋 Starting 24/7 Standalone Android Phone Server..."
echo "================================================================"

# 1. Acquire Termux Wake-Lock (Prevents phone CPU from sleeping)
echo "[1/3] Acquiring Android CPU wake-lock..."
termux-wake-lock

# 2. Kill any old existing instance of app.py
pkill -f "python app.py" 2>/dev/null

# 3. Start Python Flask server with nohup in background or foreground
echo "[2/3] Starting GSM Alert System Server..."
echo "----------------------------------------------------------------"
echo "✅ Laptop can now be SHUT DOWN completely!"
echo "✅ Your phone is now the 24/7 Server with SIM Calling Engine."
echo "----------------------------------------------------------------"

python app.py
