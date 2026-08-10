#!/usr/bin/env python
from setuptools import setup

__version = "1.2.2"
install_requires = [
    "requests",
    "packaging",
    "structlog"
]

spec = {
    "name": "oc-logging",
    "version": __version,
    "license": "Apache2.0",
    "description": "Custom Development python API logging libraries",
    "long_description": "Custom Development python API logging libraries",
    "long_description_content_type": "text/plain",
    "install_requires": install_requires,
    "python_requires": ">=3.8",
}

setup(**spec)
