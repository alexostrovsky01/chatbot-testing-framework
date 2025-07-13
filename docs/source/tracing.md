## 3. Comprehensive Guide to Tracing

Tracing is the foundation of the framework. It's how you gain visibility into your chatbot's internal workings. You can use the tracing functionality on its own, even without running the full test suite.

### The `@trace` Decorator

The primary interface for tracing is the `@tracer.trace()` decorator. You apply it to any function or method you want to monitor.

```python
@self.tracer.trace(step_name="authorize_user")
def _authorize(user_id: str, token: str):
    # ... logic ...
    return {"status": "ok"}
```

When this function is called, the decorator automatically captures:
*   **`name`**: The `step_name` you provided ("authorize_user").
*   **`inputs`**: The arguments passed to the function (`{"args": ["user123"], "kwargs": {"token": "xyz"}}`).
*   **`outputs`**: The value returned by the function (`{"status": "ok"}`).
*   **`status`**: "success" if it completes, "error" if it raises an exception.
*   **`start_time` / `end_time`**: Timestamps for latency calculation.
*   **`run_id`**: The unique ID for the entire interaction.

### The `Tracer` and `Recorder` Relationship

These two components work together. The `Tracer` is initialized for each unique request and linked to a `Recorder`.

1.  **Your App Receives a Request:** The API endpoint gets a `session_id`.
2.  **Initialize Recorder:** You create an instance of a `Recorder` class (e.g., `LocalJsonRecorder`).
3.  **Initialize Tracer:** You create a `Tracer`, passing it the `recorder` instance and the `session_id` (as `run_id`).
4.  **Execute Logic:** You call your business logic, which uses the `@trace` decorator.
5.  **Record Data:** The decorator sends the captured trace data to the `recorder.record()` method.

Here is the logic from our quick start example, annotated:

```python
# In your /invoke endpoint
def invoke():
    # ... get session_id from request ...
    
    # 1. The framework passes the recorder config in the request body
    trace_config = data.get('trace_config', {})
    recorder_settings = trace_config.get('settings', {})
    
    # 2. Initialize the correct recorder based on the config
    recorder = LocalJsonRecorder(recorder_settings)
    
    # 3. Initialize the tracer for this specific run
    tracer = Tracer(recorder, run_id=session_id)
    
    # 4. Pass the tracer to your application logic
    bot = MockBot(tracer)
    
    # 5. When these methods are called, they will record data via the tracer
    agent = bot.route_request(question=question)
    result = bot.execute_agent(agent=agent)
    
    return jsonify({"final_answer": result['response']})
```

### Advanced Tracing: Injecting Custom Metadata

Often, you want to record dynamic data that isn't part of the function's direct inputs or outputs. This is perfect for things like model confidence scores, tool parameters, or which LLM was used for a specific step.

You can do this by passing a special `_extra_metadata` dictionary when you call a traced function.

```python
# In your chatbot logic
@self.tracer.trace(step_name="synthesize_response")
def _synthesize(agent_response: dict):
    # ... logic to call an LLM ...
    return {"final_answer": "Some generated text."}

# When you call the function
final_result = bot.synthesize_response(
    agent_response=agent_result,
    # This dictionary will be merged into the root of the trace data for this step
    _extra_metadata={
        "synthesis_details": {
            "model_id": "gpt-4o",
            "temperature": 0.2,
        },
        "confidence_score": 0.97
    }
)
```
The resulting trace data for this step will now include `synthesis_details` and `confidence_score` at the top level, making them easy to query.

### Recorders In-Depth

Recorders are the pluggable storage backends for your trace data.

#### LocalJsonRecorder

This is the simplest recorder, perfect for local development and debugging.
*   **How it works:** It appends all trace data to a single JSON file, organized by `run_id`.
*   **Configuration:**
    ```yaml
    tracing:
      recorder:
        type: "local_json"
        settings:
          filepath: "results/my_traces.json" # Path to the output file
    ```
*   **Pros:** No setup, easy to inspect the output.
*   **Cons:** Not suitable for production or concurrent writes at scale.

#### DynamoDBRecorder and Custom Schemas

This is the recommended recorder for scalable, cloud-based deployments.
*   **How it works:** It stores trace data in an AWS DynamoDB table. By default, it appends each trace step to a list within an item identified by the `run_id`.
*   **Configuration:**
    ```yaml
    tracing:
      recorder:
        type: "dynamodb"
        settings:
          table_name: "my-chatbot-traces"
          region: "us-east-1"
          run_id_key: "sessionId" # The primary key of your table
    ```

*   **Advanced Feature: `schema_mapping`**
    This is an extremely powerful feature for making your trace data queryable. You can define a schema that maps values from your trace data (including custom metadata) to top-level attributes in your DynamoDB item. This allows you to create Global Secondary Indexes (GSIs) on these attributes for efficient lookups.

    1.  **Define the schema in your application code:**
        ```python
        # In your chatbot's app.py
        MY_CUSTOM_SCHEMA = {
            # DynamoDB Attribute Name : Path in trace_data dictionary (using dot notation)
            "step_status": "status",
            "final_agent_response": "outputs.final_answer",
            
            # Map the custom metadata we injected earlier!
            "synthesis_model": "synthesis_details.model_id",
            "routing_confidence": "confidence_score",

            # 'latency' is a special key that calculates the step's duration
            "latency_seconds": "latency", 
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
    Now, your DynamoDB items will have top-level attributes like `step_status` and `routing_confidence`, which you can index and query efficiently.

### Tracing Integration Patterns

#### Pattern 1: Standard Application
This is the pattern we've used so far. You encapsulate your logic in a class, pass a `tracer` instance to it, and use the `@tracer.trace` decorator on its methods.

#### Pattern 2: LangGraph
LangGraph's structure requires a slightly different approach. The key is to create the graph nodes inside a factory function that has access to the `tracer`.

```python
# From examples/langgraph_app.py
from langgraph.graph import StateGraph, END

def create_graph_components(tracer):
    # Define nodes as functions and apply the decorator
    @tracer.trace(step_name="web_search_tool")
    def web_search(state: AgentState):
        state["documents"] = ["LangGraph is a library..."]
        return state

    # For LangGraph, you can pass metadata via the state dictionary
    @tracer.trace(step_name="generate_final_answer")
    def generate(state: AgentState):
        state['current_metadata'] = {"confidence_score": 0.98}
        state["generation"] = f"Based on research: {state['documents'][0]}"
        return state
    
    return web_search, generate

# In your main app logic:
# 1. Initialize the tracer
tracer = Tracer(recorder=recorder, run_id=session_id)
# 2. Create the graph nodes using the factory
web_search_node, generate_node = create_graph_components(tracer)
# 3. Build the graph with the traced nodes
workflow = StateGraph(AgentState)
workflow.add_node("web_search", web_search_node)
# ... etc ...
```

#### Pattern 3: LlamaIndex & Other Libraries
When using a library where the core logic is inside a pre-built object (like a LlamaIndex `QueryEngine`), the cleanest pattern is to wrap the call in your own traced function.

```python
# From examples/llamaindex_app.py

# Assume 'query_engine' is an initialized LlamaIndex QueryEngine
def run_traced_query(engine, question, tracer):
    """Wraps the core LlamaIndex logic so we can trace it."""
    
    @tracer.trace(step_name="rag_query_pipeline")
    def _run_query(q: str):
        # This is the actual call to the library
        return engine.query(q)
    
    # Prepare metadata to inject into the trace
    metadata_to_inject = {"llm_used": "MockLLM", "retrieval_top_k": 2}

    # Call your decorated wrapper function
    response = _run_query(question, _extra_metadata=metadata_to_inject)
    return response

# In your main app logic:
tracer = Tracer(recorder=recorder, run_id=session_id)
rag_response = run_traced_query(query_engine, question, tracer)
```

---