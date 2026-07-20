"""Org CRUD + switch + ownership transfer.

Routes (behind Proxy, which injects x-iq-user):
  GET    /orgs                       -> list current user's orgs (switcher)
  POST   /orgs/{id}/switch           -> validate the user may select this org
  PATCH  /orgs/{id}                  -> rename (owner only)
  POST   /orgs/{id}/transfer-owner   -> transfer ownership (owner only)
  DELETE /orgs/{id}                  -> delete a solo org (owner only)
"""
import json
import time as _time
from datetime import datetime, timezone
import boto3
import _logging
import _org

FUNCTION_NAME = 'Orgs'
response = _logging.response

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
    user_id = _org.normalize_email(_org.header(headers, 'x-iq-user'))
    if not user_id:
        return response(401, {'error': 'Unauthorized'})

    path = (event.get('path') or event.get('resource') or '')
    pp = event.get('pathParameters') or {}
    org_id = pp.get('id') or pp.get('orgID')

    try:
        if method == 'GET' and not org_id:
            return response(200, {'orgs': _org.list_user_orgs(user_id)})

        if not org_id:
            return response(400, {'error': 'Missing org id'})

        membership = _org.get_membership(org_id, user_id)
        if not membership:
            return response(403, {'error': 'Not a member of this organization'})
        role = membership.get('role')

        if path.endswith('/switch'):
            org = _org._orgs.get_item(Key={'orgID': org_id}).get('Item')
            if not org or org.get('deletedAt'):
                return response(404, {'error': 'Organization not found'})
            return response(200, {'orgID': org_id, 'role': role, 'name': org.get('name', '')})

        if path.endswith('/transfer-owner'):
            return _transfer(event, org_id, user_id, role)

        if method == 'PATCH':
            return _rename(event, org_id, role)

        if method == 'DELETE':
            return _delete(org_id, role)

        return response(400, {'error': 'Unsupported operation'})
    except Exception as e:
        _logging.capture_error(e, function=FUNCTION_NAME)
        return response(500, {'error': 'Internal Server Error'})


def _rename(event, org_id, role):
    if role != 'owner':
        return response(403, {'error': 'Only the owner can rename the organization'})
    name = (json.loads(event.get('body') or '{}').get('name') or '').strip()
    if not name:
        return response(400, {'error': 'name is required'})
    _org._orgs.update_item(
        Key={'orgID': org_id},
        UpdateExpression='SET #n = :n, updatedAt = :u',
        ExpressionAttributeNames={'#n': 'name'},
        ExpressionAttributeValues={':n': name, ':u': datetime.now(timezone.utc).isoformat()})
    return response(200, {'orgID': org_id, 'name': name})


def _delete(org_id, role):
    if role != 'owner':
        return response(403, {'error': 'Only the owner can delete the organization'})
    org = _org._orgs.get_item(Key={'orgID': org_id}).get('Item')
    if not org:
        return response(404, {'error': 'Organization not found'})
    if int(org.get('memberCount', 1)) > 1 or int(org.get('seatCount', 1)) > 1:
        return response(409, {'error': 'Remove other members and pending invites before deleting'})
    _org._orgs.update_item(
        Key={'orgID': org_id},
        UpdateExpression='SET deletedAt = :d',
        ExpressionAttributeValues={':d': datetime.now(timezone.utc).isoformat()})
    _org._members.delete_item(Key={'orgID': org_id, 'userID': org['ownerUserID']})
    return response(200, {'message': 'Organization deleted'})


def _transfer(event, org_id, user_id, role):
    if role != 'owner':
        return response(403, {'error': 'Only the owner can transfer ownership'})
    target = _org.normalize_email(json.loads(event.get('body') or '{}').get('userID'))
    if not target or target == user_id:
        return response(400, {'error': 'Provide a different member to transfer to'})
    if not _org.get_membership(org_id, target):
        return response(400, {'error': 'Target must be an active member'})
    # Atomic: promote target -> owner, demote current owner -> admin, point org at new owner.
    try:
        _client.transact_write_items(TransactItems=[
            {'Update': {
                'TableName': _org.MEMBERS_TABLE,
                'Key': {'orgID': {'S': org_id}, 'userID': {'S': target}},
                'UpdateExpression': 'SET #r = :owner',
                'ExpressionAttributeNames': {'#r': 'role'},
                'ExpressionAttributeValues': {':owner': {'S': 'owner'}},
                'ConditionExpression': 'attribute_exists(userID)'}},
            {'Update': {
                'TableName': _org.MEMBERS_TABLE,
                'Key': {'orgID': {'S': org_id}, 'userID': {'S': user_id}},
                'UpdateExpression': 'SET #r = :admin',
                'ExpressionAttributeNames': {'#r': 'role'},
                'ExpressionAttributeValues': {':admin': {'S': 'admin'}}}},
            {'Update': {
                'TableName': _org.ORGS_TABLE,
                'Key': {'orgID': {'S': org_id}},
                'UpdateExpression': 'SET ownerUserID = :o',
                'ExpressionAttributeValues': {':o': {'S': target}}}},
        ])
    except _client.exceptions.TransactionCanceledException:
        return response(409, {'error': 'Transfer failed — member state changed, retry'})
    return response(200, {'message': 'Ownership transferred', 'newOwner': target})
