import os                                                                                                         
from flask import Flask, request, jsonify                                                                         
from chatbot_test_framework import Tracer, LocalJsonRecorder                                                      
from langchain_openai import ChatOpenAI, OpenAIEmbeddings                                                         
from langchain_community.document_loaders import DirectoryLoader                                                  
from langchain.text_splitter import RecursiveCharacterTextSplitter                                                
from langchain_community.vectorstores import FAISS                                                                
from langchain.chains.combine_documents import create_stuff_documents_chain                                       
from langchain_core.prompts import ChatPromptTemplate                                                                                                                                    
from dotenv import load_dotenv                                                                                    
from langgraph.graph import StateGraph, END                                                                       
from typing import TypedDict, List                                                                                
                                                                                                                
load_dotenv()                                                                                                     
                                                                                                                
# --- 1. Setup: Same components as V1 ---                                                                         
llm = ChatOpenAI(model="gpt-4.1", temperature=0)                                                                                   
embeddings = OpenAIEmbeddings()                                                                                   
loader = DirectoryLoader("data/hr_policies/")                                                                     
docs = loader.load()                                                                                              
text_splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=0)                                   
splits = text_splitter.split_documents(docs)                                                                      
vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)                                        
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})                                                                                                                                      
                                                                                                                
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
    prompt = ChatPromptTemplate.from_template("""Rewrite the user's question into vector store queries for better retrieval:
"{input}". Try to limit number of queries to less than 3. Only write the queries, one per line.""")
    response = llm.invoke(prompt.format(input=question))
    print(f"Sub-questions generated: {response.content}")  # Debugging output
    sub_qs = response.content.split('\n')  # Assuming the LLM returns sub-questions in a list format                                                                                                      
    return {"sub_questions": sub_qs}                                                                               
                                                                                                                
def retrieve_docs(state: RAGState):                                                                               
    all_docs = []                                                                                                 
    for q in state['sub_questions']:                                                                              
        all_docs.extend(retriever.invoke(q))                                                                      
    # Simple deduplication                                                                                        
    unique_docs = {doc.page_content: doc for doc in all_docs}.values()                                            
    return {"retrieved_docs": list(unique_docs)}                                                                  
                                                                                                                                                                                          
                                                                                                                
def synthesize_answer(state: RAGState):                                                                           
    prompt = ChatPromptTemplate.from_template("""
Answer the following question based only on the provided context.
Do not use any external knowledge or assumptions. ONLY THE INFORMATION IN THE CONTEXT IS ALLOWED.
You must answer the question as close as possible to the provided context. retain all relevant facts. 
If context is not sufficient, say "I don't have information regarding...".
Not all information in the context is relevant, so you must select the most relevant parts.
<context>{context}</context>
Question: {input}""")                                                 
    document_chain = create_stuff_documents_chain(llm, prompt)                                                    
    response = document_chain.invoke({"input": state['question'], "context": state['retrieved_docs']})             
    return {"final_answer": response}                                                                             
                                                                                                                
# --- 4. The Flask App with a Granular Graph ---                                                                  
app = Flask(__name__)                                                                                             
                                                                                                                
@app.route('/invoke', methods=['POST'])                                                                           
def handle_request():                                                                                             
    data = request.json                                                                                           
    question, session_id = data["question"], data["session_id"]                                                   
                                                                                                                
    recorder = LocalJsonRecorder(settings={"filepath": "tests/results/traces_v2_2.json"})                                 
    tracer = Tracer(recorder=recorder, run_id=session_id)                                                         
                                                                                                                
    traced_rewrite = tracer.trace(step_name="rewrite_query")(rewrite_query)                                       
    traced_retrieve = tracer.trace(step_name="retrieve_docs")(retrieve_docs)                                                                                
    traced_synthesize = tracer.trace(step_name="synthesize_answer")(synthesize_answer)                            
                                                                                                                
    workflow = StateGraph(RAGState)                                                                               
    workflow.add_node("rewrite", traced_rewrite)                                                                  
    workflow.add_node("retrieve", traced_retrieve)                                                                                                                                  
    workflow.add_node("synthesize", traced_synthesize)                                                            
                                                                                                                
    workflow.set_entry_point("rewrite")                                                                           
    workflow.add_edge("rewrite", "retrieve")                                                                                                                                            
    workflow.add_edge("retrieve", "synthesize")                                                                     
    workflow.add_edge("synthesize", END)                                                                          
                                                                                                                
    graph = workflow.compile()                                                                                    
                                                                                                                
    try:                                                                                                          
        result = graph.invoke({"question": question})                                                             
        return jsonify({"final_answer": result['final_answer']})                                                  
    except Exception as e:                                                                                        
        return jsonify({"error": str(e)}), 500                                                                    
                                                                                                                
if __name__ == '__main__':                                                                                        
    app.run(port=5002, debug=True) 