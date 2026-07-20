#!/usr/bin/env python3
"""One-shot backfill: give every existing user a personal org and stamp orgID on their data.

SAFE BY DEFAULT: dry-run prints what it would do and writes nothing.
Pass --apply to actually write. Idempotent — re-running skips users/items already migrated.

  python scripts/migrate_orgs.py                 # dry-run report
  python scripts/migrate_orgs.py --apply         # perform migration
  python scripts/migrate_orgs.py --selftest      # offline logic check, no AWS

Prereqs (NOT created here — create first): tables Organizations, OrgMembers
(+ GSI userID-index), OrgInvites (+ GSIs orgID-index, email-index), and an
orgID-index GSI on InventoryIQ / InventoryTransactions / Suppliers.
"""
import argparse
import uuid
from datetime import datetime, timezone

USERS_TABLE   = 'Users'
ORGS_TABLE    = 'Organizations'
MEMBERS_TABLE = 'OrgMembers'
# (table, partition-key attr) for data that gets stamped with orgID
DATA_TABLES = [('InventoryIQ', 'itemID'), ('InventoryTransactions', 'transactionID'), ('Suppliers', 'supplierID')]


def normalize_email(email):
    return (email or '').strip().lower()


def needs_orgid(item):
    """An item should be stamped only if it has a userID and no orgID yet."""
    return bool(item.get('userID')) and not item.get('orgID')


def org_for_user(email, mapping):
    return mapping.get(normalize_email(email))


# ── AWS path ────────────────────────────────────────────────────────────────

def _scan(table):
    items, kwargs = [], {}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get('Items', []))
        if 'LastEvaluatedKey' not in resp:
            return items
        kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']


def run(apply):
    import boto3
    from boto3.dynamodb.conditions import Key
    ddb = boto3.resource('dynamodb')
    users   = ddb.Table(USERS_TABLE)
    orgs    = ddb.Table(ORGS_TABLE)
    members = ddb.Table(MEMBERS_TABLE)

    now = datetime.now(timezone.utc).isoformat()
    mapping = {}      # email -> orgID
    created_orgs = 0

    # 1. Personal org + owner membership per user (skip if already an owner somewhere)
    for u in _scan(users):
        email = normalize_email(u.get('Email'))
        if not email:
            continue
        existing = members.query(IndexName='userID-index',
                                 KeyConditionExpression=Key('userID').eq(email)).get('Items', [])
        owner_row = next((m for m in existing if m.get('role') == 'owner'), None)
        if owner_row:
            mapping[email] = owner_row['orgID']
            continue
        org_id = str(uuid.uuid4())
        mapping[email] = org_id
        created_orgs += 1
        print(f"  + org {org_id} owner={email}")
        if apply:
            orgs.put_item(Item={'orgID': org_id, 'name': 'My Inventory', 'ownerUserID': email,
                                'memberCount': 1, 'seatCount': 1, 'createdAt': now, 'updatedAt': now})
            members.put_item(Item={'orgID': org_id, 'userID': email, 'role': 'owner',
                                   'status': 'active', 'joinedAt': now})

    # 2. Stamp orgID on each user's data
    stamped, orphans = 0, 0
    for tname, pk in DATA_TABLES:
        table = ddb.Table(tname)
        for item in _scan(table):
            if not needs_orgid(item):
                continue
            org_id = org_for_user(item.get('userID'), mapping)
            if not org_id:
                orphans += 1
                print(f"  ! {tname}:{item.get(pk)} userID={item.get('userID')} has no org (orphan)")
                continue
            stamped += 1
            if apply:
                table.update_item(Key={pk: item[pk]},
                                  UpdateExpression='SET orgID = :o',
                                  ExpressionAttributeValues={':o': org_id})

    mode = 'APPLIED' if apply else 'DRY-RUN (no writes)'
    print(f"\n{mode}: {created_orgs} orgs to create, {stamped} items to stamp, {orphans} orphans.")
    if orphans:
        print("Resolve orphans before relying on org-scoped reads — those items would be invisible.")


# ── Offline self-check ──────────────────────────────────────────────────────

def _selftest():
    assert normalize_email('  Foo@Bar.COM ') == 'foo@bar.com'
    assert normalize_email(None) == ''
    assert needs_orgid({'userID': 'a@b.com'}) is True
    assert needs_orgid({'userID': 'a@b.com', 'orgID': 'x'}) is False
    assert needs_orgid({'orgID': 'x'}) is False          # no userID -> skip
    m = {'a@b.com': 'org-1'}
    assert org_for_user('A@B.com', m) == 'org-1'
    assert org_for_user('none@x.com', m) is None
    print('selftest OK')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='perform writes (default: dry-run)')
    ap.add_argument('--selftest', action='store_true', help='run offline logic check, no AWS')
    args = ap.parse_args()
    if args.selftest:
        _selftest()
    else:
        run(args.apply)
