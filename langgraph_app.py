import time
from typing import TypedDict, List
from flask import Flask, request, jsonify
from langgraph.graph import StateGraph, END

# Import your framework's components
from chatbot_test_framework import Tracer, DynamoDBRecorder, LocalJsonRecorder

# --- 1. Define the State for our Graph ---
class AgentState(TypedDict):
    question: str
    generation: str
    documents: List[str]

MY_CUSTOM_SCHEMA = {
    # DynamoDB Attribute Name : Path in trace_data dictionary
    "step_status": "status",
    # Special calculated value
    "latency_seconds": "latency",
    # Example of mapping a nested value from the trace data
    "final_agent_response": "outputs.generation",
    # --- Let's add our new custom fields to the schema! ---
    "routing_confidence": "confidence_score",
}

# --- 2. Define the Nodes and the Routing Condition ---
def create_graph_components(tracer):
    """
    Factory to create graph components. We now separate the nodes from the
    routing logic function.
    """
    
    # --- FIX: This is now a simple node that just passes state ---
    @tracer.trace(step_name="start_routing")
    def start_routing(state: AgentState):
        """
        This node acts as the entry point for routing. It performs its action
        (which could be logging or some other prep) and then returns the
        state dictionary, satisfying the LangGraph rule.
        """
        print("---LANGGRAPH NODE: start_routing---")
        time.sleep(0.1)
        # It must return a dictionary to update the state (even if no changes are made).
        return state

    # --- FIX: The routing logic is now in a separate function ---
    def decide_next_step(state: AgentState) -> str:
        """
        This function is NOT a node. It's the 'condition' for the
        conditional edge. It inspects the state and returns a string
        which is the name of the next node to run.
        """
        print("---LANGGRAPH CONDITION: Deciding next step---")
        if "langgraph" in state.get("question", "").lower():
            print("Routing decision: web_search")
            return "web_search"
        else:
            print("Routing decision: generate")
            return "generate"

    @tracer.trace(step_name="web_search_tool")
    def web_search(state: AgentState):
        """Mock tool that returns a hardcoded document."""
        print("---LANGGRAPH NODE: web_search---")
        time.sleep(0.5)
        state["documents"] = ["LangGraph is a library for building stateful, multi-actor applications with LLMs."]
        return state

    @tracer.trace(step_name="generate_final_answer")
    def generate(state: AgentState):
        """Mock final LLM call to synthesize an answer."""
        print("---LANGGRAPH NODE: generate---")
        time.sleep(0.3)
        state['current_metadata'] = {"confidence_score": 0.98}  # Example of adding metadata
        if documents := state.get("documents"):
            state["generation"] = f"Based on my research: {documents[0]}"
        else:
            state["generation"] = "I can answer basic questions. For complex topics, ask about 'LangGraph'."
        return state

    return start_routing, decide_next_step, web_search, generate

# --- 3. Build the Graph ---
def create_langgraph_app(tracer):
    start_routing, decide_next_step, web_search, generate = create_graph_components(tracer)
    
    workflow = StateGraph(AgentState)
    
    # Add the actual nodes
    workflow.add_node("start_routing", start_routing)
    workflow.add_node("web_search", web_search)
    workflow.add_node("generate", generate)
    
    # --- FIX: The graph structure is now defined correctly ---
    workflow.set_entry_point("start_routing")
    
    # The conditional edge starts from 'start_routing' and uses our new
    # 'decide_next_step' function to choose the path.
    workflow.add_conditional_edges(
        "start_routing",
        decide_next_step,
        {
            "web_search": "web_search",
            "generate": "generate",
        },
    )
    
    workflow.add_edge("web_search", "generate")
    workflow.add_edge("generate", END)
    
    return workflow.compile()

# --- 4. Flask API Wrapper (No changes needed here) ---
app = Flask(__name__)

@app.route('/invoke', methods=['POST'])
def handle_request():
    data = request.json
    question = data.get("question")
    session_id = data.get("session_id")
    if not question or not session_id:
        return jsonify({"error": "Missing 'question' or 'session_id'"}), 400

    recorder_settings = {"table_name": "chatbot-traces", "region": "us-east-1"}
    # recorder = DynamoDBRecorder(settings=recorder_settings, schema_mapping=MY_CUSTOM_SCHEMA) # Add schema_mapping here if you want
    recorder = LocalJsonRecorder(settings={"filepath": "my_chatbot_app/results/traces.json"})
    tracer = Tracer(recorder=recorder, run_id=session_id)
    
    langgraph_app = create_langgraph_app(tracer)
    
    try:
        inputs = {"question": question} # Simplified inputs
        final_state = langgraph_app.invoke(inputs)
        return jsonify({"final_answer": final_state.get("generation")})
    except Exception as e:
        app.logger.error("An error occurred!", exc_info=True)
        # LangGraph exceptions are verbose, so we return the string representation
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting LangGraph mock application on http://127.0.0.1:5001")
    app.run(port=5001, debug=True)