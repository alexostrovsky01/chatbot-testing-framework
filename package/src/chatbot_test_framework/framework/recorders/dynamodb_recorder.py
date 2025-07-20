import logging
from typing import Dict, Any, List, Optional
from decimal import Decimal

import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

from .base import TraceRecorder

logger = logging.getLogger(__name__)

class DynamoDBRecorder(TraceRecorder):
    """
    Records trace data to an AWS DynamoDB table.

    This recorder supports two modes, determined by the `schema_mapping` parameter:
    1.  Default Mode: If no schema_mapping is provided, it appends the full, original
        trace object for each step to a list named 'trace_steps'.
    2.  Hybrid Mode: If a schema_mapping is provided, it performs two actions in one
        API call:
        a) Maps specified values from the trace data to top-level attributes for easy
           querying and indexing.
        b) Appends the full, original trace object to the 'trace_steps' list to
           ensure the complete data is always preserved as the source of truth.
    """
    def __init__(self, settings: Dict[str, Any], schema_mapping: Optional[Dict[str, str]] = None):
        """
        Initializes the recorder.

        Args:
            settings: Dictionary with core settings like 'table_name' and 'region'.
            schema_mapping (Optional): A dictionary defining how to map trace data
                                      to top-level DynamoDB attributes.
        """
        super().__init__(settings)
        if 'table_name' not in self.settings:
            raise ValueError("DynamoDBRecorder settings must include 'table_name'.")
        
        self.table_name = self.settings['table_name']
        self.region = self.settings.get('region')
        self.run_id_key = self.settings.get('run_id_key', 'run_id')
        self.schema_mapping = schema_mapping
        self.trace_list_key = 'trace_steps'

        try:
            self.client = boto3.client('dynamodb', region_name=self.region)
            self._serializer = TypeSerializer()
        except ImportError:
            raise ImportError("The 'boto3' package is required for DynamoDB.")

    def _sanitize_item_for_dynamodb(self, obj: Any) -> Any:
        """
        Recursively traverses a Python object and converts float values to Decimals.
        """
        if isinstance(obj, dict):
            return {k: self._sanitize_item_for_dynamodb(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize_item_for_dynamodb(elem) for elem in obj]
        elif isinstance(obj, float):
            return Decimal(str(obj))
        return obj

    @staticmethod
    def _get_nested_value(data: Dict, path: str, default: Any = None) -> Any:
        """
        Retrieves a value from a nested dictionary using dot notation.
        """
        keys = path.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def _record_hybrid(self, run_id: str, trace_data: Dict[str, Any]):
        """
        Builds and executes a single, combined UpdateItem call to both map
        attributes and append the full trace to a list.
        """
        update_parts = []
        expression_attribute_names = {}
        expression_attribute_values = {}

        # --- Part 1: Build the expression for mapping top-level attributes ---
        for dynamo_attr, trace_path in self.schema_mapping.items():
            name_placeholder = f"#{dynamo_attr}"
            value_placeholder = f":{dynamo_attr}_val"
            
            expression_attribute_names[name_placeholder] = dynamo_attr
            
            if trace_path == "latency":
                start = trace_data.get('start_time')
                end = trace_data.get('end_time')
                value = (end - start) if start is not None and end is not None else None
            else:
                value = self._get_nested_value(trace_data, trace_path)

            update_parts.append(f"{name_placeholder} = {value_placeholder}")
            expression_attribute_values[value_placeholder] = self._serializer.serialize(self._sanitize_item_for_dynamodb(value)) if value is not None else {'NULL': True}

        # --- Part 2: Build the expression for appending the full trace to the list ---
        safe_full_trace = self._sanitize_item_for_dynamodb(trace_data)
        step_as_dynamodb_json = [self._serializer.serialize(safe_full_trace)]
        
        list_name_placeholder = f"#{self.trace_list_key}"
        expression_attribute_names[list_name_placeholder] = self.trace_list_key
        
        update_parts.append(f"{list_name_placeholder} = list_append(if_not_exists({list_name_placeholder}, :empty_list), :step)")
        expression_attribute_values[':step'] = {'L': step_as_dynamodb_json}
        expression_attribute_values[':empty_list'] = {'L': []}
        
        # --- Part 3: Combine and execute the single API call ---
        update_expression = "SET " + ", ".join(update_parts)
        
        self.client.update_item(
            TableName=self.table_name,
            Key={self.run_id_key: {'S': run_id}},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values
        )
        logger.debug(f"Successfully recorded hybrid data for run_id {run_id}.")

    def _record_default(self, run_id: str, trace_data: Dict[str, Any]):
        """The original behavior: appends the entire step to a list."""
        safe_trace_data = self._sanitize_item_for_dynamodb(trace_data)
        step_as_dynamodb_json = [self._serializer.serialize(safe_trace_data)]
        
        self.client.update_item(
            TableName=self.table_name,
            Key={self.run_id_key: {'S': run_id}},
            UpdateExpression=f"SET {self.trace_list_key} = list_append(if_not_exists({self.trace_list_key}, :empty_list), :step)",
            ExpressionAttributeValues={
                ':step': {'L': step_as_dynamodb_json},
                ':empty_list': {'L': []}
            }
        )
        logger.debug(f"Successfully appended step '{safe_trace_data.get('name')}' for run_id {run_id}.")

    def record(self, trace_data: Dict[str, Any]):
        """
        Records trace data using either the hybrid (schema + list) mode or
        the default (list only) mode.
        """
        run_id = trace_data.get('run_id')
        if not run_id:
            logger.error("Trace data is missing 'run_id'. Cannot record.")
            return
        
        try:
            if self.schema_mapping:
                self._record_hybrid(run_id, trace_data)
            else:
                self._record_default(run_id, trace_data)
        except ClientError as e:
            logger.error(f"Failed to record trace to DynamoDB for run_id {run_id}.", exc_info=True)
            raise e

    def get_trace(self, run_id: str) -> List[Dict[str, Any]]:
        """
        Retrieves the complete list of trace steps for a given run_id.
        This method always reads from the 'trace_steps' list, as it is the
        guaranteed source of truth for the full trace data.
        """
        from boto3.dynamodb.types import TypeDeserializer
        deserializer = TypeDeserializer()
        
        try:
            response = self.client.get_item(
                TableName=self.table_name,
                Key={self.run_id_key: {'S': run_id}},
                # We only need to retrieve the trace_steps list for evaluation
                ProjectionExpression=self.trace_list_key
            )
        except ClientError as e:
            logger.error(f"Failed to get trace from DynamoDB for run_id {run_id}: {e}")
            return []
        
        item = response.get('Item')
        if not item or self.trace_list_key not in item:
            logger.warning(f"No trace data found in '{self.trace_list_key}' for run_id: {run_id}")
            return []

        dynamodb_list = item[self.trace_list_key].get('L', [])
        return [deserializer.deserialize({'M': step['M']}) for step in dynamodb_list]