import React from "react";
import { StepLayout } from "@/components/step-layout";
import { CodeSnippet } from "@/components/code-snippet";
import { CollapsibleSection } from "@/components/collapsible-section";
import { MarkdownContent } from "@/components/markdown-content";
import { DcTracingDemo } from "@/components/dc-assistant/DcTracingDemo";
import { MultiToolDemo } from "@/components/dc-assistant/MultiToolDemo";
import { MultiTurnDemo } from "@/components/dc-assistant/MultiTurnDemo";
import { QuestionTester } from "@/components/dc-assistant/QuestionTester";
import { Button } from "@/components/ui/button";
import { ExternalLink } from "lucide-react";
import { useQueryPreloadedResults } from "@/queries/useQueryPreloadedResults";
import { useQueryExperiment } from "@/queries/useQueryTracing";
import { NotebookReference } from "@/components/notebook-reference";

const introContent = `
# MLflow Tracing: Foundation for Agent Observability

**MLflow Tracing is one of the core constructs of MLflow 3.0+**, providing complete observability into GenAI agent behavior. Every agent interaction—tool calls, LLM invocations, data queries—is automatically captured as a structured trace, giving you the foundation for debugging, evaluation, and continuous improvement.

**Why Tracing Matters for Quality Agents:**
- **Debugging**: See exactly which tools fired, what parameters were used, and where failures occurred
- **Evaluation**: Link quality metrics and expert feedback directly to specific agent behaviors
- **Optimization**: Identify bottlenecks, inefficient tool usage, and opportunities for improvement
- **Accountability**: Maintain complete audit trail of agent decisions and data sources

When a coach asks "What do the Cowboys do on 3rd and 6?", the DC Assistant makes multiple decisions: which Unity Catalog functions to call, what parameters to use, how to interpret the results. **MLflow Tracing automatically captures all of this**, creating a detailed execution graph that serves as the input for evaluation and feedback collection.

**Without tracing, you're flying blind.** Tracing is the prerequisite for everything that follows: evaluation, labeling, judge alignment, and prompt optimization.
`;

const simpleTracingCode = `
  import mlflow
  from databricks.agents import ResponsesAgent
  from databricks.agents.toolkits import UCFunctionToolkit

+ # 🔍 TRACING: Enable tracing for the agent
+ mlflow.set_experiment(experiment_id=MLFLOW_EXPERIMENT_ID)

  # Load Unity Catalog tools (SQL functions)
  tools = UCFunctionToolkit(
      catalog=UC_CATALOG,
      schema=UC_SCHEMA,
      function_names=[
          "who_got_ball_by_down_distance",
          "success_by_pass_rush_and_coverage",
          "tendencies_by_personnel",
          "screen_play_tendencies",
          # ... more tools
      ]
  )

  # Create the agent with automatic tracing
+ # 🔍 TRACING: ResponsesAgent automatically traces all interactions
  agent = ResponsesAgent(
      tools=tools.get_tools(),
      system_prompt=system_prompt,
      model=LLM_MODEL,
  )

  # Example: Coach asks about 3rd down tendencies
  question = "What do the Cowboys do on 3rd and 6?"

+ # 🔍 TRACING: Agent.predict() creates a trace automatically
  response = agent.predict({"input": [{"role": "user", "content": question}]})

+ # 🔍 TRACING: Get the trace ID from the active trace
+ trace_id = mlflow.get_current_active_trace().info.request_id

  print(f"Analysis complete. Trace ID: {trace_id}")

  # The trace captures:
  # - RETRIEVER: Tool call to who_got_ball_by_down_distance("Cowboys", [2024], 3, "medium")
  # - PARSER: Data formatting and aggregation
  # - LLM: Final synthesis and recommendations`;

const userFeedbackCode = `\`\`\`diff
  import mlflow
  from enum import Enum
  from typing import Optional, Dict, Any
  from pydantic import BaseModel

+ # 🔍 FEEDBACK: Log user feedback directly to traces
+ # After the agent generates a response, attach feedback to the trace

  # Backend API implementation (FastAPI endpoint):
  @router.post('/feedback', response_model=FeedbackResponse)
  async def submit_feedback(feedback: FeedbackRequest):
      """Submit user feedback linked to trace."""
      try:
-         # Log feedback without tracing
+         # 🔍 FEEDBACK: Use mlflow.log_feedback to attach feedback to trace
          mlflow.log_feedback(
              trace_id=feedback.trace_id,
              name='user_feedback',
              value=feedback.rating == 'up',  # Convert to boolean
              rationale=feedback.comment,
              source=mlflow.entities.AssessmentSource(
                  source_type='HUMAN',
                  source_id=feedback.user_name or 'anonymous',
              ),
          )

          return FeedbackResponse(
              success=True,
              message='Feedback submitted successfully'
          )

      except Exception as e:
          return FeedbackResponse(
              success=False,
              message=f'Error submitting feedback: {str(e)}'
          )

  # Usage example - Submit positive feedback from the frontend
+ # 🔍 FEEDBACK: Call log_feedback with trace_id from agent response
  positive_feedback = log_feedback(
      trace_id=current_trace_id,  # Use trace_id from agent response
      value=True,  # True = positive feedback
      comment='Great analysis! The personnel package breakdown was exactly what I needed.',
      user_name='coach_smith',
  )

  # Submit negative feedback
  negative_feedback = log_feedback(
      trace_id=second_trace_id,
      value=False,  # False = negative feedback
      comment="The analysis didn't account for the opponent's recent defensive scheme changes.",
      user_name='coach_smith',
  )
\`\`\``;

const advancedTracingCode = `\`\`\`diff
  from mlflow.entities import SpanType
  from typing import List, Dict, Any

+ # 🔍 ADVANCED: Add custom span types and attributes to traces
+ @mlflow.trace(
+     name="tool-execution",  # [CUSTOM-NAME] Better than function name
+     span_type=SpanType.TOOL,  # [SPAN-TYPE] Categorize the span
+     attributes={"component": "uc_function", "catalog": UC_CATALOG}  # [ATTRIBUTES]
+ )
  def execute_tool(tool_name: str, args: dict) -> Any:
      """Execute a Unity Catalog function with detailed tracing."""
      result = uc_function_client.execute_function(tool_name, args)
      return result.value if result.error is None else result.error

  # Using span context manager for detailed processing steps
+ @mlflow.trace(name="dc_assistant_analysis")
  def predict_stream_local(question: str) -> Generator[dict, None, None]:
      """Stream analysis with detailed span tracking."""

-     # Build request without tracking
-     request = ResponsesAgentRequest(input=[Message(role="user", content=question)])
+     # 🔍 ADVANCED: Use span context manager for sub-operations
+     with mlflow.start_span(name="conversation_turn", span_type=SpanType.AGENT) as span:
+         span.set_inputs({"request": question})  # [SET-INPUTS]
+
+         request = ResponsesAgentRequest(input=[Message(role="user", content=question)])

          for event in self.predict_stream(request):
              yield event

-     # No response tracking
+         # 🔍 ADVANCED: Track response for clean display in MLflow UI
+         if full_response:
+             span.set_outputs({"response": full_response})  # [SET-OUTPUTS]
+             mlflow.update_current_trace(response_preview=full_response)
\`\`\``;

export function TracingDemo() {
  const introSection = <MarkdownContent content={introContent} />;

  const codeSection = (
    <div className="space-y-6">
      <CollapsibleSection
        title="Step 1: Instrument with tracing"
        variant="simple"
        // defaultOpen
        docsUrl="https://docs.databricks.com/aws/en/mlflow3/genai/tracing/app-instrumentation/"
      >
        <div className="space-y-4">
          <MarkdownContent
            content={`MLflow supports automatic tracing of 20+ popular GenAI SDKs - from OpenAI to LangChain. Automatic tracing can be supplemented with manual tracing to capture your application's specific logic.

The diff below shows exactly what to add (green lines with + symbols):`}
          />
          <CodeSnippet
            code={simpleTracingCode}
            title=""
            filename="agent.py"
            language="diff"
          />
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="Step 2: Attach user feedback to the trace"
        variant="simple"
        docsUrl="https://docs.databricks.com/aws/en/mlflow3/genai/tracing/collect-user-feedback/"
      >
        <div className="space-y-4">
          <MarkdownContent
            content={`MLflow enables you to attach user feedback directly to traces, creating a powerful feedback loop for quality improvement.

The diff below shows the key additions for feedback logging:`}
          />
          <CodeSnippet
            code={userFeedbackCode}
            title=""
            filename="agent.py"
            language="diff"
          />
        </div>
      </CollapsibleSection>

      <CollapsibleSection
        title="Advanced: Manual Tracing"
        variant="advanced"
        docsUrl="https://docs.databricks.com/aws/en/mlflow3/genai/tracing/app-instrumentation/manual-tracing/"
      >
        <div className="space-y-4">
          <MarkdownContent
            content={`For more granular observability, MLflow provides advanced tracing capabilities to capture detailed execution flow.

The diff below shows how to add advanced tracing features:`}
          />
          <CodeSnippet
            code={advancedTracingCode}
            title="Advanced Tracing Features - What to Add"
            filename="agent.py"
            language="diff"
          />
        </div>
      </CollapsibleSection>

      <NotebookReference
        notebookPath="mlflow_demo/notebooks/1_observe_with_traces.ipynb"
        notebookName="1_observe_with_traces"
        description=""
      />
    </div>
  );

  const { data: preloadedResultsData, isLoading: isPreloadedResultsLoading } =
    useQueryPreloadedResults();
  const { data: experimentData, isLoading: isExperimentLoading } =
    useQueryExperiment();
  const preloadedTraceUrl = preloadedResultsData?.sample_trace_url;

  // Build fallback traces URL from experiment data if sample trace URL isn't available
  const tracesListUrl = experimentData?.link;

  const demoSection = (
    <div className="space-y-8">
      {/* Step 1: View Pre-generated Example */}
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 bg-blue-100 text-blue-600 rounded-full font-semibold text-sm">
            1
          </div>
          <h3 className="text-lg font-semibold">
            View a pre-generated example
          </h3>
        </div>

        <div className="ml-11 space-y-3">
          <p className="text-muted-foreground">
            Start by viewing a pre-generated example to see how traces capture
            DC analysis and user feedback.
          </p>

          <div className="p-4 bg-muted/30 rounded-lg border">
            <Button
              variant="open_mlflow_ui"
              size="lg"
              disabled={isPreloadedResultsLoading && isExperimentLoading}
              onClick={() => {
                const url = preloadedTraceUrl || tracesListUrl;
                if (url) window.open(url, "_blank");
              }}
            >
              <ExternalLink className="h-4 w-4 mr-2" />
              View sample trace
            </Button>
          </div>
        </div>
      </div>

      {/* Step 2: Try Interactive Demo - Single Question */}
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 bg-green-100 text-green-600 rounded-full font-semibold text-sm">
            2
          </div>
          <h3 className="text-lg font-semibold">Try the interactive demo - Single question</h3>
        </div>

        <div className="ml-11 space-y-4">
          <p className="text-muted-foreground">
            Configure a question about opponent tendencies and watch the agent call Unity Catalog tools.
            See which functions are invoked and how the data flows through the trace.
          </p>

          <DcTracingDemo />
        </div>
      </div>

      {/* Step 3: Multi-Tool Questions */}
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 bg-orange-100 text-orange-600 rounded-full font-semibold text-sm">
            3
          </div>
          <h3 className="text-lg font-semibold">
            Multi-tool questions
          </h3>
        </div>

        <div className="ml-11 space-y-4">
          <p className="text-muted-foreground">
            Some coaching questions require combining data from multiple sources. Watch how the
            agent orchestrates multiple Unity Catalog function calls to build comprehensive answers,
            and see how MLflow traces capture the entire execution flow.
          </p>

          <MultiToolDemo />
        </div>
      </div>

      {/* Step 4: Multi-Turn Conversations */}
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 bg-purple-100 text-purple-600 rounded-full font-semibold text-sm">
            4
          </div>
          <h3 className="text-lg font-semibold">
            Explore multi-turn conversations with session tracking
          </h3>
        </div>

        <div className="ml-11 space-y-4">
          <p className="text-muted-foreground">
            Real coaching conversations aren't single questions—they involve follow-ups that
            build on previous context. See how MLflow groups related turns together in a
            single session trace, making it easy to understand and debug conversational flows.
          </p>

          <MultiTurnDemo />
        </div>
      </div>

      {/* Step 5: Question Tester */}
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 bg-yellow-100 text-yellow-600 rounded-full font-semibold text-sm">
            5
          </div>
          <h3 className="text-lg font-semibold">
            Question Tester
          </h3>
          <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full">
            Testing Only
          </span>
        </div>

        <div className="ml-11 space-y-4">
          <p className="text-muted-foreground">
            Free-form multi-turn chat for curating session-level evaluation questions.
            Type any question, send it, and continue the conversation. Hit "New Session"
            to start a fresh chain of thought.
          </p>

          <QuestionTester />
        </div>
      </div>
    </div>
  );

  return (
    <StepLayout
      title="Observe DC Analysis with Tracing"
      description="See how MLflow captures tool calls, data queries, and agent reasoning"
      intro={introSection}
      codeSection={codeSection}
      demoSection={demoSection}
    />
  );
}
