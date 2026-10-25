# hermes-ops
Ops workflows run from outside the Hermes server (e.g. Hetzner rescale).

## AI CRM marketing output gate (SAA-75)

The LLM marketing advisor stores its daily result **locally**. The separate
no-agent `scripts/ai_crm_marketing_gate.py` reads only today's newest completed
local output, never a prior good draft when the latest says `[SILENT]`.
It delivers nothing unless that text has exactly three lines, at most 550
characters, a source URL, and an explicit human approval gate. Identical text
is suppressed by a durable local fingerprint. This is a mechanical format and
noise gate, **not** a fact-check or permission to contact leads, spend money,
merge main or release the app. Failures/too-long messages stay local; a
failed Slack delivery may require operator reconciliation because the hash is
recorded before Hermes attempts delivery (at-most-once bias to avoid spam).

The advisor runs first; schedule this no-agent gate later in the day and only
to Flo's designated AI-CRM thread. Run `python -m unittest discover -s tests -v`
and `python scripts/ai_crm_marketing_gate.py` against the actual local outputs
before enabling delivery.
