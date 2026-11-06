#!/usr/bin/env python
from setuptools import setup

__version = "1.3.0"
install_requires = [
    "requests",
    "packaging",
    "structlog"
]

# Optional, so existing users do not get them: oc_logging.ecs needs "ecs", oc_logging.tracing
# needs "tracing" (OpenTelemetry, python3.9+). The minimums are the versions tested with
extras_require = {
    "ecs": [
        "ecs-logging>=2.3.0",
    ],
    "tracing": [
        "ecs-logging>=2.3.0",
        "opentelemetry-sdk>=1.45.2",
        "opentelemetry-exporter-otlp-proto-http>=1.45.2",
        "opentelemetry-instrumentation-flask>=0.66b2",
        "opentelemetry-instrumentation-logging>=0.66b2",
        "opentelemetry-instrumentation-requests>=0.66b2",
    ],
}

spec = {
    "name": "oc-logging",
    "version": __version,
    "license": "Apache2.0",
    "description": "Custom Development python API logging libraries",
    "long_description": "Custom Development python API logging libraries",
    "long_description_content_type": "text/plain",
    "install_requires": install_requires,
    "extras_require": extras_require,
    "python_requires": ">=3.8",
}

setup(**spec)
