import boto3
import time
import zipfile
import os

ROLE_ARN = 'arn:aws:iam::023202272390:role/InventoryIQ-LambdaExecutionRole'
LAMBDA_NAME = 'Suppliers'
TABLE_NAME = 'Suppliers'
API_ID = 'd1g2j27343'

ddb = boto3.client('dynamodb')
lam = boto3.client('lambda')
apig = boto3.client('apigateway')

def create_table():
    try:
        ddb.describe_table(TableName=TABLE_NAME)
        print(f"Table {TABLE_NAME} already exists.")
    except ddb.exceptions.ResourceNotFoundException:
        print(f"Creating table {TABLE_NAME}...")
        ddb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{'AttributeName': 'supplierID', 'KeyType': 'HASH'}],
            AttributeDefinitions=[
                {'AttributeName': 'supplierID', 'AttributeType': 'S'},
                {'AttributeName': 'userID', 'AttributeType': 'S'},
                {'AttributeName': 'createdAt', 'AttributeType': 'S'},
            ],
            GlobalSecondaryIndexes=[{
                'IndexName': 'userID-index',
                'KeySchema': [
                    {'AttributeName': 'userID', 'KeyType': 'HASH'},
                    {'AttributeName': 'createdAt', 'KeyType': 'RANGE'},
                ],
                'Projection': {'ProjectionType': 'ALL'},
                'ProvisionedThroughput': {'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
            }],
            ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
        )
        print("Waiting for table to become active...")
        waiter = ddb.get_waiter('table_exists')
        waiter.wait(TableName=TABLE_NAME)
        print("Table created.")

def deploy_lambda():
    print(f"Deploying Lambda {LAMBDA_NAME}...")
    with zipfile.ZipFile('function.zip', 'w') as z:
        z.write('lambda/Suppliers.py', 'Suppliers.py')
        z.write('lambda/_logging.py', '_logging.py')

    with open('function.zip', 'rb') as f:
        zip_bytes = f.read()

    try:
        lam.get_function(FunctionName=LAMBDA_NAME)
        lam.update_function_code(FunctionName=LAMBDA_NAME, ZipFile=zip_bytes)
        print(f"Lambda {LAMBDA_NAME} updated.")
    except lam.exceptions.ResourceNotFoundException:
        resp = lam.create_function(
            FunctionName=LAMBDA_NAME,
            Runtime='python3.9',
            Role=ROLE_ARN,
            Handler='Suppliers.lambda_handler',
            Code={'ZipFile': zip_bytes},
            Timeout=15,
            Environment={'Variables': {'SUPPLIERS_TABLE': TABLE_NAME}}
        )
        print(f"Lambda {LAMBDA_NAME} created.")
        
    return lam.get_function(FunctionName=LAMBDA_NAME)['Configuration']['FunctionArn']

def configure_apigateway(lambda_arn):
    print("Configuring API Gateway...")
    
    # Get resources
    resources = apig.get_resources(restApiId=API_ID, limit=500)['items']
    root_id = next(r['id'] for r in resources if r['path'] == '/')
    
    suppliers_resource = next((r for r in resources if r['path'] == '/suppliers'), None)
    if not suppliers_resource:
        suppliers_resource = apig.create_resource(restApiId=API_ID, parentId=root_id, pathPart='suppliers')
    
    suppliers_id_resource = next((r for r in resources if r['path'] == '/suppliers/{id}'), None)
    if not suppliers_id_resource:
        suppliers_id_resource = apig.create_resource(restApiId=API_ID, parentId=suppliers_resource['id'], pathPart='{id}')

    region = boto3.session.Session().region_name
    uri = f"arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations"

    def setup_method(resource_id, method):
        try:
            apig.get_method(restApiId=API_ID, resourceId=resource_id, httpMethod=method)
        except apig.exceptions.NotFoundException:
            apig.put_method(restApiId=API_ID, resourceId=resource_id, httpMethod=method, authorizationType='NONE')
        
        apig.put_integration(
            restApiId=API_ID,
            resourceId=resource_id,
            httpMethod=method,
            type='AWS_PROXY',
            integrationHttpMethod='POST',
            uri=uri
        )

    setup_method(suppliers_resource['id'], 'ANY')
    setup_method(suppliers_resource['id'], 'OPTIONS')
    setup_method(suppliers_id_resource['id'], 'ANY')
    setup_method(suppliers_id_resource['id'], 'OPTIONS')
    
    # Add permissions for API Gateway to invoke the Lambda
    try:
        lam.add_permission(
            FunctionName=LAMBDA_NAME,
            StatementId='apigateway-invoke-suppliers',
            Action='lambda:InvokeFunction',
            Principal='apigateway.amazonaws.com',
            SourceArn=f"arn:aws:execute-api:{region}:023202272390:{API_ID}/*/*/*"
        )
    except lam.exceptions.ResourceConflictException:
        pass

    # Deploy
    print("Creating deployment...")
    apig.create_deployment(restApiId=API_ID, stageName='prod')
    print("API Gateway deployed.")

if __name__ == '__main__':
    create_table()
    arn = deploy_lambda()
    configure_apigateway(arn)
    print("Setup complete.")
