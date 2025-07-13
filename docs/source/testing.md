## 4. Comprehensive Guide to Testing

While tracing is powerful on its own, the testing suite is what turns that data into actionable insights.

### The Three-Phase Testing Approach

The framework runs tests in three distinct, optional phases. This allows you to, for example, run a massive batch of questions overnight (Phase 1) and then run the expensive LLM evaluations the next day (Phase 2).

*   **Phase 1: Send Questions (`--phase1`)**
    *   **What it does:** Reads the `dataset_path` CSV, iterates through each question, and calls your chatbot's API via the configured `client`.
    *   **Result:** Your `Recorder` (e.g., DynamoDB) is populated with trace data for all test runs. A `run_map.csv` is created to link questions to `session_id`s.

*   **Phase 2: Evaluate Performance (`--phase2`)**
    *   **What it does:** Reads the `run_map.csv`, retrieves the trace data for each run from the `Recorder`, and uses the configured `llm_provider` to evaluate the quality of each step and the final answer.
    *   **Result:** Generates `step_performance.json`, `final_answer_performance.json`, and the AI-generated `performance_summary.txt`.

*   **Phase 3: Analyze Latency (`--phase3`)**
    *   **What it does:** Reads the `run_map.csv`, retrieves the trace data, and calculates the duration of each step and the total run time.
    *   **Result:** Generates `latency_per_run.json` and `average_latencies.json`.

### The Command-Line Interface (CLI) In-Depth

The `chatbot-tester` command is your primary tool for running tests.

*   **`chatbot-tester init <path>`**: Initializes a new project structure at the given path.
*   **`chatbot-tester run [options]`**: Executes the test runs.

**Common `run` Options:**

| Flag         | Description                                                              | Example                                        |
| :----------- | :----------------------------------------------------------------------- | :--------------------------------------------- |
| `--config`   | Path to your main configuration file.                                    | `--config configs/production_test.yaml`        |
| `--full-run` | Executes all three phases sequentially. The easiest way to run a test.   | `chatbot-tester run --full-run`                |
| `--phase1`   | Runs only Phase 1 (sending questions).                                   | `chatbot-tester run --phase1`                  |
| `--phase2`   | Runs only Phase 2 (performance evaluation).                              | `chatbot-tester run --phase2`                  |
| `--phase3`   | Runs only Phase 3 (latency analysis).                                    | `chatbot-tester run --phase3`                  |
| `--run-id`   | Specifies a custom ID for the run folder. Defaults to a timestamp.       | `--run-id "release-v1.2-test"`                 |

### Configuration (`test_config.yaml`) In-Depth

This file is the heart of your test setup.

#### General Settings
```yaml
dataset_path: "data/test_questions.csv"
results_dir: "results"
```
*   `dataset_path`: Path to your CSV file of test questions. It must contain a `model_question` column and an optional `model_answer` column for quality comparison.
*   `results_dir`: The root directory where all run reports will be saved.

#### Client Configuration
This section defines how the framework communicates with your chatbot.
```yaml
client:
  type: "api"
  settings:
    url: "http://127.0.0.1:5000/invoke"
    method: "POST"
    headers:
      "Content-Type": "application/json"
      "x-api-key": "YOUR_API_KEY"
    body_template: '{ "question": "{question}", "session_id": "{session_id}", "trace_config": {trace_config} }'
```
*   `type`: Currently, only `api` (for HTTP requests) is supported.
*   `settings`:
    *   `url`, `method`, `headers`: Standard HTTP request parameters.
    *   `body_template`: A crucial string that defines the JSON payload. The framework will replace the placeholders:
        *   `{question}`: The question from the CSV.
        *   `{session_id}`: A unique UUID generated for the run.
        *   `{trace_config}`: A JSON object containing the `tracing.recorder` configuration. This is how the framework tells your app how to record the trace for this specific run.

#### Tracing Configuration
This section is passed *to your application* inside the `{trace_config}` placeholder.
```yaml
tracing:
  recorder:
    type: "local_json" # or "dynamodb"
    settings:
      filepath: "results/traces.json"
      # For dynamodb:
      # table_name: "my-traces"
      # region: "us-east-1"
```

#### Evaluation Configuration
This section controls the performance evaluation phase (Phase 2).
```yaml
evaluation:
  prompts_path: "configs/prompts.py"
  workflow_description: >
    A multi-agent chatbot for an insurance company. It first authorizes the user,
    then routes their question to either a Commercial or Property insurance agent.

  llm_provider:
    type: "bedrock" # Options: 'claude', 'openai', 'gemini', 'bedrock'
    settings:
      # Settings vary by provider
      region: "us-east-1"
      model: "anthropic.claude-3-sonnet-20240229-v1:0"
```
*   `prompts_path`: Path to your Python file containing custom evaluation logic.
*   `workflow_description`: A high-level description of your chatbot's purpose. This is given to the evaluator LLM to provide crucial context for its judgments.
*   `llm_provider`: Defines which LLM to use for evaluation.
    *   `type`: `claude`, `openai`, `gemini`, or `bedrock`.
    *   `settings`:
        *   For `claude`/`openai`/`gemini`: requires `model` and an API key (set in config or as an environment variable like `ANTHROPIC_API_KEY`).
        *   For `bedrock`: requires `model` and `region`. IAM credentials are used automatically.

### Customizing Evaluations (`prompts.py`)

This file gives you direct control over the LLM's evaluation criteria.
*   `CUSTOM_POLICIES`: A list of strings defining your chatbot's rules. The LLM will check if the final answer violates any of these.
    ```python
    CUSTOM_POLICIES = [
        "The response must be polite and professional at all times.",
        "The response must not suggest any medical, legal, or financial advice.",
        "If the chatbot cannot find an answer, it should explicitly state that."
    ]
    ```
*   `FINAL_ANSWER_EVALUATION_PROMPT`: The master prompt for judging the final user-facing answer. It instructs the LLM to score the answer on Coherence, Safety, Policy Adherence, and Quality vs. a model answer.
*   `STEP_EVALUATION_PROMPT`: The prompt used to evaluate each individual traced step.
*   `DEEP_DIVE_SUMMARY_PROMPT`: The prompt used to generate the final qualitative summary report.

You can edit these prompts to tailor the evaluation to your specific needs.

### Understanding the Reports

After a `--full-run`, your `results/<run_id>` folder will contain:

*   `run_map.csv`: Maps each `question` to its unique `session_id`.
*   `traces.json` (if using `local_json` recorder): The raw trace data.
*   **Performance Reports:**
    *   `step_performance.json`: The detailed LLM evaluation for every single traced step across all runs.
    *   `final_answer_performance.json`: The detailed LLM evaluation of the final answer for each run.
    *   `performance_summary.txt`: **This is often the most valuable report.** An AI-generated qualitative summary that includes:
        *   An executive summary.
        *   Key findings (e.g., "The 'route_request' step consistently fails on ambiguous inputs.").
        *   A step-by-step analysis of common failure patterns.
        *   Actionable recommendations for your development team.
*   **Latency Reports:**
    *   `latency_per_run.json`: A step-by-step latency breakdown for each individual test run.
    *   `average_latencies.json`: The average latency for each step across all runs, helping you identify systemic bottlenecks.

---