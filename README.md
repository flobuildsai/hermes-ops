# hermes-ops
Ops workflows run from outside the Hermes server (e.g. Hetzner rescale).

## AI CRM worker preflight (SAA-77)

Create repo-bound Kanban cards **unassigned** with an exact `dir:` or worktree
workspace and an explicit model/provider pin. Before assigning a profile, run
`scripts/ai_crm_worker_preflight.py --card t_... --profile af-reviewer --repo
flobuildsai/hermes-ops --pr 3`. It verifies the card and workspace, GitHub
PR head, enabled profile skills, provider cooldown, available worker/build
slots and a bounded **real** model response. A fallback answer is a failure,
not a pass. A `PASS` is only permission to attempt assignment, never proof that
a Kanban worker ran, reviewed the right code, or shipped anything. Afterwards
read back the actual run/log, artifact and independent QA.

This script is read-only; it cannot override the gateway dispatcher, and it
must not be used to revive a product card owned by another Slack session.
One build-capable worker at a time; two lightweight lanes only when the total
active worker count stays within the host limit. The profile/repo/PR are all
explicit, so a default CWD cannot silently review the wrong repository.

Test: `python tests/test_ai_crm_worker_preflight.py -v`. No key, access,
production, external message, ad or main-branch changes occur.
