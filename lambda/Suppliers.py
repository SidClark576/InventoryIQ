import json
import os
import uuid
import time
import boto3
from boto3.dynamodb.conditions import Key
import _logging
import re

FUNCTION_NAME = 'Suppliers'

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('SUPPLIERS_TABLE', 'Suppliers'))

CORS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
    'Access-Control-Allow-Methods': 'OPTIONS,GET,POST,PUT,DELETE'
}

def lambda_handler(event, context):
    t0 = time.time()
    res = _handle(event)
    _logging.log_json(
        event=event,
        function=FUNCTION_NAME,
        latency_ms=(time.time() - t0) * 1000,
        status=res.get('statusCode'),
        is_error=res.get('statusCode', 200) >= 500,
    )
    return res

def _handle(event):
    method = event.get('httpMethod', 'GET')
    
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}
        
    headers = event.get('headers') or {}
    user_id = (headers.get('x-iq-user') or headers.get('X-Iq-User') or '').strip()
    
    if not user_id:
        return {'statusCode': 401, 'headers': CORS, 'body': json.dumps({'error': 'Unauthorized: userID required'})}
        
    path_params = event.get('pathParameters') or {}
    supplier_id = path_params.get('id')
    
    if method == 'GET':
        return get_suppliers(user_id)
    elif method == 'POST':
        return create_supplier(event, user_id)
    elif method == 'PUT' and supplier_id:
        return update_supplier(event, supplier_id, user_id)
    elif method == 'DELETE' and supplier_id:
        return delete_supplier(supplier_id, user_id)
        
    return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'Unsupported method or missing ID'})}

def get_suppliers(user_id):
    try:
        res = table.query(
            IndexName='userID-index',
            KeyConditionExpression=Key('userID').eq(user_id)
        )
        items = res.get('Items', [])
        while 'LastEvaluatedKey' in res:
            res = table.query(
                IndexName='userID-index',
                KeyConditionExpression=Key('userID').eq(user_id),
                ExclusiveStartKey=res['LastEvaluatedKey']
            )
            items.extend(res.get('Items', []))
            
        items.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
        return {'statusCode': 200, 'headers': CORS, 'body': json.dumps(items)}
    except Exception as e:
        _logging.log_json(function="Suppliers_get", error=str(e))
        return {'statusCode': 500, 'headers': CORS, 'body': json.dumps({'error': 'An internal error occurred'})}

def create_supplier(event, user_id):
    try:
        body = json.loads(event.get('body') or '{}')
        name = body.get('name', '').strip()
        if not name:
            return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'Supplier name is required'})}
            
        contact_email = body.get('contactEmail', '').strip()
        if contact_email and not re.match(r"^[^@]+@[^@]+\.[^@]+$", contact_email):
            return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'Invalid email format'})}

        supplier = {
            'supplierID': str(uuid.uuid4()),
            'userID': user_id,
            'name': name,
            'contactEmail': contact_email,
            'phone': body.get('phone', '').strip(),
            'notes': body.get('notes', '').strip(),
            'createdAt': datetime.utcnow().isoformat() + 'Z' if 'datetime' in globals() else time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }
        
        table.put_item(Item=supplier)
        return {'statusCode': 201, 'headers': CORS, 'body': json.dumps(supplier)}
    except Exception as e:
        _logging.log_json(function="Suppliers_create", error=str(e))
        return {'statusCode': 500, 'headers': CORS, 'body': json.dumps({'error': 'An internal error occurred'})}

def update_supplier(event, supplier_id, user_id):
    try:
        body = json.loads(event.get('body') or '{}')
        
        # Verify ownership
        resp = table.get_item(Key={'supplierID': supplier_id})
        if 'Item' not in resp or resp['Item'].get('userID') != user_id:
            return {'statusCode': 404, 'headers': CORS, 'body': json.dumps({'error': 'Supplier not found'})}
            
        update_expr = "SET #nm = :name, contactEmail = :email, phone = :phone, notes = :notes"
        contact_email = body.get('contactEmail', resp['Item'].get('contactEmail', '')).strip()
        if contact_email and not re.match(r"^[^@]+@[^@]+\.[^@]+$", contact_email):
            return {'statusCode': 400, 'headers': CORS, 'body': json.dumps({'error': 'Invalid email format'})}

        expr_vals = {
            ':name': body.get('name', resp['Item'].get('name')).strip(),
            ':email': contact_email,
            ':phone': body.get('phone', resp['Item'].get('phone', '')).strip(),
            ':notes': body.get('notes', resp['Item'].get('notes', '')).strip()
        }
        expr_names = {'#nm': 'name'}
        
        updated = table.update_item(
            Key={'supplierID': supplier_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_vals,
            ExpressionAttributeNames=expr_names,
            ReturnValues="ALL_NEW"
        )
        return {'statusCode': 200, 'headers': CORS, 'body': json.dumps(updated.get('Attributes', {}))}
    except Exception as e:
        _logging.log_json(function="Suppliers_update", error=str(e))
        return {'statusCode': 500, 'headers': CORS, 'body': json.dumps({'error': 'An internal error occurred'})}

def delete_supplier(supplier_id, user_id):
    try:
        # Verify ownership
        resp = table.get_item(Key={'supplierID': supplier_id})
        if 'Item' not in resp or resp['Item'].get('userID') != user_id:
            return {'statusCode': 404, 'headers': CORS, 'body': json.dumps({'error': 'Supplier not found'})}
            
        table.delete_item(Key={'supplierID': supplier_id})
        return {'statusCode': 204, 'headers': CORS, 'body': ''}
    except Exception as e:
        _logging.log_json(function="Suppliers_delete", error=str(e))
        return {'statusCode': 500, 'headers': CORS, 'body': json.dumps({'error': 'An internal error occurred'})}
