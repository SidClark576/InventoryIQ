"""Org CRUD + switch + ownership transfer.

Routes (behind Proxy, which injects x-iq-user):
  GET    /orgs                       -> list current user's orgs (switcher)
  POST   /orgs/{id}/switch           -> validate the user may select this org
  PUT    /orgs/{id}                  -> update store fields (owner only; PATCH too, but CORS has no PATCH)
  POST   /orgs/{id}/transfer-owner   -> transfer ownership (owner only)
  DELETE /orgs/{id}                  -> delete a solo org (owner only)
"""
import json
import re
import time as _time
from datetime import datetime, timezone
import boto3
import _logging
import _org

FUNCTION_NAME = 'Orgs'
response = _logging.response
STORE_FIELDS = ('name', 'storeType', 'country', 'currency', 'onboardedAt')
STORE_TYPES = {'sari-sari', 'grocery', 'pharmacy', 'hardware', 'other'}

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
            return response(200, {'orgID': org_id, 'role': role, 'name': org.get('name', ''),
                                  **{k: org[k] for k in STORE_FIELDS[1:] if org.get(k)}})

        if path.endswith('/transfer-owner'):
            return _transfer(event, org_id, user_id, role)

        if method in ('PUT', 'PATCH'):
            return _update(event, org_id, role)

        if method == 'DELETE':
            return _delete(org_id, role)

        return response(400, {'error': 'Unsupported operation'})
    except Exception as e:
        _logging.capture_error(e, function=FUNCTION_NAME)
        return response(500, {'error': 'Internal Server Error'})


def _store_body(event):
    """Validated {name, storeType?, country?, currency?}: (fields, None) or (None, 400 response)."""
    body, err = _logging.json_body(event)
    if err:
        return None, err
    fields = {k: str(body[k]).strip() for k in STORE_FIELDS[:4] if body.get(k) is not None}
    name, store_type = fields.get('name', ''), fields.get('storeType')
    if not name or len(name) > 80:
        return None, response(400, {'error': 'name is required (80 characters max)'})
    if store_type is not None and store_type not in STORE_TYPES:
        return None, response(400, {'error': 'storeType is not valid'})
    if not re.fullmatch(r'[A-Z]{2}', fields.get('country', 'PH')):
        return None, response(400, {'error': 'country must be a 2-letter code'})
    if not re.fullmatch(r'[A-Z]{3}', fields.get('currency', 'PHP')):
        return None, response(400, {'error': 'currency must be a 3-letter code'})
    return fields, None


def _update(event, org_id, role):
    if role != 'owner':
        return response(403, {'error': 'Only the owner can change the store details'})
    fields, err = _store_body(event)
    if err:
        return err
    names = {f'#{k}': k for k in fields}
    values = {f':{k}': v for k, v in fields.items()}
    values.update({':u': datetime.now(timezone.utc).isoformat()})
    sets = [f'#{k} = :{k}' for k in fields] + ['updatedAt = :u', 'onboardedAt = if_not_exists(onboardedAt, :u)']
    try:
        org = _org._orgs.update_item(
            Key={'orgID': org_id}, UpdateExpression='SET ' + ', '.join(sets),
            ExpressionAttributeNames=names, ExpressionAttributeValues=values,
            ConditionExpression='attribute_exists(orgID) AND attribute_not_exists(deletedAt)',
            ReturnValues='ALL_NEW')['Attributes']
    except _org._orgs.meta.client.exceptions.ConditionalCheckFailedException:
        return response(404, {'error': 'Organization not found'})
    return response(200, {'orgID': org_id, **{k: org[k] for k in STORE_FIELDS if org.get(k)}})


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
