#!/usr/bin/env bash
# AI-Image Investigator — one-command setup
set -e

echo "== AI-Image Investigator setup =="

if ! command -v tesseract >/dev/null 2>&1; then
  echo "Installing Tesseract OCR + language packs (English, Hindi, Gujarati)..."
  sudo apt-get update -y
  sudo apt-get install -y tesseract-ocr tesseract-ocr-hin tesseract-ocr-guj
else
  echo "Tesseract already installed."
  # make sure Hindi/Gujarati packs are present too
  sudo apt-get install -y tesseract-ocr-hin tesseract-ocr-guj || true
fi

echo "Creating Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r backend/requirements.txt

echo ""
echo "Setup complete."
echo "Start the app with:  ./run.sh"
echo "Then open:           http://localhost:5000"
