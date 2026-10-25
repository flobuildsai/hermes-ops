import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

P = Path(__file__).resolve().parents[1] / 'scripts/ai_crm_quota_circuit.py'
spec = importlib.util.spec_from_file_location('quota_circuit', P)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
NOW = 2000000

class Circuit(unittest.TestCase):
    def setUp(self):
        self.card={'id':'t_core','status':'ready','assignee':'af-reviewer',
                   'provider_override':'openai-codex'}
        self.runs=[{'task_id':'t_core','status':'rate_limited','outcome':'rate_limited','ended_at':NOW-300},
                   {'task_id':'t_core','status':'rate_limited','outcome':'rate_limited','ended_at':NOW-100}]

    def test_two_recent_closed_quota_failures_alert(self):
        self.assertEqual(m.candidates([self.card],self.runs,NOW),['t_core'])

    def test_not_ready_or_already_unassigned_does_not_alert(self):
        for status,assignee in [('running','af-reviewer'),('ready',None),('done','af-reviewer')]:
            self.assertEqual(m.candidates([dict(self.card,status=status,assignee=assignee)],self.runs,NOW),[])

    def test_active_claim_or_running_run_status_suppresses_alert(self):
        live=self.runs+[{'task_id':'t_core','status':'running','outcome':None,'ended_at':None}]
        self.assertEqual(m.candidates([self.card],live,NOW),[])
        weird=self.runs+[{'task_id':'t_core','status':'running','outcome':'rate_limited','ended_at':NOW-10}]
        self.assertEqual(m.candidates([self.card],weird,NOW),[])

    def test_copilot_switch_or_success_breaks_sequence(self):
        self.assertEqual(m.candidates([dict(self.card,provider_override='copilot')],self.runs,NOW),[])
        success=self.runs+[{'task_id':'t_core','status':'done','outcome':'completed','ended_at':NOW-10}]
        self.assertEqual(m.candidates([self.card],success,NOW),[])

    def test_one_or_old_failure_insufficient(self):
        self.assertEqual(m.candidates([self.card],self.runs[:1],NOW),[])
        old=[dict(self.runs[0],ended_at=NOW-4000),self.runs[1]]
        self.assertEqual(m.candidates([self.card],old,NOW),[])

    def test_credential_parser_rejects_historical_429_text(self):
        self.assertTrue(m.pool_exhausted('openai-codex (1 credentials):\n #1 oauth rate-limited usage_limit_reached (429)'))
        self.assertFalse(m.pool_exhausted('openai-codex (2 credentials):\n #1 healthy (previous rate-limited request)\n #2 oauth rate-limited usage_limit_reached (429)'))
        self.assertFalse(m.pool_exhausted('copilot (1 credentials):\n #1 healthy'))

    def _db(self, root):
        db=root/'kanban.db'
        con=sqlite3.connect(db)
        con.executescript('CREATE TABLE tasks(id TEXT,status TEXT,assignee TEXT,provider_override TEXT);'
                          'CREATE TABLE task_runs(task_id TEXT,status TEXT,outcome TEXT,ended_at INTEGER);')
        con.execute('INSERT INTO tasks VALUES (?,?,?,?)',('t_core','ready','af-reviewer','openai-codex'))
        con.executemany('INSERT INTO task_runs VALUES (?,?,?,?)',
                        [('t_core','rate_limited','rate_limited',NOW-300),('t_core','rate_limited','rate_limited',NOW-100)])
        con.commit();con.close()
        return db

    def test_read_only_snapshot_uses_board_database(self):
        with TemporaryDirectory() as d:
            db=self._db(Path(d)); cards,runs=m.load_snapshot(db)
            self.assertEqual(m.candidates(cards,runs,NOW),['t_core'])
            self.assertEqual(cards[0]['assignee'],'af-reviewer')

    def test_main_alert_is_read_only_and_no_assign_command(self):
        with TemporaryDirectory() as d:
            db=self._db(Path(d)); seen=[]
            def fake(*cmd):
                seen.append(cmd)
                if cmd==('hermes','auth','list'):
                    return 'openai-codex (1 credentials):\n #1 oauth rate-limited usage_limit_reached (429)'
                raise AssertionError('board write attempted')
            out=io.StringIO()
            with redirect_stdout(out): rc=m.main(['--db',str(db)],now=NOW,runner=fake)
            self.assertEqual(rc,0)
            self.assertEqual(seen,[('hermes','auth','list')])
            self.assertIn('ALERT',out.getvalue())
            self.assertIn('t_core',out.getvalue())
            self.assertEqual(m.load_snapshot(db)[0][0]['assignee'],'af-reviewer')

    def test_main_silent_if_pool_has_healthy_credential(self):
        with TemporaryDirectory() as d:
            db=self._db(Path(d)); out=io.StringIO()
            with redirect_stdout(out):
                rc=m.main(['--db',str(db)],now=NOW,runner=lambda *a:'openai-codex (1 credentials):\n #1 healthy (previous rate-limited request)')
            self.assertEqual(rc,0)
            self.assertEqual(out.getvalue(),'')

if __name__ == '__main__': unittest.main()
