# octopus-oc-corelibs-logging

A flexible logging library built on top of [structlog](https://www.structlog.org/), providing opinionated configuration, JSON/text formatting, and request context binding for Flask applications.

---

## Features

- Simple setup for **JSON** or **Text** logging formats
- Built-in **timestamp**, **log level**, and **context support**
- **Flask integration** with automatic `X-Request-ID` binding
- Extensible with custom structlog processors
- Compatible with Python’s standard `logging` library

---

## Installation

```bash
pip install octopus-oc-corelibs-logging