#!/usr/bin/env python3
"""SAA-77: read-only AI CRM quota detector. Never mutates or kills a worker."""
import argparse
from collections import defaultdict
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

DEFAULT_DB = Path('/home/hermes/.hermes/kanban/boards/ai-crm/kanban.db')


def command(*args):
    done = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if done.returncode:
        raise RuntimeError(f'quota detector source failed: {args[0]}')
    return done.stdout


def load_snapshot(db_path):
    con = sqlite3.connect(f'file:{Path(db_path)}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        cards = [dict(row) for row in con.execute('SELECT id,status,assignee,provider_override FROM tasks')]
        runs = [dict(row) for row in con.execute('SELECT task_id,status,outcome,ended_at FROM task_runs')]
        return cards, runs
    finally:
        con.close()


def candidates(cards, runs, now, window_seconds=3600):
    grouped = defaultdict(list)
    active = {r['task_id'] for r in runs if r.get('status') == 'running' or
              (r.get('outcome') is None and r.get('ended_at') is None)}
    for run in runs:
        if run.get('status') != 'running' and run.get('ended_at') is not None and run.get('outcome'):
            grouped[run['task_id']].append(run)
    result = []
    for card in cards:
        if (card.get('id') in active or card.get('status') not in ('ready', 'review')
                or not card.get('assignee') or card.get('provider_override') != 'openai-codex'):
            continue
        last_two = sorted(grouped[card['id']], key=lambda r: r['ended_at'])[-2:]
        if len(last_two) == 2 and all(r['status'] == r['outcome'] == 'rate_limited'
                                      and 0 <= now - r['ended_at'] <= window_seconds for r in last_two):
            result.append(card['id'])
    return result


def pool_exhausted(auth_text):
    match = re.search(r'^openai-codex \(\d+ credentials?\):\n(.*?)(?=\n\n|\Z)', auth_text, re.M | re.S)
    if not match:
        return False
    credentials = [line.lower() for line in match.group(1).splitlines() if re.match(r'^\s*#\d+', line)]
    return bool(credentials) and all(re.search(r'\brate-limited\s+usage_limit_reached\b', line) for line in credentials)


def main(argv=None, now=None, runner=command):
    parser = argparse.ArgumentParser(description='Read-only AI CRM 429 detector')
    parser.add_argument('--db', type=Path, default=DEFAULT_DB)
    args = parser.parse_args(argv)
    cards, runs = load_snapshot(args.db)
    ids = candidates(cards, runs, time.time() if now is None else now)
    if ids and pool_exhausted(runner('hermes', 'auth', 'list')):
        print('ALERT ai-crm quota: ' + ','.join(ids[:3]) + (f' (+{len(ids)-3} more)' if len(ids)>3 else '')
              + '; two recent 429 runs, no active claim. Operator: verify exact card/provider, then park or re-pin manually.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
