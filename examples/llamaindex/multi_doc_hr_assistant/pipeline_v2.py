import os   
import time  
from flask import Flask, request, jsonify                                                                                                       
from llama_index.core import (                                                                                    
    SimpleDirectoryReader,                                                                                        
    VectorStoreIndex,                                                                                             
    QueryBundle,                                                                                                  
)                                                                                                                 
from llama_index.core.retrievers import VectorIndexRetriever                                                      
from llama_index.core.query_engine import RetrieverQueryEngine                                                    
from llama_index.core.response_synthesizers import get_response_synthesizer                                       
from llama_index.postprocessor.cohere_rerank import CohereRerank                                           
from llama_index.core.tools import QueryEngineTool                                                                
from llama_index.llms.openai import OpenAI                                                                        
from dotenv import load_dotenv  
from chatbot_test_framework import Tracer, LocalJsonRecorder    

load_dotenv() # For OPENAI_API_KEY and COHERE_API_KEY                                         
                                                                                                                
# --- Refactor the pipeline into distinct, traceable functions ---   

# --- 1. Data Loading and Indexing ---                                                                                                                                               
docs = SimpleDirectoryReader("data/hr_policies_v2").load_data()                                                   
index = VectorStoreIndex.from_documents(docs)     

# --- 2. Build the RAG Pipeline Components ---                                                                    
llm = OpenAI(model="gpt-4.1")                                                                  

retriever = VectorIndexRetriever(index=index, similarity_top_k=2, doc_ids=list(index.ref_doc_info.keys()))                                                 
reranker = CohereRerank(top_n=2)                                                                                  
synthesizer = get_response_synthesizer(llm=llm) 
                                                                                                                
def rewrite_query(question: str):                                                                                 
    print("---V2 STEP: Rewriting Query---")                                                                       
    prompt = f"Given the user query, generate 2-3 more specific questions for a search engine. Query: {question}" 
    response = llm.complete(prompt)                                                                               
    return response.text.strip().split('\n')                                                                      
                                                                                                                
def retrieve_nodes(queries: list):                                                                                
    print("---V2 STEP: Retrieving Documents---")                                                                  
    all_nodes = []                                                                                                
    for q in queries:                                                                                             
        all_nodes.extend(retriever.retrieve(q))                           
    return all_nodes                                                                                              
                                                                                                                
def rerank_nodes(nodes: list, original_question: str):                                                            
    print("---V2 STEP: Re-ranking Documents---")                                                                  
    query_bundle = QueryBundle(original_question)                                                                 
    return reranker.postprocess_nodes(nodes, query_bundle)                                                        
                                                                                                                
def synthesize_answer(ranked_nodes: list, original_question: str):                                                
    print("---V2 STEP: Synthesizing Final Answer---")                                                             
    return synthesizer.synthesize(original_question, nodes=ranked_nodes)                                          
                                                                                                                
# --- The Flask App with Granular Tracing ---                                                                     
app = Flask(__name__)                                                                                             
                                                                                                                
@app.route('/invoke', methods=['POST'])                                                                           
def handle_request():                                                                                             
    data = request.json                                                                                           
    question, session_id = data["question"], data["session_id"]                                                   
                                                                                                                
    recorder = LocalJsonRecorder(settings={"filepath": "tests/results/traces_v2.json"})                                 
    tracer = Tracer(recorder=recorder, run_id=session_id)                                                         
                                                                                                                
    # --- Apply the @trace decorator to EACH function ---                                                         
    traced_rewrite = tracer.trace(step_name="rewrite_query")(rewrite_query)                                       
    traced_retrieve = tracer.trace(step_name="retrieve_nodes")(retrieve_nodes)                                    
    traced_rerank = tracer.trace(step_name="rerank_nodes")(rerank_nodes)                                          
    traced_synthesize = tracer.trace(step_name="synthesize_answer")(synthesize_answer)                            
                                                                                                                
    try:                                                                                                          
        # --- Execute the pipeline step-by-step ---                                                               
        rewritten_queries = traced_rewrite(question)                                                              
        retrieved_nodes = traced_retrieve(rewritten_queries)                                                    
        final_nodes = traced_rerank(retrieved_nodes, question)                                                    
        response = traced_synthesize(final_nodes, question)                                                       
                                                                                                                
        return jsonify({"final_answer": str(response)})                                                           
    except Exception as e:                                                                                        
        return jsonify({"error": str(e)}), 500                                                                    
                                                                                                                
if __name__ == '__main__':                                                                                        
    app.run(port=5002, debug=True)  