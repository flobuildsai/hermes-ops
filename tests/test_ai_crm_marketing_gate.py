import importlib.util
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[1] / 'scripts/ai_crm_marketing_gate.py'
spec = importlib.util.spec_from_file_location('marketing_gate', P)
assert spec is not None and spec.loader is not None
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

GOOD = ('Move: Ein enger Audit der ungeklärten Refund-Zuordnung als Discovery-Hypothese.\n'
        'Beleg: https://example.org/buyer-post vom 25.10.2026, Ersthandbericht; Nachfrage unbewiesen.\n'
        'Nächster Schritt/Gate: Frage als Entwurf an Flo; Kontakt nur nach seinem Ja.')

class MarketingGate(unittest.TestCase):
    def test_valid_short_sourced_draft_passes(self):
        self.assertEqual(m.eligible_response(GOOD), GOOD)

    def test_silent_and_failure_never_leave_local(self):
        for text in ('[SILENT]', '[CRON_FAILURE]\nFehler', ''):
            self.assertIsNone(m.eligible_response(text))

    def test_rejects_long_or_four_line_message(self):
        self.assertIsNone(m.eligible_response(GOOD + '\nVierte Zeile'))
        self.assertIsNone(m.eligible_response(GOOD + 'x' * 550))

    def test_requires_source_and_flo_gate(self):
        self.assertIsNone(m.eligible_response(GOOD.replace('https://example.org/buyer-post', 'nicht belegt')))
        self.assertIsNone(m.eligible_response(GOOD.replace('Kontakt nur nach seinem Ja', 'Kontakt sofort')))

    def test_latest_real_run_today_only(self):
        from datetime import datetime
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d:
            file = Path(d) / '2026-10-25_13-01-00.md'
            file.write_text('# Cron Job\n**Run Time:** 2026-10-25 13:01:00\n## Prompt\n...\n## Response\n' + GOOD)
            self.assertEqual(m.latest_eligible([file], datetime(2026, 10, 25, 13, 20)), GOOD)
            self.assertIsNone(m.latest_eligible([file], datetime(2026, 10, 26, 13, 20)))
            self.assertIsNone(m.latest_eligible([file], datetime(2026, 10, 25, 20, 0)))

    def test_newest_silent_run_blocks_old_good_draft(self):
        from datetime import datetime
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d:
            old = Path(d) / '2026-10-25_13-01-00.md'
            new = Path(d) / '2026-10-25_13-15-00.md'
            old.write_text('**Run Time:** 2026-10-25 13:01:00\n## Response\n' + GOOD)
            new.write_text('**Run Time:** 2026-10-25 13:15:00\n## Response\n[SILENT]')
            self.assertIsNone(m.latest_eligible([old, new], datetime(2026, 10, 25, 13, 20)))

    def test_identical_message_is_never_delivered_twice(self):
        key = m.fingerprint(GOOD)
        self.assertTrue(m.is_new(GOOD, None))
        self.assertFalse(m.is_new(GOOD, key))

    def test_real_gate_writes_state_only_for_accepted_message(self):
        from datetime import datetime
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as d:
            root = Path(d)
            output = root / '2026-10-25_13-01-00.md'
            state = root / 'state.json'
            output.write_text('**Run Time:** 2026-10-25 13:01:00\n## Response\n' + GOOD)
            self.assertEqual(m.run([output], state, datetime(2026, 10, 25, 13, 20)), GOOD)
            self.assertIsNone(m.run([output], state, datetime(2026, 10, 25, 13, 21)))
            output.write_text('**Run Time:** 2026-10-25 13:01:00\n## Response\n[SILENT]')
            self.assertIsNone(m.run([output], state, datetime(2026, 10, 25, 13, 22)))

    def test_cli_only_prints_accepted_content(self):
        import io
        from datetime import datetime
        from tempfile import TemporaryDirectory
        from contextlib import redirect_stdout
        with TemporaryDirectory() as d:
            root = Path(d)
            out = root / '2026-10-25_13-01-00.md'
            state = root / 'state.json'
            out.write_text('**Run Time:** 2026-10-25 13:01:00\n## Response\n' + GOOD)
            captured = io.StringIO()
            with redirect_stdout(captured):
                m.main(root, state, datetime(2026, 10, 25, 13, 20))
            self.assertEqual(captured.getvalue().strip(), GOOD)
            captured = io.StringIO()
            with redirect_stdout(captured):
                m.main(root, state, datetime(2026, 10, 25, 13, 21))
            self.assertEqual(captured.getvalue(), '')

if __name__ == '__main__': unittest.main()
