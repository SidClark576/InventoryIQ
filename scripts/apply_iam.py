#!/usr/bin/env python3
"""Least-privilege IAM: one role per Lambda from scripts/iam/<Fn>.json. SAFE BY DEFAULT: a dry run prints the plan.

  --apply     (1) delete the event-source mappings fed by the leftover LambdaDLQ queue, (2) create/update role
              panindo-<Fn> + inline policy `least-privilege` (X-Ray added when tracing is Active), (3) check every
              (action, resource) with iam:SimulatePrincipalPolicy and abort before any Role switch on a deny,
              (4) switch each Lambda's Role, retrying while IAM propagates. Re-runs are idempotent.
  --rollback  switch every Lambda back to the shared InventoryIQ-LambdaExecutionRole (writes; no --apply needed).
              The deleted LambdaDLQ triggers are not recreated.
  --only Fn   limit any mode to one function.

  AWS_PROFILE=inventoryiq .venv/bin/python scripts/apply_iam.py                               # dry run
  ROLLOUT_LIVE=1 AWS_PROFILE=inventoryiq .venv/bin/python scripts/apply_iam.py --apply         # live
  ROLLOUT_LIVE=1 AWS_PROFILE=inventoryiq .venv/bin/python scripts/apply_iam.py --rollback      # undo

Live runs are the user's call. The old shared role is left untouched.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

IAM_DIR = Path(__file__).resolve().parent / 'iam'
OLD_ROLE = 'InventoryIQ-LambdaExecutionRole'
DLQ = 'LambdaDLQ'
POLICY = 'least-privilege'
TRUST = {'Version': '2012-10-17', 'Statement': [
    {'Effect': 'Allow', 'Principal': {'Service': 'lambda.amazonaws.com'}, 'Action': 'sts:AssumeRole'}]}
XRAY = {'Sid': 'XRay', 'Effect': 'Allow', 'Action': ['xray:PutTraceSegments', 'xray:PutTelemetryRecords'],
        'Resource': '*'}  # X-Ray has no resource ARNs
SWITCH_TRIES, SWITCH_PAUSE = 7, 5  # ~30 s for a new role to become assumable


def _as_list(v):
    return v if isinstance(v, list) else [v]


def functions(only=None):
    names = sorted(p.stem for p in IAM_DIR.glob('*.json'))
    if only and only not in names:
        raise SystemExit(f'no policy scripts/iam/{only}.json')
    return [only] if only else names


def policy_for(lam, name, region, account):
    text = (IAM_DIR / f'{name}.json').read_text().replace('${Region}', region).replace('${AccountId}', account)
    doc = json.loads(text)
    if (lam.get_function_configuration(FunctionName=name).get('TracingConfig') or {}).get('Mode') == 'Active':
        doc['Statement'].append(XRAY)
    return doc


def dlq_mappings(lam, names):
    pages = lam.get_paginator('list_event_source_mappings').paginate()
    return [m for p in pages for m in p['EventSourceMappings']
            if m['EventSourceArn'].endswith(f':{DLQ}') and m['FunctionArn'].split(':')[6] in names]


def ensure_role(iam, name, doc, apply):
    role = f'panindo-{name}'
    try:
        iam.get_role(RoleName=role)
        print(f'  update policy {role}')
    except iam.exceptions.NoSuchEntityException:
        print(f'  create role {role}')
        if apply:
            iam.create_role(RoleName=role, AssumeRolePolicyDocument=json.dumps(TRUST),
                            Description=f'Least-privilege execution role for Lambda {name}')
    if apply:
        iam.put_role_policy(RoleName=role, PolicyName=POLICY, PolicyDocument=json.dumps(doc))


def simulate(iam, role_arn, action, resource, context):
    """EvalDecision for one call: 'allowed', 'implicitDeny' or 'explicitDeny'."""
    res = iam.simulate_principal_policy(PolicySourceArn=role_arn, ActionNames=[action], ResourceArns=[resource],
                                        ContextEntries=context)
    return res['EvaluationResults'][0]['EvalDecision']


def _context(stmt):
    return [{'ContextKeyName': k, 'ContextKeyValues': [v], 'ContextKeyType': 'string'}
            for k, v in (stmt.get('Condition') or {}).get('StringEquals', {}).items()]


def denied(iam, role_arn, doc):
    """(action, resource, decision) for every grant in doc the simulator does not allow."""
    checks = [(a, r, _context(s)) for s in doc['Statement'] for a in _as_list(s['Action']) for r in _as_list(s['Resource'])]
    return [(a, r, d) for a, r, ctx in checks if (d := simulate(iam, role_arn, a, r, ctx)) != 'allowed']


def switch_role(lam, name, role_arn, apply):
    if lam.get_function_configuration(FunctionName=name)['Role'] == role_arn:
        print(f'  keep {name} (already on {role_arn.rsplit("/", 1)[-1]})')
        return
    print(f'  switch {name} -> {role_arn.rsplit("/", 1)[-1]}')
    if not apply:
        return
    for attempt in range(SWITCH_TRIES):
        try:
            lam.update_function_configuration(FunctionName=name, Role=role_arn)
            break
        except lam.exceptions.InvalidParameterValueException:  # new role not assumable yet
            if attempt == SWITCH_TRIES - 1:
                raise
            time.sleep(SWITCH_PAUSE)
    lam.get_waiter('function_updated').wait(FunctionName=name)


def rollout(clients, names, apply):
    iam, lam = clients['iam'], clients['lambda']
    region, account = lam.meta.region_name, clients['sts'].get_caller_identity()['Account']
    for m in dlq_mappings(lam, names):
        print(f"  delete trigger {DLQ} -> {m['FunctionArn'].split(':')[6]} ({m['UUID']})")
        if apply:
            lam.delete_event_source_mapping(UUID=m['UUID'])
    docs = {n: policy_for(lam, n, region, account) for n in names}
    for n in names:
        ensure_role(iam, n, docs[n], apply)
    arns = {n: f'arn:aws:iam::{account}:role/panindo-{n}' for n in names}
    if apply:
        bad = {n: d for n in names if (d := denied(iam, arns[n], docs[n]))}
        for n, rows in bad.items():
            print(f'  DENY {n}: ' + '; '.join(f'{a} on {r} ({d})' for a, r, d in rows))
        if bad:
            raise SystemExit(f'simulate denied grants for {", ".join(bad)}; no Role switched')
    else:
        print(f'  simulate every grant of {len(names)} role(s) before switching')
    for n in names:
        switch_role(lam, n, arns[n], apply)


def rollback(clients, names, apply=True):
    old = clients['iam'].get_role(RoleName=OLD_ROLE)['Role']['Arn']
    for n in names:
        switch_role(clients['lambda'], n, old, apply)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='perform writes (default: dry run)')
    mode.add_argument('--rollback', action='store_true', help=f'switch every Lambda back to {OLD_ROLE}')
    ap.add_argument('--only', metavar='FN', help='one function only')
    args = ap.parse_args(argv)
    if (args.apply or args.rollback) and os.environ.get('ROLLOUT_LIVE') != '1':
        print('Refusing live IAM writes: set ROLLOUT_LIVE=1 for the real rollout.', file=sys.stderr)
        return 2
    os.environ['AWS_PAGER'] = ''
    import boto3
    clients = {'iam': boto3.client('iam'), 'lambda': boto3.client('lambda'), 'sts': boto3.client('sts')}
    names = functions(args.only)
    label = 'ROLLBACK' if args.rollback else 'APPLY' if args.apply else 'DRY RUN'
    print(f'{label} least-privilege IAM for {len(names)} function(s)', flush=True)
    (rollback if args.rollback else rollout)(clients, names, args.rollback or args.apply)
    return 0


if __name__ == '__main__':
    sys.exit(main())
