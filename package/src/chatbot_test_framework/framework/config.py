# This module is responsible for loading the config.yaml file and making it available to the rest of the application as a structured object.

import yaml
from typing import Dict, Any, TypedDict

# Using TypedDict for better static analysis and code completion
class ClientConfig(TypedDict):
    type: str
    settings: Dict[str, Any]

class RecorderConfig(TypedDict):
    type: str
    settings: Dict[str, Any]

class TracingConfig(TypedDict):
    recorder: RecorderConfig

class LLMProviderConfig(TypedDict):
    type: str
    settings: Dict[str, Any]

class EvaluationConfig(TypedDict):
    workflow_description: str
    llm_provider: LLMProviderConfig

class FrameworkConfig(TypedDict):
    dataset_path: str
    results_dir: str
    client: ClientConfig
    tracing: TracingConfig
    evaluation: EvaluationConfig


def load_config(path: str) -> FrameworkConfig:
    """
    Loads and validates the framework's configuration from a YAML file.

    Args:
        path: The path to the config.yaml file.

    Returns:
        A dictionary (typed as FrameworkConfig) containing the configuration.

    Raises:
        FileNotFoundError: If the config file does not exist.
        yaml.YAMLError: If the file is not valid YAML.
        KeyError: If a required top-level key is missing.
    """
    try:
        with open(path, 'r') as f:
            config_data = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found at: {path}")
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Error parsing YAML configuration file: {e}")

    # Basic validation for required top-level keys
    required_keys = ['dataset_path', 'results_dir', 'client', 'tracing', 'evaluation']
    for key in required_keys:
        if key not in config_data:
            raise KeyError(f"Required configuration key '{key}' is missing from {path}.")
            
    return config_data