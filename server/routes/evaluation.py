"""Evaluation routes for running MLflow LLM judge evaluations."""

import json
import logging
import os
from datetime import datetime
from typing import Optional

import mlflow
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from mlflow_demo.utils.mlflow_helpers import get_mlflow_experiment_id
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/evaluation', tags=['evaluation'])

# 10 representative coaching questions for live demo evaluation
EVAL_QUESTIONS = [
  'How does the 2024 Kansas City Chiefs offense approach third-and-long situations?',
  'What are the most common passing concepts used by the 2023 San Francisco 49ers in the red zone?',
  'How does the 2024 Baltimore Ravens offense adjust when facing a blitz-heavy defense?',
  'What tendencies does the 2024 Dallas Cowboys offense show on first down?',
  'Which running plays are most effective for the 2023 Cleveland Browns against a blitz?',
  'How does the 2024 Miami Dolphins offense attack Cover 2 defenses?',
  'What is the typical play sequence for the 2024 Buffalo Bills with under two minutes left in the half?',
  'How does the 2024 Green Bay Packers offense change their approach in the red zone?',
  'Which receivers are most targeted by the 2024 Los Angeles Rams on third down?',
  'How does the 2024 New England Patriots offense exploit man-to-man coverage?',
]


class RunEvalRequest(BaseModel):
  """Request to run evaluation with selected scorers."""

  builtin_judges: list[str] = []
  custom_guidelines: list[dict] = []


class RunSessionEvalRequest(BaseModel):
  """Request to run session-level evaluation with selected scorers."""

  session_judges: list[str] = []


@router.post('/run')
async def run_evaluation(request: RunEvalRequest):
  """Run mlflow.genai.evaluate() with selected scorers, streaming progress via SSE."""

  async def generate():
    from mlflow.genai.scorers import Guidelines

    try:
      # Set experiment
      mlflow.set_experiment(experiment_id=get_mlflow_experiment_id())

      # Build scorers list
      scorers = []

      # Add built-in judges
      from mlflow.genai import scorers as mlflow_scorers

      # Map frontend checkbox names to actual scorer classes
      builtin_map = {
        'RelevanceToQuery': mlflow_scorers.RelevanceToQuery,
        'Safety': mlflow_scorers.Safety,
        'ToolCallCorrectness': mlflow_scorers.ToolCallCorrectness,
        'ToolCallEfficiency': mlflow_scorers.ToolCallEfficiency,
      }

      logger.info(f'Requested built-in judges: {request.builtin_judges}')
      logger.info(f'Available builtin_map keys: {list(builtin_map.keys())}')

      for name in request.builtin_judges:
        if name in builtin_map:
          scorers.append(builtin_map[name]())
          logger.info(f'Added built-in scorer: {name}')
        else:
          logger.warning(f'Built-in scorer not found: {name}')

      # Add custom guidelines judges (always included)
      logger.info(f'Requested custom guidelines: {[g.get("name") for g in request.custom_guidelines]}')
      for g in request.custom_guidelines:
        if g.get('name') and g.get('guideline'):
          scorers.append(Guidelines(name=g['name'], guidelines=g['guideline']))
          logger.info(f'Added custom guideline scorer: {g["name"]}')

      total_questions = len(EVAL_QUESTIONS)
      total_scorers = len(scorers)
      logger.info(f'Total scorers built: {total_scorers} ({[type(s).__name__ for s in scorers]})')

      yield f'data: {json.dumps({"type": "start", "total_questions": total_questions, "total_scorers": total_scorers})}\n\n'

      logger.info(
        f'Starting evaluation: {total_questions} questions, {total_scorers} scorers'
      )

      # Build evaluation data - match notebook pattern
      # 'input' key matches predict_fn parameter name
      from mlflow_demo.agent import AGENT

      eval_data = [
        {'inputs': {'input': [{'role': 'user', 'content': q}]}}
        for q in EVAL_QUESTIONS
      ]

      def predict_fn(input):
        AGENT.start_new_session()
        return AGENT.predict({'input': input})

      # Send progress updates as we go
      # We'll run the actual evaluation and stream progress
      yield f'data: {json.dumps({"type": "progress", "step": "loading", "message": "Loading agent and scorers...", "percent": 5})}\n\n'

      yield f'data: {json.dumps({"type": "progress", "step": "running", "message": f"Running {total_scorers} scorers against {total_questions} questions...", "percent": 15})}\n\n'

      # Run mlflow.genai.evaluate()
      from datetime import datetime

      with mlflow.start_run(
        run_name=f'{datetime.now().strftime("%Y%m%d_%H%M%S")}_dc_eval'
      ) as run:
        results = mlflow.genai.evaluate(
          data=eval_data,
          predict_fn=predict_fn,
          scorers=scorers,
        )
        run_id = run.info.run_id

      yield f'data: {json.dumps({"type": "progress", "step": "finalizing", "message": "Finalizing results...", "percent": 90})}\n\n'

      # Extract summary metrics
      metrics_summary = {}
      if hasattr(results, 'metrics') and results.metrics:
        metrics_summary = {
          k: v for k, v in results.metrics.items() if isinstance(v, (int, float))
        }

      yield f'data: {json.dumps({"type": "done", "run_id": run_id, "metrics": metrics_summary, "percent": 100})}\n\n'

      logger.info(f'Evaluation complete. Run ID: {run_id}')

    except Exception as e:
      logger.error(f'Evaluation error: {e}')
      yield f'data: {json.dumps({"type": "error", "error": str(e)})}\n\n'

  return StreamingResponse(
    generate(),
    media_type='text/event-stream',
    headers={
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  )


# Dataset name for session-level evaluation traces
SESSION_EVAL_DATASET = 'short_eval_session_set'


@router.post('/run-session')
async def run_session_evaluation(request: RunSessionEvalRequest):
  """Run session-level evaluation on pre-collected multi-turn traces via SSE."""

  async def generate():
    try:
      from mlflow.genai import scorers as mlflow_scorers
      from datetime import datetime

      exp_id = get_mlflow_experiment_id()
      mlflow.set_experiment(experiment_id=exp_id)

      # Map frontend names to session-level scorer classes
      session_scorer_map = {
        'ConversationCompleteness': mlflow_scorers.ConversationCompleteness,
        'ConversationalRoleAdherence': mlflow_scorers.ConversationalRoleAdherence,
        'ConversationalSafety': mlflow_scorers.ConversationalSafety,
        'ConversationalToolCallEfficiency': mlflow_scorers.ConversationalToolCallEfficiency,
        'KnowledgeRetention': mlflow_scorers.KnowledgeRetention,
        'UserFrustration': mlflow_scorers.UserFrustration,
      }

      # Build scorers
      scorers = []
      for name in request.session_judges:
        if name in session_scorer_map:
          scorers.append(session_scorer_map[name]())
          logger.info(f'Added session scorer: {name}')
        else:
          logger.warning(f'Session scorer not found: {name}')

      total_scorers = len(scorers)
      logger.info(f'Session evaluation: {total_scorers} scorers')

      yield f'data: {json.dumps({"type": "start", "total_scorers": total_scorers})}\n\n'

      # Load trace IDs from the evaluation dataset
      catalog = os.environ.get('UC_CATALOG', '')
      schema = os.environ.get('UC_SCHEMA', '')
      dataset_name = f'{catalog}.{schema}.{SESSION_EVAL_DATASET}'

      logger.info(f'Loading dataset: {dataset_name}')
      ds = mlflow.genai.datasets.get_dataset(name=dataset_name)
      df = ds.to_df()

      trace_ids = set()
      for _, row in df.iterrows():
        source = row.get('source', {})
        if isinstance(source, dict) and 'trace' in source:
          trace_ids.add(source['trace']['trace_id'])

      logger.info(f'Dataset contains {len(trace_ids)} trace IDs')

      yield f'data: {json.dumps({"type": "progress", "message": f"Loaded {len(trace_ids)} traces from dataset"})}\n\n'

      # Load actual trace objects with session metadata
      filter_str = 'metadata.`mlflow.trace.session` != ""'
      all_traces = mlflow.search_traces(
        locations=[exp_id],
        filter_string=filter_str,
        return_type='list',
        max_results=100,
      )

      # Filter to only traces in our dataset
      dataset_traces = [t for t in all_traces if t.info.request_id in trace_ids]
      logger.info(f'Matched {len(dataset_traces)} traces from experiment')

      if not dataset_traces:
        yield f'data: {json.dumps({"type": "error", "error": "No matching traces found in experiment"})}\n\n'
        return

      # Count sessions
      sessions = set()
      for t in dataset_traces:
        sid = t.info.request_metadata.get('mlflow.trace.session', '')
        if sid:
          sessions.add(sid)

      yield f'data: {json.dumps({"type": "progress", "message": f"Evaluating {len(sessions)} sessions ({len(dataset_traces)} traces) with {total_scorers} scorers..."})}\n\n'

      # Run mlflow.genai.evaluate with session-level scorers
      with mlflow.start_run(
        run_name=f'{datetime.now().strftime("%Y%m%d_%H%M%S")}_session_eval'
      ) as run:
        results = mlflow.genai.evaluate(
          data=dataset_traces,
          scorers=scorers,
        )
        run_id = run.info.run_id

      # Extract summary metrics
      metrics_summary = {}
      if hasattr(results, 'metrics') and results.metrics:
        metrics_summary = {
          k: v for k, v in results.metrics.items() if isinstance(v, (int, float))
        }

      yield f'data: {json.dumps({"type": "done", "run_id": run_id, "metrics": metrics_summary, "sessions": len(sessions), "traces": len(dataset_traces)})}\n\n'

      logger.info(f'Session evaluation complete. Run ID: {run_id}')

    except Exception as e:
      logger.error(f'Session evaluation error: {e}')
      yield f'data: {json.dumps({"type": "error", "error": str(e)})}\n\n'

  return StreamingResponse(
    generate(),
    media_type='text/event-stream',
    headers={
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  )


class ReviewAppResponse(BaseModel):
  """Response with the review app URL."""

  success: bool
  url: Optional[str] = None
  error: Optional[str] = None


@router.get('/review-app-url', response_model=ReviewAppResponse)
async def get_review_app_url():
  """Get the review app URL for the most recent labeling session."""
  try:
    from mlflow.genai import get_labeling_sessions

    exp_id = get_mlflow_experiment_id()
    mlflow.set_experiment(experiment_id=exp_id)

    # Find the most recent labeling session with the football_analysis_base schema
    sessions = get_labeling_sessions()
    if sessions:
      # Prefer sessions with the football_analysis_base schema
      for s in reversed(sessions):
        schemas = s.label_schemas if hasattr(s, 'label_schemas') else []
        if 'football_analysis_base' in schemas:
          url = s.url if hasattr(s, 'url') else None
          if url:
            return ReviewAppResponse(success=True, url=url)

      # Fallback to most recent session if none match
      latest = sessions[-1]
      url = latest.url if hasattr(latest, 'url') else None
      if url:
        return ReviewAppResponse(success=True, url=url)

    # Fallback: return the review app root
    from mlflow.genai import get_review_app
    review_app = get_review_app(experiment_id=exp_id)
    url = review_app.url if hasattr(review_app, 'url') else None
    return ReviewAppResponse(success=True, url=url)

  except Exception as e:
    logger.error(f'Failed to get review app URL: {e}')
    return ReviewAppResponse(success=False, error=str(e))


class CreateLabelingSessionResponse(BaseModel):
  """Response from creating a labeling session."""

  success: bool
  session_url: Optional[str] = None
  session_name: Optional[str] = None
  error: Optional[str] = None


@router.post('/create-labeling-session', response_model=CreateLabelingSessionResponse)
async def create_labeling_session_endpoint():
  """Create labeling schemas, a labeling session, and add recent traces for SME review."""
  try:
    from mlflow.genai import create_labeling_session, label_schemas

    exp_id = get_mlflow_experiment_id()
    mlflow.set_experiment(experiment_id=exp_id)

    # Ensure label schema exists (matches the football_analysis_base judge name)
    # CRITICAL: schema name must match judge name for align() to work
    LABEL_SCHEMA_NAME = 'football_analysis_base'
    try:
      label_schemas.create_label_schema(
        name=LABEL_SCHEMA_NAME,
        type='feedback',
        title=LABEL_SCHEMA_NAME,
        input=label_schemas.InputCategorical(
          options=['1', '2', '3', '4', '5'],
        ),
        instruction=(
          'Evaluate if the response appropriately analyzes the available data and provides an actionable recommendation '
          'for the question. The response should be accurate, contextually relevant, and give a strategic advantage to the '
          'person making the request. '
          '\n\n Your grading criteria should be: '
          '\n 1: Completely unacceptable. Incorrect data interpretation or no recommendations'
          '\n 2: Mostly unacceptable. Irrelevant or spurious feedback or weak recommendations provided with minimal strategic advantage'
          '\n 3: Somewhat acceptable. Relevant feedback provided with some strategic advantage'
          '\n 4: Mostly acceptable. Relevant feedback provided with strong strategic advantage'
          '\n 5: Completely acceptable. Relevant feedback provided with excellent strategic advantage'
        ),
        enable_comment=True,
      )
      logger.info(f'Created label schema: {LABEL_SCHEMA_NAME}')
    except Exception as schema_err:
      # Schema already exists — that's fine, reuse it
      logger.info(f'Label schema {LABEL_SCHEMA_NAME} already exists, reusing: {schema_err}')

    # Create the labeling session
    session_name = f'{datetime.now().strftime("%Y%m%d_%H%M%S")}_dc_assistant_review'
    session = create_labeling_session(
      name=session_name,
      assigned_users=[],
      label_schemas=[LABEL_SCHEMA_NAME],
    )
    logger.info(f'Created labeling session: {session_name}')

    # Search for recent OK traces and add them to the session
    traces = mlflow.search_traces(
      locations=[exp_id],
      filter_string='status = "OK"',
      max_results=20,
      order_by=['timestamp DESC'],
      return_type='pandas',
    )

    if len(traces) > 0:
      # Rename columns for merge_records compatibility
      if 'inputs' not in traces.columns and 'request' in traces.columns:
        traces = traces.rename(columns={'request': 'inputs'})
      if 'outputs' not in traces.columns and 'response' in traces.columns:
        traces = traces.rename(columns={'response': 'outputs'})

      from mlflow.genai.datasets import create_dataset, get_dataset

      catalog = os.environ.get('UC_CATALOG', '')
      schema = os.environ.get('UC_SCHEMA', '')
      dataset_name = f'{catalog}.{schema}.dc_labeling_dataset'
      try:
        ds = get_dataset(name=dataset_name)
      except Exception:
        ds = create_dataset(name=dataset_name)

      ds.merge_records(traces)
      session.add_dataset(dataset_name=dataset_name)
      logger.info(f'Added {len(traces)} traces to labeling session')

    session_url = session.url if hasattr(session, 'url') else None
    logger.info(f'Labeling session URL: {session_url}')

    return CreateLabelingSessionResponse(
      success=True,
      session_url=session_url,
      session_name=session_name,
    )

  except Exception as e:
    logger.error(f'Failed to create labeling session: {e}')
    return CreateLabelingSessionResponse(
      success=False,
      error=str(e),
    )
