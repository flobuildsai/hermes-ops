#!/usr/bin/env python3
"""SAA-77: bounded AI CRM quota circuit; never kill a running worker."""
from collections import defaultdict
from pathlib import Path
import sqlite3
import argparse
import time
import subprocess
import sys
import re

DEFAULT_DB = Path('/home/hermes/.hermes/kanban/boards/ai-crm/kanban.db')


def command(*args):
    done = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if done.returncode:
        raise RuntimeError(f'quota circuit command failed: {args[0]}')
    return done.stdout


def load_snapshot(db_path):
    con = sqlite3.connect(f'file:{Path(db_path)}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        cards = [dict(row) for row in con.execute('SELECT id,status,assignee,provider_override FROM tasks')]
        runs = [dict(row) for row in con.execute('SELECT task_id,outcome,ended_at FROM task_runs')]
        return cards, runs
    finally:
        con.close()


def candidates(cards, runs, now, window_seconds=3600):
    grouped = defaultdict(list)
    active_ids = {r['task_id'] for r in runs if r.get('outcome') is None and r.get('ended_at') is None}
    for run in runs:
        if run.get('ended_at') is not None and run.get('outcome'):
            grouped[run['task_id']].append(run)
    targets=[]
    for card in cards:
        if (card.get('id') in active_ids or card.get('status') not in ('ready','review') or not card.get('assignee')
                or card.get('provider_override') != 'openai-codex'):
            continue
        recent=sorted(grouped[card['id']],key=lambda r:r['ended_at'])[-2:]
        if len(recent)==2 and all(r['outcome']=='rate_limited' and 0 <= now-r['ended_at'] <= window_seconds for r in recent):
            targets.append(card['id'])
    return targets


def park_once(read, assign, comment):
    before = read()
    if (before.get('active_run') or before.get('status') not in ('ready', 'review') or not before.get('assignee')
            or before.get('provider_override') != 'openai-codex'):
        return 'skip'
    assign()
    after = read()
    if after.get('assignee') is not None:
        raise RuntimeError('assignee readback mismatch')
    if after.get('status') == 'running':
        return 'race_running'
    comment()
    return 'parked'


def load_card(db_path, card_id):
    con = sqlite3.connect(f'file:{Path(db_path)}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute('SELECT id,status,assignee,provider_override, '
                          'EXISTS(SELECT 1 FROM task_runs WHERE task_id=tasks.id '
                          'AND outcome IS NULL AND ended_at IS NULL) AS active_run '
                          'FROM tasks WHERE id=?', (card_id,)).fetchone()
        return dict(row) if row else {}
    finally:
        con.close()


def pool_exhausted(auth_text):
    match = re.search(r'^openai-codex \(\d+ credentials?\):\n(.*?)(?=\n\n|\Z)', auth_text, re.M | re.S)
    if not match:
        return False
    creds = [line.lower() for line in match.group(1).splitlines() if re.match(r'^\s*#\d+', line)]
    return bool(creds) and all(('rate-limited' in line or 'usage_limit_reached' in line or '(429)' in line) for line in creds)


def main(argv=None, now=None, runner=command):
    parser=argparse.ArgumentParser(description='AI CRM quota circuit; dry-run by default')
    parser.add_argument('--db',type=Path,default=DEFAULT_DB)
    parser.add_argument('--run',action='store_true',help='Unassign at most one safe, repeatedly 429-limited card')
    args=parser.parse_args(argv)
    cards,runs=load_snapshot(args.db)
    targets=candidates(cards,runs,time.time() if now is None else now)
    if not args.run:
        print('DRY ' + (','.join(targets) if targets else 'none'))
        return 0
    if not targets:
        return 0
    if not pool_exhausted(runner('hermes','auth','list')):
        print('SKIP provider pool not exhausted')
        return 0
    target = targets[0]  # One card per tick; no bulk queue changes.
    reason = ('SAA-77 quota circuit: last two closed runs were 429/rate_limited '
              'within 1h and Codex pool is exhausted. Unassigned to stop retry churn; '
              'operator must preflight a real working provider before resume. No live claim killed.')
    outcome = park_once(lambda: load_card(args.db,target),
                        lambda: runner('hermes','kanban','--board','ai-crm','assign',target,'none'),
                        lambda: runner('hermes','kanban','--board','ai-crm','comment',target,reason))
    if outcome == 'race_running':
        raise RuntimeError('card became running during circuit; inspect exact run')
    if outcome == 'parked':
        print('parked '+target)
    return 0


if __name__ == '__main__':
    sys.exit(main())
