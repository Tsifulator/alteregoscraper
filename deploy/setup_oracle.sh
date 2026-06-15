#!/usr/bin/env bash
# Set up the ALTER EGO lead scraper on a fresh Oracle Cloud "Always Free"
# Ubuntu ARM (VM.Standard.A1.Flex) instance: Ollama + model + Python venv +
# twice-daily cron. Safe to re-run. Assumes the project is already at
# ~/alteregoscraper (rsync it up first).
set -euo pipefail

PROJECT_DIR="$HOME/alteregoscraper"
MODEL="${OLLAMA_MODEL:-gemma3}"

echo "==> [1/6] Timezone -> Europe/Athens (cron follows DST automatically)"
sudo timedatectl set-timezone Europe/Athens

echo "==> [2/6] System packages"
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip curl

echo "==> [3/6] Ollama (installs + runs as a systemd service)"
command -v ollama >/dev/null 2>&1 || curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
# Wait for the local server to accept connections before pulling.
for _ in $(seq 1 30); do
  curl -sf http://localhost:11434/api/tags >/dev/null 2>&1 && break
  sleep 1
done

echo "==> [4/6] Pull model: $MODEL  (first pull downloads a few GB)"
ollama pull "$MODEL"

echo "==> [5/6] Python venv + dependencies"
mkdir -p "$PROJECT_DIR/logs"
cd "$PROJECT_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -r requirements.txt

echo "==> [6/6] Cron: 08:00 & 18:00 Athens, twice daily"
LINE="0 8,18 * * * cd $PROJECT_DIR && $PROJECT_DIR/.venv/bin/python main.py >> $PROJECT_DIR/logs/cron.log 2>&1 # alterego-scraper"
( crontab -l 2>/dev/null | grep -v 'alterego-scraper'; echo "$LINE" ) | crontab -

echo
echo "Done. Verify with a dry run (no email sent):"
echo "  cd $PROJECT_DIR && DRY_RUN=true .venv/bin/python main.py"
echo "Scheduled runs use .env (DRY_RUN=false) -> real digests at 08:00 & 18:00 Athens."
