import logging
import os
import time
import json
import pandas as pd
from uuid import uuid4

from .config import FrameworkConfig
from .clients.api_client import ApiClient
from .evaluators.performance import PerformanceEvaluator
from .evaluators.latency import LatencyEvaluator
from .recorders.dynamodb_recorder import DynamoDBRecorder
from .recorders.local_json_recorder import LocalJsonRecorder


logger = logging.getLogger(__name__)

class TestRunner:
    """
    Orchestrates the chatbot testing process based on the framework configuration.
    """
    def __init__(self, config: FrameworkConfig, run_id: str):
        self.config = config
        self.run_id = run_id
        
        # --- FIX: Changed config.results_dir to config['results_dir'] ---
        self.run_dir = os.path.join(config['results_dir'], self.run_id)
        os.makedirs(self.run_dir, exist_ok=True)

        self.run_map_path = os.path.join(self.run_dir, 'run_map.csv')

    def _get_client(self):
        """Initializes the chatbot client based on config."""
        # This part was already correct, using dictionary access
        client_type = self.config['client']['type']
        if client_type == 'api':
            return ApiClient(self.config['client']['settings'])
        else:
            raise ValueError(f"Unsupported client type: {client_type}")

    def _get_recorder(self):
        """Initializes the trace data recorder based on config."""
        # This part was already correct, using dictionary access
        recorder_type = self.config['tracing']['recorder']['type']
        
        if recorder_type == 'dynamodb':
            return DynamoDBRecorder(self.config['tracing']['recorder']['settings'])
        elif recorder_type == 'local_json':
            return LocalJsonRecorder(self.config['tracing']['recorder']['settings'])
        else:
            raise ValueError(f"Unsupported recorder type: {recorder_type}")

    def run_phase1_send_questions(self):
        """
        Executes Phase 1: Reads the dataset and sends each question to the
        chatbot using the configured client.
        """
        client = self._get_client()
        try:
            # --- FIX: Changed self.config.dataset_path to self.config['dataset_path'] ---
            dataset_df = pd.read_csv(self.config['dataset_path'])
            logger.info(f"Loaded {len(dataset_df)} questions from {self.config['dataset_path']}")
        except FileNotFoundError:
            logger.error(f"Dataset file not found at: {self.config['dataset_path']}")
            return

        recorder_config = self.config['tracing']['recorder']

        if recorder_config.get('type') == 'local_json':
            filepath = recorder_config.get('settings', {}).get('filepath')
            if filepath:
                absolute_path = os.path.abspath(filepath)
                recorder_config['settings']['filepath'] = absolute_path
                logger.info(f"Resolved local trace path to: {absolute_path}")

        run_map_data = []
        for index, row in dataset_df.iterrows():
            question = row['model_question']
            model_answer = row.get('model_answer')
            session_id = str(uuid4())
            try:
                client.send(question, session_id, trace_config=recorder_config)
                logger.info(f"Sent question (session_id: {session_id}): '{question[:70]}...'")
                run_map_data.append({'session_id': session_id, 'question': question, 'model_answer': model_answer})
                time.sleep(self.config['client']['delay'])  # Throttle requests to avoid overwhelming the server
            except Exception as e:
                logger.error(f"Failed to send question (session_id: {session_id}): {e}")

        pd.DataFrame(run_map_data).to_csv(self.run_map_path, index=False)
        logger.info(f"Run map saved to {self.run_map_path}")


    def run_phase2_evaluate_performance(self):
        """
        Executes Phase 2: Retrieves trace data for the run and evaluates performance.
        """
        recorder = self._get_recorder()
        
        # --- FIX: Changed self.config.evaluation to self.config['evaluation'] ---
        evaluator = PerformanceEvaluator(self.config['evaluation'])
        
        try:
            run_map_df = pd.read_csv(self.run_map_path)
        except FileNotFoundError:
            logger.error(f"Run map file not found at {self.run_map_path}. Cannot run Phase 2 without Phase 1.")
            return

        all_evaluations = []
        for index, row in run_map_df.iterrows():
            session_id = row['session_id']
            question = row['question']
            model_answer = row.get('model_answer')
            
            if pd.isna(model_answer):
                model_answer = None

            logger.info(f"Evaluating run for session_id: {session_id}")
            
            trace_data = recorder.get_trace(session_id)
            if not trace_data:
                logger.warning(f"No trace data found for session_id: {session_id}. Skipping.")
                continue

            evaluation_report = evaluator.evaluate_trace(
                trace_data=trace_data, 
                original_question=question, 
                model_answer=model_answer
            )
            all_evaluations.append(evaluation_report)
        
        all_step_evals = [step for report in all_evaluations for step in report.get('step_evaluations', [])]
        all_final_evals = [report['final_answer_evaluation'] for report in all_evaluations if 'final_answer_evaluation' in report]

        report_path = os.path.join(self.run_dir, 'step_performance.json')
        with open(report_path, 'w') as f:
            json.dump(all_step_evals, f, indent=2)
        logger.info(f"Step performance report saved to {report_path}")

        final_report_path = os.path.join(self.run_dir, 'final_answer_performance.json')
        with open(final_report_path, 'w') as f:
            json.dump(all_final_evals, f, indent=2)
        logger.info(f"Final answer performance report saved to {final_report_path}")

        summary = evaluator.generate_overall_summary(all_step_evals, all_final_evals)
        summary_path = os.path.join(self.run_dir, 'performance_summary.txt')
        with open(summary_path, 'w') as f:
            f.write(summary)
        logger.info(f"Overall performance summary saved to {summary_path}")


    def run_phase3_evaluate_latency(self):
        """
        Executes Phase 3: Retrieves trace data for the run and evaluates latency.
        """
        recorder = self._get_recorder()
        evaluator = LatencyEvaluator()

        try:
            run_map_df = pd.read_csv(self.run_map_path)
        except FileNotFoundError:
            logger.error(f"Run map file not found at {self.run_map_path}. Cannot run Phase 3 without Phase 1.")
            return

        all_latency_reports = []
        for index, row in run_map_df.iterrows():
            session_id = row['session_id']
            logger.info(f"Analyzing latency for session_id: {session_id}")
            
            trace_data = recorder.get_trace(session_id)
            if not trace_data:
                logger.warning(f"No trace data found for session_id: {session_id}. Skipping.")
                continue
            
            latency_report = evaluator.analyze_trace(trace_data)
            all_latency_reports.append(latency_report)

        per_run_path = os.path.join(self.run_dir, 'latency_per_run.json')
        with open(per_run_path, 'w') as f:
            json.dump(all_latency_reports, f, indent=2)
        logger.info(f"Per-run latency report saved to {per_run_path}")

        avg_report = evaluator.calculate_averages(all_latency_reports)
        avg_path = os.path.join(self.run_dir, 'average_latencies.json')
        with open(avg_path, 'w') as f:
            json.dump(avg_report, f, indent=2)
        logger.info(f"Average latency report saved to {avg_path}")