from __future__ import annotations

from copy import deepcopy

from ..llm.types import ToolCall
from .types import AgentTool


class SchemaValidationError(ValueError):
    pass


def validate_tool_arguments(tool: AgentTool, tool_call: ToolCall) -> object:
    return validate_json_value(tool_call.arguments, tool.parameters, path="arguments")


def validate_json_value(value: object, schema: object, *, path: str = "value") -> object:
    if not isinstance(schema, dict):
        return deepcopy(value)

    if "const" in schema and value != schema["const"]:
        raise SchemaValidationError(f"{path} must equal {schema['const']!r}")

    if "enum" in schema:
        enum_values = schema["enum"]
        if isinstance(enum_values, list) and value not in enum_values:
            raise SchemaValidationError(f"{path} must be one of {enum_values!r}")

    if "anyOf" in schema:
        any_of = schema["anyOf"]
        if not isinstance(any_of, list):
            raise SchemaValidationError(f"{path} has invalid anyOf schema")
        errors: list[str] = []
        for candidate in any_of:
            try:
                return validate_json_value(value, candidate, path=path)
            except SchemaValidationError as exc:
                errors.append(str(exc))
        joined = "; ".join(errors) if errors else "no matching schema"
        raise SchemaValidationError(f"{path} did not match any allowed schema: {joined}")

    if "oneOf" in schema:
        one_of = schema["oneOf"]
        if not isinstance(one_of, list):
            raise SchemaValidationError(f"{path} has invalid oneOf schema")
        matches: list[object] = []
        for candidate in one_of:
            try:
                matches.append(validate_json_value(value, candidate, path=path))
            except SchemaValidationError:
                continue
        if len(matches) != 1:
            raise SchemaValidationError(f"{path} must match exactly one schema")
        return matches[0]

    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        errors: list[str] = []
        for candidate in expected_type:
            try:
                return validate_json_value(value, {**schema, "type": candidate}, path=path)
            except SchemaValidationError as exc:
                errors.append(str(exc))
        joined = "; ".join(errors) if errors else "no matching type"
        raise SchemaValidationError(f"{path} did not match any allowed type: {joined}")

    if expected_type == "object":
        return _validate_object(value, schema, path)
    if expected_type == "array":
        return _validate_array(value, schema, path)
    if expected_type == "string":
        return _validate_string(value, schema, path)
    if expected_type == "integer":
        return _validate_integer(value, schema, path)
    if expected_type == "number":
        return _validate_number(value, schema, path)
    if expected_type == "boolean":
        return _validate_boolean(value, schema, path)
    if expected_type == "null":
        if value is not None:
            raise SchemaValidationError(f"{path} must be null")
        return None

    return deepcopy(value)


def _validate_object(value: object, schema: dict[str, object], path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SchemaValidationError(f"{path} must be an object")

    properties = schema.get("properties")
    if properties is None:
        properties = {}
    if not isinstance(properties, dict):
        raise SchemaValidationError(f"{path} has invalid properties schema")

    required = schema.get("required")
    required_keys = set(required) if isinstance(required, list) else set()
    missing = sorted(key for key in required_keys if key not in value)
    if missing:
        raise SchemaValidationError(f"{path} is missing required fields: {', '.join(missing)}")

    additional_properties = schema.get("additionalProperties", True)
    if additional_properties is False:
        unknown_keys = sorted(key for key in value if key not in properties)
        if unknown_keys:
            raise SchemaValidationError(f"{path} has unknown fields: {', '.join(unknown_keys)}")

    result: dict[str, object] = {}
    for key, item in value.items():
        item_path = f"{path}.{key}"
        property_schema = properties.get(key)
        if property_schema is not None:
            result[key] = validate_json_value(item, property_schema, path=item_path)
            continue
        if isinstance(additional_properties, dict):
            result[key] = validate_json_value(item, additional_properties, path=item_path)
            continue
        result[key] = deepcopy(item)

    return result


def _validate_array(value: object, schema: dict[str, object], path: str) -> list[object]:
    if not isinstance(value, list):
        raise SchemaValidationError(f"{path} must be an array")

    min_items = schema.get("minItems")
    if isinstance(min_items, int) and len(value) < min_items:
        raise SchemaValidationError(f"{path} must contain at least {min_items} item(s)")

    max_items = schema.get("maxItems")
    if isinstance(max_items, int) and len(value) > max_items:
        raise SchemaValidationError(f"{path} must contain at most {max_items} item(s)")

    item_schema = schema.get("items")
    if item_schema is None:
        return deepcopy(value)

    return [
        validate_json_value(item, item_schema, path=f"{path}[{index}]")
        for index, item in enumerate(value)
    ]


def _validate_string(value: object, schema: dict[str, object], path: str) -> str:
    if not isinstance(value, str):
        raise SchemaValidationError(f"{path} must be a string")

    min_length = schema.get("minLength")
    if isinstance(min_length, int) and len(value) < min_length:
        raise SchemaValidationError(f"{path} must be at least {min_length} character(s)")

    max_length = schema.get("maxLength")
    if isinstance(max_length, int) and len(value) > max_length:
        raise SchemaValidationError(f"{path} must be at most {max_length} character(s)")

    return value


def _validate_integer(value: object, schema: dict[str, object], path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaValidationError(f"{path} must be an integer")
    _apply_numeric_bounds(value, schema, path)
    return value


def _validate_number(value: object, schema: dict[str, object], path: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SchemaValidationError(f"{path} must be a number")
    _apply_numeric_bounds(value, schema, path)
    return value


def _validate_boolean(value: object, _schema: dict[str, object], path: str) -> bool:
    if not isinstance(value, bool):
        raise SchemaValidationError(f"{path} must be a boolean")
    return value


def _apply_numeric_bounds(value: int | float, schema: dict[str, object], path: str) -> int | float:
    minimum = schema.get("minimum")
    if isinstance(minimum, int | float) and value < minimum:
        raise SchemaValidationError(f"{path} must be >= {minimum}")

    maximum = schema.get("maximum")
    if isinstance(maximum, int | float) and value > maximum:
        raise SchemaValidationError(f"{path} must be <= {maximum}")

    return value
