"""MLflow evaluation logic for DC Assistant football analysis."""

import os

import mlflow
from mlflow.genai.judges import meets_guidelines
from mlflow.genai.scorers import Guidelines, RelevanceToQuery, scorer
from mlflow.genai import make_judge

from mlflow_demo.utils.mlflow_helpers import generate_evaluation_links

# Prompt registry configuration
DEV_PROMPT_ALIAS = 'development'


def validate_env_vars():
  """Validate required environment variables are set."""
  PROMPT_NAME = os.getenv('PROMPT_NAME')
  PROMPT_ALIAS = os.getenv('PROMPT_ALIAS')
  if not PROMPT_NAME or not PROMPT_ALIAS:
    raise Exception('PROMPT_NAME and PROMPT_ALIAS environment variables must be set')
  return PROMPT_NAME, PROMPT_ALIAS


REGRESSION_DATASET_NAME = 'regression_set'
FIX_DATASET_NAME = 'low_accuracy'

UC_CATALOG = os.environ.get('UC_CATALOG')
UC_SCHEMA = os.environ.get('UC_SCHEMA')

# Football Language Guideline - Ensure appropriate professional football terminology
football_language_judge = Guidelines(
  name='football_language',
  guidelines='The response must use language that is appropriate for professional football players and coaches',
)

# Football Analysis Judge - Custom judge with Likert scale for analysis quality
football_analysis_judge = make_judge(
  name='football_analysis_base',
  instructions=(
    'Evaluate if the response in {{ outputs }} appropriately analyzes the available data and provides an actionable recommendation '
    'the question in {{ inputs }}. The response should be accurate, contextually relevant, and give a strategic advantage to the '
    'person making the request. '
    'Your grading criteria should be: '
    ' 1: Completely unacceptable. Incorrect data interpretation or no recommendations'
    ' 2: Mostly unacceptable. Irrelevant or spurious feedback or weak recommendations provided with minimal strategic advantage'
    ' 3: Somewhat acceptable. Relevant feedback provided with some strategic advantage'
    ' 4: Mostly acceptable. Relevant feedback provided with strong strategic advantage'
    ' 5: Completely acceptable. Relevant feedback provided with excellent strategic advantage'
  ),
  feedback_value_type=int,
)

# Convenience list of all scorers for easy use in evaluation
SCORERS = [RelevanceToQuery(), football_analysis_judge, football_language_judge]


def run_evaluation():
  """Run evaluation on recent traces."""
  print('\nLoading recent traces from DC Assistant...')

  # Load recent traces for evaluation
  traces = mlflow.search_traces(
    max_results=3,
    filter_string='status = "OK"',
    order_by=['timestamp DESC'],
  )
  print(f'Found {len(traces)} traces for evaluation')

  # Run evaluation using scorers
  eval_results = mlflow.genai.evaluate(data=traces, scorers=SCORERS)

  print('\nEvaluation completed!')
  print(f'Run ID: {eval_results._run_id}')

  # Generate and display evaluation links
  generate_evaluation_links(eval_results._run_id)

  return eval_results
