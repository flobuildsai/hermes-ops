# hermes-ops
Ops workflows run from outside the Hermes server (e.g. Hetzner rescale).

## AI CRM quota circuit (SAA-77)

`scripts/ai_crm_quota_circuit.py` reads **only** the `ai-crm` Kanban SQLite DB.
Default invocation is dry-run. A guarded `--run` may unassign at most one
ready/review card when its last two closed runs both ended `rate_limited`
within the hour, its pinned provider is `openai-codex`, the entire Codex
credential pool currently reports cooldown, and no run is active on the card.
It re-reads the exact card before changing anything, unassigns through Hermes'
CLI, checks the assignee is now empty and leaves an audit comment. It never
kills a live worker, changes provider/credential, touches product code or
unblocks downstream QA. A race from ready to running stops with an error for
the operator instead of claiming success. Cards already on Copilot, with a
successful intervening run or with one transient 429 are untouched.

Test: `PYTHONDONTWRITEBYTECODE=1 python tests/test_ai_crm_quota_circuit.py -v`.
Check `python scripts/ai_crm_quota_circuit.py` against the live board before
any no-agent schedule. A Cron wrapper must explicitly pass `--run`; do not
mistake the safe default dry-run for active recovery. Resume requires a
separate real provider preflight and exact Kanban/Linear readback.
