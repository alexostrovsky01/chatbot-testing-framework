import time                                                                                                       
import functools                                                                                                  
from typing import Any, Callable, List, Dict, Optional                                                            
                                                                                                                
class Tracer:                                                                                                     
    """                                                                                                           
    A tracer that captures execution data and sends it to a configured recorder.                                  
    It now includes a robust serialization mechanism to handle complex,                                           
    non-JSON-serializable objects gracefully.                                                                     
    """                                                                                                           
    def __init__(self, recorder, run_id: str):                                                                    
        if not hasattr(recorder, 'record'):                                                                       
            raise TypeError("Recorder must have a 'record' method.")                                              
        self._recorder = recorder                                                                                 
        self._run_id = run_id                                                                                     
                                                                                                                
    def _serialize_safely(self, obj: Any) -> Any:                                                                 
        """                                                                                                       
        Recursively traverses an object to convert non-JSON-serializable                                          
        parts into a serializable format.                                                                         
        """                                                                                                       
        if isinstance(obj, (str, int, float, bool, type(None))):                                                  
            return obj                                                                                            
        elif isinstance(obj, dict):                                                                               
            return {self._serialize_safely(k): self._serialize_safely(v) for k, v in obj.items()}                 
        elif isinstance(obj, (list, tuple, set)):                                                                 
            return [self._serialize_safely(item) for item in obj]                                                 
                                                                                                                
        # --- The Core of the Generic Solution ---                                                                
        # 1. Try to use a built-in .to_dict() method if it exists                                                 
        if hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):                                         
            return obj.to_dict()                                                                                  
                                                                                                                
        # 2. Fall back to the object's __dict__ if it exists                                                      
        if hasattr(obj, '__dict__'):                                                                              
            return self._serialize_safely(obj.__dict__)                                                           
                                                                                                                
        # 3. As a last resort, convert the object to its string representation                                    
        try:                                                                                                      
            return repr(obj)                                                                                      
        except Exception:                                                                                         
            return "<UnserializableObject>"                                                                       
                                                                                                                
    def trace(self, step_name: str) -> Callable:                                                                  
        """A decorator to trace a function's execution."""                                                        
        def decorator(func: Callable) -> Callable:                                                                
            @functools.wraps(func)                                                                                
            def wrapper(*args, **kwargs) -> Any:                                                                  
                """                                                                                               
                The wrapper that executes the function and records the trace.                                     
                """                                                                                               
                extra_metadata_from_kwargs = kwargs.pop('_extra_metadata', None)                                  
                                                                                                                
                start_time = time.time()                                                                          
                try:                                                                                              
                    output = func(*args, **kwargs)                                                                
                    status = "success"                                                                            
                    return output                                                                                 
                except Exception as e:                                                                            
                    status = "error"                                                                              
                    output = {"error": type(e).__name__, "message": str(e)}                                       
                    raise                                                                                         
                finally:                                                                                          
                    end_time = time.time()                                                                        
                                                                                                                
                    extra_metadata_from_state = None                                                              
                    if args and isinstance(args[0], dict) and 'current_metadata' in args[0]:                      
                        extra_metadata_from_state = args[0].get('current_metadata')                               
                                                                                                                
                    original_kwargs = kwargs.copy()                                                               
                    if extra_metadata_from_kwargs:                                                                
                        original_kwargs['_extra_metadata'] = extra_metadata_from_kwargs                           
                                                                                                                
                    # --- APPLY THE SAFE SERIALIZATION ---                                                        
                    # We serialize the inputs and outputs before creating the trace record.                       
                    # This ensures all data sent to the recorder is clean.                                        
                    safe_inputs = self._serialize_safely({"args": args, "kwargs": original_kwargs})               
                    safe_outputs = self._serialize_safely(output)                                                 
                                                                                                                
                    trace_data = {                                                                                
                        "run_id": self._run_id, "name": step_name,                                                
                        "start_time": start_time, "end_time": end_time,                                           
                        "status": status,                                                                         
                        "inputs": safe_inputs,                                                                    
                        "outputs": safe_outputs                                                                   
                    }                                                                                             
                                                                                                                
                    if extra_metadata_from_kwargs and isinstance(extra_metadata_from_kwargs, dict):               
                        trace_data.update(extra_metadata_from_kwargs)                                             
                    if extra_metadata_from_state and isinstance(extra_metadata_from_state, dict):                 
                        trace_data.update(extra_metadata_from_state)                                              
                        if isinstance(output, dict):                                                              
                            output.pop('current_metadata', None)                                                  
                                                                                                                
                    self._recorder.record(trace_data)                                                             
            return wrapper                                                                                        
        return decorator                                                                                          
                        