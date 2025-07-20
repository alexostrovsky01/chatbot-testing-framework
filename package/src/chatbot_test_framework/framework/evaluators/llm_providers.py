# This module provides the pluggable system for using different LLMs for evaluation. It abstracts away the specific SDKs, allowing the PerformanceEvaluator to remain generic.

import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any
import boto3

logger = logging.getLogger(__name__)

class BaseLLMProvider(ABC):
    """Abstract Base Class for LLM providers."""
    def __init__(self, settings: Dict[str, Any]):
        self.settings = settings
        self.model = settings.get('model')
        if not self.model:
            raise ValueError("LLM provider settings must include a 'model'.")

    @abstractmethod
    def invoke(self, prompt: str) -> str:
        """Sends a prompt to the LLM and returns the text response."""
        raise NotImplementedError

# --- Concrete Implementations ---

class ClaudeProvider(BaseLLMProvider):
    """Provider for Anthropic's Claude models."""
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        try:
            import anthropic
            api_key = self.settings.get('api_key') or os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("Anthropic API key not found. Set it in config or ANTHROPIC_API_KEY env var.")
            self.client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise ImportError("The 'anthropic' package is required for Claude. Please run 'pip install anthropic'.")

    def invoke(self, prompt: str) -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text

class OpenAIProvider(BaseLLMProvider):
    """Provider for OpenAI's GPT models."""
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        try:
            from openai import OpenAI
            api_key = self.settings.get('api_key') or os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key not found. Set it in config or OPENAI_API_KEY env var.")
            self.client = OpenAI(api_key=api_key)
        except ImportError:
            raise ImportError("The 'openai' package is required. Please run 'pip install openai'.")

    def invoke(self, prompt: str) -> str:
        chat_completion = self.client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
            temperature=0.0,
        )
        return chat_completion.choices[0].message.content

class GeminiProvider(BaseLLMProvider):
    """Provider for Google's Gemini models."""
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        try:
            # import google.generativeai as genai
            api_key = self.settings.get('api_key') or os.environ.get("GOOGLE_API_KEY")
            from google import genai
            if not api_key:
                raise ValueError("Google API key not found. Set it in config or GOOGLE_API_KEY env var.")
            self.genai_client = genai.Client(api_key=api_key)
            # genai.configure(api_key=api_key)
            # self.genai_model = genai.GenerativeModel(self.model)
        except ImportError:
            raise ImportError("The 'google-genai' package is required. Please run 'pip install google-genai'.")

    def invoke(self, prompt: str) -> str:
        # logger.info(f" -- Invoking llm with prompt: {prompt}")
        response = self.genai_client.models.generate_content(
            model=self.model, contents=prompt
        )
        # logger.info(f" -- Rceived results: {response.text}")
        # response = self.genai_model.generate_content(prompt)
        return response.text
    
class BedrockClaudeProvider(BaseLLMProvider):
    """Provider for Anthropic's Claude models via AWS Bedrock."""
    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        if 'region' not in self.settings:
            raise ValueError("Bedrock provider settings must include a 'region'.")
        
        try:
            # boto3 will automatically use credentials from IAM roles or environment variables
            self.client = boto3.client(
                service_name='bedrock-runtime', 
                region_name=self.settings['region']
            )
        except NameError:
             raise ImportError("The 'boto3' package is required for Bedrock. Please run 'pip install boto3'.")

    def invoke(self, prompt: str) -> str:
        """Invokes the Claude model on Bedrock and returns the response."""
        
        # Claude 3 models on Bedrock use the "Messages" API format.
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "temperature": 0.0,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                }
            ],
        }
        
        # Convert the payload to bytes
        body_bytes = json.dumps(payload).encode('utf-8')

        try:
            response = self.client.invoke_model(
                body=body_bytes,
                modelId=self.model, # The model ID from the config, e.g., 'anthropic.claude-3-sonnet...'
                contentType="application/json",
                accept="application/json"
            )
            
            response_body_str = response.get("body").read().decode('utf-8')
            response_body_parsed = json.loads(response_body_str)
            
            # The response text is nested in the 'content' block
            response_text = response_body_parsed.get("content")[0].get("text")
            return response_text

        except Exception as e:
            logger.error(f"AWS Bedrock invocation failed: {e}")
            # Propagate the error to be handled by the evaluator
            raise

# --- Factory Function ---

def get_llm_provider(config: Dict[str, Any]) -> BaseLLMProvider:
    """
    Factory function to instantiate the correct LLM provider based on config.
    """
    provider_type = config.get('type')
    settings = config.get('settings', {})
    
    logger.info(f"Initializing LLM provider of type: {provider_type}")
    
    if provider_type == 'claude':
        return ClaudeProvider(settings)
    elif provider_type == 'openai':
        return OpenAIProvider(settings)
    elif provider_type == 'gemini':
        return GeminiProvider(settings)
    elif provider_type == 'bedrock':
        return BedrockClaudeProvider(settings)
    else:
        raise ValueError(f"Unsupported LLM provider type: '{provider_type}'")

