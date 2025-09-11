"""
Structlog Configuration Wrapper Library

A flexible wrapper for configuring structlog with different output formats
and common configurations.
"""
from oc_logging.wrapper import StructlogWrapper

def setup_json_logging(level: str = "info", **kwargs):
    """
    Setup log in json format.
    Example of the output:
    {"level": "info", "message": "test", "timestamp": "2025-09-11 08:47:42"}
    """
    return StructlogWrapper.quick_setup("json", level, **kwargs)

def setup_text_logging(level: str = "info", **kwargs):
    """
    Setup log in text format.
    Example of the output:
    [2025-09-11 08:47:42 +0000] [INFO] test
    """
    return StructlogWrapper.quick_setup("text", level, **kwargs)

def setup_flask_request_context():
    """
    Setup request context binding for Flask applications.
    Call this in your Flask before_request handler.
    Example of the output:
    {"request_id": "070bbde3-ccf5-4fb5-9683-b99a8a73ada8", "path": "/test", "method": "GET", "level": "info", "message": "test", "timestamp": "2025-09-11 08:49:58"}
    """
    import uuid
    import structlog
    try:
        from flask import request
        structlog.contextvars.clear_contextvars()
        incoming_request_id = request.headers.get("X-Request-ID")
        request_id = incoming_request_id or str(uuid.uuid4())
        if not incoming_request_id:
            request.environ["X-Request-ID"] = request_id

        structlog.contextvars.bind_contextvars(
            path=request.path,
            method=request.method,
            request_id=request_id,
        )
    except ImportError:
        raise ImportError("Flask is required for setup_flask_request_context")
