#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# GSM Assignment Alert System - Android Termux 1-Click Setup Script
# ==============================================================================

echo "================================================================"
echo "🚀 Setting up GSM Assignment Alert System on Android Termux"
echo "================================================================"

# 1. Update Termux Package Repositories
echo "[1/5] Updating packages..."
pkg update -y && pkg upgrade -y

# 2. Install Python, Termux API & Git
echo "[2/5] Installing Python, Git, and Termux API..."
pkg install -y python git termux-api

# 3. Request Wake-Lock to keep server running 24/7 in background
echo "[3/5] Acquiring Termux wake-lock (prevents CPU sleep)..."
termux-wake-lock

# 4. Install Python Dependencies
echo "[4/5] Installing Python requirements..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Check SIM card & Termux telephony permission
echo "[5/5] Checking Termux telephony & TTS tools..."
if command -v termux-telephony-call &> /dev/null; then
    echo "✅ termux-telephony-call is ready."
else
    echo "⚠️  termux-telephony-call not found. Ensure 'Termux:API' app is installed from F-Droid."
fi

if command -v termux-tts-speak &> /dev/null; then
    echo "✅ termux-tts-speak is ready."
else
    echo "⚠️  termux-tts-speak not found. Ensure 'Termux:API' app is installed from F-Droid."
fi

echo ""
echo "================================================================"
echo "🎉 Setup Complete! Starting GSM Assignment Alert Server..."
echo "================================================================"
echo "Open your mobile browser at: http://127.0.0.1:5000"
echo "================================================================"

python app.py
