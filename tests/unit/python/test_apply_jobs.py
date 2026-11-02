"""scripts/apply_jobs.py against moto: dry run, gate, apply, idempotent re-run, --only, missing stream mapping."""
import sys
from pathlib import Path

import boto3
import botocore.client
import pytest
from moto import mock_aws

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))

import apply_jobs  # noqa: E402

DLQ_ARN = 'arn:aws:sqs:us-east-1:123456789012:panindo-jobs-dlq'
SCHEDULES = {'InventoryIQ-DailyAlert': 'cron(0 7 * * ? *)', 'Daily_Purge_Schedule': 'cron(0 3 * * ? *)'}
JOBS = ('DailyAlert', 'PurgeDeletedItems', 'LowItemInsight')
READ_PREFIXES = ('Get', 'Describe', 'List', 'Scan', 'Query')


def _function(lam, role, name):
    return lam.create_function(FunctionName=name, Runtime='python3.12', Role=role, Handler='x.handler',
                               Code={'ZipFile': b'PK\x05\x06' + b'\x00' * 18})['FunctionArn']


def _table(ddb, name, key, **extra):
    return ddb.create_table(TableName=name, KeySchema=[{'AttributeName': key, 'KeyType': 'HASH'}],
                            AttributeDefinitions=[{'AttributeName': key, 'AttributeType': 'S'}],
                            BillingMode='PAY_PER_REQUEST', **extra)['TableDescription']


def _fixture(with_mapping=True):
    iam, lam, ddb = boto3.client('iam'), boto3.client('lambda'), boto3.client('dynamodb')
    role = iam.create_role(RoleName='lambda-role', AssumeRolePolicyDocument='{}')['Role']['Arn']
    sched_role = iam.create_role(RoleName='Amazon_EventBridge_Scheduler_LAMBDA_x', Path='/service-role/',
                                 AssumeRolePolicyDocument='{}')['Role']['Arn']
    arns = {n: _function(lam, role, n) for n in (*JOBS, 'CascadeDeleteUser')}
    users = _table(ddb, 'Users', 'Email', StreamSpecification={'StreamEnabled': True, 'StreamViewType': 'OLD_IMAGE'})
    if with_mapping:
        lam.create_event_source_mapping(EventSourceArn=users['LatestStreamArn'], FunctionName='CascadeDeleteUser',
                                        StartingPosition='LATEST')
    _table(ddb, 'InventoryTransactions', 'transactionID')
    _table(ddb, 'OrgInvites', 'inviteTokenHash')
    for key, item in {'a': {'expiresAt': {'N': '1900000000'}},
                      'b': {'expiresAt': {'N': '1900000001'}, 'ttl': {'N': '42'}},
                      'c': {}}.items():
        ddb.put_item(TableName='OrgInvites', Item={'inviteTokenHash': {'S': key}, 'inviteID': {'S': key}, **item})
    target = arns['PurgeDeletedItems']
    for name, cron in SCHEDULES.items():
        boto3.client('scheduler').create_schedule(
            Name=name, GroupName='default', ScheduleExpression=cron, ScheduleExpressionTimezone='Pacific/Honolulu',
            FlexibleTimeWindow={'Mode': 'OFF'},
            Target={'Arn': target, 'RoleArn': sched_role, 'RetryPolicy': {'MaximumRetryAttempts': 0}})
    return {'iam': iam, 'lambda': lam, 'dynamodb': ddb, 'sqs': boto3.client('sqs'),
            'scheduler': boto3.client('scheduler')}


@pytest.fixture
def env(monkeypatch):
    for k, v in {'AWS_DEFAULT_REGION': 'us-east-1', 'AWS_ACCESS_KEY_ID': 'testing',
                 'AWS_SECRET_ACCESS_KEY': 'testing', 'ROLLOUT_LIVE': '1'}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv('AWS_PROFILE', raising=False)
    monkeypatch.delenv('AWS_ENDPOINT_URL', raising=False)


@pytest.fixture
def aws(env):
    with mock_aws():
        yield _fixture()


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


def _queues(aws):
    return aws['sqs'].list_queues().get('QueueUrls', [])


def _indexes(aws):
    t = aws['dynamodb'].describe_table(TableName='InventoryTransactions')['Table']
    return [g['IndexName'] for g in t.get('GlobalSecondaryIndexes', [])]


def _invites(aws):
    items = aws['dynamodb'].scan(TableName='OrgInvites')['Items']
    return {i['inviteID']['S']: i.get('ttl', {}).get('N') for i in items}


def _mapping(aws):
    return aws['lambda'].list_event_source_mappings(FunctionName='CascadeDeleteUser')['EventSourceMappings'][0]


def _schedule(aws, name):
    return aws['scheduler'].get_schedule(Name=name, GroupName='default')


def _state(aws):
    lam = aws['lambda']
    cfg = lam.get_function_configuration(FunctionName='DailyAlert')
    m = _mapping(aws)
    return {
        'queues': _queues(aws), 'indexes': _indexes(aws), 'invites': _invites(aws),
        'mapping': (m.get('MaximumRetryAttempts'), m.get('BisectBatchOnFunctionError'), m.get('DestinationConfig')),
        'dailyalert': (cfg['MemorySize'], cfg['Timeout']),
        'schedules': {n: (s['ScheduleExpression'], s['ScheduleExpressionTimezone'], s['Target'])
                      for n in SCHEDULES for s in [_schedule(aws, n)]},
        'ttl': aws['dynamodb'].describe_time_to_live(TableName='OrgInvites')['TimeToLiveDescription'],
        'policies': aws['iam'].list_role_policies(RoleName='Amazon_EventBridge_Scheduler_LAMBDA_x')['PolicyNames'],
    }


def _changes(out):
    return [line.split()[0] for line in out.splitlines() if line.startswith('  ')]


# AC1 ---------------------------------------------------------------------------------------------------------------

def test_dry_run_prints_every_step_and_writes_nothing(aws, capsys, writes):
    before = _state(aws)
    assert apply_jobs.main([]) == 0
    out = capsys.readouterr().out
    for step in apply_jobs.STEPS:
        assert f'[{step}]' in out
    assert 'create queue panindo-jobs-dlq' in out
    assert 'create index InventoryTransactions/orgID-createdAt-index' in out
    assert 'update invite a' in out and 'skip invite c' in out
    assert writes == []
    assert _state(aws) == before


# AC2 ---------------------------------------------------------------------------------------------------------------

def test_apply_without_rollout_live_exits_2(aws, monkeypatch, writes):
    monkeypatch.delenv('ROLLOUT_LIVE')
    assert apply_jobs.main(['--apply']) == 2
    assert writes == [] and _queues(aws) == []


# AC3 + AC7 ---------------------------------------------------------------------------------------------------------

def test_apply_produces_the_target_state(aws):
    assert apply_jobs.main(['--apply']) == 0
    sqs = aws['sqs']
    attrs = sqs.get_queue_attributes(QueueUrl=sqs.get_queue_url(QueueName='panindo-jobs-dlq')['QueueUrl'],
                                     AttributeNames=['All'])['Attributes']
    assert attrs['QueueArn'] == DLQ_ARN and attrs['MessageRetentionPeriod'] == '1209600'
    gsi = {g['IndexName']: g for g in aws['dynamodb'].describe_table(
        TableName='InventoryTransactions')['Table']['GlobalSecondaryIndexes']}['orgID-createdAt-index']
    assert gsi['KeySchema'] == [{'AttributeName': 'orgID', 'KeyType': 'HASH'},
                                {'AttributeName': 'createdAt', 'KeyType': 'RANGE'}]
    assert gsi['Projection'] == {'ProjectionType': 'ALL'}
    m = _mapping(aws)
    assert (m['MaximumRetryAttempts'], m['BisectBatchOnFunctionError']) == (3, True)
    assert m['DestinationConfig']['OnFailure']['Destination'] == DLQ_ARN
    for fn in JOBS:
        cfg = aws['lambda'].get_function_event_invoke_config(FunctionName=fn)
        assert cfg['MaximumRetryAttempts'] == 2 and cfg['DestinationConfig']['OnFailure']['Destination'] == DLQ_ARN
    cfg = aws['lambda'].get_function_configuration(FunctionName='DailyAlert')
    assert (cfg['MemorySize'], cfg['Timeout']) == (512, 30)
    for name, cron in SCHEDULES.items():
        s = _schedule(aws, name)
        assert s['ScheduleExpression'] == cron  # AC7
        assert s['ScheduleExpressionTimezone'] == 'Asia/Manila'
        assert s['Target']['RetryPolicy']['MaximumRetryAttempts'] == 2
        assert s['Target']['DeadLetterConfig'] == {'Arn': DLQ_ARN}
    doc = aws['iam'].get_role_policy(RoleName='Amazon_EventBridge_Scheduler_LAMBDA_x',
                                     PolicyName='panindo-jobs-dlq')['PolicyDocument']
    assert doc['Statement'] == [{'Effect': 'Allow', 'Action': 'sqs:SendMessage', 'Resource': DLQ_ARN}]
    ttl = aws['dynamodb'].describe_time_to_live(TableName='OrgInvites')['TimeToLiveDescription']
    assert ttl['TimeToLiveStatus'] in ('ENABLED', 'ENABLING') and ttl['AttributeName'] == 'ttl'
    assert _invites(aws) == {'a': '1900000000', 'b': '42', 'c': None}


# AC4 ---------------------------------------------------------------------------------------------------------------

def test_second_apply_only_keeps_and_skips(aws, capsys, writes):
    apply_jobs.main(['--apply'])
    capsys.readouterr()
    writes.clear()
    assert apply_jobs.main(['--apply']) == 0
    assert set(_changes(capsys.readouterr().out)) <= {'keep', 'skip'}
    assert writes == []


# AC5 ---------------------------------------------------------------------------------------------------------------

def test_only_runs_one_step(aws, capsys):
    assert apply_jobs.main(['--apply', '--only', 'ttl']) == 0
    out = capsys.readouterr().out
    assert '[ttl]' in out and '[dlq]' not in out
    assert _queues(aws) == [] and _invites(aws)['a'] == '1900000000'
    assert _schedule(aws, 'InventoryIQ-DailyAlert')['ScheduleExpressionTimezone'] == 'Pacific/Honolulu'


def test_unknown_step_exits_non_zero(aws):
    with pytest.raises(SystemExit) as e:
        apply_jobs.main(['--only', 'nope'])
    assert e.value.code != 0


# AC6 ---------------------------------------------------------------------------------------------------------------

def test_missing_stream_mapping_aborts_only_the_stream_step(env):
    with mock_aws():
        aws = _fixture(with_mapping=False)
        with pytest.raises(SystemExit, match='CascadeDeleteUser'):
            apply_jobs.main(['--apply', '--only', 'stream'])
        assert apply_jobs.main(['--apply', '--only', 'retries']) == 0
        cfg = aws['lambda'].get_function_event_invoke_config(FunctionName='DailyAlert')
        assert cfg['MaximumRetryAttempts'] == 2
