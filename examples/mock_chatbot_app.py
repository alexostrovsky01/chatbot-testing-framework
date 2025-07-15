import time
import logging
from flask import Flask, request, jsonify

# Import the necessary components from your installed framework package
from chatbot_test_framework import Tracer, DynamoDBRecorder, LocalJsonRecorder

# --- Flask App Setup ---
app = Flask(__name__)
# Configure basic logging for the Flask app to see requests and errors
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [ChatbotApp] - %(message)s')


# --- Schema Definition for DynamoDB ---
# The application developer defines their desired schema here.
# This makes the application's data storage contract clear and explicit.
MY_CUSTOM_SCHEMA = {
    # DynamoDB Attribute Name : Path in trace_data dictionary
    # "step_name": "name",
    "step_status": "status",
    # "step_start_time": "start_time",
    # "step_end_time": "end_time",
    # Special calculated value
    "latency_seconds": "latency",
    # Example of mapping a nested value from the trace data
    "final_agent_response": "outputs.final_answer",
    # --- Let's add our new custom fields to the schema! ---
    "routing_confidence": "confidence_score",
    "synthesis_model": "synthesis_details.model_id"
}


# --- Mock Application Logic ---
class MockChatbotApp:
    def __init__(self, tracer):
        self.tracer = tracer

    @property
    def authorize(self):
        @self.tracer.trace(step_name="authorize_user")
        def _authorize(user_id: str):
            """Simulates checking if a user is authorized."""
            time.sleep(0.1)
            if "premium" in user_id:
                return {"status": "authorized", "level": "premium"}
            return {"status": "unauthorized"}
        return _authorize

    @property
    def route_request(self):
        @self.tracer.trace(step_name="route_request")
        def _route_request(question: str):
            """Simulates routing a request to the correct agent."""
            time.sleep(0.2)
            question = question.lower()
            if "billing" in question:
                return {"agent": "BillingAgent"}
            if "password" in question or "reset" in question:
                return {"agent": "PasswordAgent"}
            return {"agent": "GeneralAgent"}
        return _route_request

    @property
    def execute_agent(self):
        @self.tracer.trace(step_name="execute_agent")
        def _execute_agent(agent: str, question: str):
            """Simulates executing a tool or specialized agent."""
            time.sleep(0.5)
            if agent == "BillingAgent":
                return {"response": "Your last invoice was $50. Please check your email for details."}
            if agent == "PasswordAgent":
                return {"response": "A password reset link has been sent to your registered email."}
            return {"response": "I can help with general questions. How can I assist you today?"}
        return _execute_agent

    @property
    def synthesize_response(self):
        @self.tracer.trace(step_name="synthesize_response")
        def _synthesize_response(agent_response: dict):
            """Simulates the final LLM call to format the answer."""
            time.sleep(0.15)
            final_message = f"Support Bot: {agent_response['response']}"
            return {"final_answer": final_message}
        return _synthesize_response


# --- Flask API Endpoint ---
@app.route('/invoke', methods=['POST'])
def handle_request():
    """This is the API endpoint our testing framework will call."""
    data = request.json
    question = data.get('question')
    session_id = data.get('session_id')
    user_id = "user_premium_123"

    if not question or not session_id:
        return jsonify({"error": "Missing 'question' or 'session_id'"}), 400

    # --- TRACING SETUP ---
    # The application developer has full control here.
    
    # 1. Define the core recorder settings.
    recorder_settings = {"table_name": "chatbot-traces", "region": "us-east-1"}

    # 2. Initialize the recorder, passing the schema map if desired.
    #    This uses the new, flexible __init__ method of the DynamoDBRecorder.
    recorder = DynamoDBRecorder(
        settings=recorder_settings,
        schema_mapping=MY_CUSTOM_SCHEMA  # <-- Pass the schema map here.
    )
    # recorder = LocalJsonRecorder(settings={"filepath": "my_chatbot_app/results/traces.json"})

    # To use the default "list append" behavior instead, you would simply omit the argument:
    # recorder = DynamoDBRecorder(settings=recorder_settings)

    # 3. Initialize the Tracer, linking it to this specific run via the session_id.
    tracer = Tracer(recorder=recorder, run_id=session_id)
    
    # 4. Instantiate our app logic, passing the tracer to it.
    app_logic = MockChatbotApp(tracer)

    # --- EXECUTE THE MULTI-STEP WORKFLOW ---
    try:
        auth_result = app_logic.authorize(user_id=user_id)
        if auth_result.get("status") != "authorized":
            return jsonify({"answer": "Sorry, you are not authorized."})

        route_result = app_logic.route_request(
            question=question,
            _extra_metadata={"confidence_score": 0.95}
        )  # Example of adding extra metadata to the trace
        agent_to_use = route_result.get("agent")

        agent_result = app_logic.execute_agent(agent=agent_to_use, question=question)

        final_result = app_logic.synthesize_response(
            agent_response=agent_result,
            _extra_metadata={
                "synthesis_details": {
                    "model_id": "mock-gpt-4o",
                    "temperature": 0.1,
                },
                'confidence_score': 0.95
            }
        )

        # The response only contains the final answer. Tracing happens directly to the DB.
        return jsonify(final_result)

    except Exception as e:
        # Log the full exception traceback to the console for easy debugging
        app.logger.error("An error occurred while processing the request!", exc_info=True)
        return jsonify({"error": "An internal server error occurred."}), 500

if __name__ == '__main__':
    print("Starting mock chatbot application on http://127.0.0.1:5000")
    # debug=True provides helpful interactive tracebacks in the console.
    app.run(port=5000, debug=True)