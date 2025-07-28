import logging
import json
import re
import os
import time
import sys
import importlib.util
from typing import List, Dict, Any, Optional
from collections import defaultdict

from .llm_providers import get_llm_provider

logger = logging.getLogger(__name__)

class PerformanceEvaluator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.llm_provider = get_llm_provider(config['llm_provider'])
        self.workflow_description = config['workflow_description']

        self._load_prompts_from_config()

    def _load_prompts_from_config(self):
        """Dynamically loads prompts and policies from the user-specified file."""
        prompts_path = self.config.get('prompts_path')
        if not prompts_path:
            raise ValueError("Configuration error: 'prompts_path' is missing from the [evaluation] section.")

        # Resolve the path relative to the current working directory
        absolute_path = os.path.abspath(prompts_path)
        logger.info(f"Loading custom prompts from: {absolute_path}")

        if not os.path.exists(absolute_path):
            raise FileNotFoundError(f"Prompts file not found at the specified path: {absolute_path}")

        try:
            # Use importlib to load the file as a module
            spec = importlib.util.spec_from_file_location("user_prompts", absolute_path)
            user_prompts_module = importlib.util.module_from_spec(spec)
            sys.modules["user_prompts"] = user_prompts_module
            spec.loader.exec_module(user_prompts_module)

            # Store the loaded variables as instance attributes
            self.CUSTOM_POLICIES = getattr(user_prompts_module, 'CUSTOM_POLICIES')
            self.STEP_EVALUATION_PROMPT = getattr(user_prompts_module, 'STEP_EVALUATION_PROMPT')
            self.FINAL_ANSWER_EVALUATION_PROMPT = getattr(user_prompts_module, 'FINAL_ANSWER_EVALUATION_PROMPT')
            self.DEEP_DIVE_SUMMARY_PROMPT = getattr(user_prompts_module, 'DEEP_DIVE_SUMMARY_PROMPT')
        except (AttributeError, FileNotFoundError) as e:
            logger.error(f"Failed to load prompts from '{absolute_path}'. Make sure the file exists and contains all required prompt variables.")
            raise e

    def _extract_json_from_response(self, text: str) -> str:
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    def evaluate_trace(self, trace_data: List[Dict[str, Any]], original_question: str, model_answer: Optional[str]) -> Dict[str, Any]:
        # This method remains the same as the previous version.
        # It performs the individual evaluations that will be used as input for the deep dive.
        report = {"step_evaluations": []}
        if not trace_data:
            logger.warning("Cannot evaluate trace: trace data is empty.")
            return report

        sorted_trace = sorted(trace_data, key=lambda x: x.get('start_time', 0))

        for step in sorted_trace:
            step_name = step.get('name', 'Unknown Step')
            logger.info(f"  - Evaluating step: {step_name}")
            prompt = self.STEP_EVALUATION_PROMPT.format(
                workflow_description=self.workflow_description, original_question=original_question, step_name=step_name,
                step_inputs=json.dumps(step.get('inputs', 'N/A'), indent=2, default=str),
                step_outputs=json.dumps(step.get('outputs', 'N/A'), indent=2, default=str)
            )
            try:
                raw_response = self.llm_provider.invoke(prompt)
                json_str = self._extract_json_from_response(raw_response)
                llm_eval = json.loads(json_str)
                report["step_evaluations"].append({
                    "session_id": step.get('run_id'), "step_name": step_name, "evaluation": llm_eval
                })
                time.sleep(self.config['llm_provider']['requests_delay']) 
            except Exception as e:
                logger.error(f"Failed to evaluate step '{step_name}'. Error: {e}")
                report["step_evaluations"].append({
                    "session_id": step.get('run_id'), "step_name": step_name,
                    "evaluation": {"error": f"LLM evaluation failed. Details: {str(e)}"}
                })
        
        if model_answer:
            final_step = sorted_trace[-1]
            chatbot_final_output = final_step.get('outputs', {})
            if isinstance(chatbot_final_output, str) and chatbot_final_output:
                chatbot_answer_str = chatbot_final_output
            elif isinstance(chatbot_final_output, dict) and 'final_answer' in chatbot_final_output:
                chatbot_answer_str = chatbot_final_output.get('final_answer', str(chatbot_final_output))
            else:
                chatbot_answer_str = str(chatbot_final_output)
                
            policies_str = "\n     ".join(f"{i+1}. {policy}" for i, policy in enumerate(self.CUSTOM_POLICIES))
            logger.info(f"  - Performing sophisticated evaluation of final answer.")
            prompt = self.FINAL_ANSWER_EVALUATION_PROMPT.format(
                original_question=original_question, model_answer=model_answer,
                chatbot_answer=chatbot_answer_str, policies=policies_str
            )
            try:
                raw_response = self.llm_provider.invoke(prompt)
                json_str = self._extract_json_from_response(raw_response)
                llm_eval = json.loads(json_str)
                report["final_answer_evaluation"] = {
                    "session_id": final_step.get('run_id'), "original_question": original_question,
                    "model_answer": model_answer, "chatbot_answer": chatbot_answer_str, "evaluation": llm_eval
                }
                time.sleep(self.config['llm_provider']['requests_delay']) 
            except Exception as e:
                logger.error(f"Failed to evaluate final answer. Error: {e}")
                report["final_answer_evaluation"] = {
                    "session_id": final_step.get('run_id'), "original_question": original_question,
                    "evaluation": {"error": f"LLM evaluation failed. Details: {str(e)}"}
                }
        return report

    def _generate_deep_dive_summary(self, all_step_evaluations: List[Dict], all_final_evaluations: List[Dict]) -> str:                                                                                                              
        """                                                                                                       
        Uses an LLM to generate a qualitative deep-dive summary from both final answer and step evaluations.      
        """                                                                                                       
        logger.info("Generating deep-dive performance summary...")                                                
                                                                                                                
        summary_parts = []                                                                                        
                                                                                                                
        # --- Part 1: Pre-process and Format Final Answer Evaluations ---                                         
        summary_parts.append("## Final Answer Performance Analysis")                                              
        if not all_final_evaluations:                                                                             
            summary_parts.append("No final answer evaluations were available to analyze.")                        
        else:                                                                                                     
            final_answer_analysis = defaultdict(lambda: {'scores': [], 'low_score_reasons': []})                  
            final_answer_criteria = [                                                                             
                "coherence_and_relevance", "safety", "policy_adherence", "answer_quality_vs_model"                
            ]                                                                                                     
                                                                                                                
            for final_eval in all_final_evaluations:                                                              
                eval_data = final_eval.get('evaluation', {})                                                      
                if 'error' in eval_data:                                                                          
                    continue                                                                                      
                                                                                                                
                for criterion in final_answer_criteria:                                                           
                    criterion_data = eval_data.get(criterion, {})                                                 
                    if (score := criterion_data.get('score')) is not None:                                        
                        final_answer_analysis[criterion]['scores'].append(score)                                  
                        if score < 4:  # Low score threshold                                                      
                            reason = criterion_data.get('reasoning', 'No reasoning provided.')                    
                            final_answer_analysis[criterion]['low_score_reasons'].append(reason)                  
                                                                                                                
            for criterion, data in sorted(final_answer_analysis.items()):                                         
                scores = data['scores']                                                                           
                avg_score = f"{sum(scores) / len(scores):.2f}" if scores else "N/A"                               
                summary_parts.append(f"### Criterion: {criterion}")                                               
                summary_parts.append(f"- Average Score: {avg_score} / 5.0 across {len(scores)} runs.")            
                if data['low_score_reasons']:                                                                     
                    summary_parts.append("- Examples of Low-Score Reasons:")                                      
                    unique_reasons = list(set(data['low_score_reasons']))                                         
                    for reason in unique_reasons[:3]:  # Limit to 3 unique examples                               
                        summary_parts.append(f"  - \"{reason}\"")                                                 
                summary_parts.append("") # Add a newline for spacing                                              
                                                                                                                
        summary_parts.append("\n---\n") # Separator                                                               
                                                                                                                
        # --- Part 2: Pre-process and Format Step Evaluations ---                                                 
        summary_parts.append("## Step-by-Step Workflow Analysis")                                                 
        if not all_step_evaluations:                                                                              
            summary_parts.append("No step evaluations were available to analyze.")                                
        else:                                                                                                     
            step_analysis = defaultdict(lambda: {                                                                 
                'correctness_scores': [],                                                                         
                'relevance_scores': [],                                                                           
                'failure_reasons': []                                                                             
            })                                                                                                    
                                                                                                                
            for eval_item in all_step_evaluations:                                                                
                step_name = eval_item['step_name']                                                                
                eval_data = eval_item.get('evaluation', {})                                                       
                if 'error' in eval_data:                                                                          
                    continue                                                                                      
                                                                                                                
                correctness = eval_data.get('correctness', {})                                                    
                relevance = eval_data.get('relevance', {})                                                        
                                                                                                                
                if (score := correctness.get('score')) is not None:                                               
                    step_analysis[step_name]['correctness_scores'].append(score)                                  
                    if score < 4:                                                                                 
                        step_analysis[step_name]['failure_reasons'].append(correctness.get('reasoning', 'No reasoning provided.'))                                                                                            
                                                                                                                
                if (score := relevance.get('score')) is not None:                                                 
                    step_analysis[step_name]['relevance_scores'].append(score)                                    
                    if score < 4 and (reasoning := relevance.get('reasoning')):                                   
                        if reasoning not in step_analysis[step_name]['failure_reasons']:                          
                            step_analysis[step_name]['failure_reasons'].append(reasoning)                         
                                                                                                                
            for step_name, data in sorted(step_analysis.items()):                                                 
                c_scores = data['correctness_scores']                                                             
                r_scores = data['relevance_scores']                                                               
                avg_c = f"{sum(c_scores) / len(c_scores):.2f}" if c_scores else "N/A"                             
                avg_r = f"{sum(r_scores) / len(r_scores):.2f}" if r_scores else "N/A"                             
                                                                                                                
                summary_parts.append(f"### Step: {step_name}")                                                    
                summary_parts.append(f"- Average Correctness Score: {avg_c} / 5.0")                               
                summary_parts.append(f"- Average Relevance Score: {avg_r} / 5.0")                                 
                                                                                                                
                if data['failure_reasons']:                                                                       
                    summary_parts.append("- Examples of Failure Reasons:")                                        
                    unique_reasons = list(set(data['failure_reasons']))                                           
                    for reason in unique_reasons[:5]:                                                             
                        summary_parts.append(f"  - \"{reason}\"")                                                 
                summary_parts.append("\n")                                                                        
                                                                                                                
        # --- Part 3: Create the final prompt and invoke the LLM ---                                              
        evaluation_data_summary = "\n".join(summary_parts)                                                        
        prompt = self.DEEP_DIVE_SUMMARY_PROMPT.format(evaluation_data_summary=evaluation_data_summary)            
                                                                                                                
        try:                                                                                                      
            deep_dive_text = self.llm_provider.invoke(prompt)                                                     
            time.sleep(self.config['llm_provider']['requests_delay'])                                             
            return deep_dive_text                                                                                 
        except Exception as e:                                                                                    
            logger.error(f"Failed to generate deep-dive summary from LLM: {e}")                                   
            return "Error: The deep-dive summary could not be generated due to an LLM provider error." 

    def generate_overall_summary(self, all_step_evaluations: List[Dict], all_final_evaluations: List[Dict]) -> str:
        """Generates the complete summary, including metrics, violations, and the deep-dive analysis."""
        report_lines = ["# Performance Evaluation Summary\n"]
        
        # --- Section 1: Final Answer Violations (from previous step) ---
        if all_final_evaluations:
            # (Safety and Policy violation reporting logic remains here)
            report_lines.append("\n## 🚨 Safety Violations (Score < 5)\n")
            safety_violations = [f for f in all_final_evaluations if f.get('evaluation', {}).get('safety', {}).get('score', 5) < 5]
            if not safety_violations:
                report_lines.append("- ✅ No safety violations detected.")
            else:
                # ... (error reporting logic) ...
                pass 
            
            report_lines.append("\n## 📜 Policy Adherence Issues (Score < 5)\n")
            policy_violations = [f for f in all_final_evaluations if f.get('evaluation', {}).get('policy_adherence', {}).get('score', 5) < 5]
            if not policy_violations:
                report_lines.append("- ✅ No policy violations detected.")
            else:
                # ... (error reporting logic) ...
                pass

        # --- Section 2: LLM-Generated Deep Dive Analysis ---
        if all_step_evaluations or all_final_evaluations:                                                         
            report_lines.append("\n# Deep Dive Workflow Analysis\n")                                              
            # Pass both sets of evaluations to the summary generator                                              
            deep_dive_report = self._generate_deep_dive_summary(all_step_evaluations, all_final_evaluations)      
            report_lines.append(deep_dive_report)                                                                 
        else:                                                                                                     
            report_lines.append("No evaluation data was available to generate a summary.")                        
                                                                                                                
        return "\n".join(report_lines)