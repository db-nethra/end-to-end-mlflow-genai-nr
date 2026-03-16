"""Create Unity Catalog functions for the DC Assistant agent.

Reads SQL function definitions from create_uc_functions.sql and executes them
in the configured catalog/schema using the Databricks SQL Statement Execution API.
"""

import re
import time
from pathlib import Path

from databricks.sdk import WorkspaceClient


def create_uc_functions(
    client: WorkspaceClient,
    catalog: str,
    schema: str,
    warehouse_id: str = None,
) -> dict:
    """Create all UC functions in the specified catalog.schema.

    Args:
        client: Authenticated WorkspaceClient
        catalog: UC catalog name
        schema: UC schema name
        warehouse_id: Optional SQL warehouse ID. If not provided, uses serverless.

    Returns:
        dict with 'created', 'failed', and 'errors' keys
    """
    sql_file = Path(__file__).parent / 'create_uc_functions.sql'
    if not sql_file.exists():
        raise FileNotFoundError(f'SQL file not found: {sql_file}')

    sql_content = sql_file.read_text()

    # Split on CREATE OR REPLACE FUNCTION boundaries
    # This handles cases where multiple functions are in one block
    parts = re.split(r'(?=CREATE OR REPLACE FUNCTION\b)', sql_content)
    statements = []
    for part in parts:
        part = part.strip()
        if part.startswith('CREATE OR REPLACE FUNCTION'):
            # Remove trailing semicolons and comments after the function body
            # The function body ends at the last closing paren before any trailing ;
            statements.append(part.rstrip().rstrip(';').rstrip())

    print(f'Found {len(statements)} UC function definitions')

    results = {'created': [], 'failed': [], 'errors': []}

    for stmt in statements:
        # Extract function name
        match = re.search(r'CREATE OR REPLACE FUNCTION\s+(\w+)', stmt)
        func_name = match.group(1) if match else 'unknown'

        # Qualify the function name with catalog.schema
        full_sql = stmt.replace(
            f'CREATE OR REPLACE FUNCTION {func_name}',
            f'CREATE OR REPLACE FUNCTION `{catalog}`.`{schema}`.{func_name}',
        )
        # Qualify all unqualified table references (FROM and JOIN)
        full_sql = re.sub(
            r'\b(football_pbp_data|football_participation)\b',
            lambda m: f'`{catalog}`.`{schema}`.{m.group(0)}',
            full_sql,
        )

        try:
            # Execute via statement execution API
            response = client.statement_execution.execute_statement(
                statement=full_sql,
                warehouse_id=warehouse_id,
                wait_timeout='50s',
            )

            status = response.status
            if status and status.state:
                state = status.state.value if hasattr(status.state, 'value') else str(status.state)
                if state in ('SUCCEEDED', 'CLOSED'):
                    results['created'].append(func_name)
                    print(f'  Created: {catalog}.{schema}.{func_name}')
                else:
                    error_msg = status.error.message if status.error else state
                    results['failed'].append(func_name)
                    results['errors'].append(f'{func_name}: {error_msg}')
                    print(f'  Failed: {func_name} - {error_msg}')
            else:
                results['created'].append(func_name)
                print(f'  Created: {catalog}.{schema}.{func_name}')

        except Exception as e:
            results['failed'].append(func_name)
            results['errors'].append(f'{func_name}: {str(e)}')
            print(f'  Failed: {func_name} - {e}')

    print(f'\nSummary: {len(results["created"])} created, {len(results["failed"])} failed')
    return results


def get_or_create_warehouse(client: WorkspaceClient) -> str:
    """Find an existing serverless SQL warehouse or return None."""
    try:
        warehouses = list(client.warehouses.list())
        # Prefer serverless warehouses
        for wh in warehouses:
            if wh.enable_serverless_compute and wh.state and wh.state.value in ('RUNNING', 'STOPPED'):
                return wh.id
        # Fall back to any available warehouse
        for wh in warehouses:
            if wh.state and wh.state.value in ('RUNNING', 'STOPPED'):
                return wh.id
    except Exception as e:
        print(f'Warning: Could not list warehouses: {e}')

    return None


if __name__ == '__main__':
    import json
    import os

    # Load config
    config_path = Path(__file__).resolve().parents[1] / 'config' / 'dc_assistant.json'
    if not config_path.exists():
        print(f'Config not found: {config_path}')
        exit(1)

    config = json.loads(config_path.read_text())
    catalog = config['workspace']['catalog']
    schema = config['workspace']['schema']

    profile = os.environ.get('DATABRICKS_CONFIG_PROFILE')
    client = WorkspaceClient(profile=profile) if profile else WorkspaceClient()

    warehouse_id = get_or_create_warehouse(client)
    if not warehouse_id:
        print('No SQL warehouse found. Please create one or set WAREHOUSE_ID env var.')
        exit(1)

    print(f'Using warehouse: {warehouse_id}')
    print(f'Creating functions in {catalog}.{schema}...\n')

    results = create_uc_functions(client, catalog, schema, warehouse_id)

    if results['failed']:
        print(f'\nErrors:')
        for err in results['errors']:
            print(f'  {err}')
        exit(1)
