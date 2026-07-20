"""Shared org/membership/RBAC helpers. Imported by Proxy + org Lambdas + data handlers.

Tenant model: orgID is the data boundary; userID (email) is the actor.
Role authz is looked up live (never trusted from client/JWT) so removal is instant.
"""
import os
import boto3
from boto3.dynamodb.conditions import Key

ORGS_TABLE    = os.environ.get('ORGS_TABLE',    'Organizations')
MEMBERS_TABLE = os.environ.get('MEMBERS_TABLE', 'OrgMembers')
INVITES_TABLE = os.environ.get('INVITES_TABLE', 'OrgInvites')

SEAT_CAP = int(os.environ.get('ORG_SEAT_CAP', '5'))

# Higher number = more privilege. Role check is `rank(have) >= rank(need)`.
ROLE_RANK = {'viewer': 1, 'editor': 2, 'admin': 3, 'owner': 4}

_ddb = boto3.resource('dynamodb')
_orgs    = _ddb.Table(ORGS_TABLE)
_members = _ddb.Table(MEMBERS_TABLE)
_invites = _ddb.Table(INVITES_TABLE)


def normalize_email(email):
    return (email or '').strip().lower()


def header(headers, name):
    """Case-insensitive header read (API Gateway lowercases; clients may not)."""
    headers = headers or {}
    return (headers.get(name) or headers.get(name.title()) or
            headers.get(name.upper()) or '').strip()


def get_membership(org_id, user_id):
    """Active membership item or None. Single GetItem — the instant-revoke read."""
    if not org_id or not user_id:
        return None
    item = _members.get_item(Key={'orgID': org_id, 'userID': user_id}).get('Item')
    if not item or item.get('status') != 'active':
        return None
    return item


def has_role(role, minimum):
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(minimum, 99)


def list_user_orgs(user_id):
    """Orgs the user is an active member of (for the switcher). Uses userID-index GSI."""
    res = _members.query(IndexName='userID-index',
                         KeyConditionExpression=Key('userID').eq(user_id))
    rows = [m for m in res.get('Items', []) if m.get('status') == 'active']
    out = []
    for m in rows:
        org = _orgs.get_item(Key={'orgID': m['orgID']}).get('Item')
        if org and not org.get('deletedAt'):
            out.append({'orgID': org['orgID'], 'name': org.get('name', ''),
                        'role': m.get('role'), 'memberCount': int(org.get('memberCount', 1))})
    return out
