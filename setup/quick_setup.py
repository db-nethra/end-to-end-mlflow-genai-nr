#!/usr/bin/env python3
"""DC Assistant Quick Setup

Interactive setup script that configures the DC Assistant demo for any workspace.
Works for both AI coding tool users (Claude Code, Cursor) and terminal users.

Usage:
    uv run python setup/quick_setup.py
    uv run python setup/quick_setup.py --profile my_profile --catalog my_catalog --schema dc_assistant

Steps:
    1. Select Databricks profile
    2. Select catalog and schema
    3. Create schema (if needed)
    4. Load NFL data tables
    5. Create UC SQL functions
    6. Create MLflow experiment
    7. Register system prompt
    8. Generate config files
    9. Install dependencies
    10. Create labeling session
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ── Helpers ──────────────────────────────────────────────────────────────────

def prompt_user(question: str, default: str = None, options: list = None) -> str:
    """Prompt user for input. Works in both interactive and non-interactive contexts."""
    if options:
        print(f'\n{question}')
        for i, opt in enumerate(options, 1):
            marker = ' (default)' if opt == default else ''
            print(f'  {i}. {opt}{marker}')
        while True:
            choice = input(f'Enter choice [1-{len(options)}]: ').strip()
            if not choice and default:
                return default
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return options[idx]
            except ValueError:
                # Allow typing the value directly
                if choice in options:
                    return choice
            print(f'  Invalid choice. Enter a number 1-{len(options)}.')
    else:
        suffix = f' [{default}]' if default else ''
        value = input(f'{question}{suffix}: ').strip()
        return value if value else (default or '')


def run_command(cmd: list, **kwargs) -> bool:
    """Run a command and return success."""
    result = subprocess.run(cmd, **kwargs)
    return result.returncode == 0


# ── Step Functions ───────────────────────────────────────────────────────────

def step_select_profile(args) -> dict:
    """Step 1: Select Databricks profile."""
    print('\n' + '=' * 60)
    print('Step 1: Select Databricks Profile')
    print('=' * 60)

    if args.profile:
        profile = args.profile
        print(f'Using profile from args: {profile}')
    else:
        # Parse ~/.databrickscfg for available profiles
        cfg_path = Path.home() / '.databrickscfg'
        profiles = []
        if cfg_path.exists():
            current_profile = None
            for line in cfg_path.read_text().splitlines():
                line = line.strip()
                if line.startswith('[') and line.endswith(']'):
                    current_profile = line[1:-1]
                    if current_profile != 'DEFAULT':
                        profiles.append(current_profile)

        if not profiles:
            print('No profiles found in ~/.databrickscfg')
            print('Run: databricks auth login --profile <name>')
            return None

        profile = prompt_user('Select a Databricks profile:', options=profiles)

    # Validate the profile
    from databricks.sdk import WorkspaceClient
    try:
        w = WorkspaceClient(profile=profile)
        host = w.config.host
        user = w.current_user.me()
        print(f'  Connected to: {host}')
        print(f'  Logged in as: {user.user_name}')
        return {'profile': profile, 'host': host, 'user_email': user.user_name, 'client': w}
    except Exception as e:
        print(f'  Failed to connect with profile "{profile}": {e}')
        return None


def step_select_catalog_schema(args, ctx: dict) -> dict:
    """Step 2: Select catalog and schema."""
    print('\n' + '=' * 60)
    print('Step 2: Select Catalog & Schema')
    print('=' * 60)

    w = ctx['client']

    if args.catalog:
        catalog = args.catalog
        print(f'Using catalog from args: {catalog}')
    else:
        # List available catalogs
        try:
            catalogs = [c.name for c in w.catalogs.list()]
            # Filter out system catalogs
            catalogs = [c for c in catalogs if c not in ('system', 'hive_metastore', '__databricks_internal')]
            if catalogs:
                catalog = prompt_user('Select a catalog:', options=catalogs[:20])
            else:
                catalog = prompt_user('Enter catalog name:')
        except Exception:
            catalog = prompt_user('Enter catalog name:')

    if args.schema:
        schema = args.schema
        print(f'Using schema from args: {schema}')
    else:
        schema = prompt_user('Enter schema name (will be created if needed):', default='dc_assistant')

    print(f'  Will use: {catalog}.{schema}')
    return {'catalog': catalog, 'schema': schema}


def step_create_schema(ctx: dict) -> bool:
    """Step 3: Create schema if needed."""
    print('\n' + '=' * 60)
    print('Step 3: Create Schema')
    print('=' * 60)

    w = ctx['client']
    catalog = ctx['catalog']
    schema = ctx['schema']

    try:
        w.schemas.get(f'{catalog}.{schema}')
        print(f'  Schema {catalog}.{schema} already exists')
        return True
    except Exception:
        pass

    try:
        w.schemas.create(name=schema, catalog_name=catalog, comment='DC Assistant demo schema')
        print(f'  Created schema: {catalog}.{schema}')
        return True
    except Exception as e:
        print(f'  Failed to create schema: {e}')
        print(f'  You may need to create it manually or pick a different catalog.')
        return False


def step_load_data(ctx: dict) -> bool:
    """Step 4: Load NFL data tables via databricks-connect."""
    print('\n' + '=' * 60)
    print('Step 4: Load NFL Data Tables')
    print('=' * 60)

    catalog = ctx['catalog']
    schema = ctx['schema']
    w = ctx['client']
    profile = ctx['profile']

    # Check if tables already exist
    tables_needed = ['football_pbp_data', 'football_participation']
    all_exist = True
    for table in tables_needed:
        try:
            w.tables.get(f'{catalog}.{schema}.{table}')
            print(f'  Table {table} already exists')
        except Exception:
            all_exist = False
            print(f'  Table {table} not found')

    if all_exist:
        print('  All data tables exist, skipping data load')
        return True

    print('  Loading NFL data via databricks-connect...')
    print('  This downloads play-by-play and participation data and writes to Delta tables.')
    print('  This may take a few minutes on first run.\n')

    try:
        from setup.load_nfl_data import load_nfl_data
        load_nfl_data(catalog=catalog, schema=schema, profile=profile)
        return True
    except Exception as e:
        print(f'  Failed to load data: {e}')
        print(f'  Alternative: Run 01_DataCollection.py as a notebook in your workspace')
        return False


def step_create_uc_functions(ctx: dict) -> bool:
    """Step 5: Create UC SQL functions."""
    print('\n' + '=' * 60)
    print('Step 5: Create UC Functions')
    print('=' * 60)

    from setup.create_uc_tools import create_uc_functions, get_or_create_warehouse

    w = ctx['client']
    catalog = ctx['catalog']
    schema = ctx['schema']

    warehouse_id = get_or_create_warehouse(w)
    if not warehouse_id:
        print('  No SQL warehouse available. Functions must be created via notebook.')
        return False

    print(f'  Using warehouse: {warehouse_id}')
    results = create_uc_functions(w, catalog, schema, warehouse_id)

    if results['created']:
        ctx['tool_names'] = [f'{catalog}.{schema}.{name}' for name in results['created']]
    else:
        # Fall back to expected tool names
        ctx['tool_names'] = [
            f'{catalog}.{schema}.{name}' for name in [
                'who_got_ball_by_down_distance', 'screen_play_tendencies',
                'tendencies_by_down_distance', 'tendencies_by_drive_start',
                'tendencies_by_offense_formation', 'tendencies_two_minute_drill',
                'first_play_after_turnover', 'tendencies_by_score_2nd_half',
                'who_got_ball_by_offense_situation', 'who_got_ball_by_down_distance_and_form',
                'who_got_ball_two_minute_drill', 'success_by_pass_rush_and_coverage',
            ]
        ]

    return True


def step_create_experiment(ctx: dict) -> bool:
    """Step 6: Create MLflow experiment."""
    print('\n' + '=' * 60)
    print('Step 6: Create MLflow Experiment')
    print('=' * 60)

    import mlflow

    os.environ['DATABRICKS_CONFIG_PROFILE'] = ctx['profile']
    mlflow.set_tracking_uri('databricks')

    user_email = ctx['user_email']
    experiment_name = f'/Users/{user_email}/dc-assistant-demo'

    exp = mlflow.get_experiment_by_name(experiment_name)
    if exp:
        experiment_id = exp.experiment_id
        print(f'  Experiment already exists: {experiment_name} (ID: {experiment_id})')
    else:
        experiment_id = mlflow.create_experiment(
            name=experiment_name,
            tags={'purpose': 'football_analysis', 'product': 'mlflow'},
        )
        print(f'  Created experiment: {experiment_name} (ID: {experiment_id})')

    mlflow.set_experiment(experiment_name)
    ctx['experiment_id'] = experiment_id
    ctx['experiment_name'] = experiment_name
    return True


def step_register_prompt(ctx: dict) -> bool:
    """Step 7: Register system prompt in UC Prompt Registry."""
    print('\n' + '=' * 60)
    print('Step 7: Register System Prompt')
    print('=' * 60)

    os.environ['DATABRICKS_CONFIG_PROFILE'] = ctx['profile']

    from setup.setup_prompt_registry import register_prompt

    catalog = ctx['catalog']
    schema = ctx['schema']
    prompt_name = 'dc_assistant_system_prompt'
    experiment_id = ctx['experiment_id']

    try:
        register_prompt(catalog, schema, prompt_name, experiment_id)
        ctx['prompt_name'] = prompt_name
        return True
    except Exception as e:
        print(f'  Failed to register prompt: {e}')
        print(f'  The agent will use a fallback prompt for local development.')
        ctx['prompt_name'] = prompt_name
        return True  # Non-blocking


def step_generate_config(ctx: dict) -> bool:
    """Step 8: Generate config files."""
    print('\n' + '=' * 60)
    print('Step 8: Generate Configuration')
    print('=' * 60)

    catalog = ctx['catalog']
    schema = ctx['schema']
    experiment_id = ctx['experiment_id']
    prompt_name = ctx.get('prompt_name', 'dc_assistant_system_prompt')
    tool_names = ctx.get('tool_names', [])
    host = ctx['host']
    profile = ctx['profile']
    user_email = ctx['user_email']

    # Generate config/dc_assistant.json
    dc_config = {
        'workspace': {'catalog': catalog, 'schema': schema},
        'data_collection': {'seasons': [2022, 2023, 2024]},
        'mlflow': {'experiment_id': experiment_id},
        'prompt_registry': {
            'prompt_name': prompt_name,
            'reflection_model': 'databricks:/databricks-claude-sonnet-4',
        },
        'llm': {
            'endpoint_name': 'databricks-claude-3-7-sonnet',
            'judge_model': 'databricks:/databricks-claude-sonnet-4',
        },
        'model': {
            'model_name': 'dc_assistant',
            'uc_model_name': f'{catalog}.{schema}.dc_assistant',
        },
        'evaluation': {
            'dataset_name': f'{catalog}.{schema}.dc_assistant_eval_trace_data',
            'label_schema_name': 'football_analysis_base',
            'labeling_session_name': 'dcassistant_eval_labeling',
            'assigned_users': [user_email],
        },
        'judges': {'aligned_judge_name': 'football_analysis_judge_align'},
        'optimization': {
            'optimization_dataset_name': f'{catalog}.{schema}.dcassistant_optimization_data',
        },
        'alignment': {
            'alignment_runs_table': f'{catalog}.{schema}.alignment_runs',
        },
        'tools': {'uc_tool_names': tool_names},
        'prompt_registry_auth': {
            'use_oauth': True,
            'secret_scope_name': 'dc-assistant-secrets',
            'oauth_client_id_key': 'oauth-client-id',
            'oauth_client_secret_key': 'oauth-client-secret',
            'databricks_host': host,
        },
    }

    config_dir = PROJECT_ROOT / 'config'
    config_dir.mkdir(exist_ok=True)
    config_file = config_dir / 'dc_assistant.json'
    with open(config_file, 'w') as f:
        json.dump(dc_config, f, indent=2)
    print(f'  Created: {config_file}')

    # Generate .env
    env_file = PROJECT_ROOT / '.env'
    with open(env_file, 'w') as f:
        f.write(f'# Generated by quick_setup.py\n\n')
        f.write(f'DATABRICKS_HOST="{host}"\n')
        f.write(f'DATABRICKS_APP_NAME="mlflow-genai-demo"\n')
        f.write(f'LHA_SOURCE_CODE_PATH="/Workspace/Users/{user_email}/mlflow-demo"\n')
        f.write(f'MLFLOW_EXPERIMENT_ID="{experiment_id}"\n')
        f.write(f'UC_CATALOG="{catalog}"\n')
        f.write(f'UC_SCHEMA="{schema}"\n')
        f.write(f'LLM_MODEL="databricks-claude-3-7-sonnet"\n')
        f.write(f'DATABRICKS_CONFIG_PROFILE="{profile}"\n')
        f.write(f'MLFLOW_ENABLE_ASYNC_TRACE_LOGGING="false"\n')
        f.write(f'PROMPT_NAME="{prompt_name}"\n')
        f.write(f'PROMPT_ALIAS="production"\n')
        f.write(f'MLFLOW_TRACKING_URI="databricks"\n')
    print(f'  Created: {env_file}')

    return True


def step_install_deps() -> bool:
    """Step 9: Install dependencies."""
    print('\n' + '=' * 60)
    print('Step 9: Install Dependencies')
    print('=' * 60)

    print('  Installing Python dependencies...')
    if not run_command(['uv', 'sync'], cwd=PROJECT_ROOT):
        print('  Failed to install Python deps')
        return False

    print('  Installing frontend dependencies...')
    if not run_command(['bun', 'install'], cwd=PROJECT_ROOT / 'client'):
        print('  Failed to install frontend deps')
        return False

    print('  Dependencies installed')
    return True


def step_create_labeling_session(ctx: dict) -> bool:
    """Step 10: Create master labeling session."""
    print('\n' + '=' * 60)
    print('Step 10: Create Labeling Session')
    print('=' * 60)

    import mlflow

    os.environ['DATABRICKS_CONFIG_PROFILE'] = ctx['profile']
    mlflow.set_tracking_uri('databricks')
    mlflow.set_experiment(experiment_id=ctx['experiment_id'])

    try:
        from mlflow.genai import create_labeling_session, label_schemas

        # Create the football_analysis_base label schema
        LABEL_SCHEMA_NAME = 'football_analysis_base'
        try:
            label_schemas.create_label_schema(
                name=LABEL_SCHEMA_NAME,
                type='feedback',
                title=LABEL_SCHEMA_NAME,
                input=label_schemas.InputCategorical(options=['1', '2', '3', '4', '5']),
                instruction=(
                    'Evaluate if the response appropriately analyzes the available data and provides '
                    'an actionable recommendation for the question.\n\n'
                    '1: Completely unacceptable. Incorrect data or no recommendations\n'
                    '2: Mostly unacceptable. Irrelevant feedback or weak recommendations\n'
                    '3: Somewhat acceptable. Relevant feedback with some strategic advantage\n'
                    '4: Mostly acceptable. Relevant feedback with strong strategic advantage\n'
                    '5: Completely acceptable. Excellent strategic advantage'
                ),
                enable_comment=True,
            )
            print(f'  Created label schema: {LABEL_SCHEMA_NAME}')
        except Exception:
            print(f'  Label schema {LABEL_SCHEMA_NAME} already exists')

        # Create master session
        session = create_labeling_session(
            name='master_session',
            assigned_users=[],
            label_schemas=[LABEL_SCHEMA_NAME],
        )
        print(f'  Created labeling session: master_session')
        if hasattr(session, 'url'):
            print(f'  Review App URL: {session.url}')
        return True

    except Exception as e:
        print(f'  Failed to create labeling session: {e}')
        print(f'  You can create one from the app UI later.')
        return True  # Non-blocking


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='DC Assistant Quick Setup')
    parser.add_argument('--profile', help='Databricks CLI profile name')
    parser.add_argument('--catalog', help='Unity Catalog name')
    parser.add_argument('--schema', help='Schema name (default: dc_assistant)', default=None)
    args = parser.parse_args()

    # Ensure we're running from project root
    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, str(PROJECT_ROOT))

    print('=' * 60)
    print('  DC Assistant - Quick Setup')
    print('=' * 60)
    print()
    print('This script will configure everything needed to run the')
    print('DC Assistant demo in your Databricks workspace.')
    print()

    # Step 1: Profile
    ctx = step_select_profile(args)
    if not ctx:
        print('\nSetup failed at profile selection.')
        sys.exit(1)

    # Step 2: Catalog / Schema
    cs = step_select_catalog_schema(args, ctx)
    if not cs:
        print('\nSetup failed at catalog/schema selection.')
        sys.exit(1)
    ctx.update(cs)

    # Step 3: Create schema
    if not step_create_schema(ctx):
        sys.exit(1)

    # Step 4: Load data
    step_load_data(ctx)

    # Step 5: UC Functions
    step_create_uc_functions(ctx)

    # Step 6: MLflow Experiment
    if not step_create_experiment(ctx):
        sys.exit(1)

    # Step 7: Prompt Registry
    step_register_prompt(ctx)

    # Step 8: Config files
    if not step_generate_config(ctx):
        sys.exit(1)

    # Step 9: Dependencies
    step_install_deps()

    # Step 10: Labeling session
    step_create_labeling_session(ctx)

    # Done
    print('\n' + '=' * 60)
    print('  Setup Complete!')
    print('=' * 60)
    print()
    print(f'  Workspace:    {ctx["host"]}')
    print(f'  Catalog:      {ctx["catalog"]}.{ctx["schema"]}')
    print(f'  Experiment:   {ctx.get("experiment_name", "N/A")}')
    print()
    print('  Next steps:')
    print('    1. Run the app:  ./watch.sh')
    print('    2. Open:         http://localhost:8000')
    print()
    print('  For deployment setup (service principal + OAuth):')
    print('    uv run python setup/setup_prompt_registry.py --deploy')
    print()


if __name__ == '__main__':
    main()
