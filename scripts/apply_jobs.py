#!/usr/bin/env python3
"""Scheduled-job hardening rollout (job 020's live half). SAFE BY DEFAULT: a dry run prints the plan.

Steps, in order (--only <step> runs one):
  dlq         SQS queue panindo-jobs-dlq, 14-day retention
  gsi         InventoryTransactions GSI orgID-createdAt-index (does not wait for ACTIVE)
  stream      CascadeDeleteUser Users-stream mapping: 3 retries, bisect on error, on-failure -> DLQ
  retries     DailyAlert, PurgeDeletedItems, LowItemInsight async invoke: 2 retries, on-failure -> DLQ
  dailyalert  DailyAlert 512 MB / 30 s
  schedules   InventoryIQ-DailyAlert + Daily_Purge_Schedule: Asia/Manila (cron kept), 2 retries, DLQ;
              inline policy panindo-jobs-dlq (sqs:SendMessage on the DLQ only) on the schedule role
  ttl         OrgInvites TTL on `ttl`; backfill ttl = expiresAt where missing

  AWS_PROFILE=inventoryiq .venv/bin/python scripts/apply_jobs.py                           # dry run
  ROLLOUT_LIVE=1 AWS_PROFILE=inventoryiq .venv/bin/python scripts/apply_jobs.py --apply     # live

Live runs are the user's call. Re-runs are idempotent.
"""
import argparse
import json
import os
import sys

QUEUE, RETENTION = 'panindo-jobs-dlq', '1209600'  # 14 days, the SQS maximum
TX, GSI = 'InventoryTransactions', 'orgID-createdAt-index'
JOBS = ('DailyAlert', 'PurgeDeletedItems', 'LowItemInsight')
SCHEDULES, GROUP = ('InventoryIQ-DailyAlert', 'Daily_Purge_Schedule'), 'default'
READ_ONLY = ('Arn', 'CreationDate', 'LastModificationDate', 'ResponseMetadata')
INVITES = 'OrgInvites'


def _on_failure(cfg):
    return ((cfg.get('DestinationConfig') or {}).get('OnFailure') or {}).get('Destination')


def dlq(c, arn, apply):
    try:
        c['sqs'].get_queue_url(QueueName=QUEUE)
        print(f'  keep queue {QUEUE}')
    except c['sqs'].exceptions.QueueDoesNotExist:
        print(f'  create queue {QUEUE} (retention {RETENTION} s)')
        if apply:
            c['sqs'].create_queue(QueueName=QUEUE, Attributes={'MessageRetentionPeriod': RETENTION})


def gsi(c, arn, apply):
    table = c['dynamodb'].describe_table(TableName=TX)['Table']
    if any(g['IndexName'] == GSI for g in table.get('GlobalSecondaryIndexes', [])):
        print(f'  keep index {TX}/{GSI}')
        return
    print(f'  create index {TX}/{GSI}')
    if apply:
        c['dynamodb'].update_table(
            TableName=TX,
            AttributeDefinitions=[{'AttributeName': 'orgID', 'AttributeType': 'S'},
                                  {'AttributeName': 'createdAt', 'AttributeType': 'S'}],
            GlobalSecondaryIndexUpdates=[{'Create': {
                'IndexName': GSI, 'Projection': {'ProjectionType': 'ALL'},
                'KeySchema': [{'AttributeName': 'orgID', 'KeyType': 'HASH'},
                              {'AttributeName': 'createdAt', 'KeyType': 'RANGE'}]}}])


def stream(c, arn, apply):
    lam = c['lambda']
    pages = lam.get_paginator('list_event_source_mappings').paginate(FunctionName='CascadeDeleteUser')
    found = [m for p in pages for m in p['EventSourceMappings'] if ':table/Users/stream/' in m['EventSourceArn']]
    if not found:
        raise SystemExit('stream: no Users stream mapping for CascadeDeleteUser; step aborted')
    for m in found:
        if (m.get('MaximumRetryAttempts'), m.get('BisectBatchOnFunctionError'), _on_failure(m)) == (3, True, arn):
            print(f"  keep mapping CascadeDeleteUser {m['UUID']}")
            continue
        print(f"  update mapping CascadeDeleteUser {m['UUID']}: 3 retries, bisect, on-failure -> {QUEUE}")
        if apply:
            lam.update_event_source_mapping(UUID=m['UUID'], MaximumRetryAttempts=3, BisectBatchOnFunctionError=True,
                                            DestinationConfig={'OnFailure': {'Destination': arn}})


def retries(c, arn, apply):
    lam = c['lambda']
    for fn in JOBS:
        try:
            cur = lam.get_function_event_invoke_config(FunctionName=fn)
        except lam.exceptions.ResourceNotFoundException:
            cur = {}
        if (cur.get('MaximumRetryAttempts'), _on_failure(cur)) == (2, arn):
            print(f'  keep invoke-config {fn}')
            continue
        print(f'  update invoke-config {fn}: 2 retries, on-failure -> {QUEUE}')
        if apply:
            lam.put_function_event_invoke_config(FunctionName=fn, MaximumRetryAttempts=2,
                                                 DestinationConfig={'OnFailure': {'Destination': arn}})


def dailyalert(c, arn, apply):
    lam = c['lambda']
    cfg = lam.get_function_configuration(FunctionName='DailyAlert')
    if (cfg['MemorySize'], cfg['Timeout']) == (512, 30):
        print('  keep function DailyAlert 512 MB / 30 s')
        return
    print(f"  update function DailyAlert {cfg['MemorySize']} MB / {cfg['Timeout']} s -> 512 MB / 30 s")
    if apply:
        lam.update_function_configuration(FunctionName='DailyAlert', MemorySize=512, Timeout=30)
        lam.get_waiter('function_updated').wait(FunctionName='DailyAlert')


def _role_policy(iam, role, arn, apply):
    doc = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Action': 'sqs:SendMessage', 'Resource': arn}]}
    try:
        if iam.get_role_policy(RoleName=role, PolicyName=QUEUE)['PolicyDocument'] == doc:
            print(f'  keep policy {role}/{QUEUE}')
            return
    except iam.exceptions.NoSuchEntityException:
        pass
    print(f'  update policy {role}/{QUEUE}: sqs:SendMessage on {QUEUE} only')
    if apply:
        iam.put_role_policy(RoleName=role, PolicyName=QUEUE, PolicyDocument=json.dumps(doc))


def _wanted(current, arn):
    want = {k: v for k, v in current.items() if k not in READ_ONLY}
    target = current['Target']
    want['ScheduleExpressionTimezone'] = 'Asia/Manila'
    want['Target'] = {**target, 'RetryPolicy': {**target.get('RetryPolicy', {}), 'MaximumRetryAttempts': 2},
                      'DeadLetterConfig': {'Arn': arn}}
    return want


def schedules(c, arn, apply):
    sch = c['scheduler']
    current = {n: sch.get_schedule(Name=n, GroupName=GROUP) for n in SCHEDULES}
    for role in sorted({s['Target']['RoleArn'].rsplit('/', 1)[-1] for s in current.values()}):
        _role_policy(c['iam'], role, arn, apply)
    for name, s in current.items():
        want = _wanted(s, arn)
        if want == {k: v for k, v in s.items() if k not in READ_ONLY}:
            print(f'  keep schedule {name}')
            continue
        print(f"  update schedule {name}: {s['ScheduleExpression']} {s.get('ScheduleExpressionTimezone')} -> "
              f'Asia/Manila, 2 retries, DLQ {QUEUE}')
        if apply:
            sch.update_schedule(**want)


def ttl(c, arn, apply):
    ddb = c['dynamodb']
    d = ddb.describe_time_to_live(TableName=INVITES)['TimeToLiveDescription']
    if d.get('TimeToLiveStatus') in ('ENABLED', 'ENABLING') and d.get('AttributeName') == 'ttl':
        print(f'  keep ttl {INVITES}.ttl')
    else:
        print(f'  update ttl {INVITES}.ttl: enable')
        if apply:
            ddb.update_time_to_live(TableName=INVITES, TimeToLiveSpecification={'Enabled': True, 'AttributeName': 'ttl'})
    names = {'#t': 'ttl'}  # TTL is a DynamoDB reserved word
    pages = ddb.get_paginator('scan').paginate(TableName=INVITES, FilterExpression='attribute_not_exists(#t)',
                                               ExpressionAttributeNames=names)
    for item in (i for p in pages for i in p['Items']):
        label, expires = item.get('inviteID', {}).get('S', '?'), item.get('expiresAt', {}).get('N')
        if not expires:
            print(f'  skip invite {label} (no numeric expiresAt)')
            continue
        print(f'  update invite {label} ttl={expires}')
        if apply:
            ddb.update_item(TableName=INVITES, Key={'inviteTokenHash': item['inviteTokenHash']},
                            UpdateExpression='SET #t = :e', ExpressionAttributeNames=names,
                            ExpressionAttributeValues={':e': {'N': expires}})


STEPS = {f.__name__: f for f in (dlq, gsi, stream, retries, dailyalert, schedules, ttl)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apply', action='store_true', help='perform writes (default: dry run)')
    ap.add_argument('--only', choices=list(STEPS), help='one step only')
    args = ap.parse_args(argv)
    if args.apply and os.environ.get('ROLLOUT_LIVE') != '1':
        print('Refusing live writes: set ROLLOUT_LIVE=1 for the real rollout.', file=sys.stderr)
        return 2
    os.environ['AWS_PAGER'] = ''
    import boto3
    c = {n: boto3.client(n) for n in ('sqs', 'dynamodb', 'lambda', 'scheduler', 'iam', 'sts')}
    # ponytail: the queue ARN is deterministic, so a dry run (queue absent) and --only share one value
    arn = f"arn:aws:sqs:{c['sqs'].meta.region_name}:{c['sts'].get_caller_identity()['Account']}:{QUEUE}"
    print(f"{'APPLY' if args.apply else 'DRY RUN'} scheduled-job rollout", flush=True)
    for name in [args.only] if args.only else STEPS:
        print(f'[{name}]', flush=True)
        STEPS[name](c, arn, args.apply)
    return 0


if __name__ == '__main__':
    sys.exit(main())
