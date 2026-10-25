# hermes-ops
Ops workflows run from outside the Hermes server (e.g. Hetzner rescale).

## AI CRM role-learning operator (SAA-71)

`scripts/ai_crm_role_learning.py` is deployed to the host's `~/.hermes/scripts/`
and the existing `ai-crm-role-learning` no-agent cron runs `--run` daily. It
creates one role-specific Linear issue (or reuses the exact title), reads it
back, then creates one Kanban research/review card and records the linkage.
The daily run never starts a second side-lane while a role card remains open.

When a role has been independently reviewed and its exact Linear issue is
`Done`, the operator may run `--operator-run --run` **once** to advance one
additional role on the same day. It still checks the prior issue's project and
status, existing active cards, and the SAA→Kanban readbacks. Do not put
`--operator-run` into the cron. A completed dossier is a researched role, not
an installed skill, enabled profile, deployed product, or permission to contact
anyone. If a headless reviewer cannot use Linear, it leaves its evidence on
the same card; the top-level operator performs the exact Linear write/readback
and a local-only acceptance bridge when needed. Do not repeatedly unblock the
same OAuth failure into a Kanban triage loop.

Run lightweight tests: `python -m unittest discover -s tests -v`.
No production data, Slack outreach, ad spend, main merge, or skill promotion is
authorized by this script.
