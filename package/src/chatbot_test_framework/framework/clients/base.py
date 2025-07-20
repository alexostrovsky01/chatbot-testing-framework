# This file defines the abstract base class for all chatbot clients. It ensures that any client you create (e.g., for API, SQS, gRPC) will have the same, predictable interface.

from abc import ABC, abstractmethod
from typing import Dict, Any

class ChatbotClient(ABC):
    """
    Abstract Base Class for clients that send messages to the chatbot application.
    
    This class defines the interface that all concrete client implementations
    must follow, ensuring they can be used interchangeably by the TestRunner.
    """
    def __init__(self, settings: Dict[str, Any]):
        """
        Initializes the client with its specific configuration.

        Args:
            settings: A dictionary containing all necessary configuration
                      parameters for this client (e.g., URL, headers, queue name).
        """
        self.settings = settings

    @abstractmethod
    def send(self, question: str, session_id: str):
        """
        Sends a question to the chatbot application.

        Args:
            question: The text of the question to send.
            session_id: A unique identifier for this interaction, used for
                        tracking and linking trace data.
        
        Raises:
            NotImplementedError: If the method is not implemented by a subclass.
            Exception: Can raise any exception related to the communication
                       (e.g., ConnectionError, Timeout).
        """
        raise NotImplementedError