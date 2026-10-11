"""Shared org/membership/RBAC helpers. Imported by Proxy + org Lambdas + data handlers.

Tenant model: orgID is the data boundary; userID (email) is the actor.
Role authz is looked up live (never trusted from client/JWT) so removal is instant.
"""
import os
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
import _logging

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
    try:
        item = _members.get_item(Key={'orgID': org_id, 'userID': user_id}).get('Item')
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return None
        raise
    if not item or item.get('status') != 'active':
        return None
    return item


def has_role(role, minimum):
    return ROLE_RANK.get(role, 0) >= ROLE_RANK.get(minimum, 99)


def require_member(headers, minimum=None):
    """Validate proxy-injected identity. Returns (ctx, error_response).

    ctx keys: user_id, org_id, role, legacy.
    `legacy=True` when org tables are not provisioned or no workspace is selected
    — handlers must fall back to userID-scoped reads so current prod keeps working.
    """
    user_id = normalize_email(header(headers, 'x-iq-user'))
    org_id = header(headers, 'x-iq-org')
    if not user_id:
        return None, _logging.response(401, {'error': 'Unauthorized'})

    membership = None
    try:
        if org_id:
            membership = get_membership(org_id, user_id)
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            return {'user_id': user_id, 'org_id': org_id, 'role': 'owner', 'legacy': True}, None
        raise

    if org_id and not membership:
        return None, _logging.response(403, {'error': 'Not a member of this organization'})

    if not org_id:
        return {'user_id': user_id, 'org_id': '', 'role': 'owner', 'legacy': True}, None

    role = membership.get('role')
    if minimum and not has_role(role, minimum):
        return None, _logging.response(403, {'error': f'Requires {minimum} role'})
    return {'user_id': user_id, 'org_id': org_id, 'role': role, 'legacy': False}, None


def item_in_scope(item, org_id, user_id):
    """Org-scoped when orgID is stamped; otherwise only the creating user."""
    if not item:
        return False
    if item.get('orgID'):
        return bool(org_id) and item['orgID'] == org_id
    return bool(user_id) and item.get('userID') == user_id


def query_gsi(table, index, key_name, key_value, filter_expr=None):
    kwargs = {
        'IndexName': index,
        'KeyConditionExpression': Key(key_name).eq(key_value),
    }
    if filter_expr is not None:
        kwargs['FilterExpression'] = filter_expr
    result = table.query(**kwargs)
    items = result.get('Items', [])
    while 'LastEvaluatedKey' in result:
        kwargs['ExclusiveStartKey'] = result['LastEvaluatedKey']
        result = table.query(**kwargs)
        items.extend(result.get('Items', []))
    return items


def list_scoped_items(table, org_id, user_id, filter_expr=None):
    """Prefer orgID-index; fall back to userID-index (legacy / missing GSI)."""
    if org_id:
        try:
            return query_gsi(table, 'orgID-index', 'orgID', org_id, filter_expr)
        except ClientError:
            pass
    if not user_id:
        return []
    return query_gsi(table, 'userID-index', 'userID', user_id, filter_expr)


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
