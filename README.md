# hermes-ops
Ops workflows run from outside the Hermes server (e.g. Hetzner rescale).

## AI CRM quota detector (SAA-77)

`scripts/ai_crm_quota_circuit.py` reads the `ai-crm` Kanban SQLite database in
read-only mode and the existing Codex credential status. It reports a local
alert only if a ready/review card pinned to `openai-codex` has no active claim,
its two latest closed runs ended `rate_limited` within one hour, and every
Codex credential explicitly says `rate-limited usage_limit_reached`. It does
not unassign, kill, retry or modify any worker, product code or credential.

The original automatic-unassign design was rejected after an independent
review reproduced a Read→Assign race that could strip a *running* worker's
assignee. Hermes' `kanban assign` CLI has no atomic status/run condition, so
there is deliberately **no** `--run` mode. `scripts/ai_crm_quota_circuit.sh`
executes this read-only detector as a no-agent Cron; delivery remains local.
The operator reads the exact card, checks a real working provider and decides
whether to park/re-pin it manually. Never infer acceptance or release from an
alert or a healthy crash-rate metric.

Test: `PYTHONDONTWRITEBYTECODE=1 python tests/test_ai_crm_quota_circuit.py -v`.
Real read-only check: `python scripts/ai_crm_quota_circuit.py`.
