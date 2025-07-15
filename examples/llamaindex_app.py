import time
import logging
from flask import Flask, request, jsonify

# --- FIX: Using the correct import paths for the LlamaIndex mock classes ---
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.core.llms.mock import MockLLM
from llama_index.core.embeddings.mock_embed_model import MockEmbedding

# Import your framework's components
from chatbot_test_framework import Tracer, DynamoDBRecorder, LocalJsonRecorder

MY_CUSTOM_SCHEMA = {
    # DynamoDB Attribute Name : Path in trace_data dictionary
    "LLM": "llm_used",
    # Special calculated value
    "latency_seconds": "latency",
}

# --- Flask App Setup ---
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [LlamaIndexApp] - %(message)s')


# --- 1. Configure LlamaIndex to use Mock Models (runs once) ---
Settings.llm = MockLLM(max_tokens=256)
Settings.embed_model = MockEmbedding(embed_dim=384)

# --- 2. Create In-Memory Index (runs once) ---
documents = [
    Document(text="The company policy for sick leave is 10 days per year."),
    Document(text="To request vacation, submit a request in the HR portal at least 2 weeks in advance."),
    Document(text="The guest wifi password is 'GuestPassword123'."),
]
index = VectorStoreIndex.from_documents(documents)
query_engine = index.as_query_engine()


# --- 3. Define the Traced Query Function with Corrected Logic ---
def run_traced_query(engine, question, tracer):
    """Wraps the core LlamaIndex logic so we can trace it."""
    
    # This is the function that will be decorated.
    # It does not need to know about _extra_metadata.
    @tracer.trace(step_name="rag_query_pipeline")
    def _run_query(q: str):
        print("---LLAMAINDEX NODE: rag_query_pipeline---")
        time.sleep(0.7) # Simulate RAG latency
        
        response = engine.query(q)
        
        # This function should only return the data relevant to the business logic.
        return response.response
    
    # Prepare the metadata dictionary that you want to inject into the trace.
    # This is guaranteed to be a dict, preventing the AttributeError.
    metadata_to_inject = {
        "llm_used": "MockLLM",
        "embedding_model_used": "MockEmbedding",
        "retrieval_top_k": 2 # Example of another piece of useful metadata
    }

    # Call the decorated function, passing the metadata in the special argument.
    # The tracer's wrapper will handle this argument correctly.
    response_text = _run_query(
        question, 
        _extra_metadata=metadata_to_inject
    )
    
    return response_text


# --- 4. Flask API Wrapper ---
@app.route('/invoke', methods=['POST'])
def handle_request():
    data = request.json
    question = data.get("question")
    session_id = data.get("session_id")
    if not question or not session_id:
        return jsonify({"error": "Missing 'question' or 'session_id'"}), 400

    # The application developer configures and initializes the recorder.
    recorder_settings = {"table_name": "chatbot-traces", "region": "us-east-1"}
    # recorder = DynamoDBRecorder(settings=recorder_settings, schema_mapping=MY_CUSTOM_SCHEMA) # Add a schema_mapping here if desired
    recorder = LocalJsonRecorder(settings={"filepath": "my_chatbot_app/results/traces.json"})
    tracer = Tracer(recorder=recorder, run_id=session_id)

    try:
        rag_response = run_traced_query(query_engine, question, tracer)
        final_answer = f"According to our knowledge base: {rag_response}"
        return jsonify({"final_answer": final_answer})
        
    except Exception as e:
        app.logger.error("An error occurred!", exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting LlamaIndex mock application on http://127.0.0.1:5002")
    app.run(port=5002, debug=True)