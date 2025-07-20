import logging
import requests
import json
from typing import Dict, Any

from .base import ChatbotClient

logger = logging.getLogger(__name__)

class ApiClient(ChatbotClient):
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        if 'url' not in self.settings or 'body_template' not in self.settings:
            raise ValueError("ApiClient settings must include 'url' and 'body_template'.")
        
        self.url = self.settings['url']
        self.method = self.settings.get('method', 'POST').upper()
        self.headers = self.settings.get('headers', {})
        self.body_template = self.settings['body_template']

    def send(self, question: str, session_id: str, trace_config: Dict[str, Any]):
        """
        Formats and sends an HTTP request, injecting trace configuration.
        """
        try:
            # Serialize the trace_config dict to a JSON string for injection
            trace_config_str = json.dumps(trace_config)
            logger.info(f"trace_config_str: {trace_config_str}")
            
            # Replace all placeholders in the template string
            body_str = self.body_template.replace(
                "{question}", json.dumps(question)[1:-1] # Escape quotes in the question
            ).replace(
                "{session_id}", session_id
            ).replace(
                "{trace_config}", trace_config_str # Inject the config JSON string
            )
            # Parse the final string back into a valid JSON object
            payload = json.loads(body_str)
        except json.JSONDecodeError:
            logger.error("Failed to parse 'body_template' as JSON. Check your config for correctness.")
            raise ValueError("Invalid JSON in 'body_template' configuration.")

        try:
            response = requests.request(
                method=self.method,
                url=self.url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            logger.debug(f"API request to {self.url} for session {session_id} successful.")
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for session {session_id}: {e}")
            raise