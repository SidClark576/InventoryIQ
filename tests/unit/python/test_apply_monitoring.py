"""scripts/apply_monitoring.py against moto: dry run, gate, apply, idempotent re-run, --only, abort paths."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import boto3
import botocore.client
import pytest
from moto import mock_aws

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))

import apply_monitoring  # noqa: E402

EMAIL = 'ops@example.test'
OPS_ARN = 'arn:aws:sns:us-east-1:123456789012:panindo-ops'
ALARMS = {'panindo-lambda-throttles', 'panindo-proxy-errors', 'panindo-authentication-errors', 'panindo-api-5xx',
          'panindo-dlq-depth', 'panindo-ses-bounce-rate'}
READ_PREFIXES = ('Get', 'Describe', 'List', 'Scan', 'Query')
MOTO = {'iam': {'load_aws_managed_policies': True}}


def _rest_api(apigw):
    api = apigw.create_rest_api(name='InventoryIQ-API')['id']
    root = apigw.get_resources(restApiId=api)['items'][0]['id']
    for parent, child, method in (('auth', '{proxy+}', 'POST'), ('barcode', '{code}', 'GET')):
        pid = apigw.create_resource(restApiId=api, parentId=root, pathPart=parent)['id']
        rid = apigw.create_resource(restApiId=api, parentId=pid, pathPart=child)['id']
        for m in (method, 'OPTIONS'):
            apigw.put_method(restApiId=api, resourceId=rid, httpMethod=m, authorizationType='NONE')
            apigw.put_integration(restApiId=api, resourceId=rid, httpMethod=m, type='MOCK')
    apigw.create_deployment(restApiId=api, stageName='prod')
    return api


def _fixture(monkeypatch, emails=(EMAIL,), foreign_alarms=0):
    sns, cw, apigw = boto3.client('sns'), boto3.client('cloudwatch'), boto3.client('apigateway')
    source = sns.create_topic(Name='InventoryIQ-Alerts')['TopicArn']
    for e in emails:
        sns.subscribe(TopicArn=source, Protocol='email', Endpoint=e)
    sns.subscribe(TopicArn=source, Protocol='sms', Endpoint='+15555550100')
    for i in range(foreign_alarms):
        cw.put_metric_alarm(AlarmName=f'other-{i}', Namespace='X', MetricName='Y', Statistic='Sum', Period=60,
                            EvaluationPeriods=1, Threshold=1, ComparisonOperator='GreaterThanThreshold')
    monkeypatch.setattr(apply_monitoring, 'API_ID', _rest_api(apigw))
    boto3.client('sqs').create_queue(QueueName='panindo-jobs-dlq')
    return {'sns': sns, 'cloudwatch': cw, 'apigateway': apigw, 'iam': boto3.client('iam'), 'logs': boto3.client('logs')}


@pytest.fixture
def env(monkeypatch):
    for k, v in {'AWS_DEFAULT_REGION': 'us-east-1', 'AWS_ACCESS_KEY_ID': 'testing',
                 'AWS_SECRET_ACCESS_KEY': 'testing', 'ROLLOUT_LIVE': '1'}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv('AWS_PROFILE', raising=False)
    monkeypatch.delenv('AWS_ENDPOINT_URL', raising=False)


@pytest.fixture
def aws(env, monkeypatch):
    with mock_aws(config=MOTO):
        yield _fixture(monkeypatch)


@pytest.fixture
def writes(monkeypatch):
    """Names of every non-read AWS operation made after this fixture starts."""
    seen, real = [], botocore.client.BaseClient._make_api_call

    def spy(self, op, params):
        if not op.startswith(READ_PREFIXES) and op != 'GetCallerIdentity':
            seen.append(op)
        return real(self, op, params)
    monkeypatch.setattr(botocore.client.BaseClient, '_make_api_call', spy)
    return seen


def _alarms(aws):
    return {a['AlarmName']: a for a in aws['cloudwatch'].describe_alarms()['MetricAlarms']}


def _stage(aws):
    return aws['apigateway'].get_stage(restApiId=apply_monitoring.API_ID, stageName='prod')


def _state(aws):
    return {'topics': aws['sns'].list_topics()['Topics'], 'alarms': sorted(_alarms(aws)),
            'roles': [r['RoleName'] for r in aws['iam'].list_roles()['Roles']],
            'account': aws['apigateway'].get_account().get('cloudwatchRoleArn'),
            'groups': aws['logs'].describe_log_groups()['logGroups'],
            'stage': (_stage(aws).get('accessLogSettings'), _stage(aws).get('methodSettings'))}


def _changes(out):
    return [line.split()[0] for line in out.splitlines() if line.startswith('  ')]


# AC1 ---------------------------------------------------------------------------------------------------------------

def test_dry_run_prints_every_step_and_writes_nothing(aws, capsys, writes):
    before = _state(aws)
    assert apply_monitoring.main([]) == 0
    out = capsys.readouterr().out
    for step in apply_monitoring.STEPS:
        assert f'[{step}]' in out
    assert 'create topic panindo-ops' in out and 'create subscription' in out
    for name in ALARMS:
        assert f'create alarm {name}' in out
    assert 'create role panindo-apigateway-logs' in out
    assert 'update stage prod throttling */* 20/40' in out
    assert 'update stage prod throttling /auth/{proxy+} POST 2/5' in out
    assert 'barcode' not in out
    assert EMAIL not in out
    assert writes == []
    assert _state(aws) == before


# AC2 ---------------------------------------------------------------------------------------------------------------

def test_apply_without_rollout_live_exits_2(aws, monkeypatch, writes):
    monkeypatch.delenv('ROLLOUT_LIVE')
    assert apply_monitoring.main(['--apply']) == 2
    assert writes == [] and _alarms(aws) == {}


# AC3 ---------------------------------------------------------------------------------------------------------------

def test_apply_produces_the_target_state(aws):
    assert apply_monitoring.main(['--apply']) == 0
    subs = aws['sns'].list_subscriptions_by_topic(TopicArn=OPS_ARN)['Subscriptions']
    assert [(s['Protocol'], s['Endpoint']) for s in subs] == [('email', EMAIL)]
    alarms = _alarms(aws)
    assert set(alarms) == ALARMS
    for a in alarms.values():
        assert a['AlarmActions'] == [OPS_ARN] and a['TreatMissingData'] == 'notBreaching'
        assert a['EvaluationPeriods'] == 1
    api5xx = alarms['panindo-api-5xx']
    assert (api5xx['Namespace'], api5xx['MetricName']) == ('AWS/ApiGateway', '5XXError')
    assert api5xx['Dimensions'] == [{'Name': 'ApiName', 'Value': 'InventoryIQ-API'}, {'Name': 'Stage', 'Value': 'prod'}]
    assert alarms['panindo-proxy-errors']['Dimensions'] == [{'Name': 'FunctionName', 'Value': 'Proxy'}]
    dlq = alarms['panindo-dlq-depth']
    assert (dlq['Statistic'], dlq['Dimensions']) == ('Maximum', [{'Name': 'QueueName', 'Value': 'panindo-jobs-dlq'}])
    ses = alarms['panindo-ses-bounce-rate']
    assert (ses['Threshold'], ses['ComparisonOperator'], ses['Period']) == (0.05, 'GreaterThanOrEqualToThreshold', 3600)
    role = aws['iam'].get_role(RoleName='panindo-apigateway-logs')['Role']
    assert role['AssumeRolePolicyDocument']['Statement'][0]['Principal'] == {'Service': 'apigateway.amazonaws.com'}
    attached = aws['iam'].list_attached_role_policies(RoleName='panindo-apigateway-logs')['AttachedPolicies']
    assert [p['PolicyArn'] for p in attached] == [apply_monitoring.PUSH_POLICY]
    assert aws['apigateway'].get_account()['cloudwatchRoleArn'] == role['Arn']
    group = aws['logs'].describe_log_groups(logGroupNamePrefix='/aws/apigateway/InventoryIQ-API/prod')['logGroups'][0]
    assert group['retentionInDays'] == 7
    stage = _stage(aws)
    assert stage['accessLogSettings']['destinationArn'].endswith(':log-group:/aws/apigateway/InventoryIQ-API/prod')
    fmt = json.loads(stage['accessLogSettings']['format'])
    assert fmt['ip'] == '$context.identity.sourceIp'
    assert set(fmt) == {'requestId', 'ip', 'requestTime', 'httpMethod', 'resourcePath', 'status', 'responseLatency',
                        'userAgent'}
    ms = {k: (v['throttlingRateLimit'], v['throttlingBurstLimit']) for k, v in stage['methodSettings'].items()}
    assert ms == {'*/*': (20.0, 40), '~1auth~1{proxy+}/POST': (2.0, 5), '~1auth~1{proxy+}/OPTIONS': (2.0, 5)}


# AC4 ---------------------------------------------------------------------------------------------------------------

def test_second_apply_only_keeps_and_skips(aws, capsys, writes):
    apply_monitoring.main(['--apply'])
    capsys.readouterr()
    writes.clear()
    assert apply_monitoring.main(['--apply']) == 0
    assert set(_changes(capsys.readouterr().out)) <= {'keep', 'skip'}
    assert writes == []


# AC5 ---------------------------------------------------------------------------------------------------------------

def test_only_runs_one_step(aws, capsys):
    assert apply_monitoring.main(['--apply', '--only', 'throttles']) == 0
    out = capsys.readouterr().out
    assert '[throttles]' in out and '[topic]' not in out
    assert _alarms(aws) == {} and len(aws['sns'].list_topics()['Topics']) == 1
    assert '*/*' in _stage(aws)['methodSettings']


def test_unknown_step_exits_non_zero(aws):
    with pytest.raises(SystemExit) as e:
        apply_monitoring.main(['--only', 'nope'])
    assert e.value.code != 0


# AC6 ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('emails', [(), (EMAIL, 'other@example.test')])
def test_topic_aborts_without_exactly_one_confirmed_email(env, monkeypatch, emails):
    with mock_aws(config=MOTO):
        aws = _fixture(monkeypatch, emails=emails)
        with pytest.raises(SystemExit, match='topic'):
            apply_monitoring.main(['--apply', '--only', 'topic'])
        assert len(aws['sns'].list_topics()['Topics']) == 1
        assert apply_monitoring.main(['--apply', '--only', 'alarms']) == 0
        assert set(_alarms(aws)) == ALARMS


def test_alarms_abort_over_the_free_tier_cap(env, monkeypatch):
    with mock_aws(config=MOTO):
        aws = _fixture(monkeypatch, foreign_alarms=5)
        with pytest.raises(SystemExit, match='alarms'):
            apply_monitoring.main(['--apply', '--only', 'alarms'])
        assert len(_alarms(aws)) == 5
        assert apply_monitoring.main(['--apply', '--only', 'accesslog']) == 0
        assert _stage(aws)['accessLogSettings']


def test_confirmed_emails_ignores_pending_and_other_protocols():
    subs = [{'Protocol': 'email', 'Endpoint': 'a@x.test', 'SubscriptionArn': 'arn:aws:sns:r:1:t:1'},
            {'Protocol': 'email', 'Endpoint': 'b@x.test', 'SubscriptionArn': 'PendingConfirmation'},
            {'Protocol': 'sms', 'Endpoint': '+1', 'SubscriptionArn': 'arn:aws:sns:r:1:t:2'}]
    assert apply_monitoring.confirmed_emails(subs) == ['a@x.test']


def test_log_role_retries_while_iam_propagates(monkeypatch):
    class BadRequest(Exception):
        pass
    calls = []

    def update_account(**kw):
        calls.append(kw)
        if len(calls) < 3:
            raise BadRequest()
    apigw = SimpleNamespace(exceptions=SimpleNamespace(BadRequestException=BadRequest,
                                                       TooManyRequestsException=TooMany), update_account=update_account)
    monkeypatch.setattr(apply_monitoring.time, 'sleep', lambda s: None)
    apply_monitoring.set_log_role(apigw, 'arn:role')
    assert len(calls) == 3


class TooMany(Exception):
    pass


def test_log_role_retries_when_update_account_is_rate_limited(monkeypatch):
    # Live 2026-11-02: UpdateAccount raised TooManyRequestsException (boto3 gave up after 4 tries).
    calls, sleeps = [], []

    def update_account(**kw):
        calls.append(kw)
        if len(calls) < 3:
            raise TooMany()
    apigw = SimpleNamespace(exceptions=SimpleNamespace(BadRequestException=ValueError, TooManyRequestsException=TooMany),
                            update_account=update_account)
    monkeypatch.setattr(apply_monitoring.time, 'sleep', sleeps.append)
    apply_monitoring.set_log_role(apigw, 'arn:role')
    assert len(calls) == 3 and min(sleeps) >= 20
