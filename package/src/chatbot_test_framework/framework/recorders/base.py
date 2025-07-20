# This file defines the abstract base class for all trace recorders. It establishes a contract that any storage backend must follow, ensuring the TestRunner can retrieve data consistently, regardless of whether it's stored in DynamoDB, a local file, or a future SQL database.

from abc import ABC, abstractmethod
from typing import Dict, Any, List

class TraceRecorder(ABC):
    """
    Abstract Base Class for recorders that store and retrieve trace data.

    This class defines the interface that all concrete recorder implementations
    (e.g., DynamoDB, local file, PostgreSQL) must follow.
    """
    def __init__(self, settings: Dict[str, Any]):
        """
        Initializes the recorder with its specific configuration.

        Args:
            settings: A dictionary of parameters needed for the recorder,
                      such as table name, file path, or DB connection string.
        """
        self.settings = settings

    @abstractmethod
    def record(self, trace_data: Dict[str, Any]):
        """
        Saves a single trace step to the data store.

        This method is called by the @tracer decorator within the chatbot application.

        Args:
            trace_data: A dictionary containing the details of one traced step,
                        including run_id, step name, timings, inputs, and outputs.
        
        Raises:
            NotImplementedError: If the method is not implemented by a subclass.
        """
        raise NotImplementedError

    @abstractmethod
    def get_trace(self, run_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves all trace steps associated with a specific run_id.

        This method is called by the TestRunner during the evaluation and
        latency analysis phases.

        Args:
            run_id: The unique identifier for the test run.

        Returns:
            A list of dictionaries, where each dictionary is a recorded trace step.
            Returns an empty list if the run_id is not found.
        
        Raises:
            NotImplementedError: If the method is not implemented by a subclass.
        """
        raise NotImplementedError