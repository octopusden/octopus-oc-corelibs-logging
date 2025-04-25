#!/usr/bin/env python
from setuptools import setup

__version = "1.0.0"
install_requires = [
    "requests",
    "packaging",
]
tests_require = []

spec = {
    "name": "oc-logging",
    "version": __version,
    "license": "Apache2.0",
    "description": "Custom Development python API logging libraries",
    "long_description": "Custom Development python API logging libraries",
    "long_description_content_type": "text/plain",
    "install_requires": install_requires,
    "tests_require": tests_require,
    "python_requires": ">=3.6",
}

setup(**spec)
