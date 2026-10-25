import importlib.util
from pathlib import Path
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
        self.runs=[{'task_id':'t_core','outcome':'rate_limited','ended_at':NOW-300},
                   {'task_id':'t_core','outcome':'rate_limited','ended_at':NOW-100}]

    def test_two_recent_quota_failures_park_ready_card(self):
        self.assertEqual(m.candidates([self.card],self.runs,NOW),['t_core'])

    def test_never_reclaim_live_or_already_unassigned_card(self):
        for status,assignee in [('running','af-reviewer'),('ready',None),('done','af-reviewer')]:
            self.assertEqual(m.candidates([dict(self.card,status=status,assignee=assignee)],self.runs,NOW),[])

    def test_active_claim_blocks_parking_even_if_card_looks_ready(self):
        live=self.runs+[{'task_id':'t_core','outcome':None,'ended_at':None}]
        self.assertEqual(m.candidates([self.card],live,NOW),[])
        self.assertEqual(m.park_once(lambda:dict(self.card,active_run=True),lambda:None,lambda:None),'skip')

    def test_copilot_switch_or_success_breaks_quota_sequence(self):
        self.assertEqual(m.candidates([dict(self.card,provider_override='copilot')],self.runs,NOW),[])
        success=self.runs+[{'task_id':'t_core','outcome':'completed','ended_at':NOW-10}]
        self.assertEqual(m.candidates([self.card],success,NOW),[])

    def test_one_failure_or_old_failure_is_not_enough(self):
        self.assertEqual(m.candidates([self.card],self.runs[:1],NOW),[])
        old=[dict(self.runs[0],ended_at=NOW-4000),self.runs[1]]
        self.assertEqual(m.candidates([self.card],old,NOW),[])

    def test_read_only_snapshot_uses_exact_board_database(self):
        import sqlite3
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d:
            db=Path(d)/'kanban.db'
            con=sqlite3.connect(db)
            con.executescript('CREATE TABLE tasks(id TEXT,status TEXT,assignee TEXT,provider_override TEXT);'
                              'CREATE TABLE task_runs(task_id TEXT,outcome TEXT,ended_at INTEGER);')
            con.execute('INSERT INTO tasks VALUES (?,?,?,?)',('t_core','ready','af-reviewer','openai-codex'))
            con.executemany('INSERT INTO task_runs VALUES (?,?,?)', [('t_core','rate_limited',NOW-300),('t_core','rate_limited',NOW-100)])
            con.commit(); con.close()
            cards,runs=m.load_snapshot(db)
            self.assertEqual(m.candidates(cards,runs,NOW),['t_core'])

    def test_park_rechecks_target_and_reads_assignment_back(self):
        current: dict[str, str | None] = dict(self.card)
        actions=[]
        def read(): return dict(current)
        def assign(): actions.append('assign'); current['assignee']=None
        def comment(): actions.append('comment')
        self.assertEqual(m.park_once(read,assign,comment),'parked')
        self.assertEqual(actions,['assign','comment'])
        self.assertIsNone(current['assignee'])

    def test_park_skips_card_claimed_between_snapshot_and_action(self):
        current=dict(self.card,status='running')
        actions=[]
        self.assertEqual(m.park_once(lambda:current,lambda:actions.append('assign'),lambda:actions.append('comment')),'skip')
        self.assertEqual(actions,[])

    def test_main_dry_run_never_assigns(self):
        import io,sqlite3
        from contextlib import redirect_stdout
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d:
            db=Path(d)/'kanban.db'
            con=sqlite3.connect(db)
            con.executescript('CREATE TABLE tasks(id TEXT,status TEXT,assignee TEXT,provider_override TEXT);'
                              'CREATE TABLE task_runs(task_id TEXT,outcome TEXT,ended_at INTEGER);')
            con.execute('INSERT INTO tasks VALUES (?,?,?,?)',('t_core','ready','af-reviewer','openai-codex'))
            con.executemany('INSERT INTO task_runs VALUES (?,?,?)',[('t_core','rate_limited',NOW-300),('t_core','rate_limited',NOW-100)])
            con.commit();con.close()
            out=io.StringIO()
            with redirect_stdout(out):
                rc=m.main(['--db',str(db)],now=NOW,runner=lambda *a: (_ for _ in ()).throw(AssertionError('no command in dry run')))
            self.assertEqual(rc,0)
            self.assertIn('t_core',out.getvalue())
            self.assertEqual(m.load_snapshot(db)[0][0]['assignee'],'af-reviewer')

    def test_main_run_parks_only_after_credential_and_readback(self):
        import io,sqlite3
        from contextlib import redirect_stdout
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d:
            db=Path(d)/'kanban.db'
            con=sqlite3.connect(db)
            con.executescript('CREATE TABLE tasks(id TEXT,status TEXT,assignee TEXT,provider_override TEXT);'
                              'CREATE TABLE task_runs(task_id TEXT,outcome TEXT,ended_at INTEGER);')
            con.execute('INSERT INTO tasks VALUES (?,?,?,?)',('t_core','ready','af-reviewer','openai-codex'))
            con.executemany('INSERT INTO task_runs VALUES (?,?,?)',[('t_core','rate_limited',NOW-300),('t_core','rate_limited',NOW-100)])
            con.commit();con.close()
            actions=[]
            def fake(*cmd):
                if cmd[:3]==('hermes','auth','list'): return 'openai-codex (1 credentials):\n #1 rate-limited usage_limit_reached (429)\n'
                if 'assign' in cmd:
                    with sqlite3.connect(db) as c: c.execute('UPDATE tasks SET assignee=NULL WHERE id=?',('t_core',))
                    actions.append('assign'); return 'Assigned'
                if 'comment' in cmd: actions.append('comment'); return 'Commented'
                raise AssertionError(cmd)
            out=io.StringIO()
            with redirect_stdout(out):
                rc=m.main(['--db',str(db),'--run'],now=NOW,runner=fake)
            self.assertEqual(rc,0)
            self.assertEqual(actions,['assign','comment'])
            self.assertIsNone(m.load_snapshot(db)[0][0]['assignee'])
            self.assertIn('parked',out.getvalue())

if __name__ == '__main__': unittest.main()
