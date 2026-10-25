#!/usr/bin/env python3
"""Dispatch at most one AI-CRM role-learning card per day, after Linear readback.

No product mutation. All role research is read-only; never publishes a skill or
changes ad spend, production, access, or main. Cron invokes --run; --dry-run is
safe for preflight. Only the existing ai-crm board is in scope.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

HOME = Path('/home/hermes/.hermes')
CATALOG = HOME / 'state/ai_crm_role_research_catalog.json'
STATE = HOME / 'state/ai_crm_role_learning_state.json'
LINEAR_SYNC = HOME / 'scripts/linear_board_sync.py'
VAULT = Path('/home/hermes/vault/20 Projekte/AI CRM Rollen')
PROJECT = 'Revenue OS / AI CRM'
BOARD = 'ai-crm'


def load_api():
    spec = importlib.util.spec_from_file_location('ai_crm_linear_sync', LINEAR_SYNC)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.LinearCLI(os.environ.get('HERMES_LINEAR_PYTHON', sys.executable))


def choose(cards, state, roles, today, operator_run=False):
    # A manual, explicit operator run may advance the queue after acceptance.
    # The unattended daily cron remains limited to one dispatch per day.
    if state.get('last_date') == today and not operator_run:
        return None, 'today_already_dispatched'
    # Never spawn a second side-lane while another Growth/role worker is open.
    for c in cards:
        if c['id'] == 't_b9bef074' and c['status'] in ('running', 'ready', 'review', 'blocked'):
            return None, 'growth_lane_not_finished'
        if c['title'].startswith('AI CRM Role Research: ') and c['status'] in ('running', 'ready', 'review', 'blocked', 'todo'):
            return None, 'previous_role_not_accepted'
    active = [c for c in cards if c['status'] in ('running', 'review')]
    if len(active) > 1:
        return None, 'other_work_is_active'
    index = state.get('next_index', 0) % len(roles)
    return (roles[index], state.get('round', 1) + state.get('next_index', 0) // len(roles)), 'ok'


def call(command, timeout=40):
    p = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'{command[1]} failed: {p.stderr[-300:]}')
    return p.stdout


def issue_for(api, role):
    title = f'AI CRM Agentenrolle: {role["title"]} – Research, Skill, Evals'
    existing = [x for x in api.list_issues(PROJECT) if x.get('title') == title]
    if len(existing) > 1:
        raise RuntimeError('ambiguous Linear role issue')
    if existing:
        issue = api.get_issue(existing[0]['id'])
    else:
        description = (f'Rolle {role["title"]} in AI CRM. Spezifische Forschungsfrage: {role["question"]}\n\n'
                       f'Skill-Kandidaten (vor Installation prüfen): {", ".join(role["skills"])}.\n'
                       f'Negativfähige Abnahme: {role["eval"]}\n\n'
                       'Ein Research-/Eval-Artefakt pro Karte; kein Profil- oder Zugangswechsel, keine Produktion, '
                       'keine externen Nachrichten, Posts oder Ads. Board ai-crm; genaue Karte folgt. '
                       'Done bedeutet recherchiertes Rollenpaket, nicht verkaufbares CRM.')
        saved = api.save_issue({'team': 'SAA', 'project': PROJECT, 'state': 'Todo',
                                'title': title, 'description': description, 'priority': 3})
        issue = api.get_issue(saved['id'])
    if issue.get('project') != PROJECT or issue.get('title') != title:
        raise RuntimeError('Linear readback mismatch')
    return issue


def previous_accepted(api, state):
    """Do not confuse an archived/triaged card with accepted research."""
    issue_id = state.get('last_issue')
    if not issue_id:
        return True
    issue = api.get_issue(issue_id)
    return (issue.get('id') == issue_id and issue.get('project') == PROJECT
            and issue.get('status') == 'Done')


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--operator-run', action='store_true',
                        help='Advance one accepted role today; never set on cron')
    args = parser.parse_args()
    if args.operator_run and not args.run:
        parser.error('--operator-run requires --run')
    roles = json.loads(CATALOG.read_text())['roles']
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    today = datetime.now(ZoneInfo('Europe/Berlin')).date().isoformat()
    cards = json.loads(call(['hermes', 'kanban', '--board', BOARD, 'list', '--json']))
    selected, reason = choose(cards, state, roles, today, operator_run=args.operator_run)
    if not selected:
        print(f'AI CRM Rollenlernen: heute kein neuer Worker ({reason}); bestehende Karte zuerst abschließen.')
        return
    role, round_no = selected
    if args.dry_run:
        print(f'DRY RUN: {role["slug"]}, Runde {round_no}; Linear vor Dispatch, max. ein leichter Worker. Vorherige SAA-Abnahme wird im echten Lauf geprüft.')
        return
    api = load_api()
    if not previous_accepted(api, state):
        print('AI CRM Rollenlernen: vorherige Rolle in Linear nicht abgenommen; kein neuer Worker.')
        return
    issue = issue_for(api, role)
    body = (f'Linear {issue["id"]} | AI CRM role-specific research round {round_no}. '
            f'Role: {role["title"]}. Research question: {role["question"]}. '
            f'Existing skill candidates to inspect with skill_view and, for external alternatives, '
            f'hermes skills search/inspect + security/license check: {", ".join(role["skills"])}. '
            f'Independent red-capable evaluation: {role["eval"]}. '
            f'First read /home/hermes/vault/AGENTS.md, /home/hermes/vault/20 Projekte/Revenue OS.md '
            f'and /home/hermes/vault/20 Projekte/AI CRM Agenten-Firma Recherche.md. '
            f'Produce dated evidence-backed role dossier at {VAULT / (role["slug"] + ".md")}: '
            'input/output contract, allowed tools/data, negative and positive evals, handoff, '
            'source comparison (official docs + practical Reddit/X/YouTube where relevant), '
            'one real safe dry-run/example and measured gap. If this is a later round, compare '
            'the previous dossier with fresh sources and real board failures; no evidence means '
            'no skill change. Write a proposed SKILL.md draft in the dossier, not an installed '
            'skill; independent reviewer and operator approve promotion. '
            'No real recipients, posts, campaign changes, purchases, secrets, prod/DB writes, '
            'main merge or build. Do not touch Pullwire development or SalesQueens live. '
            'Do not spawn subagents. Readback the written artifact and report source URLs and '
            'limitations. Request independent Kanban review; reviewer returns specific changes '
            'to this card. If headless Linear OAuth fails, comment exact evidence on the card '
            'for top-level operator to update and read back the issue; do not guess success. '
            'For the independent reviewer: examine evidence and negative evals. '
            'If headless Linear OAuth fails, post ONE exact verdict and evidence on this '
            'same card, then leave it in review or block ONCE for operator handoff; '
            'do not retry the same OAuth/block. The top-level operator writes and '
            'reads back Linear, then records a local-only acceptance bridge if the '
            'original review card is stuck in triage. A role dossier is not an '
            'installed or active role.')
    key = f'ai-crm-role-{role["slug"]}-round-{round_no}'
    result = json.loads(call(['hermes', 'kanban', '--board', BOARD, 'create',
                              f'AI CRM Role Research: {role["title"]} ({issue["id"]})',
                              '--body', body, '--assignee', 'default', '--workspace', 'scratch',
                              '--idempotency-key', key, '--max-runtime', '45m',
                              '--model', 'gpt-6-sol', '--provider', 'openai-codex', '--json']))
    card_id = result['id']
    shown = call(['hermes', 'kanban', '--board', BOARD, 'show', card_id])
    if issue['id'] not in shown or role['title'] not in shown:
        raise RuntimeError('Kanban readback mismatch')
    api.save_issue({'id': issue['id'], 'state': 'In Progress',
                    'patch': [{'op': 'append', 'text': f'\n\nRunde {round_no}, {today}: '
                               f'Kanban ai-crm:{card_id}, Rolle {role["title"]}. '
                               'Recherche/Skill-Draft, kein Live-Gate.'}]})
    exact = api.get_issue(issue['id'])
    if exact.get('status') != 'In Progress' or card_id not in (exact.get('description') or ''):
        raise RuntimeError('Linear status readback mismatch')
    next_index = state.get('next_index', 0) + 1
    new_state = {'next_index': next_index, 'round': state.get('round', 1),
                 'last_date': today, 'last_card': card_id, 'last_issue': issue['id']}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(new_state, sort_keys=True, indent=2))
    tmp.replace(STATE)
    print(f'AI CRM Rollenlernen: {role["title"]} → {issue["url"]}, Kanban {card_id}; '
          'Research/Review gestartet, kein Skill-Promotion oder Live-Gang.')


if __name__ == '__main__':
    main()
