import os                                                                                                         
from flask import Flask, request, jsonify                                                                         
from chatbot_test_framework import Tracer, LocalJsonRecorder                                                      
from langchain_openai import ChatOpenAI, OpenAIEmbeddings                                                         
from langchain_community.document_loaders import DirectoryLoader                                                  
from langchain.text_splitter import RecursiveCharacterTextSplitter                                                
from langchain_community.vectorstores import FAISS                                                                
from langchain.chains.combine_documents import create_stuff_documents_chain                                       
from langchain_core.prompts import ChatPromptTemplate                                                             
from langchain_cohere import CohereRerank                                                                         
from dotenv import load_dotenv                                                                                    
from langgraph.graph import StateGraph, END                                                                       
from typing import TypedDict, List                                                                                
                                                                                                                
load_dotenv()                                                                                                     
                                                                                                                
# --- 1. Setup: Same components as V1 ---                                                                         
llm = ChatOpenAI(model="gpt-4.1")                                                                                  
embeddings = OpenAIEmbeddings()                                                                                   
loader = DirectoryLoader("data/hr_policies/")                                                                     
docs = loader.load()                                                                                              
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)                                   
splits = text_splitter.split_documents(docs)                                                                      
vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)                                        
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})                                                      
reranker = CohereRerank(model="rerank-english-v3.0", top_n=2)                                                                                  
                                                                                                                
# --- 2. Define Graph State ---                                                                                   
class RAGState(TypedDict):                                                                                        
    question: str                                                                                                 
    sub_questions: List[str]                                                                                      
    retrieved_docs: List                                                                                          
    reranked_docs: List                                                                                           
    final_answer: str                                                                                             
                                                                                                                
# --- 3. Define Traceable Nodes ---                                                                               
def rewrite_query(state: RAGState):                                                                               
    question = state['question']                                                                                  
    sub_qs = [question, f"details about {question.split(' and ')[0]}", f"details about {question.split(' and ')[-1]}"]                                                                                                         
    return {"sub_questions": sub_qs}                                                                              
                                                                                                                
def retrieve_docs(state: RAGState):                                                                               
    all_docs = []                                                                                                 
    for q in state['sub_questions']:                                                                              
        all_docs.extend(retriever.invoke(q))                                                                      
    # Simple deduplication                                                                                        
    unique_docs = {doc.page_content: doc for doc in all_docs}.values()                                            
    return {"retrieved_docs": list(unique_docs)}                                                                  
                                                                                                                
def rerank_docs(state: RAGState):                                                                                 
    reranked = reranker.compress_documents(documents=state['retrieved_docs'], query=state['question'])            
    return {"reranked_docs": reranked}                                                                            
                                                                                                                
def synthesize_answer(state: RAGState):                                                                           
    prompt = ChatPromptTemplate.from_template("""
Answer the following question based only on the provided context.
Do not use any external knowledge or assumptions. ONLY THE INFORMATION IN THE CONTEXT IS ALLOWED.
<context>{context}</context>
Question: {input}""")                                                 
    document_chain = create_stuff_documents_chain(llm, prompt)                                                    
    response = document_chain.invoke({"input": state['question'], "context": state['reranked_docs']})             
    return {"final_answer": response}                                                                             
                                                                                                                
# --- 4. The Flask App with a Granular Graph ---                                                                  
app = Flask(__name__)                                                                                             
                                                                                                                
@app.route('/invoke', methods=['POST'])                                                                           
def handle_request():                                                                                             
    data = request.json                                                                                           
    question, session_id = data["question"], data["session_id"]                                                   
                                                                                                                
    recorder = LocalJsonRecorder(settings={"filepath": "tests/results/traces_v2.json"})                                 
    tracer = Tracer(recorder=recorder, run_id=session_id)                                                         
                                                                                                                
    traced_rewrite = tracer.trace(step_name="rewrite_query")(rewrite_query)                                       
    traced_retrieve = tracer.trace(step_name="retrieve_docs")(retrieve_docs)                                      
    traced_rerank = tracer.trace(step_name="rerank_docs")(rerank_docs)                                            
    traced_synthesize = tracer.trace(step_name="synthesize_answer")(synthesize_answer)                            
                                                                                                                
    workflow = StateGraph(RAGState)                                                                               
    workflow.add_node("rewrite", traced_rewrite)                                                                  
    workflow.add_node("retrieve", traced_retrieve)                                                                
    workflow.add_node("rerank", traced_rerank)                                                                    
    workflow.add_node("synthesize", traced_synthesize)                                                            
                                                                                                                
    workflow.set_entry_point("rewrite")                                                                           
    workflow.add_edge("rewrite", "retrieve")                                                                      
    workflow.add_edge("retrieve", "rerank")                                                                       
    workflow.add_edge("rerank", "synthesize")                                                                     
    workflow.add_edge("synthesize", END)                                                                          
                                                                                                                
    graph = workflow.compile()                                                                                    
                                                                                                                
    try:                                                                                                          
        result = graph.invoke({"question": question})                                                             
        return jsonify({"final_answer": result['final_answer']})                                                  
    except Exception as e:                                                                                        
        return jsonify({"error": str(e)}), 500                                                                    
                                                                                                                
if __name__ == '__main__':                                                                                        
    app.run(port=5002, debug=True) 