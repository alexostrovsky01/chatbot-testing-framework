import json
import os
import logging
import pandas as pd
import markdown
from datetime import datetime
import html

logger = logging.getLogger(__name__)

class HtmlReportGenerator:
    """
    Generates a self-contained HTML report from the test run results.
    """
    def __init__(self, run_dir: str, run_id: str):
        self.run_dir = run_dir
        self.run_id = run_id
        self.template_path = os.path.join(os.path.dirname(__file__), 'report_template.html')
        
        # Input file paths
        self.final_answer_path = os.path.join(run_dir, 'final_answer_performance.json')
        self.step_performance_path = os.path.join(run_dir, 'step_performance.json')
        self.latency_per_run_path = os.path.join(run_dir, 'latency_per_run.json')
        self.avg_latencies_path = os.path.join(run_dir, 'average_latencies.json')
        self.summary_path = os.path.join(run_dir, 'performance_summary.txt')
        self.run_map_path = os.path.join(run_dir, 'run_map.csv')
        
        # Output file path
        self.output_path = os.path.join(run_dir, 'report.html')

    def _read_json(self, path, default=None):
        if default is None:
            default = []
        if not os.path.exists(path):
            logger.warning(f"File not found, skipping: {path}")
            return default
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error reading {path}: {e}")
            return default

    def _read_text(self, path, default=""):
        if not os.path.exists(path):
            logger.warning(f"File not found, skipping: {path}")
            return default
        try:
            with open(path, 'r') as f:
                return f.read()
        except IOError as e:
            logger.error(f"Error reading {path}: {e}")
            return default

    def _get_score_color(self, score):
        if score is None: return "#888"
        if score >= 4: return "#28a745"  # Green
        if score >= 3: return "#ffc107"  # Yellow
        return "#dc3545"  # Red

    def _prepare_summary_data(self, final_evals, avg_latencies):
        if not final_evals:
            return {
                "kpis": {}, "final_answer_chart_data": "null", "step_performance_chart_data": "null"
            }

        total_tests = len(final_evals)
        passed_tests = sum(1 for e in final_evals if all(c.get('score', 0) >= 4 for c in e.get('evaluation', {}).values()))
        pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

        kpis = {
            "total_tests": total_tests,
            "pass_rate": f"{pass_rate:.1f}%",
            "avg_latency": f"{avg_latencies.get('overall_average_run_latency_seconds', 0):.2f}s"
        }

        # Data for Final Answer Chart
        final_scores = {"coherence_and_relevance": [], "safety": [], "policy_adherence": [], "answer_quality_vs_model": []}
        for e in final_evals:
            for key in final_scores.keys():
                score = e.get('evaluation', {}).get(key, {}).get('score')
                if score is not None:
                    final_scores[key].append(score)
        
        final_avg_scores = {k.replace('_', ' ').title(): (sum(v) / len(v) if v else 0) for k, v in final_scores.items()}
        final_answer_chart_data = json.dumps({
            "labels": list(final_avg_scores.keys()),
            "data": list(final_avg_scores.values())
        })

        return {
            "kpis": kpis,
            "final_answer_chart_data": final_answer_chart_data
        }

    def _prepare_performance_tables(self, final_evals, step_evals, run_map_df):
        final_rows = []
        for item in final_evals:
            session_id = item.get('session_id', 'N/A')
            eval_data = item.get('evaluation', {})
            if 'error' in eval_data: continue

            row = f"""
            <tr>
                <td>{session_id}</td>
                <td>{html.escape(item.get('original_question', ''))}</td>
                <td>{html.escape(item.get('model_answer', ''))}</td>
                <td>{html.escape(item.get('chatbot_answer', ''))}</td>
            """
            for key in ["coherence_and_relevance", "safety", "policy_adherence", "answer_quality_vs_model"]:
                score = eval_data.get(key, {}).get('score')
                reasoning = eval_data.get(key, {}).get('reasoning', '')
                color = self._get_score_color(score)
                row += f'<td><span class="score" style="background-color:{color};">{score or "N/A"}</span><div class="reasoning">{html.escape(reasoning)}</div></td>'
            row += "</tr>"
            final_rows.append(row)

        step_rows = []
        for item in step_evals:
            session_id = item.get('session_id', 'N/A')
            eval_data = item.get('evaluation', {})
            if 'error' in eval_data: continue

            correctness_score = eval_data.get('correctness', {}).get('score')
            correctness_reason = eval_data.get('correctness', {}).get('reasoning', '')
            relevance_score = eval_data.get('relevance', {}).get('score')
            relevance_reason = eval_data.get('relevance', {}).get('reasoning', '')

            row = f"""
            <tr>
                <td>{session_id}</td>
                <td>{html.escape(item.get('step_name', ''))}</td>
                <td><span class="score" style="background-color:{self._get_score_color(correctness_score)};">{correctness_score or "N/A"}</span><div class="reasoning">{html.escape(correctness_reason)}</div></td>
                <td><span class="score" style="background-color:{self._get_score_color(relevance_score)};">{relevance_score or "N/A"}</span><div class="reasoning">{html.escape(relevance_reason)}</div></td>
            </tr>
            """
            step_rows.append(row)

        return "".join(final_rows), "".join(step_rows)

    def _prepare_latency_tables(self, latency_per_run, avg_latencies):
        avg_rows = []
        for item in avg_latencies.get("average_step_latencies", []):
            avg_rows.append(f"<tr><td>{html.escape(item['step_name'])}</td><td>{item['average_latency_seconds']:.4f}</td></tr>")

        per_run_rows = []
        for run in latency_per_run:
            for step in run.get("step_latencies", []):
                per_run_rows.append(f"<tr><td>{run['run_id']}</td><td>{html.escape(step['step_name'])}</td><td>{step['latency_seconds']:.4f}</td></tr>")
        
        return "".join(avg_rows), "".join(per_run_rows)

    def _prepare_violations_tab(self, final_evals):
        safety_violations = []
        policy_violations = []
        
        for item in final_evals:
            session_id = item.get('session_id', 'N/A')
            eval_data = item.get('evaluation', {})
            if 'error' in eval_data: continue

            safety_score = eval_data.get('safety', {}).get('score')
            if safety_score is not None and safety_score < 4:
                safety_violations.append(f"""
                <div class="violation-card">
                    <h4>Safety Violation (Score: {safety_score})</h4>
                    <p><strong>Session ID:</strong> {session_id}</p>
                    <p><strong>Question:</strong> {html.escape(item.get('original_question', ''))}</p>
                    <p><strong>Chatbot Answer:</strong> <span class="violation-text">{html.escape(item.get('chatbot_answer', ''))}</span></p>
                    <p><strong>Reasoning:</strong> {html.escape(eval_data.get('safety', {}).get('reasoning', ''))}</p>
                </div>
                """)

            policy_score = eval_data.get('policy_adherence', {}).get('score')
            if policy_score is not None and policy_score < 4:
                policy_violations.append(f"""
                <div class="violation-card">
                    <h4>Policy Violation (Score: {policy_score})</h4>
                    <p><strong>Session ID:</strong> {session_id}</p>
                    <p><strong>Question:</strong> {html.escape(item.get('original_question', ''))}</p>
                    <p><strong>Chatbot Answer:</strong> <span class="violation-text">{html.escape(item.get('chatbot_answer', ''))}</span></p>
                    <p><strong>Reasoning:</strong> {html.escape(eval_data.get('policy_adherence', {}).get('reasoning', ''))}</p>
                </div>
                """)
        
        return "".join(safety_violations) or "<p>No safety violations found.</p>", "".join(policy_violations) or "<p>No policy violations found.</p>"

    def generate_report(self):
        logger.info("Starting HTML report generation...")
        
        # Read data
        final_evals = self._read_json(self.final_answer_path)
        step_evals = self._read_json(self.step_performance_path)
        latency_per_run = self._read_json(self.latency_per_run_path)
        avg_latencies = self._read_json(self.avg_latencies_path, default={})
        summary_text = self._read_text(self.summary_path)
        
        try:
            run_map_df = pd.read_csv(self.run_map_path)
        except FileNotFoundError:
            run_map_df = pd.DataFrame(columns=['session_id', 'question', 'model_answer'])
            logger.warning(f"File not found: {self.run_map_path}. Some data may be missing in the report.")

        # Prepare content for each section
        summary_data = self._prepare_summary_data(final_evals, avg_latencies)
        final_table, step_table = self._prepare_performance_tables(final_evals, step_evals, run_map_df)
        avg_latency_table, per_run_latency_table = self._prepare_latency_tables(latency_per_run, avg_latencies)
        safety_violations, policy_violations = self._prepare_violations_tab(final_evals)
        deep_dive_html = markdown.markdown(summary_text, extensions=['fenced_code', 'tables'])

        # Read template
        with open(self.template_path, 'r') as f:
            template = f.read()

        # Replace placeholders
        report_html = template.replace("{{RUN_ID}}", self.run_id)
        report_html = report_html.replace("{{GENERATION_TIMESTAMP}}", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        report_html = report_html.replace("{{TOTAL_TESTS}}", str(summary_data['kpis'].get('total_tests', 'N/A')))
        report_html = report_html.replace("{{PASS_RATE}}", str(summary_data['kpis'].get('pass_rate', 'N/A')))
        report_html = report_html.replace("{{AVG_LATENCY}}", str(summary_data['kpis'].get('avg_latency', 'N/A')))
        report_html = report_html.replace("{{FINAL_ANSWER_CHART_DATA}}", summary_data['final_answer_chart_data'])
        report_html = report_html.replace("{{FINAL_ANSWER_PERFORMANCE_ROWS}}", final_table)
        report_html = report_html.replace("{{STEP_PERFORMANCE_ROWS}}", step_table)
        report_html = report_html.replace("{{AVG_LATENCY_ROWS}}", avg_latency_table)
        report_html = report_html.replace("{{PER_RUN_LATENCY_ROWS}}", per_run_latency_table)
        report_html = report_html.replace("{{SAFETY_VIOLATIONS}}", safety_violations)
        report_html = report_html.replace("{{POLICY_VIOLATIONS}}", policy_violations)
        report_html = report_html.replace("{{DEEP_DIVE_CONTENT}}", deep_dive_html)

        # Write final report
        with open(self.output_path, 'w') as f:
            f.write(report_html)
        
        logger.info(f"HTML report successfully generated at {self.output_path}")