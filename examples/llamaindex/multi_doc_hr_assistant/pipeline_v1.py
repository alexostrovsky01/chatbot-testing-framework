import os   
import time                                                                                                      
from llama_index.core import (                                                                                    
    SimpleDirectoryReader,                                                                                        
    VectorStoreIndex,                                                                                             
    QueryBundle,                                                                                                  
)                                                                                                                 
from llama_index.core.retrievers import VectorIndexRetriever                                                      
from llama_index.core.query_engine import RetrieverQueryEngine                                                    
from llama_index.core.response_synthesizers import get_response_synthesizer                                       
# from llama_index.postprocessor.cohere_rerank import CohereRerank 
from llama_index.postprocessor.rankgpt_rerank import RankGPTRerank                                              
from llama_index.core.tools import QueryEngineTool                                                                
from llama_index.llms.openai import OpenAI                                                                        
from dotenv import load_dotenv                                                                                    
                                                                                                                
load_dotenv() # For OPENAI_API_KEY and COHERE_API_KEY                                                             
                                                                                                                
# --- 1. Data Loading and Indexing ---
docs = SimpleDirectoryReader("data/hr_policies_v2").load_data()                                                   
index = VectorStoreIndex.from_documents(docs)                                                                     
                                                                                                                
# --- 2. Build the RAG Pipeline Components ---                                                                    
llm = OpenAI(model="gpt-4.1")                                                                  

retriever = VectorIndexRetriever(index=index, similarity_top_k=2)                                                 
# reranker = CohereRerank(top_n=2)                                                                                  
reranker = RankGPTRerank(
            llm=llm,
            top_n=2,
            verbose=True,
        )
synthesizer = get_response_synthesizer(llm=llm)                                                                   
                                                                                                                
# --- 3. Define the V1 "Black Box" Pipeline Function ---                                                          
def run_full_pipeline_v1(question: str):                                                                          
    # STEP 1: Query Rewriting (manual implementation for clarity)                                                 
    print("---V1 STEP: Rewriting Query---")                                                                       
    rewrite_prompt = f"Given the user query, generate 2-3 more specific questions for a search engine. Query: {question}"                                                                                                       
    rewritten_queries = llm.complete(rewrite_prompt).text.strip().split('\n')                                     
                                                                                                                
    # STEP 2: Retrieval                                                                                           
    print("---V1 STEP: Retrieving Documents---")                                                                  
    all_nodes = []                                                                                                
    for q in rewritten_queries:                                                                                   
        all_nodes.extend(retriever.retrieve(q))                                                               
                                                                                                                
    # STEP 3: Re-ranking                                                                                          
    print("---V1 STEP: Re-ranking Documents---")                                                                  
    query_bundle = QueryBundle(question)                     
    ranked_nodes = all_nodes                                                     
    # ranked_nodes = reranker.postprocess_nodes(all_nodes, query_bundle)                                            
                                                                                                                
    # STEP 4: Synthesis                                                                                           
    print("---V1 STEP: Synthesizing Final Answer---")                                                             
    response = synthesizer.synthesize(question, nodes=ranked_nodes)    
    print("---V1 STEP: Final Answer Synthesized---")
    # print(response)                                         
    return str(response)  # Return the synthesized answer as a string   