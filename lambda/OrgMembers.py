"""Member listing, role changes, removal.

Routes (behind Proxy, which injects x-iq-user):
  GET    /orgs/{id}/members            -> list members + pending invites (admin+)
  PATCH  /orgs/{id}/members/{userID}   -> change role (admin+; owner boundaries owner-only)
  DELETE /orgs/{id}/members/{userID}   -> remove member (admin+; never the owner)
"""
import json
import time as _time
from datetime import datetime, timezone
import boto3
from boto3.dynamodb.conditions import Key
import _logging
import _org

FUNCTION_NAME = 'OrgMembers'
response = _logging.response

_ASSIGNABLE = ('viewer', 'editor', 'admin')  # owner is set only via transfer-owner
_client = boto3.client('dynamodb')


def lambda_handler(event, context):
    t0 = _time.time()
    res = _handle(event)
    _logging.log_json(event=event, function=FUNCTION_NAME,
                      latency_ms=(_time.time() - t0) * 1000,
                      status=res.get('statusCode'),
                      is_error=res.get('statusCode', 200) >= 500)
    return res


def _handle(event):
    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return response(200, {})

    headers = event.get('headers') or {}
    actor = _org.normalize_email(_org.header(headers, 'x-iq-user'))
    pp = event.get('pathParameters') or {}
    org_id = pp.get('id') or pp.get('orgID')
    target = _org.normalize_email(pp.get('userID'))

    if not actor or not org_id:
        return response(400, {'error': 'Missing actor or org id'})

    membership = _org.get_membership(org_id, actor)
    if not membership:
        return response(403, {'error': 'Not a member of this organization'})
    actor_role = membership.get('role')
    if not _org.has_role(actor_role, 'admin'):
        return response(403, {'error': 'Requires admin or owner'})

    try:
        if method == 'GET':
            return _list(org_id)
        if method == 'PATCH' and target:
            return _change_role(event, org_id, actor, actor_role, target)
        if method == 'DELETE' and target:
            return _remove(org_id, actor_role, target)
        return response(400, {'error': 'Unsupported operation'})
    except Exception as e:
        _logging.capture_error(e, function=FUNCTION_NAME)
        return response(500, {'error': 'Internal Server Error'})


def _list(org_id):
    members = _org._members.query(KeyConditionExpression=Key('orgID').eq(org_id)).get('Items', [])
    invites = _org._invites.query(IndexName='orgID-index',
                                  KeyConditionExpression=Key('orgID').eq(org_id)).get('Items', [])
    pending = [{'email': i.get('email'), 'role': i.get('role'),
                'status': i.get('status'), 'expiresAt': i.get('expiresAt')}
               for i in invites if i.get('status') == 'pending']
    return response(200, {
        'members': [{'userID': m['userID'], 'role': m.get('role'),
                     'status': m.get('status'), 'joinedAt': m.get('joinedAt')} for m in members],
        'pendingInvites': pending})


def _change_role(event, org_id, actor, actor_role, target):
    new_role = (json.loads(event.get('body') or '{}').get('role') or '').strip().lower()
    if new_role not in _ASSIGNABLE:
        return response(400, {'error': f'role must be one of {_ASSIGNABLE}'})
    tm = _org.get_membership(org_id, target)
    if not tm:
        return response(404, {'error': 'Member not found'})
    if tm.get('role') == 'owner':
        return response(403, {'error': 'Cannot change the owner role; use transfer-owner'})
    # Granting or revoking admin is an owner-only boundary.
    if (new_role == 'admin' or tm.get('role') == 'admin') and actor_role != 'owner':
        return response(403, {'error': 'Only the owner can grant or revoke admin'})
    _org._members.update_item(
        Key={'orgID': org_id, 'userID': target},
        UpdateExpression='SET #r = :r, updatedAt = :u',
        ExpressionAttributeNames={'#r': 'role'},
        ExpressionAttributeValues={':r': new_role, ':u': datetime.now(timezone.utc).isoformat()})
    return response(200, {'userID': target, 'role': new_role})


def _remove(org_id, actor_role, target):
    tm = _org.get_membership(org_id, target)
    if not tm:
        return response(404, {'error': 'Member not found'})
    if tm.get('role') == 'owner':
        return response(403, {'error': 'Cannot remove the owner'})
    if tm.get('role') == 'admin' and actor_role != 'owner':
        return response(403, {'error': 'Only the owner can remove an admin'})
    # Atomic: delete membership + free one seat + drop member count.
    try:
        _client.transact_write_items(TransactItems=[
            {'Delete': {
                'TableName': _org.MEMBERS_TABLE,
                'Key': {'orgID': {'S': org_id}, 'userID': {'S': target}},
                'ConditionExpression': 'attribute_exists(userID)'}},
            {'Update': {
                'TableName': _org.ORGS_TABLE,
                'Key': {'orgID': {'S': org_id}},
                'UpdateExpression': 'ADD memberCount :neg, seatCount :neg',
                'ExpressionAttributeValues': {':neg': {'N': '-1'}}}},
        ])
    except _client.exceptions.TransactionCanceledException:
        return response(409, {'error': 'Member already removed'})
    return response(200, {'message': 'Member removed', 'userID': target})
