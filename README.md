
# Chatbot Tracing and Testing Framework

[
![PyPI version](https://badge.fury.io/py/chatbot-test-framework.svg)
](https://badge.fury.io/py/chatbot-test-framework)
[
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
](https://opensource.org/licenses/MIT)
[
![Python Version](https://img.shields.io/pypi/pyversions/chatbot-test-framework.svg)
](https://pypi.org/project/chatbot-test-framework/)

An open-source framework for end-to-end testing of conversational AI and chatbot applications. It provides tools for tracing, performance evaluation, and latency analysis, helping you ensure your chatbot is reliable, safe, and efficient.

## ✨ Key Features

*   **Three-Phase Testing:** Systematically test your chatbot by (1) sending questions, (2) evaluating response quality, and (3) analyzing latency.
*   **LLM-Powered Evaluation:** Use powerful Language Models (like Claude, GPT, or Gemini) to automatically assess your chatbot's responses for coherence, safety, policy adherence, and quality against a model answer.
*   **Pluggable Architecture:**
    *   **LLM Providers:** Easily switch between evaluation models from different providers (`claude`, `openai`, `gemini`, `bedrock`).
    *   **Trace Recorders:** Store test data where you need it, with built-in support for `local_json` (for easy local development) and `dynamodb` (for scalable cloud deployments).
*   **Simple Integration:** Instrument your chatbot's internal workflow with a simple `@trace` decorator, giving you deep insights into every step of the process.
*   **Command-Line Interface:** A powerful `chatbot-tester` CLI to initialize projects, run tests, and manage test phases.
*   **Detailed Reporting:** Generates comprehensive reports for each test run, including step-by-step performance, final answer quality, latency breakdowns, and an AI-generated summary with actionable recommendations.

## ⚙️ How It Works

The framework operates in a cycle that separates the test execution from the chatbot application itself, allowing you to test any chatbot that can be instrumented.

1.  **Instrumentation:** You add the framework's `@trace` decorator to the key functions within your chatbot's code (e.g., agent execution, tool calls, API lookups).
2.  **Test Execution (Phase 1):** You run the `chatbot-tester` CLI. It reads a CSV file of questions and sends them to your chatbot's API endpoint. As your chatbot processes each question, the `@trace` decorator captures the inputs, outputs, and timings of each instrumented function and saves them to a configured **Recorder** (like DynamoDB or a local JSON file).
3.  **Evaluation (Phase 2 & 3):** The framework then reads the trace data from the Recorder.
    *   **Performance (Phase 2):** It uses a configured LLM to evaluate each step and the final answer against your custom policies and a "golden" answer.
    *   **Latency (Phase 3):** It calculates the time taken for each step and the total end-to-end duration.
4.  **Reporting:** Finally, it generates a set of detailed JSON and text reports in a `results` directory, giving you a full picture of your chatbot's performance.

## 🚀 Getting Started

### Prerequisites

*   Python 3.9+
*   An API endpoint for your chatbot application.

### 1. Installation

Install the framework from PyPI:

```bash
pip install chatbot-test-framework
```

### 2. Initialize a New Project

Create a new directory for your tests and run the `init` command. This will set up the necessary folder structure and default configuration files.

```bash
chatbot-tester init my-chatbot-tests
cd my-chatbot-tests
```

This creates the following structure:

```
my-chatbot-tests/
├── configs/
│   ├── prompts.py             # <-- Your custom evaluation policies and prompts
│   └── test_config.yaml       # <-- The main configuration for your tests
├── data/
│   └── test_questions.csv     # <-- Your test questions and ideal answers
└── results/
    └── (reports will be generated here)
```

### 3. Instrument Your Chatbot

To enable tracing, you need to integrate the `Tracer` into your chatbot application. The cleanest way is to encapsulate your logic in a class that holds the tracer instance.

Here is a minimal example using a **Flask** application:

```python
# In your chatbot's main application file (e.g., app.py)
import time
from flask import Flask, request, jsonify
from chatbot_test_framework import Tracer
from chatbot_test_framework.recorders import DynamoDBRecorder, LocalJsonRecorder

app = Flask(__name__)

# --- Your Chatbot's Logic, now in a class ---
class MyChatbot:
    def __init__(self, tracer):
        self.tracer = tracer

    @property
    def authorize(self):
        # Use the sexy decorator syntax!
        @self.tracer.trace(step_name="authorize_user")
        def _authorize(user_id: str):
            time.sleep(0.1)
            return {"status": "authorized", "user_level": "premium"}
        return _authorize

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
    def get_final_answer(self):
        @self.tracer.trace(step_name="get_final_answer")
        def _get_answer(agent_result: dict):
            time.sleep(0.15)
            return {"final_answer": f"The result is: {agent_result['data']}"}
        return _get_answer

# --- API Endpoint ---
@app.route("/invoke", methods=['POST'])
def invoke_chatbot():
    data = request.get_json()
    question, session_id = data['question'], data['session_id']
    
    # --- Framework Integration ---
    trace_config = data.get('trace_config', {})
    recorder_type = trace_config.get('type')
    recorder_settings = trace_config.get('settings', {})

    if recorder_type == 'dynamodb':
        recorder = DynamoDBRecorder(recorder_settings)
    else:
        recorder = LocalJsonRecorder(recorder_settings)
        
    tracer = Tracer(recorder, run_id=session_id)
    # -----------------------------

    # --- Execute your traced workflow ---
    try:
        bot = MyChatbot(tracer)
        bot.authorize(user_id="user123")
        agent = bot.route_request(question=question)
        agent_result = {"data": "Your last bill was $50."} 
        final_answer = bot.get_final_answer(agent_result=agent_result)
        return jsonify(final_answer)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(port=5000)
```

### 4. Configure Your Test

Edit `configs/test_config.yaml` to match your setup. You'll need to configure the `client`, `tracing`, and `evaluation` sections. (See "Configuration Details" below for more options).

```yaml
# configs/test_config.yaml
client:
  type: "api"
  settings:
    url: "http://127.0.0.1:5000/invoke"
    body_template: '{ "question": "{question}", "session_id": "{session_id}", "trace_config": {trace_config} }'

tracing:
  recorder:
    type: "local_json"
    settings:
      filepath: "results/traces.json"

evaluation:
  prompts_path: "configs/prompts.py"
  workflow_description: "An IT support chatbot."
  llm_provider:
    type: "gemini"
    settings:
      model: "gemini-1.5-pro-latest"
```

### 5. Define Test Cases and Policies

1.  **Add Questions:** Open `data/test_questions.csv` and add your test questions and the ideal "model" answers.
2.  **Edit Policies:** Open `configs/prompts.py` and edit the `CUSTOM_POLICIES` list to define the rules for your chatbot's behavior.

### 6. Run the Tests!

Make sure your chatbot application is running, then execute the test runner.

```bash
# Run all test phases sequentially
chatbot-tester run --full-run
```

## 🔧 Advanced Usage

### Injecting Custom Metadata

You can inject arbitrary data into a trace step using the `_extra_metadata` keyword argument. This is perfect for recording dynamic values like confidence scores, model IDs, or tool parameters.

```python
# In your chatbot application
@self.tracer.trace(step_name="route_request")
def _route(question: str):
    # ... routing logic ...
    return {"agent": "BillingAgent", "confidence": 0.98}

# When calling the traced function
route_result = bot.route_request(
    question=question,
    # This dictionary will be merged into the trace data for this step
    _extra_metadata={"confidence_score": 0.98, "routing_model": "distilbert-base-uncased"}
)
```

### Defining a Custom DynamoDB Schema

When using the `DynamoDBRecorder`, you can provide a `schema_mapping` to map values from your trace data (including `_extra_metadata`) to top-level attributes in your DynamoDB table. This is extremely useful for creating secondary indexes for efficient querying and analysis.

1.  **Define your schema in your application code:**

    ```python
    # In your chatbot's app.py
    MY_CUSTOM_SCHEMA = {
        # DynamoDB Attribute Name : Path in trace_data dictionary
        "step_status": "status",
        "latency_seconds": "latency", # 'latency' is a special calculated value
        "final_agent_response": "outputs.final_answer",
        
        # Map the custom metadata we injected earlier!
        "routing_confidence": "confidence_score" 
    }
    ```

2.  **Pass the schema when initializing the recorder:**

    ```python
    # In your /invoke endpoint
    recorder = DynamoDBRecorder(
        settings=recorder_settings,
        schema_mapping=MY_CUSTOM_SCHEMA  # <-- Pass the schema map here
    )
    tracer = Tracer(recorder=recorder, run_id=session_id)
    ```

Now, when your app records traces, DynamoDB items will be populated with top-level attributes like `step_status` and `routing_confidence`, which you can index and query directly.

## 🧩 Integration Examples

The framework is designed to work with any Python-based chatbot. Here are examples showing how to integrate it with popular libraries.

### With LangGraph

Tracing LangGraph involves creating the graph components within a factory function that has access to the `tracer`.

```python
# From examples/langgraph_app.py
from langgraph.graph import StateGraph, END

def create_graph_components(tracer):
    # Define nodes as functions and apply the decorator
    @tracer.trace(step_name="web_search_tool")
    def web_search(state: AgentState):
        print("---LANGGRAPH NODE: web_search---")
        state["documents"] = ["LangGraph is a library for building stateful apps."]
        return state

    @tracer.trace(step_name="generate_final_answer")
    def generate(state: AgentState):
        print("---LANGGRAPH NODE: generate---")
        # You can also inject metadata directly from the state
        state['current_metadata'] = {"confidence_score": 0.98}
        state["generation"] = f"Based on my research: {state['documents'][0]}"
        return state
    
    return web_search, generate

# In your main app logic:
# 1. Initialize the tracer
tracer = Tracer(recorder=recorder, run_id=session_id)
# 2. Create the graph
web_search_node, generate_node = create_graph_components(tracer)
workflow = StateGraph(AgentState)
workflow.add_node("web_search", web_search_node)
workflow.add_node("generate", generate_node)
# ... build the rest of your graph ...
langgraph_app = workflow.compile()
# 3. Invoke the graph
final_state = langgraph_app.invoke(inputs)
```

### With LlamaIndex

For libraries like LlamaIndex, where the core logic is inside a class instance (`QueryEngine`), the easiest pattern is to wrap the call in a dedicated, traced function.

```python
# From examples/llamaindex_app.py
from llama_index.core import VectorStoreIndex
from llama_index.core.llms.mock import MockLLM

# Assume 'query_engine' is an initialized LlamaIndex QueryEngine
# query_engine = VectorStoreIndex.from_documents(...).as_query_engine()

def run_traced_query(engine, question, tracer):
    """Wraps the core LlamaIndex logic so we can trace it."""
    
    @tracer.trace(step_name="rag_query_pipeline")
    def _run_query(q: str):
        # This is the actual call to the library
        return engine.query(q)
    
    # Prepare metadata to inject into the trace
    metadata_to_inject = {
        "llm_used": "MockLLM",
        "retrieval_top_k": 2
    }

    # Call the decorated function, passing metadata
    response = _run_query(
        question, 
        _extra_metadata=metadata_to_inject
    )
    return response

# In your main app logic:
tracer = Tracer(recorder=recorder, run_id=session_id)
rag_response = run_traced_query(query_engine, question, tracer)
```

## 📊 Output and Reports

After a run completes, check the `results/<run_id>` directory. You will find:

*   `run_map.csv`: Maps each question to the `session_id` used for the run.
*   `step_performance.json`: Raw LLM evaluation for every traced step.
*   `final_answer_performance.json`: Raw LLM evaluation for the final user-facing answer.
*   `performance_summary.txt`: An AI-generated summary of the performance evaluation, highlighting key findings and actionable recommendations.
*   `latency_per_run.json`: Latency breakdown for each individual test case.
*   `average_latencies.json`: Average latency across all runs for each step.

## 🤝 Contributing

Contributions are welcome! Please feel free to open an issue or submit a pull request.

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.