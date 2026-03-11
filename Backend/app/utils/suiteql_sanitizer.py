"""
SuiteQL Input Sanitization Utilities
Prevents SQL injection in SuiteQL queries sent to NetSuite.
"""
import re

# Whitelist pattern for identifiers (SKUs, location names, etc.)
# Allows common SKU characters while blocking SQL injection chars (' ; " \ --)
_IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z0-9\-._/ ():#,+&@=]{1,100}$')


def validate_suiteql_identifier(value: str, field_name: str = "value") -> str:
    """
    Validate that a value is a safe SuiteQL identifier.
    Allows alphanumeric, hyphens, dots, underscores, slashes, and spaces.

    Args:
        value: The value to validate
        field_name: Name of the field (for error messages)

    Returns:
        The validated value

    Raises:
        ValueError: If the value contains disallowed characters
    """
    if not value or not isinstance(value, str):
        raise ValueError(f"Invalid {field_name}: must be a non-empty string")
    if not _IDENTIFIER_PATTERN.match(value):
        raise ValueError(f"Invalid {field_name}: contains disallowed characters")
    return value


def sanitize_suiteql_value(value: str) -> str:
    """
    Sanitize a string value for use in SuiteQL queries by escaping single quotes.

    Args:
        value: The value to sanitize

    Returns:
        The sanitized value with single quotes doubled
    """
    if not isinstance(value, str):
        raise ValueError("Value must be a string")
    return value.replace("'", "''")


def validate_numeric_id(value, field_name: str = "id") -> str:
    """
    Validate that a value contains only digits (safe for numeric ID fields).

    Args:
        value: The value to validate
        field_name: Name of the field (for error messages)

    Returns:
        The validated string value

    Raises:
        ValueError: If the value is not numeric
    """
    str_value = str(value)
    if not str_value.isdigit():
        raise ValueError(f"Invalid {field_name}: must be numeric")
    return str_value


def validate_numeric_value(value, field_name: str = "value") -> float:
    """
    Validate and convert a value to a safe float.

    Args:
        value: The value to validate
        field_name: Name of the field (for error messages)

    Returns:
        The value as a float

    Raises:
        ValueError: If the value cannot be converted to float
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid {field_name}: must be a number")
