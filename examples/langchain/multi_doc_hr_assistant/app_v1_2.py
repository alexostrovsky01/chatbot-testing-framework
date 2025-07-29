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
from langchain.chains import create_retrieval_chain                                                               
from dotenv import load_dotenv                                                                                    
                                                                                                                
load_dotenv() # For OPENAI_API_KEY and COHERE_API_KEY                                                             
                                                                                                                
# --- 1. Setup: Load data and build LangChain components ---                                                      
llm = ChatOpenAI(model="gpt-4.1", temperature=0)                                                                                  
embeddings = OpenAIEmbeddings()                                                                                   
loader = DirectoryLoader("data/hr_policies/")                                                                     
docs = loader.load()                                                                                              
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)                                   
splits = text_splitter.split_documents(docs)                                                                      
vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)                                        
retriever = vectorstore.as_retriever(search_kwargs={"k": 3}) # Retrieve more to give reranker a choice            
                                                                                                                
# --- 2. The V1 "Black Box" Pipeline Function ---                                                                 
def run_full_pipeline_v1(question: str):                                                                          
    # Step 1: Query Rewriting (Simplified for clarity)                                                            
    # In a real app, this would be an LLM call. Here we simulate it.                                              
    # sub_questions = [question, f"details about {question.split(' and ')[0]}", f"details about {question.split(' and ')[-1]}"]                                                                             
 
    prompt = ChatPromptTemplate.from_template("""Rewrite the user's question into vector store queries for better retrieval:
"{input}". Try to limit number of queries to less than 3. Only write the queries, one per line.""")
    response = llm.invoke(prompt.format(input=question))  # Assuming the LLM returns sub-questions in a list format
    sub_questions = response.content.split('\n')  # Assuming the LLM returns sub-questions in a list format                                                                                                        
    print(f"Sub-questions generated: {sub_questions}")  # Debugging output
                                                                                                                
    # Step 2: Retrieval                                                                                           
    all_docs = []                                                                                                 
    for q in sub_questions:                                                                                       
        all_docs.extend(retriever.invoke(q))                                                                      
    unique_docs = {doc.page_content: doc for doc in all_docs}.values()                                                                          
    # Step 3: Re-ranking (The hidden flaw)                                                                        
    # reranker = CohereRerank(model="rerank-english-v3.0", top_n=2)                                                                              
    # reranked_docs = reranker.compress_documents(documents=all_docs, query=question)                               
                                                                                                                
    # Step 4: Synthesis                                                                                           
    prompt = ChatPromptTemplate.from_template("""
Answer the following question based only on the provided context.
Do not use any external knowledge or assumptions. ONLY THE INFORMATION IN THE CONTEXT IS ALLOWED.
You must answer the question as close as possible to the provided context.
Not all information in the context is relevant, so you must select the most relevant parts.
<context>{context}</context>
Question: {input}""")                                                   
    document_chain = create_stuff_documents_chain(llm, prompt)                                                    
                                                                                                                
    response = document_chain.invoke({                                                                            
        "input": question,                                                                                        
        "context": unique_docs                                                                                  
    })                                                                                                            
    return response                                                                                               
                                                                                                                
# --- 3. The Flask App with a single trace point ---                                                              
app = Flask(__name__)                                                                                             
                                                                                                                
@app.route('/invoke', methods=['POST'])                                                                           
def handle_request():                                                                                             
    data = request.json                                                                                           
    question, session_id = data["question"], data["session_id"]                                                   
                                                                                                                
    recorder = LocalJsonRecorder(settings={"filepath": "tests/results/traces_v1_2.json"})                                 
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