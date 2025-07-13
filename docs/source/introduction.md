## 1. Introduction

### What is the Chatbot Test Framework?

The Chatbot Test Framework is a powerful, open-source tool designed for end-to-end testing of conversational AI applications. It provides a structured way to measure and improve your chatbot's **quality**, **safety**, **performance**, and **latency**.

At its core, the framework helps you answer critical questions:
*   Does my chatbot give correct and relevant answers?
*   Does it follow my company's safety and style policies?
*   Which parts of my chatbot's internal logic are slow?
*   How does performance change after I deploy new code?

It achieves this by separating the **test runner** from your **chatbot application**, allowing you to test any Python-based chatbot with an API endpoint.

### Why Use It?

*   **Ensure Reliability:** Automate testing to catch regressions and ensure consistent quality.
*   **Improve Safety:** Use LLM-powered evaluation to check for harmful content and policy violations.
*   **Optimize Performance:** Pinpoint bottlenecks in your chatbot's workflow with detailed latency reports.
*   **Deep Insights:** Go beyond simple input/output tests. The tracing mechanism gives you a step-by-step view of your chatbot's internal decision-making process.
*   **Flexible & Pluggable:** Works with any chatbot architecture and allows you to use different LLMs (Claude, GPT, Gemini, Bedrock) for evaluation and store data where you want (local files, DynamoDB).

### Core Concepts

*   **Tracer:** An object you integrate into your chatbot's code. Its `@trace` decorator wraps key functions to capture their inputs, outputs, status, and timings.
*   **Recorder:** The storage backend for trace data. The `Tracer` sends its data to a `Recorder` (e.g., `DynamoDBRecorder` or `LocalJsonRecorder`).
*   **Test Runner:** The command-line tool (`chatbot-tester`) that orchestrates the entire testing process. It sends questions, triggers evaluations, and generates reports.

### High-Level Workflow

The framework operates in a clear, decoupled cycle:

1.  **You Instrument Your App:** You add the `@trace` decorator to key functions in your chatbot's code.
2.  **Phase 1: Send Questions:** The `Test Runner` reads a CSV of questions and sends them one by one to your chatbot's API endpoint.
3.  **Tracing in Action:** As your chatbot processes a request, the `@trace` decorators capture data and send it to the configured `Recorder` (e.g., DynamoDB).
4.  **Phase 2: Evaluate Performance:** The `Test Runner` retrieves the trace data from the `Recorder` and uses a powerful LLM to evaluate each step for quality, relevance, and policy adherence.
5.  **Phase 3: Analyze Latency:** The `Test Runner` uses the same trace data to calculate the duration of each step and the total end-to-end latency.
6.  **Reporting:** The framework generates a folder of detailed reports summarizing all findings.


 <!-- Placeholder for a visual diagram -->

 ---

## 2. Getting Started: A Quick Tour

Let's get a test running in under 5 minutes.

### Prerequisites

*   Python 3.9+
*   A running chatbot application with an HTTP API endpoint. We will create a mock one for this guide.

### Installation

Install the framework from PyPI in your terminal:
```bash
pip install chatbot-test-framework
```

### Step 1: Initialize Your Project

Create a directory for your tests and run the `init` command.

```bash
mkdir my-first-tests
cd my-first-tests
chatbot-tester init .
```
This creates the essential project structure:
```
.
├── configs/
│   ├── prompts.py             # Your custom evaluation policies
│   └── test_config.yaml       # Main test configuration
├── data/
│   └── test_questions.csv     # Your test questions
└── results/
    └── (Reports will be generated here)
```

### Step 2: Instrument a Simple Chatbot

Create a file named `mock_app.py` and paste the following Flask application code. This simulates a simple, multi-step chatbot.

```python
# mock_app.py
import time
from flask import Flask, request, jsonify
from chatbot_test_framework import Tracer
from chatbot_test_framework.recorders import LocalJsonRecorder

app = Flask(__name__)

class MockBot:
    def __init__(self, tracer):
        self.tracer = tracer

    @property
    def route_request(self):
        @self.tracer.trace(step_name="route_request")
        def _route(question: str):
            time.sleep(0.2)
            if "bill" in question.lower():
                return "billing_agent"
            return "general_agent"
        return _route

    @property
    def execute_agent(self):
        @self.tracer.trace(step_name="execute_agent")
        def _execute(agent: str):
            time.sleep(0.5)
            if agent == "billing_agent":
                return {"response": "Your last bill was $50."}
            return {"response": "I can help with general questions."}
        return _execute

@app.route("/invoke", methods=['POST'])
def invoke():
    data = request.get_json()
    question, session_id = data['question'], data['session_id']
    trace_config = data.get('trace_config', {})
    
    # The framework tells the app how to trace this run
    recorder = LocalJsonRecorder(trace_config.get('settings', {}))
    tracer = Tracer(recorder, run_id=session_id)
    
    bot = MockBot(tracer)
    agent = bot.route_request(question=question)
    result = bot.execute_agent(agent=agent)
    
    return jsonify({"final_answer": result['response']})

if __name__ == '__main__':
    app.run(port=5000)
```

### Step 3: Configure Your Test

Edit `configs/test_config.yaml` to point to our mock app and use a local recorder.

```yaml
# configs/test_config.yaml
dataset_path: "data/test_questions.csv"
results_dir: "results"

client:
  type: "api"
  settings:
    url: "http://127.0.0.1:5000/invoke"
    method: "POST"
    headers:
      "Content-Type": "application/json"
    body_template: '{ "question": "{question}", "session_id": "{session_id}", "trace_config": {trace_config} }'

tracing:
  recorder:
    type: "local_json"
    settings:
      filepath: "results/traces.json"

evaluation:
  prompts_path: "configs/prompts.py"
  workflow_description: "A simple mock chatbot that routes to a billing or general agent."
  llm_provider:
    type: "claude" # Or "openai", "gemini"
    settings:
      model: "claude-3-sonnet-20240229"
      # API key should be set as an environment variable (e.g., ANTHROPIC_API_KEY)
```

### Step 4: Run Your First Test

1.  **Start your chatbot app:**
    ```bash
    python mock_app.py
    ```
2.  **In a new terminal**, run the framework's test command:
    ```bash
    # Make sure your LLM provider API key is set as an environment variable!
    # export ANTHROPIC_API_KEY="sk-..."

    chatbot-tester run --full-run
    ```

### Step 5: Check the Results

Look inside the `results/` directory. You'll find a new folder named with a timestamp (e.g., `run_20231027_103000`). Inside, you'll find:
*   `traces.json`: The raw data captured by the `LocalJsonRecorder`.
*   `performance_summary.txt`: An AI-generated analysis of your bot's performance.
*   `average_latencies.json`: A breakdown of how long each step took on average.
*   ...and other detailed JSON reports.

Congratulations! You've completed your first end-to-end test.
