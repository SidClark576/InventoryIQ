"""scripts/iam/*.json lint + scripts/apply_iam.py against moto: dry run, apply, simulate gate, rollback, X-Ray."""
import json
import re
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

ROOT = Path(__file__).resolve().parents[3]
LAMBDA = ROOT / 'lambda'
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(LAMBDA))

import _routes  # noqa: E402
import apply_iam  # noqa: E402

FUNCTIONS = sorted({m for _, _, m in _routes.ROUTES} - {'BulkImport'} | {
    'Authentication', 'CascadeDeleteUser', 'DailyAlert', 'Proxy', 'PurgeDeletedItems'})
DLQ_TARGETS = ('DailyAlert', 'LowItemInsight', 'PurgeDeletedItems')
TRACED = 'Proxy'
# _org.py symbols -> the table they reach (a function importing _org needs only the tables of the helpers it calls)
ORG_USES = {
    'Organizations': ('_org._orgs', '_org.ORGS_TABLE', 'list_user_orgs'),
    'OrgMembers': ('_org._members', '_org.MEMBERS_TABLE', 'get_membership', 'require_member', 'list_user_orgs'),
    'OrgInvites': ('_org._invites', '_org.INVITES_TABLE'),
}
TABLE_DEFAULT = re.compile(r"""(?:environ\.get\('\w+',\s*|process\.env\.\w+\s*\|\|\s*)['"](\w+)['"]""")


def _policy(name):
    return json.loads((apply_iam.IAM_DIR / f'{name}.json').read_text())


def _as_list(v):
    return v if isinstance(v, list) else [v]


def _statements():
    return [(n, s) for n in FUNCTIONS for s in _policy(n)['Statement']]


def _source(name):
    py = LAMBDA / f'{name}.py'
    return py.read_text() if py.exists() else (LAMBDA / f'{name}.mjs').read_text()


def _tables(name):
    src = _source(name)
    found = {t for t in TABLE_DEFAULT.findall(src) if t[0].isupper() and not t.isupper()}
    if 'import _org' in src:
        found |= {table for table, uses in ORG_USES.items() if any(u in src for u in uses)}
    return found


# AC1 ---------------------------------------------------------------------------------------------------------------

def test_one_policy_per_deployed_function():
    assert sorted(p.stem for p in apply_iam.IAM_DIR.glob('*.json')) == FUNCTIONS
    assert len(FUNCTIONS) == 18


def test_no_wildcard_or_forbidden_actions():
    for name, s in _statements():
        for action in _as_list(s['Action']):
            assert '*' not in action, (name, action)
            assert action != 'dynamodb:DeleteTable', name
            assert not action.startswith('secretsmanager:'), name
            assert action != 'sqs:ReceiveMessage', name


def test_every_resource_is_an_arn_except_kms_via_ssm():
    for name, s in _statements():
        for res in _as_list(s['Resource']):
            if res == '*' and _as_list(s['Action']) == ['dynamodb:ListStreams']:
                continue  # ListStreams has no resource type; IAM only matches it on "*"
            if res == '*':
                assert _as_list(s['Action']) == ['kms:Decrypt'], name
                assert s['Condition']['StringEquals']['kms:ViaService'] == 'ssm.${Region}.amazonaws.com'
            else:
                assert res.startswith('arn:aws:'), (name, res)


def test_sns_publish_only_to_the_alerts_topic():
    for name, s in _statements():
        if 'sns:Publish' in _as_list(s['Action']):
            assert _as_list(s['Resource']) == ['arn:aws:sns:${Region}:${AccountId}:InventoryIQ-Alerts'], name


def test_logs_scoped_to_own_log_group():
    for name in FUNCTIONS:
        logs = [s for s in _policy(name)['Statement'] if 'logs:PutLogEvents' in _as_list(s['Action'])]
        assert logs and all(f'log-group:/aws/lambda/{name}' in r for s in logs for r in _as_list(s['Resource']))


# AC2 ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('name', FUNCTIONS)
def test_every_table_the_code_names_is_granted(name):
    text = json.dumps(_policy(name))
    missing = [t for t in _tables(name) if f':table/{t}"' not in text]
    assert not missing, (name, missing)


def test_table_regex_sees_the_org_tables():
    assert {'Organizations', 'OrgMembers', 'OrgInvites'} <= _tables('OrgInvites')
    assert _tables('AddItem') == {'InventoryIQ', 'InventoryTransactions', 'IdempotencyKeys', 'OrgMembers'}


def test_proxy_invokes_exactly_the_deployed_route_modules():
    invoke = [s for s in _policy('Proxy')['Statement'] if 'lambda:InvokeFunction' in _as_list(s['Action'])]
    fns = {r.rsplit(':', 1)[-1] for s in invoke for r in _as_list(s['Resource'])}
    assert fns == {m for _, _, m in _routes.ROUTES} - {'BulkImport'}
    assert len(fns) == 13


# AC3-AC7 (moto) ----------------------------------------------------------------------------------------------------

@pytest.fixture
def aws(monkeypatch):
    for k, v in {'AWS_DEFAULT_REGION': 'us-east-1', 'AWS_ACCESS_KEY_ID': 'testing',
                 'AWS_SECRET_ACCESS_KEY': 'testing', 'ROLLOUT_LIVE': '1'}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv('AWS_PROFILE', raising=False)
    monkeypatch.delenv('AWS_ENDPOINT_URL', raising=False)
    monkeypatch.setattr(apply_iam, 'simulate', lambda *a: 'allowed')  # moto has no SimulatePrincipalPolicy
    with mock_aws():
        iam, lam = boto3.client('iam'), boto3.client('lambda')
        old = iam.create_role(RoleName=apply_iam.OLD_ROLE, AssumeRolePolicyDocument='{}')['Role']['Arn']
        for name in FUNCTIONS:
            tracing = {'TracingConfig': {'Mode': 'Active'}} if name == TRACED else {}
            lam.create_function(FunctionName=name, Runtime='python3.12', Role=old, Handler='x.handler',
                                Code={'ZipFile': b'PK\x05\x06' + b'\x00' * 18}, **tracing)
        dlq = boto3.client('sqs').create_queue(QueueName='LambdaDLQ')['QueueUrl']
        dlq_arn = boto3.client('sqs').get_queue_attributes(
            QueueUrl=dlq, AttributeNames=['QueueArn'])['Attributes']['QueueArn']
        for name in DLQ_TARGETS:
            lam.create_event_source_mapping(EventSourceArn=dlq_arn, FunctionName=name)
        stream = boto3.client('dynamodb').create_table(
            TableName='Users', KeySchema=[{'AttributeName': 'Email', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'Email', 'AttributeType': 'S'}], BillingMode='PAY_PER_REQUEST',
            StreamSpecification={'StreamEnabled': True, 'StreamViewType': 'OLD_IMAGE'})['TableDescription']
        lam.create_event_source_mapping(EventSourceArn=stream['LatestStreamArn'], FunctionName='CascadeDeleteUser',
                                        StartingPosition='LATEST')
        yield {'iam': iam, 'lambda': lam, 'old': old}


def _roles(aws):
    return {n: aws['lambda'].get_function_configuration(FunctionName=n)['Role'] for n in FUNCTIONS}


def _mapped(aws):
    return sorted(m['FunctionArn'].split(':')[6] for m in aws['lambda'].list_event_source_mappings()['EventSourceMappings'])


def _new_roles(aws):
    return [r['RoleName'] for r in aws['iam'].list_roles()['Roles'] if r['RoleName'].startswith('panindo-')]


def test_dry_run_prints_the_plan_and_writes_nothing(aws, capsys):
    before = _mapped(aws)
    assert apply_iam.main([]) == 0
    out = capsys.readouterr().out
    assert all(f'delete trigger LambdaDLQ -> {n}' in out for n in DLQ_TARGETS)
    assert 'create role panindo-Proxy' in out and 'switch Proxy' in out
    assert _new_roles(aws) == []
    assert set(_roles(aws).values()) == {aws['old']}
    assert _mapped(aws) == before


def test_apply_deletes_dlq_triggers_creates_roles_and_switches(aws):
    assert apply_iam.main(['--apply']) == 0
    assert _mapped(aws) == ['CascadeDeleteUser']
    assert sorted(_new_roles(aws)) == sorted(f'panindo-{n}' for n in FUNCTIONS)
    for name, role in _roles(aws).items():
        assert role.endswith(f':role/panindo-{name}')
        doc = aws['iam'].get_role_policy(RoleName=f'panindo-{name}', PolicyName='least-privilege')['PolicyDocument']
        assert '${' not in json.dumps(doc)
    assert apply_iam.main(['--apply']) == 0  # idempotent re-run
    assert len(_new_roles(aws)) == 18 and _mapped(aws) == ['CascadeDeleteUser']


def test_only_touches_one_function(aws):
    assert apply_iam.main(['--apply', '--only', 'DailyAlert']) == 0
    assert _new_roles(aws) == ['panindo-DailyAlert']
    assert _mapped(aws) == ['CascadeDeleteUser', 'LowItemInsight', 'PurgeDeletedItems']
    assert _roles(aws)['AddItem'] == aws['old']


def test_live_apply_or_rollback_without_rollout_live_exits_2(aws, monkeypatch):
    monkeypatch.delenv('ROLLOUT_LIVE')
    assert apply_iam.main(['--apply']) == 2
    assert apply_iam.main(['--rollback']) == 2
    assert _new_roles(aws) == []


@pytest.mark.parametrize('decision', ['implicitDeny', 'explicitDeny'])
def test_simulated_deny_aborts_before_any_role_switch(aws, monkeypatch, decision):
    monkeypatch.setattr(apply_iam, 'simulate', lambda iam, arn, action, res, ctx:
                        decision if arn.endswith('panindo-Proxy') and action == 'ssm:GetParameter' else 'allowed')
    with pytest.raises(SystemExit, match='no Role switched'):
        apply_iam.main(['--apply'])
    assert set(_roles(aws).values()) == {aws['old']}


def test_simulate_passes_the_statement_condition_as_context(aws, monkeypatch):
    seen = []
    monkeypatch.setattr(apply_iam, 'simulate', lambda iam, arn, action, res, ctx: seen.append((action, ctx)) or 'allowed')
    apply_iam.main(['--apply', '--only', 'Proxy'])
    kms = [ctx for action, ctx in seen if action == 'kms:Decrypt']
    assert kms == [[{'ContextKeyName': 'kms:ViaService', 'ContextKeyValues': ['ssm.us-east-1.amazonaws.com'],
                     'ContextKeyType': 'string'}]]


def test_simulate_checks_list_streams_on_star_and_stream_reads_on_the_stream_arn(aws, monkeypatch):
    seen = {}
    monkeypatch.setattr(apply_iam, 'simulate', lambda iam, arn, action, res, ctx: seen.setdefault(action, res) and 'allowed')
    apply_iam.main(['--apply', '--only', 'CascadeDeleteUser'])
    assert seen['dynamodb:ListStreams'] == '*'
    stream = 'arn:aws:dynamodb:us-east-1:123456789012:table/Users/stream/*'
    assert [seen[a] for a in ('dynamodb:DescribeStream', 'dynamodb:GetRecords', 'dynamodb:GetShardIterator')] == [stream] * 3


def test_rollback_restores_the_shared_role(aws):
    apply_iam.main(['--apply'])
    assert apply_iam.main(['--rollback']) == 0
    assert set(_roles(aws).values()) == {aws['old']}


def test_xray_only_for_active_tracing(aws):
    apply_iam.main(['--apply'])
    for name in FUNCTIONS:
        doc = json.dumps(aws['iam'].get_role_policy(RoleName=f'panindo-{name}', PolicyName='least-privilege'))
        assert ('xray:PutTraceSegments' in doc) == (name == TRACED), name


def test_switch_retries_while_the_new_role_propagates(monkeypatch):
    class Lam:
        class exceptions:
            class InvalidParameterValueException(Exception):
                pass
        calls = 0

        def get_function_configuration(self, FunctionName):
            return {'Role': 'old'}

        def update_function_configuration(self, **kw):
            Lam.calls += 1
            if Lam.calls < 3:
                raise Lam.exceptions.InvalidParameterValueException()

        def get_waiter(self, _):
            return type('W', (), {'wait': lambda self, **kw: None})()

    monkeypatch.setattr(apply_iam.time, 'sleep', lambda s: None)
    apply_iam.switch_role(Lam(), 'AddItem', 'new', True)
    assert Lam.calls == 3
