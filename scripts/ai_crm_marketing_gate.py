#!/usr/bin/env python3
"""SAA-75: hard-format gate for locally generated AI CRM marketing advice."""
import re
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta

MAX_CHARS = 550


def eligible_response(text):
    if not text or '[SILENT]' in text or '[CRON_FAILURE]' in text:
        return None
    clean = text.strip()
    lines = clean.splitlines()
    if len(clean) > MAX_CHARS or len(lines) != 3:
        return None
    if not lines[0].startswith('Move: ') or not lines[1].startswith('Beleg: '):
        return None
    if not lines[2].startswith('Nächster Schritt/Gate: '):
        return None
    if not re.search(r'https://[^\s)]+', lines[1]):
        return None
    if not re.search(r'\b(?:Ja|Freigabe)\b', lines[2], re.I):
        return None
    return clean


def latest_eligible(paths, now):
    paths = sorted(paths)
    if not paths:
        return None
    text = paths[-1].read_text()
    run = re.search(r'^\*\*Run Time:\*\* (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)', text, re.M)
    if not run or '\n## Response\n' not in text:
        return None
    when = datetime.strptime(run.group(1), '%Y-%m-%d %H:%M:%S')
    if when.date() != now.date() or not timedelta(0) <= now - when <= timedelta(hours=6):
        return None
    return eligible_response(text.rsplit('\n## Response\n', 1)[-1])


def fingerprint(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def is_new(text, previous_hash):
    return bool(text and fingerprint(text) != previous_hash)


def run(paths, state_path, now):
    text = latest_eligible(paths, now)
    if not text:
        return None
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    if not is_new(text, previous.get('last_hash')):
        return None
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'last_hash': fingerprint(text)}, sort_keys=True) + '\n')
    tmp.replace(state_path)
    return text


OUTPUT_DIR = Path('/home/hermes/.hermes/cron/output/27d05535b671')
STATE = Path('/home/hermes/.hermes/state/ai_crm_marketing_gate.json')


def main(source_dir=OUTPUT_DIR, state_path=STATE, now=None):
    current_time = now or datetime.now()
    text = run(source_dir.glob('*.md'), state_path, current_time)
    if text:
        print(text)


if __name__ == '__main__':
    main()
