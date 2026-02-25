import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import dotenv

# Load environment variables from .env.local in project root
dotenv.load_dotenv(project_root / '.env.local')

# allow databricks-cli auth to take over
os.environ.pop('DATABRICKS_TOKEN', None)

import mlflow
from mlflow.entities import DatasetInput, LoggedModelInput

# Unity Catalog schema to store the prompt in
UC_CATALOG = os.environ.get('UC_CATALOG')
UC_SCHEMA = os.environ.get('UC_SCHEMA')
PROMPT_ALIAS = os.environ.get('PROMPT_ALIAS')
PROMPT_NAME = os.environ.get('PROMPT_NAME')

import logging
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("mlflow").setLevel(logging.ERROR)


# Exit if required environment variables are not set
if not UC_CATALOG or not UC_SCHEMA or not PROMPT_ALIAS or not PROMPT_NAME:
  print(
    'Error: UC_CATALOG, UC_SCHEMA, PROMPT_ALIAS, and PROMPT_NAME environment variables must be set'
  )
  sys.exit(1)

import json

from databricks.sdk import WorkspaceClient
from mlflow import MlflowClient
from mlflow.genai.datasets import create_dataset, get_dataset
from mlflow_demo.agent.prompts import FIXED_PROMPT_TEMPLATE

# Constants
FIX_DATASET_NAME = 'low_accuracy'
REGRESSION_DATASET_NAME = 'regression_set'

# Import the scorers from the updated evaluator module
from mlflow_demo.evaluation.evaluator import SCORERS, DEV_PROMPT_ALIAS
from mlflow_demo.agent.agent import AGENT
from mlflow_demo.utils.mlflow_helpers import get_mlflow_experiment_id, ensure_https_protocol


def predict_fn(question: str):
  """Predict function for evaluation using the DC assistant agent."""
  from mlflow.types.responses import Message, ResponsesAgentRequest

  request = ResponsesAgentRequest(
    input=[Message(role='user', content=question)]
  )
  response = AGENT.predict(request)

  # Extract text from the response
  for item in reversed(response.output):
    item_dict = item.model_dump() if hasattr(item, 'model_dump') else (item if isinstance(item, dict) else {})
    if item_dict.get('type') == 'message' and item_dict.get('role') == 'assistant':
      content = item_dict.get('content', [])
      if isinstance(content, list) and len(content) > 0:
        if isinstance(content[0], dict) and 'text' in content[0]:
          return content[0]['text']
  return str(response.output)


def run_single_evaluation(dataset_name, eval_run_name):
  dataset = mlflow.genai.datasets.get_dataset(
      uc_table_name=f'{UC_CATALOG}.{UC_SCHEMA}.{dataset_name}',
    )

  # Run evaluations
  print('Running evaluation...')
  with mlflow.start_run(run_name=f'{eval_run_name}') as run:
      eval_results = mlflow.genai.evaluate(
          data=dataset,
          predict_fn=predict_fn,
          scorers=SCORERS,
      )

  return eval_results.run_id


def register_new_prompt():
  # Register the new prompt and set alias
  print('Registering new prompt...')
  new_prompt = mlflow.genai.register_prompt(
      name=f'{UC_CATALOG}.{UC_SCHEMA}.{PROMPT_NAME}',
      template=FIXED_PROMPT_TEMPLATE,
      commit_message='Improved NFL DC assistant prompt with detailed instructions.',
  )

  mlflow.genai.set_prompt_alias(
      name=f'{UC_CATALOG}.{UC_SCHEMA}.{PROMPT_NAME}',
      alias=DEV_PROMPT_ALIAS,
      version=new_prompt.version,
  )


def run_both_evals():
  register_new_prompt()

  run_id_low_accuracy = run_single_evaluation(
      dataset_name=FIX_DATASET_NAME,
      eval_run_name='low_accuracy_new_prompt',
  )
  print(f'Low accuracy eval run ID: {run_id_low_accuracy}')

  low_accuracy_results_original_run_id = os.getenv('FIX_QUALITY_BASELINE_RUN_ID')
  regression_results_original_run_id = os.getenv('REGRESSION_BASELINE_RUN_ID')

  import mlflow

  if mlflow.utils.databricks_utils.is_in_databricks_notebook():
    databricks_host = ensure_https_protocol(mlflow.utils.databricks_utils.get_browser_hostname())
  else:
    databricks_host = ensure_https_protocol(os.getenv('DATABRICKS_HOST'))

  write_env_variable('LOW_ACCURACY_RESULTS_URL', f'{databricks_host}/ml/experiments/{get_mlflow_experiment_id()}/evaluation-runs?selectedRunUuid={run_id_low_accuracy}&compareToRunUuid={low_accuracy_results_original_run_id}')

  # Run regression eval only if the dataset has records
  regression_dataset = mlflow.genai.datasets.get_dataset(
    uc_table_name=f'{UC_CATALOG}.{UC_SCHEMA}.{REGRESSION_DATASET_NAME}',
  )
  regression_df = regression_dataset.to_df()
  if len(regression_df) > 0:
    run_id_regression = run_single_evaluation(
        dataset_name=REGRESSION_DATASET_NAME,
        eval_run_name='regression_new_prompt',
    )
    print(f'Regression eval run ID: {run_id_regression}')
    write_env_variable('REGRESSION_RESULTS_URL', f'{databricks_host}/ml/experiments/{get_mlflow_experiment_id()}/evaluation-runs?selectedRunUuid={run_id_regression}&compareToRunUuid={regression_results_original_run_id}')
  else:
    print('Skipping regression eval — no regression traces found')


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


def add_all_evals():
  traces = mlflow.search_traces()

  # load evals for all records
  with mlflow.start_run(run_name='load_all_evals'):
    load_evals = mlflow.genai.evaluate(
      data=traces,
      scorers=SCORERS,
    )

  mlflow.delete_run(run_id=load_evals.run_id)


def add_traces_to_run(run_id: str, trace_ids: list[str]):
  client.link_traces_to_run(trace_ids=trace_ids, run_id=run_id)


def traces_to_records(filter_string: str) -> list[dict]:
  """Convert search_traces results to records with 'inputs' for merge_records."""
  traces = mlflow.search_traces(filter_string=filter_string, return_type='list')
  return [
    {'inputs': {'question': t.info.request_preview}, 'trace_id': t.info.trace_id}
    for t in traces
  ]


def get_or_create_dataset(name: str):
  """Get an existing dataset or create a new one."""
  try:
    return get_dataset(uc_table_name=name)
  except Exception:
    return create_dataset(uc_table_name=name)


def create_and_add_fix_quality_dataset():
  dataset_name = f'{UC_CATALOG}.{UC_SCHEMA}.{FIX_DATASET_NAME}'
  dataset = get_or_create_dataset(dataset_name)
  records = traces_to_records('tags.eval_example = "yes"')
  if records:
    dataset.merge_records(records)
  return get_dataset(uc_table_name=dataset_name)


def create_and_add_dataset_regression():
  dataset_name = f'{UC_CATALOG}.{UC_SCHEMA}.{REGRESSION_DATASET_NAME}'
  dataset = get_or_create_dataset(dataset_name)
  records = traces_to_records('tags.eval_example = "regression"')
  if records:
    dataset.merge_records(records)
  return get_dataset(uc_table_name=dataset_name)


def make_eval_datasets_and_baseline_runs_for_prompt_test():
  # get all traces
  traces = mlflow.search_traces(return_type='list', filter_string='tags.sample_data = "yes"')

  failed_accuracy = []
  passed_all = []

  MLFLOW_EXPERIMENT_ID = os.getenv('MLFLOW_EXPERIMENT_ID')

  print('Finding traces for eval and regression datasets...')
  for trace in traces:
    number_passes = 0
    if len(trace.info.assessments) == 0:
      print(f'no assessments for {trace.info.trace_id}, deleting it')
      client.delete_traces(experiment_id=trace.info.experiment_id, trace_ids=[trace.info.trace_id])
    is_bad_example = False
    for assessment in trace.info.assessments:
      if assessment.name == 'accuracy' and assessment.feedback.value == 'no':
        if len(failed_accuracy) < 5 and trace.info.trace_id not in failed_accuracy:
          failed_accuracy.append(trace.info.trace_id)
          is_bad_example = True
      elif assessment.name == 'relevance' and assessment.feedback.value == 'yes':
        number_passes += 1
      elif assessment.name == 'actionability' and assessment.feedback.value == 'yes':
        number_passes += 1
      elif assessment.name == 'accuracy' and assessment.feedback.value == 'yes':
        number_passes += 1
    if number_passes >= 2 and not is_bad_example:
      if len(passed_all) < 5 and trace.info.trace_id not in passed_all:
        passed_all.append(trace.info.trace_id)

  print(
    f'Found {len(failed_accuracy)} traces for low accuracy and {len(passed_all)} traces for regression, adding tags'
  )
  for trace_id in failed_accuracy:
    print(f"Low accuracy trace_id: {trace_id}")
    mlflow.set_trace_tag(trace_id=trace_id, key='eval_example', value='yes')

  for trace_id in passed_all:
    print(f"Regression set trace_id: {trace_id}")
    mlflow.set_trace_tag(trace_id=trace_id, key='eval_example', value='regression')

  print('Creating and adding traces to eval datasets...')
  fix_quality_dataset = create_and_add_fix_quality_dataset()
  regression_dataset = create_and_add_dataset_regression()

  print('Creating evaluation runs...')

  active_model = mlflow.set_active_model(name=f'{PROMPT_NAME}@{PROMPT_ALIAS}@v1')

  regression_baseline_run = client.create_run(
    experiment_id=MLFLOW_EXPERIMENT_ID, run_name='regression_original_prompt'
  )

  mlflow.start_run(run_id=regression_baseline_run.info.run_id)

  if passed_all:
    add_traces_to_run(regression_baseline_run.info.run_id, trace_ids=passed_all)

  client.log_inputs(
    run_id=regression_baseline_run.info.run_id,
    datasets=[DatasetInput(regression_dataset._to_mlflow_entity())],
    models=[LoggedModelInput(model_id=active_model.model_id)],
  )

  mlflow.end_run()

  fix_quality_baseline_run = client.create_run(
    experiment_id=MLFLOW_EXPERIMENT_ID, run_name='low_accuracy_original_prompt'
  )

  mlflow.start_run(run_id=fix_quality_baseline_run.info.run_id)

  if failed_accuracy:
    add_traces_to_run(fix_quality_baseline_run.info.run_id, trace_ids=failed_accuracy)

  client.log_inputs(
    run_id=fix_quality_baseline_run.info.run_id,
    datasets=[DatasetInput(fix_quality_dataset._to_mlflow_entity())],
    models=[LoggedModelInput(model_id=active_model.model_id)],
  )

  mlflow.end_run()

  print('Writing run IDs to env variables...')

  write_env_variable('REGRESSION_BASELINE_RUN_ID', regression_baseline_run.info.run_id)
  write_env_variable('FIX_QUALITY_BASELINE_RUN_ID', fix_quality_baseline_run.info.run_id)

  # reload these env vars for use by the backend in running example evals
  dotenv.load_dotenv(project_root / '.env.local')

LATEST_TRACE_EVALUATION_TIMESTAMP_MS_TAG = "mlflow.latestTraceEvaluationTimestampMs"

def tag_experiment_to_not_run_monitoring():
  """Set the monitoring tag so that monitoring job doesn't rerun evals on the traces we just evaluated above"""
  traces = mlflow.search_traces(return_type='list')
  latest_timestamp_ms = max(trace.info.timestamp_ms for trace in traces)

  client.set_experiment_tag(experiment_id=os.getenv('MLFLOW_EXPERIMENT_ID'), key=LATEST_TRACE_EVALUATION_TIMESTAMP_MS_TAG, value=str(latest_timestamp_ms))


if __name__ == '__main__':
  w = WorkspaceClient()

  client = MlflowClient()
  add_all_evals()
  make_eval_datasets_and_baseline_runs_for_prompt_test()

  run_both_evals()
  tag_experiment_to_not_run_monitoring()
