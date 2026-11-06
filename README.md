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
```

---

## ECS JSON logs with trace ids

For services shipping logs to Elasticsearch/Kibana. Every record, from the app, its libraries
and gunicorn, becomes one [ECS](https://www.elastic.co/guide/en/ecs/current/index.html) JSON
object per line on stdout. A request's lines carry `trace.id` and `span.id`, continued from an
incoming W3C `traceparent` header and passed on to every `requests` call, so one search on
`trace.id` finds the request in every service it went through.

These use the standard `logging` library, not structlog: `logging.getLogger(__name__)` as usual.

```bash
pip install "oc-logging[ecs]"       # logs only
pip install "oc-logging[tracing]"   # logs and trace ids (OpenTelemetry, python3.9+)
```

### Flask behind gunicorn

`gunicorn.conf.py`, in the directory gunicorn starts from (otherwise gunicorn skips it and
logs plain text):

```python
from oc_logging.ecs import ecs_logconfig

logconfig_dict = ecs_logconfig()
```

`wsgi.py`:

```python
from oc_logging.ecs import log_requests
from oc_logging.tracing import setup_tracing, instrument_flask

setup_tracing()          # before the app is built, in every worker
app = create_app()
log_requests(app)        # one access line per request, with trace.id
instrument_flask(app)    # a span per request, continuing traceparent
```

Run gunicorn without `--access-logfile`: its access line is written after the request's span
ends, so it never has `trace.id`. `log_requests` replaces it. Probe paths
(`/health/liveness`, `/health/readiness`) get no access line and no span; pass `skip_paths`
or `excluded_paths` for others.

### Other processes

A worker, cron job or script that gunicorn does not start:

```python
from oc_logging.ecs import setup_ecs_logging

setup_ecs_logging()
```

### Settings

| Environment variable | Used for | Default |
| --- | --- | --- |
| `OTEL_SERVICE_NAME` | `service.name` in logs and spans | `unknown_service` |
| `PYTHON_ENV` | `service.environment`, lower case | left out |
| `LOG_LEVEL` | root log level | `INFO` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | export spans over OTLP; without it trace ids are still made and passed on | not exported |

Fields worth adding with `extra`: dotted ECS names are nested, e.g.
`logger.error("Foreman failed", extra={"error.type": "ProviderUnavailableError"})`.

### Example

```json
{"@timestamp":"2026-11-06T06:06:38.672Z","log.level":"info","message":"GET /hosts 200","ecs.version":"1.6.0","event":{"duration":41250000},"http":{"request":{"method":"GET"},"response":{"status_code":200}},"log":{"logger":"access"},"service":{"environment":"test","name":"idp-vm-foreman-service"},"span":{"id":"36999cb22b0310ad"},"trace":{"id":"bf4b57dee6ae2b235d7dc377122a43fa"},"url":{"path":"/hosts"}}
```
