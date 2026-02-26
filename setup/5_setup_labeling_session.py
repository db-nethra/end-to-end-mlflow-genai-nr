import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import dotenv

# Load environment variables from .env.local in project root
dotenv.load_dotenv(project_root / '.env.local')

# allow databricks-cli auth to take over
import os
os.environ.pop('DATABRICKS_HOST', None)


import logging
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("mlflow").setLevel(logging.ERROR)

def write_env_variable(key, value):
  """Write or update a variable in .env.local file."""
  env_file = project_root / '.env.local'

  # Read existing content
  lines = []
  if env_file.exists():
    with open(env_file, 'r') as f:
      lines = f.readlines()

  # Find if variable already exists
  updated = False
  for i, line in enumerate(lines):
    if line.strip().startswith(f'{key}='):
      lines[i] = f'{key}="{value}"\n'
      updated = True
      break

  # If variable doesn't exist, append it
  if not updated:
    lines.append(f'{key}="{value}"\n')

  # Write back to file
  with open(env_file, 'w') as f:
    f.writelines(lines)

  print(f'✅ Updated {key} in .env.local')


from datetime import datetime

import mlflow
from mlflow.genai import label_schemas


def create_labeling_schemas():
  """Create labeling schemas for human expert evaluation of DC assistant responses."""
  schemas = {}

  schema_configs = {
    'accuracy': {
      'title': 'Are all facts and statistics accurate?',
      'instruction': 'Check that all statistics, player names, formations, and tendencies match the data returned by tools. No fabricated numbers or claims.',
    },
    'relevance': {
      'title': 'Does the response address the question?',
      'instruction': 'Evaluate if the response directly answers the specific question asked about opponent tendencies, game situations, or strategy.',
    },
    'actionability': {
      'title': 'Are the defensive recommendations actionable?',
      'instruction': 'Check if the response provides specific, implementable defensive adjustments or play calls that a coach could use in game planning.',
    },
  }

  for schema_name, config in schema_configs.items():
    try:
      schema = label_schemas.create_label_schema(
        name=schema_name,
        type='feedback',
        title=config['title'],
        input=label_schemas.InputCategorical(options=['yes', 'no']),
        instruction=config['instruction'],
        enable_comment=True,
        overwrite=True,
      )
      schemas[schema_name] = schema
      print(f'Created labeling schema: {schema_name}')

    except Exception as e:
      print(f'Error creating schema {schema_name}: {e}')

  return schemas


def create_labeling_session(schemas, session_name='dc_assistant_evaluation_session'):
  """Create a labeling session for human expert review."""
  try:
    schema_names = [schema.name for schema in schemas.values()]

    session = mlflow.genai.create_labeling_session(
      name='demo_labeling_session',
      assigned_users=[],  # Add specific users as needed
      label_schemas=schema_names,
    )

    print(f'Created labeling session: {session_name}')
    return session

  except Exception as e:
    print(f'Error creating labeling session: {e}')
    return None


def add_traces_to_session(session):
  """Add traces to a labeling session and return trace IDs.

  Uses the MLflow client API (not the legacy REST API) to link traces to the
  labeling session's run, which supports UC-stored traces.
  """
  # Normally, you would query for the relevant traces, here we just grab 3.
  traces = mlflow.search_traces(max_results=3)

  if traces.empty:
    print('No traces found to add to session.')
    return None

  # Extract trace IDs and Trace objects
  trace_ids = traces['trace_id'].tolist()

  # Get the backend session to access its run_id and item creation API
  store = session._get_store()
  backend_session = store._get_backend_session(session)

  # Log each trace to the labeling session's experiment
  from mlflow.entities import Trace
  from databricks.rag_eval.review_app.utils import log_trace_to_experiment
  logged_trace_ids = []
  for trace_obj in traces['trace'].tolist():
    # Deserialize JSON strings to Trace objects if needed
    if isinstance(trace_obj, str):
      trace_obj = Trace.from_json(trace_obj)
    logged_trace = log_trace_to_experiment(trace_obj, backend_session.experiment_id)
    logged_trace_ids.append(logged_trace.info.trace_id)

  # Use the new MLflow client API to link traces to the labeling session's run
  # (instead of the legacy databricks/rag_eval REST API which doesn't support UC traces)
  if backend_session.mlflow_run_id and logged_trace_ids:
    client = mlflow.MlflowClient()
    client.link_traces_to_run(
      run_id=backend_session.mlflow_run_id,
      trace_ids=logged_trace_ids,
    )

  # Add trace items to the labeling session
  from databricks.rag_eval.review_app.entities import _get_client
  _get_client().batch_create_items_in_labeling_session(backend_session, trace_ids=logged_trace_ids)

  print(f'Added {len(logged_trace_ids)} traces to labeling session')

  # Return the first trace ID for the UI to use
  first_trace_id = traces.iloc[0]['trace_id']
  return first_trace_id


# Usage example
schemas = create_labeling_schemas()
session = create_labeling_session(schemas)
sample_trace_id = add_traces_to_session(session)

# Add traces to the session for expert review
# Experts can then access the Review App to label traces
print(f'Review App URL: {session.url}')

write_env_variable('SAMPLE_LABELING_SESSION_ID', session.labeling_session_id)
write_env_variable('SAMPLE_REVIEW_APP_URL', session.url)

# Store the sample trace ID for the UI to use
if sample_trace_id:
  write_env_variable('SAMPLE_LABELING_TRACE_ID', sample_trace_id)
  print(f'Sample trace ID for labeling: {sample_trace_id}')
