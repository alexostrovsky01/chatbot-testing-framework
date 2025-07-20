import logging
from typing import List, Dict, Any
from collections import defaultdict

logger = logging.getLogger(__name__)

class LatencyEvaluator:
    """
    Analyzes trace data to calculate step-by-step and overall latencies.
    """

    def analyze_trace(self, trace_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates latencies for each step within a single trace.

        Args:
            trace_data: A list of dictionaries, where each dictionary represents a
                        traced step from a single run. Each step must have 'name',
                        'start_time', and 'end_time'.

        Returns:
            A dictionary containing the latency of each individual step and the
            total end-to-end latency for the run.
        """
        if not trace_data:
            return {"error": "Trace data is empty."}

        # Sort by start time to ensure logical ordering
        try:
            sorted_trace = sorted(trace_data, key=lambda x: x['start_time'])
        except KeyError:
            return {"error": "One or more trace steps are missing 'start_time'."}

        run_id = sorted_trace[0].get('run_id', 'unknown_run')
        latency_report = {
            "run_id": run_id,
            "step_latencies": []
        }
        
        step_details = []
        all_start_times = []
        all_end_times = []

        for step in sorted_trace:
            try:
                step_name = step['name']
                start = float(step['start_time'])
                end = float(step['end_time'])
                duration = round(end - start, 4)

                step_details.append({
                    "step_name": step_name,
                    "latency_seconds": duration,
                })
                all_start_times.append(start)
                all_end_times.append(end)

            except (KeyError, TypeError) as e:
                logger.warning(f"Skipping step due to missing/invalid data in run {run_id}: {e}")
                step_details.append({
                    "step_name": step.get('name', 'unknown_step'),
                    "error": f"Invalid or missing time data: {e}",
                })
        
        latency_report["step_latencies"] = step_details
        
        # Calculate total latency for the entire trace
        if all_start_times and all_end_times:
            # The min() and max() functions can be used to find the earliest start and latest end time across all steps. [2, 3, 6, 8]
            min_start_time = min(all_start_times)
            max_end_time = max(all_end_times)
            total_duration = round(max_end_time - min_start_time, 4)
            latency_report["total_run_latency_seconds"] = total_duration
        
        return latency_report

    def calculate_averages(self, all_latency_reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates the average latency for each step across all test runs.

        Args:
            all_latency_reports: A list of latency reports, where each report is the
                                 output from the `analyze_trace` method.

        Returns:
            A dictionary with average latencies for each step name and the
            overall average for total run time.
        """
        if not all_latency_reports:
            return {"error": "No latency reports provided to calculate averages."}

        # Use defaultdict to easily handle sums and counts
        step_stats = defaultdict(lambda: {'total_latency': 0.0, 'count': 0})
        total_run_latencies = []

        for report in all_latency_reports:
            if "total_run_latency_seconds" in report:
                total_run_latencies.append(report["total_run_latency_seconds"])

            for step_latency in report.get("step_latencies", []):
                if "latency_seconds" in step_latency:
                    step_name = step_latency["step_name"]
                    latency = step_latency["latency_seconds"]
                    step_stats[step_name]['total_latency'] += latency
                    step_stats[step_name]['count'] += 1
        
        average_report = {
            "average_step_latencies": []
        }

        # The average can be calculated by dividing the sum of values by the number of values. [1, 4, 7]
        for step_name, stats in step_stats.items():
            average_latency = round(stats['total_latency'] / stats['count'], 4) if stats['count'] > 0 else 0
            average_report["average_step_latencies"].append({
                "step_name": step_name,
                "average_latency_seconds": average_latency,
                "total_runs_measured": stats['count']
            })
            
        if total_run_latencies:
            avg_total = round(sum(total_run_latencies) / len(total_run_latencies), 4)
            average_report["overall_average_run_latency_seconds"] = avg_total

        return average_report