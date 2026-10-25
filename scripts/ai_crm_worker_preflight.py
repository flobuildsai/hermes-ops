#!/usr/bin/env python3
"""SAA-77: fail-closed preflight before assigning a repo-bound Kanban worker.

Read-only. A PASS does not claim a worker is running or its work is correct.
"""
import re
import json
import os
import subprocess
import argparse
import sys


def command_output(command):
    env = dict(os.environ, GH_CONFIG_DIR='/home/hermes/.config/gh')
    done = subprocess.run(command, capture_output=True, text=True, timeout=120, env=env)
    if done.returncode:
        raise RuntimeError(f'preflight command failed: {command[0]}')
    return done.stdout.strip()


def provider_block(output, provider):
    match = re.search(rf'^{re.escape(provider)} \(\d+ credentials?\):\n(.*?)(?=\n\n|\Z)', output, re.M | re.S)
    return match.group(1) if match else 'no credentials'


def parse_skills(output):
    found = set()
    for line in output.splitlines():
        if not line.startswith('│') or 'enabled' not in line:
            continue
        name = line.split('│')[1].strip()
        if name:
            found.add(name)
    return found


def evaluate(card, *, repo, actual_remote, head, expected_head, installed_skills,
             auth_status, real_probe_ok, active_workers, heavy_workers, build_capable,
             target_profile=None):
    failures = []
    profile = target_profile or card.get('assignee')
    if card.get('status') not in ('ready', 'todo') or not profile or (card.get('assignee') and card['assignee'] != profile):
        failures.append('card_not_assignable')
    if card.get('workspace_kind') not in ('dir', 'worktree') or not card.get('workspace_path'):
        failures.append('workspace_unbound')
    acceptable = (f'https://github.com/{repo}.git', f'https://github.com/{repo}',
                  f'git@github.com:{repo}.git')
    if actual_remote not in acceptable or head != expected_head:
        failures.append('wrong_repo_or_head')
    if not set(card.get('skills') or []).issubset(installed_skills):
        failures.append('missing_skill')
    auth = auth_status.lower()
    if not real_probe_ok or any(x in auth for x in ('rate-limited', 'usage_limit_reached', '(429)', 'no credentials')):
        failures.append('provider_unavailable')
    if active_workers >= 3:
        failures.append('capacity_full')
    if build_capable and heavy_workers >= 1:
        failures.append('heavy_slot_busy')
    return failures


def inspect(card_id, *, profile, repo, pr, build_capable=False, run=command_output):
    cards = json.loads(run(['hermes', 'kanban', '--board', 'ai-crm', 'list', '--json']))
    card = next((item for item in cards if item['id'] == card_id), None)
    if card is None:
        return ['card_missing']
    path = card.get('workspace_path')
    actual_remote = run(['git', '-C', path, 'remote', 'get-url', 'origin']) if path else ''
    head = run(['git', '-C', path, 'rev-parse', 'HEAD']) if path else ''
    expected = json.loads(run(['gh', 'pr', 'view', str(pr), '-R', repo, '--json', 'headRefOid']))['headRefOid']
    skills = parse_skills(run(['hermes', '-p', profile, 'skills', 'list', '--enabled-only']))
    provider = card.get('provider_override') or ''
    model = card.get('model_override') or ''
    auth = provider_block(run(['hermes', 'auth', 'list']), provider)
    active = [item for item in cards if item['status'] == 'running' and item['id'] != card_id]
    heavy = sum(item.get('assignee') == 'af-builder' for item in active)
    failures = evaluate(card, repo=repo, actual_remote=actual_remote, head=head,
                        expected_head=expected, installed_skills=skills,
                        auth_status=auth, real_probe_ok=True, active_workers=len(active),
                        heavy_workers=heavy, build_capable=build_capable,
                        target_profile=profile)
    if not provider or not model:
        failures.append('model_unpinned')
    if failures:
        return failures
    output = run(['hermes', '-p', profile, '-m', model, '--provider', provider,
                  'chat', '-q', 'Antworte nur mit OK.'])
    valid = ('Primary auth failed' not in output and 'fallback' not in output.lower()
             and bool(re.search(r'(?m)^\s*OK\s*$', output)))
    return evaluate(card, repo=repo, actual_remote=actual_remote, head=head,
                    expected_head=expected, installed_skills=skills,
                    auth_status=auth, real_probe_ok=valid, active_workers=len(active),
                    heavy_workers=heavy, build_capable=build_capable,
                    target_profile=profile)


def main(argv=None, inspect_fn=inspect):
    parser = argparse.ArgumentParser(description='Fail-closed repo-bound agent preflight; does not dispatch')
    parser.add_argument('--card', required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--repo', required=True)
    parser.add_argument('--pr', type=int, required=True)
    parser.add_argument('--build-capable', action='store_true')
    args = parser.parse_args(argv)
    try:
        failures = inspect_fn(args.card, profile=args.profile, repo=args.repo,
                              pr=args.pr, build_capable=args.build_capable)
    except (RuntimeError, subprocess.SubprocessError, OSError, ValueError, KeyError) as exc:
        failures = [f'source_error:{type(exc).__name__}']
    if failures:
        print('STOP ' + ','.join(failures))
        return 2
    print('PASS preflight only; assign and read back actual running/artifact separately')
    return 0


if __name__ == '__main__':
    sys.exit(main())
