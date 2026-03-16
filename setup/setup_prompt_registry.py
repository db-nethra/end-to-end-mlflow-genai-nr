"""Register the DC Assistant system prompt in Unity Catalog Prompt Registry.

This script:
1. Registers the default system prompt as a UC prompt
2. Sets the @production alias
3. Tags the MLflow experiment with the prompt registry location

Can be run standalone or called from the main setup script.
"""

import json
import os
import sys
from pathlib import Path


def register_prompt(catalog: str, schema: str, prompt_name: str, experiment_id: str):
    """Register the system prompt in UC and set the production alias."""
    import mlflow

    mlflow.set_tracking_uri('databricks')
    mlflow.set_experiment(experiment_id=experiment_id)

    # Load the default prompt template
    prompt_file = Path(__file__).parent / 'default_system_prompt.txt'
    if not prompt_file.exists():
        raise FileNotFoundError(f'Prompt template not found: {prompt_file}')
    template = prompt_file.read_text().strip()

    full_prompt_name = f'{catalog}.{schema}.{prompt_name}'
    print(f'Registering prompt: {full_prompt_name}')

    # Register the prompt (creates a new version if it already exists)
    prompt = mlflow.genai.register_prompt(
        name=full_prompt_name,
        template=template,
        commit_message='DC Assistant system prompt for defensive coaching analysis',
    )
    print(f'  Registered: {prompt.name} v{prompt.version}')

    # Set the production alias
    mlflow.genai.set_prompt_alias(
        name=full_prompt_name,
        alias='production',
        version=prompt.version,
    )
    print(f'  Set alias: @production -> v{prompt.version}')

    # Tag the experiment so MLflow knows where to find prompts
    mlflow.set_experiment_tags({
        'mlflow.promptRegistryLocation': f'{catalog}.{schema}',
    })
    print(f'  Tagged experiment with prompt registry location: {catalog}.{schema}')

    return prompt


def setup_service_principal(catalog: str, schema: str, sp_name: str = 'dc-assistant-sp'):
    """Create a service principal and grant it access to the UC schema.

    This is only needed for deployed Databricks Apps.
    Requires workspace admin permissions.

    Returns:
        dict with 'application_id' and 'secret' if created, None if skipped
    """
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()

    # Check if SP already exists
    existing = list(w.service_principals.list(filter=f'displayName eq "{sp_name}"'))
    if existing:
        sp = existing[0]
        print(f'  Service principal already exists: {sp.display_name} (ID: {sp.application_id})')
        return {'application_id': sp.application_id, 'secret': None}

    # Create the service principal
    print(f'  Creating service principal: {sp_name}')
    sp = w.service_principals.create(display_name=sp_name)
    print(f'  Created SP: {sp.display_name} (ID: {sp.application_id})')

    # Create an OAuth secret for the SP
    secret = w.service_principals.create_oauth_secret(sp.id)
    print(f'  Created OAuth secret')

    # Grant permissions on the UC schema
    print(f'  Granting permissions on {catalog}.{schema}...')
    try:
        w.statement_execution.execute_statement(
            statement=f'GRANT USAGE ON CATALOG `{catalog}` TO `{sp.application_id}`',
            warehouse_id=_find_warehouse(w),
            wait_timeout='30s',
        )
        w.statement_execution.execute_statement(
            statement=f'GRANT USAGE ON SCHEMA `{catalog}`.`{schema}` TO `{sp.application_id}`',
            warehouse_id=_find_warehouse(w),
            wait_timeout='30s',
        )
        w.statement_execution.execute_statement(
            statement=f'GRANT EXECUTE ON SCHEMA `{catalog}`.`{schema}` TO `{sp.application_id}`',
            warehouse_id=_find_warehouse(w),
            wait_timeout='30s',
        )
        print(f'  Granted USAGE + EXECUTE on {catalog}.{schema}')
    except Exception as e:
        print(f'  Warning: Could not grant permissions: {e}')
        print(f'  You may need to grant manually via SQL or the UI')

    return {'application_id': sp.application_id, 'secret': secret.secret}


def setup_secret_scope(scope_name: str, client_id: str, client_secret: str):
    """Create a secret scope and store the SP credentials.

    Only needed for deployed Databricks Apps.
    """
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()

    # Create scope if it doesn't exist
    try:
        w.secrets.create_scope(scope=scope_name)
        print(f'  Created secret scope: {scope_name}')
    except Exception as e:
        if 'RESOURCE_ALREADY_EXISTS' in str(e):
            print(f'  Secret scope already exists: {scope_name}')
        else:
            raise

    # Store credentials
    w.secrets.put_secret(scope=scope_name, key='oauth-client-id', string_value=client_id)
    w.secrets.put_secret(scope=scope_name, key='oauth-client-secret', string_value=client_secret)
    print(f'  Stored OAuth credentials in scope: {scope_name}')


def _find_warehouse(client):
    """Find a SQL warehouse for executing statements."""
    warehouses = list(client.warehouses.list())
    for wh in warehouses:
        if wh.enable_serverless_compute and wh.state and wh.state.value in ('RUNNING', 'STOPPED'):
            return wh.id
    for wh in warehouses:
        if wh.state and wh.state.value in ('RUNNING', 'STOPPED'):
            return wh.id
    raise RuntimeError('No SQL warehouse found')


if __name__ == '__main__':
    # Load config
    config_path = Path(__file__).resolve().parents[1] / 'config' / 'dc_assistant.json'
    if not config_path.exists():
        print(f'Config not found: {config_path}')
        print('Run the setup script first to generate config/dc_assistant.json')
        sys.exit(1)

    config = json.loads(config_path.read_text())
    catalog = config['workspace']['catalog']
    schema = config['workspace']['schema']
    prompt_name = config['prompt_registry']['prompt_name']
    experiment_id = config['mlflow']['experiment_id']

    profile = os.environ.get('DATABRICKS_CONFIG_PROFILE')
    if profile:
        os.environ['DATABRICKS_CONFIG_PROFILE'] = profile

    print('=== Prompt Registry Setup ===\n')
    register_prompt(catalog, schema, prompt_name, experiment_id)

    print('\n=== Done ===')
    print(f'Prompt registered at: {catalog}.{schema}.{prompt_name}@production')
