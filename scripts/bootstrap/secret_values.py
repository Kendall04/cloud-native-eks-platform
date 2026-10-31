"""Private operator initialization. Values never enter subprocesses, files or output.
Run serially. Existing secrets are preserved; concurrent initializers fail safely.
"""
import json
import secrets
import uuid
from environment import require

SERVICES = ('auth', 'shipment', 'tracking')

def validate_value(name, raw):
    if name.endswith('-db'):
        value = json.loads(raw)
        service, purpose, _ = name.split('-')
        require(set(value) == {'username', 'password'}, 'Invalid DB secret shape')
        require(value['username'] == service + ('_runtime' if purpose == 'runtime' else '_migrator'), 'Unexpected DB identity')
        require(isinstance(value['password'], str) and len(value['password']) >= 32, 'Invalid DB credential')
    elif name == 'bootstrap-admin':
        value = json.loads(raw)
        require(set(value) == {'email','password'} and '@' in value['email'] and len(value['password']) >= 32, 'Invalid admin seed secret')
    else:
        require(isinstance(raw,str) and len(raw) >= 32 and not raw.startswith('{') and not any(x in raw.lower() for x in ('replace', 'placeholder', 'change-me', 'development')), 'Invalid shared trust secret')
    return raw

def initial_value(name, email):
    password = secrets.token_urlsafe(48) + 'aA1!'
    if name.endswith('-db'):
        service, purpose, _ = name.split('-')
        return json.dumps({'username':service + ('_runtime' if purpose == 'runtime' else '_migrator'), 'password':password})
    if name == 'bootstrap-admin':
        require(email and '@' in email, 'BOOTSTRAP_ADMIN_EMAIL is required for initial admin seeding')
        return json.dumps({'email':email,'password':password})
    return password

def initialize(c, email=None, client=None):
    if client is None:
        import boto3
        client = boto3.client('secretsmanager', region_name=c['region'])
    for name, arn in c['secrets'].items():
        metadata = client.describe_secret(SecretId=arn) # Missing container fails, never creates it.
        versions = metadata.get('VersionIdsToStages', {})
        if versions:
            require(any('AWSCURRENT' in stages for stages in versions.values()), 'Existing secret has no current version; operator recovery required')
            validate_value(name, client.get_secret_value(SecretId=arn)['SecretString'])
            continue
        raw = validate_value(name, initial_value(name,email))
        # Stable token prevents concurrent initializers silently overwriting different random values.
        client.put_secret_value(SecretId=arn, ClientRequestToken=str(uuid.uuid5(uuid.NAMESPACE_URL, arn + '/initial-v1')), SecretString=raw)
