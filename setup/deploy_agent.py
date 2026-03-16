#!/usr/bin/env python3
"""Deploy the DC Assistant agent as a Model Serving endpoint.

This script:
1. Logs the agent to MLflow
2. Registers it in UC Model Registry
3. Deploys it as a serving endpoint via agents.deploy()

Prerequisites:
- quick_setup.py has been run successfully
- Service principal + secret scope configured (for prompt registry auth)
  See docs/SETUP.md for instructions

Usage:
    uv run python setup/deploy_agent.py
    uv run python setup/deploy_agent.py --profile e2-demo-field-eng
"""

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Deploy DC Assistant agent endpoint')
    parser.add_argument('--profile', help='Databricks CLI profile name')
    parser.add_argument('--skip-validation', action='store_true', help='Skip pre-deployment validation')
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, str(PROJECT_ROOT))

    # Load config
    config_path = PROJECT_ROOT / 'config' / 'dc_assistant.json'
    if not config_path.exists():
        print('Config not found. Run quick_setup.py first.')
        sys.exit(1)

    config = json.loads(config_path.read_text())
    catalog = config['workspace']['catalog']
    schema = config['workspace']['schema']
    uc_model_name = config['model']['uc_model_name']
    llm_endpoint = config['llm']['endpoint_name']
    tool_names = config['tools']['uc_tool_names']
    auth_config = config.get('prompt_registry_auth', {})

    profile = args.profile or os.environ.get('DATABRICKS_CONFIG_PROFILE')
    if profile:
        os.environ['DATABRICKS_CONFIG_PROFILE'] = profile

    print('=' * 60)
    print('  DC Assistant - Deploy Agent Endpoint')
    print('=' * 60)
    print()
    print(f'  Model:    {uc_model_name}')
    print(f'  LLM:      {llm_endpoint}')
    print(f'  Tools:    {len(tool_names)} UC functions')
    print()

    # ── Step 1: Log the model ────────────────────────────────────────────
    print('Step 1: Logging agent model...')

    import mlflow
    from mlflow.models.resources import DatabricksFunction, DatabricksServingEndpoint

    mlflow.set_tracking_uri('databricks')
    experiment_id = config['mlflow']['experiment_id']
    mlflow.set_experiment(experiment_id=experiment_id)
    mlflow.set_registry_uri('databricks-uc')

    resources = [DatabricksServingEndpoint(endpoint_name=llm_endpoint)]
    for tool_name in tool_names:
        resources.append(DatabricksFunction(function_name=tool_name))

    input_example = {
        'input': [
            {
                'role': 'user',
                'content': 'What are the 2024 Green Bay Packers screen play tendencies?',
            }
        ]
    }

    os.environ['UV_PRERELEASE'] = 'allow'

    with mlflow.start_run():
        logged_agent_info = mlflow.pyfunc.log_model(
            name='agent',
            python_model='agent.py',
            input_example=input_example,
            pip_requirements=[
                'databricks-openai',
                'backoff',
                'mlflow>=3.9.0',
            ],
            resources=resources,
        )

    print(f'  Logged model: runs:/{logged_agent_info.run_id}/agent')

    # ── Step 2: Pre-deployment validation ─────────────────────────────────
    if not args.skip_validation:
        print('\nStep 2: Validating model...')
        try:
            mlflow.models.predict(
                model_uri=f'runs:/{logged_agent_info.run_id}/agent',
                input_data={
                    'input': [
                        {'role': 'user', 'content': 'How do the 2024 Chiefs handle the last two minutes of the half?'}
                    ]
                },
                env_manager='uv',
                extra_envs={'UV_PRERELEASE': 'allow'},
            )
            print('  Validation passed')
        except Exception as e:
            print(f'  Validation warning: {e}')
            print('  Continuing with deployment...')
    else:
        print('\nStep 2: Skipping validation (--skip-validation)')

    # ── Step 3: Register in UC ────────────────────────────────────────────
    print(f'\nStep 3: Registering model in UC: {uc_model_name}...')

    uc_registered_model_info = mlflow.register_model(
        model_uri=logged_agent_info.model_uri,
        name=uc_model_name,
    )
    print(f'  Registered: {uc_model_name} v{uc_registered_model_info.version}')

    # ── Step 4: Deploy endpoint ───────────────────────────────────────────
    print(f'\nStep 4: Deploying serving endpoint...')

    from databricks import agents

    # Build environment variables for the deployed endpoint
    config_payload = config_path.read_text()
    environment_vars = {'DC_ASSISTANT_CONFIG_JSON': config_payload}

    # Add auth config for prompt registry access
    databricks_host = auth_config.get('databricks_host', '')
    secret_scope = auth_config.get('secret_scope_name', 'dc-assistant-secrets')
    use_oauth = auth_config.get('use_oauth', True)

    if databricks_host:
        if use_oauth:
            client_id_key = auth_config.get('oauth_client_id_key', 'oauth-client-id')
            client_secret_key = auth_config.get('oauth_client_secret_key', 'oauth-client-secret')
            environment_vars.update({
                'DATABRICKS_HOST': databricks_host,
                'DATABRICKS_CLIENT_ID': f'{{{{secrets/{secret_scope}/{client_id_key}}}}}',
                'DATABRICKS_CLIENT_SECRET': f'{{{{secrets/{secret_scope}/{client_secret_key}}}}}',
            })
            print(f'  Auth: OAuth via secret scope "{secret_scope}"')
        else:
            pat_key = auth_config.get('pat_key', 'databricks-pat')
            environment_vars.update({
                'DATABRICKS_HOST': databricks_host,
                'DATABRICKS_TOKEN': f'{{{{secrets/{secret_scope}/{pat_key}}}}}',
            })
            print(f'  Auth: PAT via secret scope "{secret_scope}"')
    else:
        print('  WARNING: No DATABRICKS_HOST configured.')
        print('  Prompt Registry will not be accessible in the deployed endpoint.')
        print('  The agent will use its fallback prompt.')

    agents.deploy(
        uc_model_name,
        uc_registered_model_info.version,
        environment_vars=environment_vars,
        tags={'endpointSource': 'setup_script'},
    )

    print(f'\n  Endpoint deploying: agents_{uc_model_name.replace(".", "-")}')
    print(f'  This may take 5-10 minutes to become ready.')

    # ── Done ──────────────────────────────────────────────────────────────
    print('\n' + '=' * 60)
    print('  Deployment initiated!')
    print('=' * 60)
    print()
    print(f'  Model:     {uc_model_name} v{uc_registered_model_info.version}')
    print(f'  Endpoint:  agents_{uc_model_name.replace(".", "-")}')
    print()
    print('  Monitor deployment status:')
    print(f'    databricks serving-endpoints get agents_{uc_model_name.replace(".", "-")}')
    print()
    print('  To use the endpoint in the app, set in .env:')
    print(f'    DC_ASSISTANT_MODE="endpoint"')
    print(f'    LLM_MODEL="agents_{uc_model_name.replace(".", "-")}"')
    print()


if __name__ == '__main__':
    main()
