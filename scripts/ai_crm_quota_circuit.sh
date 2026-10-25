#!/usr/bin/env bash
# SAA-77: read-only no-agent Cron entrypoint, never changes Kanban.
set -euo pipefail
exec python3 /home/hermes/.hermes/scripts/ai_crm_quota_circuit.py
