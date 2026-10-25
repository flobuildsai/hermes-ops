#!/usr/bin/env bash
# SAA-77: no-agent Cron entrypoint; Python itself defaults to safe dry-run.
set -euo pipefail
exec python3 /home/hermes/.hermes/scripts/ai_crm_quota_circuit.py --run
