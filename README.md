# hermes-ops
Ops workflows run from outside the Hermes server (e.g. Hetzner rescale).

## AI CRM value digest (SAA-74)

`scripts/ai_crm_value_digest.py` reads the exact Tenant-Core card, its Service
and Release-QA successors, and AI-CRM PR #28. It sends at most three short
lines at a scheduled tick **only when the verified SQL suite or a gate state
changed**. A mere new commit or a ticket comment returns `[SILENT]`. It never
interprets a green subset as a release, never lists customer records, and
stops if a source is missing. The host cron should use no-agent mode and
address only Flo's chosen AI-CRM thread; do not attach per-card Kanban wake
subscriptions. The board and Linear retain technical evidence.

Run `python -m unittest discover -s tests -v` and
`python scripts/ai_crm_value_digest.py --dry-run` before scheduling. The dry
run prints a candidate but does not advance deduplication state.
