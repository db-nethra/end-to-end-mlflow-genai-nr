"""MLflow evaluation logic for the NFL Defensive Coordinator Assistant."""

import os

import mlflow
from mlflow.genai.judges import make_judge
from mlflow.genai.scorers import Guidelines, Safety, RelevanceToQuery

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

# --- Built-in Scorers ---

# Tone of voice Guideline - Ensure professional tone
tone = Guidelines(
  name='tone',
  guidelines='The response maintains a professional, knowledgeable coaching tone appropriate for an NFL defensive coordinator assistant.',
)

# Built-in safety scorer - checks for harmful content
safety = Safety()

# Built-in relevance scorer - checks if response addresses the user's request
relevance_to_query = RelevanceToQuery()

# --- Custom Judges via make_judge() ---

accuracy = make_judge(
  name='accuracy',
  instructions="""Evaluate whether the agent's response correctly references factual information from the execution trace.

  Analyze the full execution {{ trace }} to find tool call results, then assess the response against these rules:
  - All statistics (percentages, counts, ratios) must match the data returned by tools
  - Player names, team names, and formation names must be accurate
  - Tendencies described must be supported by the queried data
  - No fabricated statistics or invented game situations
  - If tools returned no data, the response should acknowledge the lack of data rather than guess
  - It is acceptable to provide general football knowledge as context, but specific claims must be data-backed

  Respond with 'yes' if the response is factually accurate, or 'no' if it contains errors or fabrications.""",
)

relevance = make_judge(
  name='relevance',
  instructions="""Evaluate whether the agent's response directly addresses the user's question.

  User's request: {{ inputs }}
  Agent's response: {{ outputs }}

  Assess based on these rules:
  - The response focuses on the specific game situation, down/distance, or tendency asked about
  - Defensive recommendations are relevant to the offensive tendency described
  - The response does not go off-topic with unrelated football analysis
  - If the question asks about a specific scenario, the answer addresses that scenario
  - Statistical breakdowns should be relevant to the question context

  Respond with 'yes' if the response is relevant, or 'no' if it is off-topic or misses the question.""",
)

actionability = make_judge(
  name='actionability',
  instructions="""Evaluate whether the agent's response provides actionable defensive insights.

  Agent's response: {{ outputs }}

  Assess based on these rules:
  - Includes specific defensive adjustments or play calls when relevant
  - Recommendations are practical and implementable in a game plan
  - Addresses personnel matchups or coverage adjustments when applicable
  - Avoids vague advice like 'be prepared' without specifics
  - When data supports it, suggests specific defensive formations or blitz packages

  Respond with 'yes' if the response is actionable, or 'no' if it is vague or unhelpful.""",
)

response_is_grounded = make_judge(
  name='response_is_grounded',
  instructions="""Evaluate whether the agent's response is grounded in the data retrieved by tool calls.

  Analyze the full execution {{ trace }} to find tool call results, then assess whether:
  - The response only makes claims supported by tool output data
  - Statistics and specific facts cited in the response appear in the tool results
  - The response does not hallucinate data that was not returned by any tool
  - If no tool data was retrieved, the response acknowledges the lack of data

  Respond with 'yes' if the response is grounded in tool results, or 'no' if it contains hallucinated or unsupported claims.""",
)

# Convenience list of all scorers for easy use in evaluation
SCORERS = [tone, safety, relevance_to_query, accuracy, relevance, actionability, response_is_grounded]


def run_evaluation():
  """Run evaluation on recent traces."""
  print('\n🔍 Loading recent traces from the DC assistant...')

  # Load recent traces for evaluation
  traces = mlflow.search_traces(
    max_results=3,
    filter_string='status = "OK"',
    order_by=['timestamp DESC'],
  )
  print(f'✅ Found {len(traces)} traces for evaluation')

  # Now, let's run evaluation using this scorer
  eval_results = mlflow.genai.evaluate(data=traces, scorers=SCORERS)

  print('\n📊 Evaluation completed!')
  print(f'🆔 Run ID: {eval_results.run_id}')

  # Generate and display evaluation links
  generate_evaluation_links(eval_results.run_id)

  return eval_results
