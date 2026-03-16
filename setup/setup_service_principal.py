#!/usr/bin/env python3
"""Set up a service principal for deployed agent authentication.

This script handles the full service principal lifecycle:
1. Creates (or finds) a service principal
2. Generates an OAuth secret
3. Creates a Databricks secret scope
4. Stores the SP credentials in the scope
5. Grants the SP access to the UC catalog/schema

This is a ONE-TIME setup per workspace. After running this, agents.deploy()
can inject {{secrets/scope/key}} references so the deployed endpoint
authenticates to UC for prompt registry access.

Requires: Workspace admin permissions

Usage:
    uv run python setup/setup_service_principal.py --profile e2-demo-field-eng

    # If SP already exists, just grant access to a new schema:
    uv run python setup/setup_service_principal.py --profile e2-demo-field-eng --grant-only
"""

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def find_or_create_sp(client, sp_name: str) -> dict:
    """Find existing SP or create a new one."""
    existing = list(client.service_principals.list(filter=f'displayName eq "{sp_name}"'))
    if existing:
        sp = existing[0]
        print(f'  Found existing SP: {sp.display_name}')
        print(f'  Application ID: {sp.application_id}')
        return {'id': sp.id, 'application_id': sp.application_id, 'created': False}

    print(f'  Creating service principal: {sp_name}')
    sp = client.service_principals.create(display_name=sp_name)
    print(f'  Created SP: {sp.display_name}')
    print(f'  Application ID: {sp.application_id}')
    return {'id': sp.id, 'application_id': sp.application_id, 'created': True}


def create_oauth_secret(client, sp_id: str) -> str:
    """Generate an OAuth secret for the service principal."""
    print(f'  Generating OAuth secret...')
    # The SDK method varies by version - try both patterns
    try:
        secret_response = client.service_principals.create_oauth2_secret(sp_id)
        secret_value = secret_response.secret
    except AttributeError:
        try:
            secret_response = client.service_principals.create_oauth_secret(sp_id)
            secret_value = secret_response.secret
        except Exception:
            # Try via API directly
            response = client.api_client.do(
                'POST',
                f'/api/2.0/accounts/servicePrincipals/{sp_id}/credentials/secrets',
            )
            secret_value = response.get('secret')

    if not secret_value:
        raise RuntimeError('Failed to generate OAuth secret')

    print(f'  OAuth secret generated')
    return secret_value


def setup_secret_scope(client, scope_name: str, client_id: str, client_secret: str):
    """Create secret scope and store SP credentials."""
    # Create scope
    try:
        client.secrets.create_scope(scope=scope_name)
        print(f'  Created secret scope: {scope_name}')
    except Exception as e:
        if 'RESOURCE_ALREADY_EXISTS' in str(e) or 'already exists' in str(e):
            print(f'  Secret scope already exists: {scope_name}')
        else:
            raise

    # Store credentials
    client.secrets.put_secret(scope=scope_name, key='oauth-client-id', string_value=client_id)
    print(f'  Stored oauth-client-id in scope')
    client.secrets.put_secret(scope=scope_name, key='oauth-client-secret', string_value=client_secret)
    print(f'  Stored oauth-client-secret in scope')


def grant_sp_access(client, catalog: str, schema: str, application_id: str, warehouse_id: str):
    """Grant the service principal access to the UC catalog/schema."""
    grants = [
        f'GRANT USAGE ON CATALOG `{catalog}` TO `{application_id}`',
        f'GRANT USAGE ON SCHEMA `{catalog}`.`{schema}` TO `{application_id}`',
        f'GRANT CREATE FUNCTION, EXECUTE, MANAGE ON SCHEMA `{catalog}`.`{schema}` TO `{application_id}`',
    ]

    for grant_sql in grants:
        try:
            client.statement_execution.execute_statement(
                statement=grant_sql,
                warehouse_id=warehouse_id,
                wait_timeout='30s',
            )
            print(f'  Executed: {grant_sql}')
        except Exception as e:
            print(f'  Warning: {grant_sql} - {e}')


def find_warehouse(client) -> str:
    """Find an available SQL warehouse."""
    warehouses = list(client.warehouses.list())
    for wh in warehouses:
        if wh.enable_serverless_compute and wh.state and wh.state.value in ('RUNNING', 'STOPPED'):
            return wh.id
    for wh in warehouses:
        if wh.state and wh.state.value in ('RUNNING', 'STOPPED'):
            return wh.id
    raise RuntimeError('No SQL warehouse found')


def main():
    parser = argparse.ArgumentParser(description='Setup service principal for deployed agent')
    parser.add_argument('--profile', help='Databricks CLI profile', required=True)
    parser.add_argument('--sp-name', default='dc-assistant-sp', help='Service principal display name')
    parser.add_argument('--scope-name', default='dc-assistant-secrets', help='Secret scope name')
    parser.add_argument('--grant-only', action='store_true',
                        help='Only grant SP access to catalog/schema (SP and secrets already exist)')
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)

    # Load config
    config_path = PROJECT_ROOT / 'config' / 'dc_assistant.json'
    if not config_path.exists():
        print('Config not found. Run quick_setup.py first.')
        sys.exit(1)

    config = json.loads(config_path.read_text())
    catalog = config['workspace']['catalog']
    schema = config['workspace']['schema']

    os.environ['DATABRICKS_CONFIG_PROFILE'] = args.profile
    from databricks.sdk import WorkspaceClient
    client = WorkspaceClient(profile=args.profile)

    print('=' * 60)
    print('  Service Principal Setup')
    print('=' * 60)
    print()
    print(f'  Workspace: {client.config.host}')
    print(f'  Catalog:   {catalog}.{schema}')
    print(f'  SP Name:   {args.sp_name}')
    print(f'  Scope:     {args.scope_name}')
    print()

    warehouse_id = find_warehouse(client)

    if args.grant_only:
        # Just grant access — find the existing SP
        print('Step 1: Finding existing service principal...')
        sp_info = find_or_create_sp(client, args.sp_name)

        print('\nStep 2: Granting access to catalog/schema...')
        grant_sp_access(client, catalog, schema, sp_info['application_id'], warehouse_id)
    else:
        # Full setup
        print('Step 1: Service Principal...')
        sp_info = find_or_create_sp(client, args.sp_name)

        if sp_info['created']:
            print('\nStep 2: OAuth Secret...')
            secret_value = create_oauth_secret(client, sp_info['id'])

            print('\nStep 3: Secret Scope...')
            setup_secret_scope(client, args.scope_name, sp_info['application_id'], secret_value)
        else:
            print('\nStep 2: SP already exists - checking secret scope...')
            # Verify scope exists
            try:
                scopes = client.secrets.list_scopes()
                scope_exists = any(s.name == args.scope_name for s in scopes)
                if scope_exists:
                    print(f'  Secret scope {args.scope_name} exists')
                else:
                    print(f'  Secret scope {args.scope_name} not found')
                    print(f'  Generating new OAuth secret and creating scope...')
                    secret_value = create_oauth_secret(client, sp_info['id'])
                    setup_secret_scope(client, args.scope_name, sp_info['application_id'], secret_value)
            except Exception as e:
                print(f'  Warning checking scope: {e}')

            print('\nStep 3: Verified')

        print('\nStep 4: Granting access to catalog/schema...')
        grant_sp_access(client, catalog, schema, sp_info['application_id'], warehouse_id)

    # Update config with SP info
    config['prompt_registry_auth']['secret_scope_name'] = args.scope_name
    config['prompt_registry_auth']['databricks_host'] = client.config.host
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f'\nUpdated config: {config_path}')

    print('\n' + '=' * 60)
    print('  Service Principal Setup Complete')
    print('=' * 60)
    print()
    print(f'  Application ID: {sp_info["application_id"]}')
    print(f'  Secret Scope:   {args.scope_name}')
    print(f'  Grants:         USAGE + EXECUTE + MANAGE on {catalog}.{schema}')
    print()
    print('  Next: Deploy the agent endpoint:')
    print(f'    uv run python setup/deploy_agent.py --profile {args.profile}')
    print()


if __name__ == '__main__':
    main()
