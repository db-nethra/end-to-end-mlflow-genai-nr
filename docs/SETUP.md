# DC Assistant Setup Guide

This guide covers three deployment scenarios for the DC Assistant MLflow demo.

## Prerequisites (All Scenarios)

- **Databricks CLI** authenticated (`databricks auth login --profile <name>`)
- **uv** (Python package manager): `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **bun** (frontend): `brew install bun` or see [bun.sh](https://bun.sh)
- A **Unity Catalog** catalog where you can create schemas
- A **SQL Warehouse** (serverless recommended)

> **Note on catalog/schema naming:** The combined `catalog__schema__function_name` must be under 64 characters due to OpenAI tool naming limits. Keep catalog and schema names short (e.g., `nr_demo.dc_assistant`, not `nethra_ranganathan.dc_assistant_demo_v2`).

## Quick Start (All Scenarios)

```bash
git clone <this-repo>
cd end-to-end-mlflow-genai-aeh
uv run python setup/quick_setup.py
```

The setup script will prompt you for:
1. **Databricks profile** — which workspace to target
2. **Catalog** — where to create resources
3. **Schema** — name for the demo schema (default: `dc_assistant`)

Everything else is automated: NFL data loading, UC function creation, MLflow experiment, prompt registry, config generation, dependency install, and labeling session creation.

For non-interactive setup (CI or AI coding tools):
```bash
uv run python setup/quick_setup.py --profile my_profile --catalog my_catalog --schema dc_assistant
```

After setup completes:
```bash
./watch.sh                    # Start local dev server
open http://localhost:8000     # Open the app
```

---

## Deploying the Agent Endpoint

The app runs the agent locally by default. For production use or sharing, you should deploy the agent as a **Model Serving endpoint**. This is a one-time step — once deployed, the endpoint stays running.

### Why is a Service Principal Needed?

The deployed model serving endpoint runs as its own identity, not as your user. To access UC resources (prompt registry, functions), it needs a **service principal** with OAuth credentials stored in a **secret scope**. The `agents.deploy()` call injects `{{secrets/scope-name/key}}` references so the endpoint can authenticate at runtime.

### Step 1: Set Up Service Principal (Required for Deployment)

**Option A: Automated (recommended)**

```bash
# First-time setup (creates SP, OAuth secret, secret scope, and grants):
uv run python setup/setup_service_principal.py --profile <your-profile>

# If SP already exists and you just need to grant access to a new schema:
uv run python setup/setup_service_principal.py --profile <your-profile> --grant-only
```

This script:
- Creates a service principal (`dc-assistant-sp`) or finds an existing one
- Generates an OAuth secret and stores it in a Databricks secret scope (`dc-assistant-secrets`)
- Grants the SP `USAGE`, `EXECUTE`, and `MANAGE` on your catalog/schema
- Updates `config/dc_assistant.json` with the scope name

> Requires workspace admin permissions. In the field demo environment (e2-demo-field-eng), the SP `dc-assistant-secret` already exists — just run with `--grant-only` to authorize it for your schema.

**Option B: Manual**

1. Create a service principal: **Settings > Identity > Service Principals > Add**
2. Generate an OAuth secret: Click into the SP > **Secrets** > **Generate secret** (save the value)
3. Create a secret scope and store credentials:
   ```bash
   databricks secrets create-scope dc-assistant-secrets --profile <your-profile>
   databricks secrets put-secret dc-assistant-secrets oauth-client-id --string-value <application-id>
   databricks secrets put-secret dc-assistant-secrets oauth-client-secret --string-value <secret-value>
   ```
4. Grant the SP access:
   ```sql
   GRANT USAGE ON CATALOG `your_catalog` TO `<application-id>`;
   GRANT USAGE ON SCHEMA `your_catalog`.`your_schema` TO `<application-id>`;
   GRANT CREATE FUNCTION, EXECUTE, MANAGE ON SCHEMA `your_catalog`.`your_schema` TO `<application-id>`;
   ```

### Step 2: Deploy the Agent

```bash
uv run python setup/deploy_agent.py --profile <your-profile>
```

This script:
1. Logs the agent model to MLflow (with UC function resources)
2. Validates the model with a test prediction
3. Registers the model in UC Model Registry
4. Deploys it as a serving endpoint via `agents.deploy()`

The endpoint takes 5-10 minutes to become ready. Monitor status:
```bash
databricks serving-endpoints get agents_<catalog>-<schema>-dc_assistant --profile <your-profile>
```

### Step 3: Point the App to the Endpoint

After the endpoint is ready, update your `.env` to use it:
```bash
DC_ASSISTANT_MODE="endpoint"
```

The app will now call the deployed endpoint instead of running the agent in-process.

---

## Scenario 1: Field Demo Environment (e2-demo-field-eng)

One-time setup for the shared demo workspace. Resources persist across demos.

### Initial Setup (One-Time)
```bash
# 1. Run the automated setup (creates schema, loads data, creates functions, etc.)
uv run python setup/quick_setup.py --profile e2-demo-field-eng --catalog <your-catalog> --schema dc_assistant

# 2. Grant the existing SP access to your new schema
#    (SP "dc-assistant-secret" already exists in e2-demo-field-eng)
uv run python setup/setup_service_principal.py --profile e2-demo-field-eng --sp-name dc-assistant-secret --grant-only

# 3. Deploy the agent as a serving endpoint (one-time, takes ~10 min)
uv run python setup/deploy_agent.py --profile e2-demo-field-eng
```

### Running the Demo
```bash
./watch.sh           # Local development
open http://localhost:8000
```

### Deploying the Lakehouse App
```bash
./deploy.sh          # Deploy to Databricks Apps
```

---

## Scenario 2: SA Field Vending Machine Workspace

Setting up a fresh demo in your own workspace.

### Step 1: Authenticate
```bash
databricks auth login --profile my-workspace
```

### Step 2: Run Setup
```bash
uv run python setup/quick_setup.py --profile my-workspace
```

This will interactively prompt for catalog/schema, then automatically:
- Create the schema
- Load NFL play-by-play and participation data (via databricks-connect)
- Create 15 UC SQL functions (the agent's tools)
- Create an MLflow experiment
- Register the system prompt in UC Prompt Registry
- Generate `config/dc_assistant.json` and `.env`
- Install Python + frontend dependencies
- Create a labeling session with the football analysis schema

### Step 3: Run Locally
```bash
./watch.sh
# Open http://localhost:8000
```

### Step 4 (Optional): Deploy Agent Endpoint
If you want the agent available as a serving endpoint:
1. Set up the service principal (see "Deploying the Agent Endpoint" above)
2. Run: `uv run python setup/deploy_agent.py --profile my-workspace`

---

## Scenario 3: Customer Workspace

For customers who want to run this demo in their own workspace.

### Prerequisites
- Workspace admin or catalog admin permissions
- A SQL warehouse (serverless recommended)
- Access to a Foundation Model endpoint (e.g., `databricks-claude-3-7-sonnet`)

### Setup Steps

1. **Clone the repo**
   ```bash
   git clone <this-repo>
   cd end-to-end-mlflow-genai-aeh
   ```

2. **Authenticate**
   ```bash
   databricks auth login --profile customer-workspace
   ```

3. **Run setup** (handles everything including NFL data loading)
   ```bash
   uv run python setup/quick_setup.py --profile customer-workspace --catalog <their-catalog>
   ```

4. **Start the app**
   ```bash
   ./watch.sh
   # Open http://localhost:8000
   ```

5. **Deploy agent endpoint (optional)**
   - Set up service principal (see "Deploying the Agent Endpoint" above)
   - Run: `uv run python setup/deploy_agent.py --profile customer-workspace`

6. **Deploy Lakehouse App (optional)**
   ```bash
   ./deploy.sh
   ```

---

## What the Setup Script Creates

| Resource | Location | Purpose |
|----------|----------|---------|
| UC Schema | `{catalog}.{schema}` | Houses all demo resources |
| Delta Tables | `football_pbp_data`, `football_participation` | NFL play-by-play and player participation data |
| UC Functions (15) | `{catalog}.{schema}.*` | SQL functions the agent calls as tools |
| MLflow Experiment | `/Users/{email}/dc-assistant-demo` | Traces, evaluations, and monitoring |
| UC Prompt | `{catalog}.{schema}.dc_assistant_system_prompt` | Versioned system prompt with `@production` alias |
| Labeling Session | `master_session` | Pre-configured for SME review with `football_analysis_base` schema |
| Config File | `config/dc_assistant.json` | Single source of truth for all app configuration |

## Configuration Reference

All configuration is in `config/dc_assistant.json` (generated by setup). Key fields:

| Field | Description | Set by setup? |
|-------|-------------|---------------|
| `workspace.catalog` | UC catalog | Yes |
| `workspace.schema` | UC schema | Yes |
| `mlflow.experiment_id` | MLflow experiment | Yes |
| `prompt_registry.prompt_name` | System prompt name | Yes |
| `llm.endpoint_name` | LLM model endpoint | Yes (default: `databricks-claude-3-7-sonnet`) |
| `tools.uc_tool_names` | UC SQL function names | Yes |
| `prompt_registry_auth.*` | Service principal config | Manual (for deployment only) |

## Troubleshooting

**"Prompt not found" warning on startup**
- Expected for local dev before prompt registry is configured. The agent uses a fallback prompt.
- Fix: Run `uv run python setup/setup_prompt_registry.py`

**UC functions fail to create**
- Ensure the NFL data tables exist in your schema (setup loads them automatically)
- Ensure you have a running SQL warehouse
- Check that you have CREATE FUNCTION permission on the schema

**Function name truncation warnings**
- The combined `catalog__schema__function_name` exceeds 64 characters
- Use shorter catalog/schema names (e.g., `nr_demo.dc_assistant`)

**Multi-turn returns 500**
- Check that `config/dc_assistant.json` points to the correct catalog/schema
- Verify UC functions exist: `databricks functions list --catalog <cat> --schema <schema>`

**Labeling session button greyed out**
- The app fetches the review app URL on load. If no labeling sessions exist, click "Create New Labeling Session"

**Agent endpoint not responding**
- Check endpoint status: `databricks serving-endpoints get <endpoint-name>`
- Endpoints take 5-10 minutes to deploy
- Verify the service principal has access to the UC schema
