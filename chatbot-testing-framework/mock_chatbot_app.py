import time
from flask import Flask, request, jsonify

# --- Import framework components for tracing ---
# # This demonstrates how your actual chatbot app would integrate the tracer.
# from framework.core.trace import Tracer
# from framework.recorders.local_json_recorder import LocalJsonRecorder

from chatbot_test_framework import Tracer
from chatbot_test_framework import LocalJsonRecorder

app = Flask(__name__)

# --- Mock Application Logic ---

class MockChatbotApp:
    def __init__(self, tracer):
        self.tracer = tracer

    @property
    def authorize(self):
        # Decorate the function with the tracer
        @self.tracer.trace(step_name="authorize_user")
        def _authorize(user_id: str):
            """Simulates checking if a user is authorized."""
            time.sleep(0.1)  # Simulate latency
            if "premium" in user_id:
                return {"status": "authorized", "level": "premium"}
            return {"status": "unauthorized"}
        return _authorize

    @property
    def route_request(self):
        @self.tracer.trace(step_name="route_request")
        def _route_request(question: str):
            """Simulates routing a request to the correct agent."""
            time.sleep(0.2) # Simulate latency
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
            time.sleep(0.5) # Simulate latency
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
            time.sleep(0.15) # Simulate latency
            final_message = f"Support Bot: {agent_response['response']}"
            return {"final_answer": final_message}
        return _synthesize_response


# --- Flask API Endpoint ---

@app.route('/invoke', methods=['POST'])
def handle_request():
    """This is the API endpoint our testing framework will call."""
    data = request.json
    question = data.get('question')
    session_id = data.get('session_id') # The framework sends this!
    user_id = "user_premium_123" # Hardcoded for this example

    if not question or not session_id:
        return jsonify({"error": "Missing 'question' or 'session_id'"}), 400

    # --- TRACING SETUP ---
    # 1. Initialize the Recorder for this run. We use the local JSON recorder.
    #    The framework's config tells the *TestRunner* where to look for this file.
    recorder = LocalJsonRecorder(settings={"filepath": "chatbot_test_framework/results/traces.json"})

    # 2. Initialize the Tracer, linking it to this specific run via the session_id.
    tracer = Tracer(recorder=recorder, run_id=session_id)
    
    # 3. Instantiate our app logic, passing the tracer to it.
    app_logic = MockChatbotApp(tracer)

    # --- EXECUTE THE MULTI-STEP WORKFLOW ---
    try:
        auth_result = app_logic.authorize(user_id=user_id)
        if auth_result.get("status") != "authorized":
            return jsonify({"answer": "Sorry, you are not authorized."})

        route_result = app_logic.route_request(question=question)
        agent_to_use = route_result.get("agent")

        agent_result = app_logic.execute_agent(agent=agent_to_use, question=question)

        final_result = app_logic.synthesize_response(agent_response=agent_result)

        return jsonify(final_result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting mock chatbot application on http://127.0.0.1:5000")
    app.run(port=5000, debug=False)