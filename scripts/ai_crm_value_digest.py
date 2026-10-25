#!/usr/bin/env python3
"""SAA-74: concise, deduplicated AI CRM value digest; no LLM or product writes."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

BOARD = 'ai-crm'
CORE = 't_f2cdb3b2'
SERVICE = 't_d0fbd7a5'
QA = 't_8cd8482e'
PR = 28
REPO = 'flobuildsai/ai-crm'
STATE = Path('/home/hermes/.hermes/state/ai_crm_value_digest.json')


def parse_sql(board_text):
    match = re.search(r'Latest summary:\s*(.*?)(?:\n\s*Comments\s*\(|\n\s*Events\s*\(|\Z)',
                      board_text, re.S)
    if not match:
        return None, None
    summary = match.group(1)
    counts = re.search(r'\b(?:volle|vollständige)\s+(?:lokale\s+)?SQL[- ](?:Gesamt)?suite(?:\s+\w+){0,2}\s+(\d{1,4})\s*/\s*(\d{1,4})\b', summary, re.I)
    if not counts:
        counts = re.search(r'\bSQL[- ](?:Pfad|Gesamtsuite)\s+(\d{1,4})\s*/\s*(\d{1,4})\b', summary, re.I)
    if not counts:
        return None, None
    passed, total = map(int, counts.groups())
    return (passed, total) if 0 <= passed <= total else (None, None)


def render(current, previous):
    keys = ('core_status', 'service_status', 'qa_status', 'sql_pass', 'sql_total')
    if previous and all(previous.get(key) == current.get(key) for key in keys):
        return '[SILENT]'
    passed, total = current.get('sql_pass'), current.get('sql_total')
    if passed is None or total is None:
        progress = 'Tenant-Suite nicht belegt'
    else:
        progress = f'Tenant-Core {passed}/{total} SQL grün ({total-passed} rot)'
    service, qa = current['service_status'], current['qa_status']
    if current['core_status'] == service == qa == 'done':
        value = 'Interne Gates erledigt; ein Produktiv-Release ist dadurch nicht belegt.'
        next_step = 'Nächster Hebel: PR-/CI-/Provider-Readback und Flo-Live-Gate.'
    else:
        value = 'Designpartner-Pilot mit Echtdaten weiter gesperrt; Website/Docs sind kein CRM-Release.'
        next_step = f'Nächster Hebel: Tenant-Core → Twilio-Services ({service}) → unabhängige QA ({qa}).'
    return '\n'.join((f'AI CRM: {progress}.', f'Nutzen/Gate: {value}',
                      f'{next_step} {current["pr_url"]}'))


def snapshot():
    base = ['hermes', 'kanban', '--board', BOARD]
    cards = json.loads(subprocess.check_output(base + ['list', '--json'], text=True, timeout=30))
    indexed = {card['id']: card for card in cards}
    for ident in (CORE, SERVICE, QA):
        if ident not in indexed:
            raise RuntimeError(f'missing required card {ident}')
    shown = subprocess.check_output(base + ['show', CORE], text=True, timeout=30)
    env = dict(os.environ, GH_CONFIG_DIR='/home/hermes/.config/gh')
    pr = json.loads(subprocess.check_output(['gh', 'pr', 'view', str(PR), '-R', REPO,
                                            '--json', 'url,state,headRefOid'],
                                           text=True, timeout=30, env=env))
    passed, total = parse_sql(shown)
    return {'core_status': indexed[CORE]['status'],
            'service_status': indexed[SERVICE]['status'],
            'qa_status': indexed[QA]['status'],
            'sql_pass': passed, 'sql_total': total,
            'pr_head': pr['headRefOid'], 'pr_url': pr['url'], 'pr_state': pr['state']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Do not update dedupe state')
    parser.add_argument('--state-file', type=Path, default=STATE)
    args = parser.parse_args()
    try:
        current = snapshot()
    except (subprocess.SubprocessError, json.JSONDecodeError, RuntimeError, KeyError) as exc:
        raise SystemExit(f'AI CRM digest source failed; no claim delivered: {type(exc).__name__}') from exc
    old = json.loads(args.state_file.read_text()) if args.state_file.exists() else None
    text = render(current, old)
    if text != '[SILENT]' and not args.dry_run:
        args.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.state_file.with_suffix('.tmp')
        tmp.write_text(json.dumps(current, sort_keys=True) + '\n')
        tmp.replace(args.state_file)
    print(text)


if __name__ == '__main__':
    main()
