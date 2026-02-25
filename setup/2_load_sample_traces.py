import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import mlflow

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
import os

import dotenv

# Load environment variables from .env.local in project root
dotenv.load_dotenv(project_root / '.env.local')

# allow databricks-cli auth to take over
os.environ.pop('DATABRICKS_TOKEN', None)

import logging
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("mlflow").setLevel(logging.ERROR)

# Link the experiment to UC schema and set tracing destination
# This ensures the OTEL spans tables exist before we log traces
from mlflow_demo.utils.mlflow_helpers import link_experiment_to_uc_schema, setup_tracing_destination
mlflow.set_experiment(experiment_id=os.environ['MLFLOW_EXPERIMENT_ID'])
link_experiment_to_uc_schema()
setup_tracing_destination()

from mlflow_demo.agent.agent import AGENT

PROMPT_NAME = os.getenv('PROMPT_NAME')
PROMPT_ALIAS = os.getenv('PROMPT_ALIAS')
if not PROMPT_NAME or not PROMPT_ALIAS:
  raise Exception('PROMPT_NAME and PROMPT_ALIAS environment variables must be set')
UC_CATALOG = os.environ.get('UC_CATALOG')
UC_SCHEMA = os.environ.get('UC_SCHEMA')


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


def generate_trace_for_question(question, line_num):
  """Generate a trace by asking the DC assistant a question."""
  try:
    print(f'Creating sample trace {line_num}: {question[:60]}...')

    from mlflow.types.responses import Message, ResponsesAgentRequest

    request = ResponsesAgentRequest(
      input=[Message(role='user', content=question)]
    )
    response = AGENT.predict(request)

    trace_id = mlflow.get_last_active_trace_id()

    # add a tag so we know what is our sample data
    if trace_id:
      mlflow.set_trace_tag(trace_id=trace_id, key='sample_data', value='yes')

    return {'trace_id': trace_id, 'question': question, 'line_number': line_num}, None

  except Exception as e:
    error_msg = f'Error generating trace for line {line_num}: {e}'
    print(error_msg)
    return None, error_msg


def process_input_data(input_file='input_data.jsonl', max_workers=3, max_records=10):
  """Load input_data.jsonl and run the DC assistant for every question.

  Args:
      input_file (str): Path to input JSONL file
      max_workers (int): Maximum number of parallel workers
      max_records (int): Maximum number of records to process
  """
  script_dir = Path(__file__).parent
  input_path = script_dir / input_file

  if not input_path.exists():
    print(f'Error: Input file {input_path} not found!')
    return

  # Load all questions
  questions = []
  with open(input_path, 'r', encoding='utf-8') as f:
    for line_num, line in enumerate(f, 1):
      try:
        data = json.loads(line.strip())
        questions.append((data.get('question', ''), line_num))
      except json.JSONDecodeError as e:
        print(f'Error parsing JSON on line {line_num}: {e}')

  if not questions:
    print('No valid questions found!')
    return

  # limit to the max records
  questions = questions[:max_records]

  print(f'Adding {len(questions)} sample traces using {max_workers} workers...')

  results = []
  error_count = 0

  # Process questions in parallel
  with ThreadPoolExecutor(max_workers=max_workers) as executor:
    future_to_question = {
      executor.submit(generate_trace_for_question, question, line_num): (
        question,
        line_num,
      )
      for question, line_num in questions
    }

    for future in as_completed(future_to_question):
      result, error = future.result()
      if result:
        results.append(result)
      if error:
        error_count += 1

  print('Sample data loaded!')
  print(f'Total processed: {len(results)}')
  print(f'Total errors: {error_count}')


def save_trace_id_sample():
  traces = mlflow.search_traces(max_results=1, return_type='list')
  trace_id = traces[0].info.trace_id
  mlflow.log_feedback(
    trace_id=trace_id,
    name='user_feedback',
    value=True,
    rationale='Great defensive analysis with actionable insights!',
    source=mlflow.entities.AssessmentSource(
      source_type='HUMAN',
      source_id='coach@team.com',
    ),
  )

  write_env_variable('SAMPLE_TRACE_ID', trace_id)


if __name__ == '__main__':
  process_input_data()
  save_trace_id_sample()
