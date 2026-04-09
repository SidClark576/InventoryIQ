import json, boto3, urllib.request, os

API_ENDPOINT = os.environ['API_ENDPOINT']
API_KEY      = os.environ['API_KEY']  # stored safely in Lambda env vars

CORS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,x-api-key',
    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET,PUT,DELETE'
}

def lambda_handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS, 'body': ''}

    # {proxy+} sends the sub-path in pathParameters
    path = event.get('pathParameters', {}).get('proxy', '')
    path = f"/{path}"  # e.g. becomes /items or /insights

    method = event.get('httpMethod', 'GET')
    body   = event.get('body') or ''

    qs = event.get('queryStringParameters') or {}
    if qs:
        query = '&'.join(f"{k}={v}" for k, v in qs.items())
        path = f"{path}?{query}"

    try:
        req = urllib.request.Request(
            f"{API_ENDPOINT}{path}",
            data=body.encode() if body else None,
            headers={
                'Content-Type': 'application/json',
                'x-api-key': API_KEY
            },
            method=method
        )
        with urllib.request.urlopen(req) as res:
            return {
                'statusCode': res.status,
                'headers': CORS,
                'body': res.read().decode()
            }
    except urllib.error.HTTPError as e:
        return {
            'statusCode': e.code,
            'headers': CORS,
            'body': e.read().decode()
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': CORS,
            'body': json.dumps({'error': str(e)})
        }