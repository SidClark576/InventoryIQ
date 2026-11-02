#!/usr/bin/env python3
"""Free-tier monitoring rollout (job 022, Phase 4). SAFE BY DEFAULT: a dry run prints the plan.

Steps, in order (--only <step> runs one):
  topic      SNS topic panindo-ops + the one confirmed email on InventoryIQ-Alerts (read from AWS, never stored)
  alarms     six CloudWatch alarms -> panindo-ops: Lambda throttles, Proxy/Authentication errors, API 5XX,
             DLQ depth, SES bounce rate >= 5% (aborts if the account would pass 10 alarms, the free tier)
  logrole    IAM role panindo-apigateway-logs (AmazonAPIGatewayPushToCloudWatchLogs) as the API Gateway account role
  accesslog  log group /aws/apigateway/InventoryIQ-API/prod (7 days) + JSON access logs on stage prod
  throttles  stage prod: */* rate 20 / burst 40; every /auth method rate 2 / burst 5

  AWS_PROFILE=inventoryiq .venv/bin/python scripts/apply_monitoring.py                           # dry run
  ROLLOUT_LIVE=1 AWS_PROFILE=inventoryiq .venv/bin/python scripts/apply_monitoring.py --apply     # live

Live runs are the user's call. Re-runs are idempotent. Confirm the panindo-ops email link once.
"""
import argparse
import json
import os
import sys
import time

TOPIC, SOURCE_TOPIC = 'panindo-ops', 'InventoryIQ-Alerts'
API_ID, STAGE = 'd1g2j27343', 'prod'
QUEUE, MAX_ALARMS = 'panindo-jobs-dlq', 10
ROLE = 'panindo-apigateway-logs'
PUSH_POLICY = 'arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs'
TRUST = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Principal': {'Service': 'apigateway.amazonaws.com'},
                                                 'Action': 'sts:AssumeRole'}]}
LOG_GROUP, RETENTION = '/aws/apigateway/InventoryIQ-API/prod', 7
LOG_FORMAT = json.dumps({'requestId': '$context.requestId', 'ip': '$context.identity.sourceIp',
                         'requestTime': '$context.requestTime', 'httpMethod': '$context.httpMethod',
                         'resourcePath': '$context.resourcePath', 'status': '$context.status',
                         'responseLatency': '$context.responseLatency', 'userAgent': '$context.identity.userAgent'})
DEFAULT_LIMITS, AUTH_LIMITS = (20, 40), (2, 5)


def _subs(sns, topic_arn):
    pages = sns.get_paginator('list_subscriptions_by_topic').paginate(TopicArn=topic_arn)
    return [s for p in pages for s in p['Subscriptions']]


def confirmed_emails(subs):
    return [s['Endpoint'] for s in subs if s['Protocol'] == 'email' and s['SubscriptionArn'].startswith('arn:')]


def topic(c, ops_arn, apply):
    sns = c['sns']
    emails = confirmed_emails(_subs(sns, ops_arn.rsplit(':', 1)[0] + ':' + SOURCE_TOPIC))
    if len(emails) != 1:
        raise SystemExit(f'topic: {SOURCE_TOPIC} has {len(emails)} confirmed email subscriptions, need 1; step aborted')
    exists = any(t['TopicArn'] == ops_arn for p in sns.get_paginator('list_topics').paginate() for t in p['Topics'])
    print(f"  {'keep' if exists else 'create'} topic {TOPIC}")
    if not exists and apply:
        sns.create_topic(Name=TOPIC)
    if exists and any(s['Endpoint'] == emails[0] for s in _subs(sns, ops_arn)):
        print(f'  keep subscription {SOURCE_TOPIC} email -> {TOPIC}')
        return
    print(f'  create subscription {SOURCE_TOPIC} email -> {TOPIC} (confirm the link in that inbox)')
    if apply:
        sns.subscribe(TopicArn=ops_arn, Protocol='email', Endpoint=emails[0])


def _alarm_specs(api_name):
    over = {'Statistic': 'Sum', 'Period': 300, 'Threshold': 0.0, 'ComparisonOperator': 'GreaterThanThreshold'}
    fn = lambda name: [{'Name': 'FunctionName', 'Value': name}]  # noqa: E731
    return {
        'panindo-lambda-throttles': {**over, 'Namespace': 'AWS/Lambda', 'MetricName': 'Throttles', 'Dimensions': []},
        'panindo-proxy-errors': {**over, 'Namespace': 'AWS/Lambda', 'MetricName': 'Errors', 'Dimensions': fn('Proxy')},
        'panindo-authentication-errors': {**over, 'Namespace': 'AWS/Lambda', 'MetricName': 'Errors',
                                          'Dimensions': fn('Authentication')},
        'panindo-api-5xx': {**over, 'Namespace': 'AWS/ApiGateway', 'MetricName': '5XXError',
                            'Dimensions': [{'Name': 'ApiName', 'Value': api_name}, {'Name': 'Stage', 'Value': STAGE}]},
        'panindo-dlq-depth': {**over, 'Statistic': 'Maximum', 'Namespace': 'AWS/SQS',
                              'MetricName': 'ApproximateNumberOfMessagesVisible',
                              'Dimensions': [{'Name': 'QueueName', 'Value': QUEUE}]},
        'panindo-ses-bounce-rate': {'Namespace': 'AWS/SES', 'MetricName': 'Reputation.BounceRate', 'Dimensions': [],
                                    'Statistic': 'Average', 'Period': 3600, 'Threshold': 0.05,
                                    'ComparisonOperator': 'GreaterThanOrEqualToThreshold'},
    }


def alarms(c, ops_arn, apply):
    cw = c['cloudwatch']
    current = {a['AlarmName']: a for p in cw.get_paginator('describe_alarms').paginate() for a in p['MetricAlarms']}
    specs = _alarm_specs(c['apigateway'].get_rest_api(restApiId=API_ID)['name'])
    foreign = len(set(current) - set(specs))
    if foreign + len(specs) > MAX_ALARMS:
        raise SystemExit(f'alarms: {foreign} other alarms + {len(specs)} would pass the free tier of {MAX_ALARMS}; '
                         'step aborted')
    for name, spec in specs.items():
        want = {**spec, 'AlarmActions': [ops_arn], 'TreatMissingData': 'notBreaching', 'EvaluationPeriods': 1}
        cur = current.get(name)
        if cur and {k: cur.get(k, []) for k in want} == want:
            print(f'  keep alarm {name}')
            continue
        print(f"  {'update' if cur else 'create'} alarm {name}: {spec['Namespace']} {spec['MetricName']} "
              f"{spec['Statistic']} {spec['Period']} s {spec['ComparisonOperator']} {spec['Threshold']}")
        if apply:
            cw.put_metric_alarm(AlarmName=name, **want)


def set_log_role(apigw, role_arn):
    for attempt in range(10):  # a new role takes a few seconds to become usable by API Gateway
        try:
            apigw.update_account(patchOperations=[{'op': 'replace', 'path': '/cloudwatchRoleArn', 'value': role_arn}])
            return
        except apigw.exceptions.BadRequestException:
            if attempt == 9:
                raise
            time.sleep(3)


def logrole(c, ops_arn, apply):
    iam = c['iam']
    try:
        role_arn = iam.get_role(RoleName=ROLE)['Role']['Arn']
        attached = [p['PolicyArn'] for p in iam.list_attached_role_policies(RoleName=ROLE)['AttachedPolicies']]
        print(f'  keep role {ROLE}')
    except iam.exceptions.NoSuchEntityException:
        role_arn, attached = f'arn:aws:iam::{ops_arn.split(":")[4]}:role/{ROLE}', []
        print(f'  create role {ROLE} (trust apigateway.amazonaws.com)')
        if apply:
            iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps(TRUST))
    if PUSH_POLICY in attached:
        print(f'  keep policy {ROLE}/AmazonAPIGatewayPushToCloudWatchLogs')
    else:
        print(f'  create policy {ROLE}/AmazonAPIGatewayPushToCloudWatchLogs')
        if apply:
            iam.attach_role_policy(RoleName=ROLE, PolicyArn=PUSH_POLICY)
    if c['apigateway'].get_account().get('cloudwatchRoleArn') == role_arn:
        print(f'  keep account cloudwatchRoleArn {ROLE}')
        return
    print(f'  update account cloudwatchRoleArn -> {ROLE}')
    if apply:
        set_log_role(c['apigateway'], role_arn)


def accesslog(c, ops_arn, apply):
    logs, apigw = c['logs'], c['apigateway']
    region, account = ops_arn.split(':')[3:5]
    group = next((g for g in logs.describe_log_groups(logGroupNamePrefix=LOG_GROUP)['logGroups']
                  if g['logGroupName'] == LOG_GROUP), None)
    if group is None:
        print(f'  create log group {LOG_GROUP}')
        if apply:
            logs.create_log_group(logGroupName=LOG_GROUP)
    if group and group.get('retentionInDays') == RETENTION:
        print(f'  keep retention {LOG_GROUP} {RETENTION} days')
    else:
        print(f'  update retention {LOG_GROUP} -> {RETENTION} days')
        if apply:
            logs.put_retention_policy(logGroupName=LOG_GROUP, retentionInDays=RETENTION)
    want = {'destinationArn': f'arn:aws:logs:{region}:{account}:log-group:{LOG_GROUP}', 'format': LOG_FORMAT}
    if apigw.get_stage(restApiId=API_ID, stageName=STAGE).get('accessLogSettings') == want:
        print(f'  keep stage {STAGE} access logs')
        return
    print(f'  update stage {STAGE} access logs -> {LOG_GROUP} (JSON incl. ip)')
    if apply:
        apigw.update_stage(restApiId=API_ID, stageName=STAGE, patchOperations=[
            {'op': 'replace', 'path': f'/accessLogSettings/{k}', 'value': v} for k, v in want.items()])


def throttles(c, ops_arn, apply):
    apigw = c['apigateway']
    settings = apigw.get_stage(restApiId=API_ID, stageName=STAGE).get('methodSettings', {})
    pages = apigw.get_paginator('get_resources').paginate(restApiId=API_ID, embed=['methods'])
    auth = [(r['path'], m) for p in pages for r in p['items'] if r['path'].startswith('/auth')
            for m in r.get('resourceMethods', {})]
    if not auth:
        print('  skip /auth throttles (no /auth resource)')
    targets = [('*/*', '*/*', DEFAULT_LIMITS)] + [
        (f"{path.replace('/', '~1')}/{m}", f'{path} {m}', AUTH_LIMITS) for path, m in sorted(auth)]
    ops = []
    for key, label, (rate, burst) in targets:
        cur = settings.get(key, {})
        if (cur.get('throttlingRateLimit'), cur.get('throttlingBurstLimit')) == (rate, burst):
            print(f'  keep stage {STAGE} throttling {label} {rate}/{burst}')
            continue
        print(f'  update stage {STAGE} throttling {label} {rate}/{burst}')
        ops += [{'op': 'replace', 'path': f'/{key}/throttling/rateLimit', 'value': str(rate)},
                {'op': 'replace', 'path': f'/{key}/throttling/burstLimit', 'value': str(burst)}]
    if ops and apply:
        apigw.update_stage(restApiId=API_ID, stageName=STAGE, patchOperations=ops)


STEPS = {f.__name__: f for f in (topic, alarms, logrole, accesslog, throttles)}


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
    c = {n: boto3.client(n) for n in ('sns', 'cloudwatch', 'iam', 'apigateway', 'logs', 'sts')}
    # ponytail: topic, role and log-group ARNs are deterministic, so a dry run and --only share one value
    ops_arn = f"arn:aws:sns:{c['sns'].meta.region_name}:{c['sts'].get_caller_identity()['Account']}:{TOPIC}"
    print(f"{'APPLY' if args.apply else 'DRY RUN'} monitoring rollout", flush=True)
    for name in [args.only] if args.only else STEPS:
        print(f'[{name}]', flush=True)
        STEPS[name](c, ops_arn, args.apply)
    return 0


if __name__ == '__main__':
    sys.exit(main())
