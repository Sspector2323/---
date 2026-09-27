#!/usr/bin/env bash
# Установка J.A.R.V.I.S. на macOS / Linux
set -e
cd "$(dirname "$0")"

if [[ "$(uname)" == "Darwin" ]]; then
  command -v brew >/dev/null || { echo "Установите Homebrew: https://brew.sh"; exit 1; }
  brew install portaudio python@3.12
  PY=python3.12
else
  sudo apt-get update
  sudo apt-get install -y python3 python3-venv python3-dev python3-tk portaudio19-dev scrot xclip alsa-utils
  PY=python3
fi

$PY -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env

echo
echo "Готово! Откройте файл .env, вставьте ANTHROPIC_API_KEY и запустите:"
echo "  source .venv/bin/activate && python main.py"
