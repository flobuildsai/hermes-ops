import importlib.util
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[1] / 'scripts/ai_crm_worker_preflight.py'
spec = importlib.util.spec_from_file_location('worker_preflight', P)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

CARD = {'id':'t_test', 'status':'ready', 'assignee':'af-reviewer',
        'workspace_kind':'dir', 'workspace_path':'/home/hermes/projects/hermes-ops-marketing',
        'skills':['ai-crm-agent-company'], 'provider_override':'copilot', 'model_override':'gpt-4.1'}

class Preflight(unittest.TestCase):
    def test_correct_repo_skill_provider_and_capacity_can_dispatch(self):
        failures = m.evaluate(CARD, repo='flobuildsai/hermes-ops', actual_remote='https://github.com/flobuildsai/hermes-ops.git',
                              head='abc123', expected_head='abc123', installed_skills={'ai-crm-agent-company'},
                              auth_status='copilot (1 credentials):\n #1 gh auth token api_key', real_probe_ok=True,
                              active_workers=1, heavy_workers=1, build_capable=False)
        self.assertEqual(failures, [])

    def test_unassigned_card_can_be_preflighted_before_assignment(self):
        card = dict(CARD, assignee=None)
        failures = m.evaluate(card, repo='flobuildsai/hermes-ops', actual_remote='https://github.com/flobuildsai/hermes-ops.git',
                              head='abc123', expected_head='abc123', installed_skills={'ai-crm-agent-company'},
                              auth_status='copilot (1 credentials):\n #1 gh auth token api_key', real_probe_ok=True,
                              active_workers=1, heavy_workers=1, build_capable=False, target_profile='af-reviewer')
        self.assertEqual(failures, [])

    def test_scratch_wrong_repo_or_head_rejected(self):
        for field, value in [('workspace_kind','scratch'), ('workspace_path',None)]:
            card=dict(CARD, **{field:value})
            self.assertTrue(m.evaluate(card, repo='flobuildsai/hermes-ops', actual_remote='https://github.com/flobuildsai/hermes-ops.git',
                              head='abc123', expected_head='abc123', installed_skills={'ai-crm-agent-company'},
                              auth_status='copilot (1 credentials):\n #1 gh auth token api_key', real_probe_ok=True,
                              active_workers=1, heavy_workers=1, build_capable=False))
        self.assertIn('wrong_repo_or_head', m.evaluate(CARD, repo='flobuildsai/hermes-ops', actual_remote='https://github.com/flobuildsai/ai-crm.git',
                              head='wrong', expected_head='abc123', installed_skills={'ai-crm-agent-company'},
                              auth_status='copilot (1 credentials):\n #1 gh auth token api_key', real_probe_ok=True,
                              active_workers=1, heavy_workers=1, build_capable=False))

    def test_rate_limited_auth_and_fallback_probe_never_count_as_ready(self):
        failures=m.evaluate(CARD, repo='flobuildsai/hermes-ops', actual_remote='https://github.com/flobuildsai/hermes-ops.git',
                              head='abc123', expected_head='abc123', installed_skills={'ai-crm-agent-company'},
                              auth_status='copilot (1 credentials):\n #1 rate-limited usage_limit_reached (429)', real_probe_ok=False,
                              active_workers=1, heavy_workers=1, build_capable=False)
        self.assertIn('provider_unavailable', failures)

    def test_missing_skill_and_full_capacity_stop_dispatch(self):
        failures=m.evaluate(CARD, repo='flobuildsai/hermes-ops', actual_remote='https://github.com/flobuildsai/hermes-ops.git',
                              head='abc123', expected_head='abc123', installed_skills=set(),
                              auth_status='copilot (1 credentials):\n #1 gh auth token api_key', real_probe_ok=True,
                              active_workers=3, heavy_workers=1, build_capable=True)
        self.assertIn('missing_skill', failures)
        self.assertIn('capacity_full', failures)
        self.assertIn('heavy_slot_busy', failures)

    def test_builder_profile_cannot_decline_heavy_classification(self):
        card=dict(CARD, assignee=None)
        failures=m.evaluate(card, repo='flobuildsai/hermes-ops', actual_remote='https://github.com/flobuildsai/hermes-ops.git',
                              head='abc123', expected_head='abc123', installed_skills={'ai-crm-agent-company'},
                              auth_status='copilot (1 credentials):\n #1 gh auth token api_key', real_probe_ok=True,
                              active_workers=1, heavy_workers=1, build_capable=False, target_profile='af-builder')
        self.assertIn('heavy_slot_busy',failures)

    def test_parse_provider_block_and_enabled_skills(self):
        auth=('anthropic (1 credentials):\n #1 oauth\n\n'
              'copilot (1 credentials):\n #1 token api_key\n\n'
              'openai-codex (1 credentials):\n #1 rate-limited usage_limit_reached (429)\n')
        self.assertIn('rate-limited', m.provider_block(auth, 'openai-codex'))
        self.assertNotIn('rate-limited', m.provider_block(auth, 'copilot'))
        table='┃ Name ┃ Status ┃\n│ sq-sales-os │ enabled │\n│ github │ enabled │\n'
        self.assertEqual(m.parse_skills(table), {'sq-sales-os','github'})

    def test_wrong_repo_stops_before_paid_model_probe(self):
        import json
        card=dict(CARD, assignee=None)
        seen=[]
        def fake_run(command):
            seen.append(command)
            if command[-2:] == ['list','--json']: return json.dumps([card])
            if command[:2] == ['git','-C'] and command[-2:] == ['get-url','origin']:
                return 'https://github.com/flobuildsai/ai-crm.git'
            if command[:2] == ['git','-C'] and command[-1] == 'HEAD': return 'abc123'
            if command[:2] == ['gh','pr']: return json.dumps({'headRefOid':'abc123'})
            if command[:2] == ['hermes','-p']: return '│ ai-crm-agent-company │ enabled │'
            if command[:3] == ['hermes','auth','list']: return 'copilot (1 credentials):\n #1 token api_key'
            raise AssertionError(command)
        failures=m.inspect('t_test',profile='af-reviewer',repo='flobuildsai/hermes-ops',pr=3,run=fake_run)
        self.assertIn('wrong_repo_or_head',failures)
        self.assertFalse(any('chat' in c for c in seen))

    def test_fallback_probe_is_not_a_pass(self):
        import json
        card=dict(CARD, assignee=None)
        def fake_run(command):
            if command[-2:] == ['list','--json']: return json.dumps([card])
            if command[:2] == ['git','-C'] and command[-2:] == ['get-url','origin']:
                return 'https://github.com/flobuildsai/hermes-ops.git'
            if command[:2] == ['git','-C'] and command[-1] == 'HEAD': return 'abc123'
            if command[:2] == ['gh','pr']: return json.dumps({'headRefOid':'abc123'})
            if command[:3] == ['hermes','auth','list']: return 'copilot (1 credentials):\n #1 token api_key'
            if 'skills' in command: return '│ ai-crm-agent-company │ enabled │'
            if 'chat' in command: return 'Primary auth failed — switching to fallback: OK'
            raise AssertionError(command)
        failures=m.inspect('t_test',profile='af-reviewer',repo='flobuildsai/hermes-ops',pr=3,run=fake_run)
        self.assertIn('provider_unavailable',failures)

    def test_probe_requires_standalone_ok_not_not_ok(self):
        import json
        card=dict(CARD, assignee=None)
        def fake_run(command):
            if command[-2:] == ['list','--json']: return json.dumps([card])
            if command[:2] == ['git','-C'] and command[-2:] == ['get-url','origin']:
                return 'https://github.com/flobuildsai/hermes-ops.git'
            if command[:2] == ['git','-C'] and command[-1] == 'HEAD': return 'abc123'
            if command[:2] == ['gh','pr']: return json.dumps({'headRefOid':'abc123'})
            if command[:3] == ['hermes','auth','list']: return 'copilot (1 credentials):\n #1 token api_key'
            if 'skills' in command: return '│ ai-crm-agent-company │ enabled │'
            if 'chat' in command: return 'Not OK'
            raise AssertionError(command)
        self.assertIn('provider_unavailable',m.inspect('t_test',profile='af-reviewer',repo='flobuildsai/hermes-ops',pr=3,run=fake_run))

    def test_probe_stderr_is_not_discarded(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        response=SimpleNamespace(returncode=0,stdout='OK\n',stderr='Primary auth failed — switching to fallback')
        with patch.object(m.subprocess,'run',return_value=response):
            captured=m.command_output(['hermes','-p','af-reviewer','--provider','copilot','chat','-q','OK'])
        self.assertIn('Primary auth failed',captured)

    def test_cli_requires_explicit_build_lane(self):
        import io
        from contextlib import redirect_stderr
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                m.main(['--card','t_test','--profile','af-reviewer','--repo','flobuildsai/hermes-ops','--pr','3'],
                       inspect_fn=lambda *a,**k:[])
        self.assertEqual(ctx.exception.code, 2)

    def test_cli_reports_stop_without_dispatch(self):
        import io
        from contextlib import redirect_stdout
        out=io.StringIO()
        with redirect_stdout(out):
            rc=m.main(['--card','t_test','--profile','af-reviewer','--repo','flobuildsai/hermes-ops','--pr','3','--light-only'],
                      inspect_fn=lambda *a,**k:['wrong_repo_or_head'])
        self.assertEqual(rc,2)
        self.assertIn('STOP wrong_repo_or_head',out.getvalue())

if __name__ == '__main__': unittest.main()
