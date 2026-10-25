import importlib.util
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[1] / 'scripts/ai_crm_role_learning.py'
spec = importlib.util.spec_from_file_location('role_learning', P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ROLES = [{'slug': 'a', 'title': 'A', 'question': 'q', 'skills': ['x'], 'eval': 'e'},
         {'slug': 'b', 'title': 'B', 'question': 'q', 'skills': ['x'], 'eval': 'e'}]

class Selection(unittest.TestCase):
    def test_growth_in_flight_blocks(self):
        result, why = m.choose([{'id': 't_b9bef074', 'status': 'running', 'title': 'Growth'}], {}, ROLES, '2026-10-26')
        self.assertIsNone(result)
        self.assertEqual(why, 'growth_lane_not_finished')

    def test_p0_can_run_alongside_role(self):
        result, why = m.choose([{'id': 'p0', 'status': 'running', 'title': 'Tenant'}], {}, ROLES, '2026-10-26')
        self.assertEqual(result, (ROLES[0], 1))
        self.assertEqual(why, 'ok')

    def test_blocked_prior_role_stops_new_dispatch(self):
        result, why = m.choose([{'id': 'r1', 'status': 'blocked', 'title': 'AI CRM Role Research: A (SAA-99)'}],
                               {'next_index': 1}, ROLES, '2026-10-26')
        self.assertIsNone(result)
        self.assertEqual(why, 'previous_role_not_accepted')

    def test_once_per_day_and_next_cycle(self):
        self.assertEqual(m.choose([], {'last_date': '2026-10-26'}, ROLES, '2026-10-26')[1], 'today_already_dispatched')
        self.assertEqual(m.choose([], {'next_index': 2}, ROLES, '2026-10-27')[0], (ROLES[0], 2))
        self.assertEqual(m.choose([], {'last_date': '2026-10-26', 'next_index': 1}, ROLES,
                                  '2026-10-26', operator_run=True)[0], (ROLES[1], 1))

    def test_operator_run_still_rejects_active_role(self):
        cards = [{'id': 'r1', 'status': 'review', 'title': 'AI CRM Role Research: A'}]
        self.assertEqual(m.choose(cards, {'last_date': '2026-10-26', 'next_index': 1},
                                  ROLES, '2026-10-26', operator_run=True)[1],
                         'previous_role_not_accepted')

    def test_previous_issue_must_be_done_in_correct_project(self):
        class A:
            def __init__(self, status, project): self.status, self.project = status, project
            def get_issue(self, identifier):
                return {'id': identifier, 'status': self.status, 'project': self.project}
        state = {'last_issue': 'SAA-64'}
        self.assertFalse(m.previous_accepted(A('In Progress', m.PROJECT), state))
        self.assertFalse(m.previous_accepted(A('Done', 'Other project'), state))
        self.assertTrue(m.previous_accepted(A('Done', m.PROJECT), state))

    def test_other_two_active_prevent_third(self):
        cards = [{'id': 'a', 'status': 'running', 'title': 'Tenant'},
                 {'id': 'b', 'status': 'review', 'title': 'Website'}]
        self.assertEqual(m.choose(cards, {}, ROLES, '2026-10-26')[1], 'other_work_is_active')

class FakeAPI:
    def __init__(self): self.saved = []
    def list_issues(self, project): return []
    def save_issue(self, payload): self.saved.append(payload); return {'id': 'SAA-99'}
    def get_issue(self, identifier): return {'id': identifier,
        'project': m.PROJECT, 'title': 'AI CRM Agentenrolle: A – Research, Skill, Evals'}

class Linear(unittest.TestCase):
    def test_issue_before_card_and_exact_fields(self):
        api = FakeAPI()
        issue = m.issue_for(api, ROLES[0])
        self.assertEqual(issue['id'], 'SAA-99')
        self.assertEqual(api.saved[0]['team'], 'SAA')
        self.assertEqual(api.saved[0]['state'], 'Todo')
        self.assertEqual(api.saved[0]['project'], m.PROJECT)

class Integration(unittest.TestCase):
    def test_run_orders_linear_before_card_and_readback(self):
        import tempfile, json, sys
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            catalog = root / 'roles.json'
            catalog.write_text(json.dumps({'roles': ROLES}))
            state = root / 'state.json'
            events = []
            class API:
                description = ''
                status = 'Todo'
                def list_issues(self, project): return []
                def save_issue(self, payload):
                    events.append('linear-'+('update' if 'id' in payload else 'create'))
                    if 'id' in payload:
                        self.status = payload['state']
                        self.description += payload['patch'][0]['text']
                    return {'id':'SAA-99'}
                def get_issue(self, identifier):
                    return {'id':'SAA-99','project':m.PROJECT,
                            'title':'AI CRM Agentenrolle: A – Research, Skill, Evals',
                            'status':self.status,'description':self.description,
                            'url':'https://linear.app/saaslaabs/issue/SAA-99/test'}
            api = API()
            def fake_call(command, timeout=40):
                if command[4:6] == ['list','--json']: return '[]'
                if command[4] == 'create':
                    events.append('kanban-create')
                    return json.dumps({'id':'t_test001'})
                if command[4] == 'show': return 'SAA-99 A t_test001'
                raise AssertionError(command)
            with patch.object(m,'CATALOG',catalog), patch.object(m,'STATE',state), \
                 patch.object(m,'call',fake_call), patch.object(m,'load_api',lambda:api), \
                 patch.object(sys,'argv',['x','--run']):
                m.main()
            self.assertEqual(events,['linear-create','kanban-create','linear-update'])
            self.assertEqual(json.loads(state.read_text())['last_card'],'t_test001')

if __name__ == '__main__': unittest.main()
