"""Invite lifecycle: create, revoke, accept.

Routes (behind Proxy, which injects x-iq-user):
  POST /orgs/{id}/invites                  -> create invite (admin+)
  POST /orgs/{id}/invites/{inviteID}/revoke-> revoke pending invite (admin+)
  POST /org-invites/{token}/accept         -> accept (invited email, must be logged in)

Tokens: opaque random; only the SHA-256 hash is stored (PK). 72h TTL, single-use.
Seat cap is enforced atomically via Organizations.seatCount (active members + pending invites).
"""
import json
import os
import time as _time
import hashlib
import secrets
from datetime import datetime, timezone
import boto3
from boto3.dynamodb.conditions import Key
import _logging
import _org

FUNCTION_NAME = 'OrgInvites'
response = _logging.response

INVITE_TTL_SECONDS = 72 * 60 * 60
_ASSIGNABLE = ('viewer', 'editor', 'admin')

SES_SENDER = os.environ.get('SES_SENDER', '')
APP_URL    = os.environ.get('APP_URL', '')

_client = boto3.client('dynamodb')
_ses    = boto3.client('ses')


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def lambda_handler(event, context):
    t0 = _time.time()
    res = _handle(event)
    _logging.log_json(event=event, function=FUNCTION_NAME,
                      latency_ms=(_time.time() - t0) * 1000,
                      status=res.get('statusCode'),
                      is_error=res.get('statusCode', 200) >= 500)
    return res


def _handle(event):
    method = event.get('httpMethod', 'POST')
    if method == 'OPTIONS':
        return response(200, {})

    headers = event.get('headers') or {}
    actor = _org.normalize_email(_org.header(headers, 'x-iq-user'))
    if not actor:
        return response(401, {'error': 'Unauthorized'})

    path = (event.get('path') or event.get('resource') or '')
    pp = event.get('pathParameters') or {}

    try:
        if path.endswith('/accept'):
            return _accept(pp.get('token'), actor)
        if path.endswith('/revoke'):
            return _revoke(pp.get('id') or pp.get('orgID'), pp.get('inviteID'), actor)
        return _create(event, pp.get('id') or pp.get('orgID'), actor)
    except Exception as e:
        _logging.capture_error(e, function=FUNCTION_NAME)
        return response(500, {'error': 'Internal Server Error'})


def _require_admin(org_id, actor):
    m = _org.get_membership(org_id, actor)
    if not m:
        return None, response(403, {'error': 'Not a member of this organization'})
    if not _org.has_role(m.get('role'), 'admin'):
        return None, response(403, {'error': 'Requires admin or owner'})
    return m, None


def _create(event, org_id, actor):
    if not org_id:
        return response(400, {'error': 'Missing org id'})
    m, err = _require_admin(org_id, actor)
    if err:
        return err

    body = json.loads(event.get('body') or '{}')
    email = _org.normalize_email(body.get('email'))
    role = (body.get('role') or 'viewer').strip().lower()
    if not email:
        return response(400, {'error': 'email is required'})
    if role not in _ASSIGNABLE:
        return response(400, {'error': f'role must be one of {_ASSIGNABLE}'})
    if email == actor:
        return response(400, {'error': 'You cannot invite yourself'})
    if _org.get_membership(org_id, email):
        return response(409, {'error': 'That person is already a member'})

    # Block duplicate pending invite for the same email + org.
    existing = _org._invites.query(IndexName='email-index',
                                   KeyConditionExpression=Key('email').eq(email)).get('Items', [])
    if any(i.get('orgID') == org_id and i.get('status') == 'pending' for i in existing):
        return response(409, {'error': 'An invite is already pending for that email'})

    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    invite = {
        'inviteTokenHash': {'S': _hash(token)},
        'inviteID':        {'S': secrets.token_hex(8)},
        'orgID':           {'S': org_id},
        'email':           {'S': email},
        'role':            {'S': role},
        'status':          {'S': 'pending'},
        'invitedBy':       {'S': actor},
        'createdAt':       {'S': now.isoformat()},
        'expiresAt':       {'N': str(int(now.timestamp()) + INVITE_TTL_SECONDS)},
    }
    # Atomic seat cap: claim a seat only if under the cap.
    try:
        _client.transact_write_items(TransactItems=[
            {'Put': {'TableName': _org.INVITES_TABLE, 'Item': invite,
                     'ConditionExpression': 'attribute_not_exists(inviteTokenHash)'}},
            {'Update': {
                'TableName': _org.ORGS_TABLE,
                'Key': {'orgID': {'S': org_id}},
                'UpdateExpression': 'ADD seatCount :one',
                'ConditionExpression': 'seatCount < :cap',
                'ExpressionAttributeValues': {':one': {'N': '1'}, ':cap': {'N': str(_org.SEAT_CAP)}}}},
        ])
    except _client.exceptions.TransactionCanceledException:
        return response(409, {'error': f'Organization is at its {_org.SEAT_CAP}-member limit'})

    _send_invite_email(email, token, org_id)
    return response(201, {'message': 'Invite sent', 'email': email, 'role': role,
                          'inviteID': invite['inviteID']['S']})


def _revoke(org_id, invite_id, actor):
    if not org_id or not invite_id:
        return response(400, {'error': 'Missing org or invite id'})
    m, err = _require_admin(org_id, actor)
    if err:
        return err
    # Find the pending invite by inviteID within the org.
    invites = _org._invites.query(IndexName='orgID-index',
                                  KeyConditionExpression=Key('orgID').eq(org_id)).get('Items', [])
    match = next((i for i in invites if i.get('inviteID') == invite_id and i.get('status') == 'pending'), None)
    if not match:
        return response(404, {'error': 'Pending invite not found'})
    try:
        _client.transact_write_items(TransactItems=[
            {'Update': {
                'TableName': _org.INVITES_TABLE,
                'Key': {'inviteTokenHash': {'S': match['inviteTokenHash']}},
                'UpdateExpression': 'SET #s = :revoked',
                'ConditionExpression': '#s = :pending',
                'ExpressionAttributeNames': {'#s': 'status'},
                'ExpressionAttributeValues': {':revoked': {'S': 'revoked'}, ':pending': {'S': 'pending'}}}},
            {'Update': {
                'TableName': _org.ORGS_TABLE,
                'Key': {'orgID': {'S': org_id}},
                'UpdateExpression': 'ADD seatCount :neg',
                'ExpressionAttributeValues': {':neg': {'N': '-1'}}}},
        ])
    except _client.exceptions.TransactionCanceledException:
        return response(409, {'error': 'Invite already accepted or revoked'})
    return response(200, {'message': 'Invite revoked'})


def _accept(token, actor):
    if not token:
        return response(400, {'error': 'Missing token'})
    invite = _org._invites.get_item(Key={'inviteTokenHash': _hash(token)}).get('Item')
    if not invite or invite.get('status') != 'pending':
        return response(400, {'error': 'Invalid or already-used invite'})
    if int(invite.get('expiresAt', 0)) < int(datetime.now(timezone.utc).timestamp()):
        return response(400, {'error': 'Invite has expired'})
    if _org.normalize_email(invite.get('email')) != actor:
        return response(403, {'error': 'This invite was sent to a different email'})

    org_id = invite['orgID']
    now = datetime.now(timezone.utc).isoformat()
    # Single-use: flip invite pending->accepted and add the member atomically.
    # Seat was already counted at invite time, so memberCount += 1 only.
    try:
        _client.transact_write_items(TransactItems=[
            {'Update': {
                'TableName': _org.INVITES_TABLE,
                'Key': {'inviteTokenHash': {'S': _hash(token)}},
                'UpdateExpression': 'SET #s = :accepted',
                'ConditionExpression': '#s = :pending',
                'ExpressionAttributeNames': {'#s': 'status'},
                'ExpressionAttributeValues': {':accepted': {'S': 'accepted'}, ':pending': {'S': 'pending'}}}},
            {'Put': {
                'TableName': _org.MEMBERS_TABLE,
                'Item': {'orgID': {'S': org_id}, 'userID': {'S': actor},
                         'role': {'S': invite['role']}, 'status': {'S': 'active'},
                         'joinedAt': {'S': now}},
                'ConditionExpression': 'attribute_not_exists(userID)'}},
            {'Update': {
                'TableName': _org.ORGS_TABLE,
                'Key': {'orgID': {'S': org_id}},
                'UpdateExpression': 'ADD memberCount :one',
                'ExpressionAttributeValues': {':one': {'N': '1'}}}},
        ])
    except _client.exceptions.TransactionCanceledException:
        return response(409, {'error': 'Invite already used or you are already a member'})
    return response(200, {'message': 'Joined organization', 'orgID': org_id, 'role': invite['role']})


def _send_invite_email(email, token, org_id):
    # ponytail: best-effort send; invite row already persisted. No APP_URL/SES -> skip silently.
    if not (SES_SENDER and APP_URL):
        return
    link = f"{APP_URL.rstrip('/')}/accept.html?token={token}"
    try:
        _ses.send_email(
            Source=SES_SENDER,
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': 'You have been invited to InventoryIQ'},
                'Body': {'Text': {'Data':
                    'You have been invited to a shared inventory on InventoryIQ.\n\n'
                    f'Accept (valid 72h): {link}\n\n'
                    'If you did not expect this, ignore this email.'}}})
    except Exception as e:
        _logging.capture_error(e, function=FUNCTION_NAME, stage='invite_email')
