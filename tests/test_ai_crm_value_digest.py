import importlib.util
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[1] / 'scripts/ai_crm_value_digest.py'
spec = importlib.util.spec_from_file_location('digest', P)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ValueDigest(unittest.TestCase):
    def setUp(self):
        self.current = {'core_status': 'running', 'service_status': 'todo',
                        'qa_status': 'todo', 'sql_pass': 61, 'sql_total': 201,
                        'pr_head': 'abc123', 'pr_url': 'https://github.com/flobuildsai/ai-crm/pull/28'}

    def test_first_summary_is_short_and_names_customer_gate(self):
        text = m.render(self.current, None)
        self.assertIn('61/201', text)
        self.assertIn('Pilot', text)
        self.assertIn(self.current['pr_url'], text)
        self.assertLessEqual(len(text.splitlines()), 4)

    def test_head_only_change_does_not_spam(self):
        old = dict(self.current, pr_head='older')
        self.assertEqual(m.render(self.current, old), '[SILENT]')

    def test_sql_progress_triggers_one_result_not_ticket_log(self):
        old = dict(self.current, sql_pass=57, sql_total=198, pr_head='older')
        text = m.render(self.current, old)
        self.assertIn('61/201', text)
        self.assertNotIn('t_f2cdb3b2', text)
        self.assertLessEqual(len(text.splitlines()), 4)

    def test_service_gate_change_is_reported(self):
        old = dict(self.current, service_status='todo')
        self.assertNotEqual(m.render(dict(self.current, service_status='running'), old), '[SILENT]')

    def test_parse_last_sql_result_and_never_invent_on_missing_data(self):
        text = 'Latest summary:\nSQL-Pfad 61/201, 140 rot. Release STOP.\n\nComments (1):'
        self.assertEqual(m.parse_sql(text), (61, 201))
        self.assertEqual(m.parse_sql('Latest summary:\nkein Lauf\n\nComments:'), (None, None))

    def test_parser_prefers_full_suite_over_focused_case(self):
        text = ('Latest summary:\nSQL113 positiver Fall 0/1; '
                'volle SQL-Suite 61/201 (140 rot).\n\nComments (2):')
        self.assertEqual(m.parse_sql(text), (61, 201))
        text = ('Latest summary:\nSQL41 0/1; volle SQL-Suite unabhängig '
                '64/201 (137 rot).\n\nComments (3):')
        self.assertEqual(m.parse_sql(text), (64, 201))

    def test_missing_evidence_never_claims_green(self):
        text = m.render(dict(self.current, sql_pass=None, sql_total=None), None)
        self.assertNotIn('grün', text)
        self.assertIn('nicht belegt', text)

    def test_unchanged_tick_produces_empty_stdout(self):
        import io
        import json
        import sys
        import tempfile
        from contextlib import redirect_stdout
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / 'state.json'
            state.write_text(json.dumps(self.current))
            out = io.StringIO()
            with patch.object(m, 'snapshot', return_value=self.current), \
                 patch.object(sys, 'argv', ['digest', '--state-file', str(state)]), \
                 redirect_stdout(out):
                m.main()
            self.assertEqual(out.getvalue(), '')

if __name__ == '__main__':
    unittest.main()
