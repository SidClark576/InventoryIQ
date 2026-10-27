"""Shared moto setup: data + org tables (with GSIs), member a@b.co (editor of o1), fresh Lambda imports."""
import importlib
import os
import sys

import boto3
import pytest
from moto import mock_aws

LAMBDA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../lambda'))
HEADERS = {'x-iq-user': 'a@b.co', 'x-iq-org': 'o1'}


def _table(ddb, name, key, range_key=None, gsis=()):
    keys = [key] + ([range_key] if range_key else [])
    kwargs = {}
    if gsis:
        kwargs['GlobalSecondaryIndexes'] = [
            {'IndexName': f'{g}-index', 'KeySchema': [{'AttributeName': g, 'KeyType': 'HASH'}],
             'Projection': {'ProjectionType': 'ALL'}} for g in gsis]
    ddb.create_table(
        TableName=name,
        KeySchema=[{'AttributeName': k, 'KeyType': t} for k, t in zip(keys, ('HASH', 'RANGE'))],
        AttributeDefinitions=[{'AttributeName': a, 'AttributeType': 'S'} for a in dict.fromkeys(keys + list(gsis))],
        BillingMode='PAY_PER_REQUEST', **kwargs)


@pytest.fixture
def ddb(monkeypatch):
    for k, v in {'AWS_DEFAULT_REGION': 'us-east-1', 'AWS_ACCESS_KEY_ID': 'testing',
                 'AWS_SECRET_ACCESS_KEY': 'testing', 'LOG_STDOUT': '0'}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.syspath_prepend(LAMBDA_DIR)
    with mock_aws():
        res = boto3.resource('dynamodb')
        _table(res, 'InventoryIQ', 'itemID', gsis=('userID', 'orgID'))
        _table(res, 'InventoryTransactions', 'transactionID', gsis=('userID', 'orgID'))
        _table(res, 'ImportJobs', 'jobId')
        _table(res, 'OrgMembers', 'orgID', 'userID')
        _table(res, 'OrgInvites', 'inviteTokenHash', gsis=('orgID',))
        res.Table('OrgMembers').put_item(Item={'orgID': 'o1', 'userID': 'a@b.co', 'role': 'editor', 'status': 'active'})
        yield res


@pytest.fixture
def load(ddb):
    def _load(name):
        for mod in ('_logging', '_org', name):
            sys.modules.pop(mod, None)
        return importlib.import_module(name)
    return _load
