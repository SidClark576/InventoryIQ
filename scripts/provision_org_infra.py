#!/usr/bin/env python3
"""Create org tables + orgID-index GSIs. Dry-run by default. Pass --apply to write.

  AWS_PROFILE=inventoryiq python3 scripts/provision_org_infra.py
  AWS_PROFILE=inventoryiq python3 scripts/provision_org_infra.py --apply
"""
import argparse
import time
try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    raise SystemExit(
        'boto3 is not installed for this python3.\n'
        'Install: python3 -m venv .venv && .venv/bin/pip install -r scripts/requirements.txt\n'
        'Then: AWS_PROFILE=inventoryiq .venv/bin/python scripts/provision_org_infra.py --apply'
    )

REGION = 'us-east-1'

ORG_TABLES = {
    'Organizations': {
        'KeySchema': [{'AttributeName': 'orgID', 'KeyType': 'HASH'}],
        'AttributeDefinitions': [{'AttributeName': 'orgID', 'AttributeType': 'S'}],
    },
    'OrgMembers': {
        'KeySchema': [
            {'AttributeName': 'orgID', 'KeyType': 'HASH'},
            {'AttributeName': 'userID', 'KeyType': 'RANGE'},
        ],
        'AttributeDefinitions': [
            {'AttributeName': 'orgID', 'AttributeType': 'S'},
            {'AttributeName': 'userID', 'AttributeType': 'S'},
        ],
        'GlobalSecondaryIndexes': [{
            'IndexName': 'userID-index',
            'KeySchema': [{'AttributeName': 'userID', 'KeyType': 'HASH'}],
            'Projection': {'ProjectionType': 'ALL'},
        }],
    },
    'OrgInvites': {
        'KeySchema': [{'AttributeName': 'inviteTokenHash', 'KeyType': 'HASH'}],
        'AttributeDefinitions': [
            {'AttributeName': 'inviteTokenHash', 'AttributeType': 'S'},
            {'AttributeName': 'orgID', 'AttributeType': 'S'},
            {'AttributeName': 'email', 'AttributeType': 'S'},
        ],
        'GlobalSecondaryIndexes': [
            {
                'IndexName': 'orgID-index',
                'KeySchema': [{'AttributeName': 'orgID', 'KeyType': 'HASH'}],
                'Projection': {'ProjectionType': 'ALL'},
            },
            {
                'IndexName': 'email-index',
                'KeySchema': [{'AttributeName': 'email', 'KeyType': 'HASH'}],
                'Projection': {'ProjectionType': 'ALL'},
            },
        ],
    },
}

DATA_GSI_TABLES = ('InventoryIQ', 'InventoryTransactions')


def wait_table_active(client, name, timeout=300):
    client.get_waiter('table_exists').wait(
        TableName=name, WaiterConfig={'Delay': 5, 'MaxAttempts': max(1, timeout // 5)}
    )


def wait_gsi_active(client, table, index_name, timeout=600):
    deadline = time.time() + timeout
    while True:
        desc = client.describe_table(TableName=table)['Table']
        indexes = desc.get('GlobalSecondaryIndexes') or []
        match = next((i for i in indexes if i['IndexName'] == index_name), None)
        if match and match.get('IndexStatus') == 'ACTIVE':
            return
        if time.time() >= deadline:
            status = match.get('IndexStatus') if match else 'MISSING'
            raise TimeoutError(f'{table}.{index_name} not ACTIVE ({status}) after {timeout}s')
        time.sleep(5)


def create_table(client, name, spec, apply):
    print(f'  + table {name}')
    if not apply:
        return
    kwargs = dict(spec)
    kwargs['TableName'] = name
    kwargs['BillingMode'] = 'PAY_PER_REQUEST'
    try:
        client.create_table(**kwargs)
    except ClientError as e:
        if e.response['Error']['Code'] != 'ResourceInUseException':
            raise
        print('    exists')
    wait_table_active(client, name)
    for gsi in spec.get('GlobalSecondaryIndexes') or []:
        wait_gsi_active(client, name, gsi['IndexName'])


def ensure_orgid_gsi(client, table, apply):
    desc = client.describe_table(TableName=table)['Table']
    indexes = [i['IndexName'] for i in desc.get('GlobalSecondaryIndexes') or []]
    if 'orgID-index' in indexes:
        print(f'  = {table} already has orgID-index')
        if apply:
            wait_gsi_active(client, table, 'orgID-index')
        return
    print(f'  + GSI orgID-index on {table}')
    if not apply:
        return
    attrs = {a['AttributeName'] for a in desc.get('AttributeDefinitions', [])}
    attr_updates = []
    if 'orgID' not in attrs:
        attr_updates.append({'AttributeName': 'orgID', 'AttributeType': 'S'})
    create = {
        'IndexName': 'orgID-index',
        'KeySchema': [{'AttributeName': 'orgID', 'KeyType': 'HASH'}],
        'Projection': {'ProjectionType': 'ALL'},
    }
    billing = (desc.get('BillingModeSummary') or {}).get('BillingMode', 'PROVISIONED')
    if billing != 'PAY_PER_REQUEST':
        tp = desc.get('ProvisionedThroughput') or {}
        create['ProvisionedThroughput'] = {
            'ReadCapacityUnits': int(tp.get('ReadCapacityUnits') or 5),
            'WriteCapacityUnits': int(tp.get('WriteCapacityUnits') or 5),
        }
    client.update_table(
        TableName=table,
        AttributeDefinitions=attr_updates or [
            {'AttributeName': 'orgID', 'AttributeType': 'S'}
        ],
        GlobalSecondaryIndexUpdates=[{'Create': create}],
    )
    wait_gsi_active(client, table, 'orgID-index')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    client = boto3.client('dynamodb', region_name=REGION)
    print('DRY-RUN' if not args.apply else 'APPLY')
    for name, spec in ORG_TABLES.items():
        create_table(client, name, spec, args.apply)
    for table in DATA_GSI_TABLES:
        try:
            ensure_orgid_gsi(client, table, args.apply)
        except ClientError as e:
            code = e.response['Error']['Code']
            msg = e.response['Error'].get('Message', '')
            print(f'  ! {table}: {code}: {msg}')
            raise


if __name__ == '__main__':
    main()
