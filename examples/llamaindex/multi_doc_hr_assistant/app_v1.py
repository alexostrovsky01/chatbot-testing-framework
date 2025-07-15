from flask import Flask, request, jsonify                                                                         
from chatbot_test_framework import Tracer, LocalJsonRecorder                                                      
from pipeline_v1 import run_full_pipeline_v1                                                                      
                                                                                                                
app = Flask(__name__)                                                                                             
                                                                                                                
@app.route('/invoke', methods=['POST'])                                                                           
def handle_request():                                                                                             
    data = request.json                                                                                           
    question, session_id = data["question"], data["session_id"]                                                   
                                                                                                                
    recorder = LocalJsonRecorder(settings={"filepath": "tests/results/traces_v1.json"})                                 
    tracer = Tracer(recorder=recorder, run_id=session_id)                                                         
                                                                                                                
    @tracer.trace(step_name="full_rag_pipeline_v1")                                                               
    def run_traced_pipeline(q: str):                                                                              
        return run_full_pipeline_v1(q)                                                                            
                                                                                                                
    try:                                                                                                          
        response = run_traced_pipeline(question)                                                                  
        return jsonify({"final_answer": response})                                                           
    except Exception as e:                                                                                        
        return jsonify({"error": str(e)}), 500                                                                    
                                                                                                                
if __name__ == '__main__':                                                                                        
    app.run(port=5001, debug=True)  