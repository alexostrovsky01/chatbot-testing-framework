# A simple recorder that saves traces to a single local JSON file. This is excellent for local development and testing the framework without needing any cloud infrastructure. It includes file locking to prevent data corruption.

import logging
import json
import os
from filelock import FileLock, Timeout
from typing import Dict, Any, List

from .base import TraceRecorder

logger = logging.getLogger(__name__)

class LocalJsonRecorder(TraceRecorder):
    """
    Records trace data to a local JSON file.
    
    This recorder is useful for local development and testing without cloud dependencies.
    It uses a file lock to ensure safe concurrent writes.
    """
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.filepath = self.settings.get('filepath', 'results/traces.json')
        self.lock_path = f"{self.filepath}.lock"
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)

    def _read_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Reads all data from the JSON file."""
        if not os.path.exists(self.filepath):
            return {}
        with open(self.filepath, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {} # Return empty if file is corrupt or empty

    def record(self, trace_data: Dict[str, Any]):
        """Appends a trace step to the JSON file under its run_id."""
        run_id = trace_data.get('run_id')
        if not run_id:
            logger.error("Trace data is missing 'run_id'. Cannot record.")
            return

        lock = FileLock(self.lock_path, timeout=5)
        try:
            with lock:
                all_data = self._read_data()
                if run_id not in all_data:
                    all_data[run_id] = []
                all_data[run_id].append(trace_data)
                
                with open(self.filepath, 'w') as f:
                    json.dump(all_data, f, indent=2)
            logger.debug(f"Successfully recorded step '{trace_data.get('name')}' for run_id {run_id} to file.")
        except Timeout:
            logger.error(f"Could not acquire file lock for {self.filepath} to record trace.")
        except Exception as e:
            logger.error(f"Failed to record trace to file: {e}")

    def get_trace(self, run_id: str) -> List[Dict[str, Any]]:
        """Retrieves all steps for a given run_id from the JSON file."""
        lock = FileLock(self.lock_path, timeout=5)
        try:
            with lock:
                all_data = self._read_data()
                return all_data.get(run_id, [])
        except Timeout:
            logger.error(f"Could not acquire file lock for {self.filepath} to get trace.")
            return []
        except Exception as e:
            logger.error(f"Failed to get trace from file: {e}")
            return []