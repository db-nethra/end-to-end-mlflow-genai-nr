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



from mlflow.genai.judges import make_judge
from mlflow.genai.scorers import (
  Guidelines, Safety, RelevanceToQuery,
  ScorerSamplingConfig, delete_scorer,
)

import logging
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("mlflow").setLevel(logging.ERROR)


# Unity Catalog schema to store the prompt in
UC_CATALOG = os.environ.get('UC_CATALOG')
UC_SCHEMA = os.environ.get('UC_SCHEMA')
# Exit if required environment variables are not set
if not UC_CATALOG or not UC_SCHEMA:
  print('Error: UC_CATALOG and UC_SCHEMA environment variables must be set')
  sys.exit(1)


# --- Built-in Scorers ---

tone = Guidelines(
  name='tone',
  guidelines='The response maintains a professional, knowledgeable coaching tone appropriate for an NFL defensive coordinator assistant.',
)

safety = Safety()

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

# All scorers to register for production monitoring
MONITORING_SCORERS = [tone, safety, relevance_to_query, accuracy, relevance, actionability, response_is_grounded]

for judge in MONITORING_SCORERS:
  # Register each scorer/judge with MLflow, then start monitoring
  try:
    registered = judge.register()
  except Exception as e:
    print(f'⚠️ Warning: Scorer {judge.name} registration failed or already exists: {e}')
    print('   Attempting to re-register by deleting existing scorer...')
    delete_scorer(name=judge.name)
    registered = judge.register()

  registered.start(sampling_config=ScorerSamplingConfig(sample_rate=1))
  print(f'✅ Registered and started scorer: {judge.name}')



