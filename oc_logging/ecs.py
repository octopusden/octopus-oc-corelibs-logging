"""
ECS JSON logging on the standard logging library.

Every record, from the app, its libraries and gunicorn, is one Elastic Common Schema (ECS)
JSON object per line on stdout, ready for Elasticsearch/Kibana without a parsing pipeline.
Needs the "ecs" extra: pip install oc-logging[ecs]

Example of the output:
{"@timestamp":"2026-11-06T06:06:38.656Z","log.level":"info","message":"GET /hosts 200",
 "ecs.version":"1.6.0","http":{"request":{"method":"GET"},"response":{"status_code":200}},
 "service":{"environment":"test","name":"idp-vm-foreman-service"},"url":{"path":"/hosts"}, ...}
"""
import logging
import logging.config
import os
import time

# Kubernetes probes call these on every pod every few seconds, so they get no access line
PROBE_PATHS = ("/health/liveness", "/health/readiness")

access_logger = logging.getLogger("access")


def ecs_logconfig(service_name=None, level=None):
    """
    dictConfig dict that writes every record as ECS JSON to stdout.

    With gunicorn, use it in gunicorn.conf.py, so the master, the workers and the app share it:

        from oc_logging.ecs import ecs_logconfig
        logconfig_dict = ecs_logconfig()

    service.name is service_name, else OTEL_SERVICE_NAME, the name traces get too.
    service.environment is PYTHON_ENV in lower case, left out when it is not set.
    The root level is level, else LOG_LEVEL, else INFO.

    gunicorn's own access line is dropped: gunicorn writes it after the request's span ends,
    so it never has trace.id. Use log_requests() instead.
    """
    extra = {"service.name": service_name or os.getenv("OTEL_SERVICE_NAME", "unknown_service")}
    environment = os.getenv("PYTHON_ENV")
    if environment:
        extra["service.environment"] = environment.lower()

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "ecs": {
                "()": "ecs_logging.StdlibFormatter",
                # log.original repeats the message
                "exclude_fields": ["log.original"],
                "extra": extra,
            },
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "ecs", "stream": "ext://sys.stdout"},
        },
        "root": {"level": (level or os.getenv("LOG_LEVEL", "INFO")).upper(), "handlers": ["console"]},
        "loggers": {
            "gunicorn.error": {"level": "INFO", "handlers": [], "propagate": True},
            "gunicorn.access": {"level": "WARNING", "handlers": [], "propagate": False},
        },
    }


def setup_ecs_logging(service_name=None, level=None):
    """
    Same logging for a process gunicorn does not start: a worker, a cron job, a script.
    Replaces the root handlers, so it may be called more than once.
    """
    logging.config.dictConfig(ecs_logconfig(service_name, level))


def log_requests(app, skip_paths=PROBE_PATHS):
    """
    Logs one access line per Flask request on the "access" logger, with the ECS fields
    http.request.method, url.path, http.response.status_code and event.duration (nanoseconds).

    The line is written from after_request, which runs inside the request's span, so with
    oc_logging.tracing it carries trace.id. Requests to skip_paths are not logged.
    """
    from flask import g, request

    def start_timer():
        g.oc_logging_started_ns = time.perf_counter_ns()

    def log_request(response):
        if request.path not in skip_paths:
            started_ns = g.get("oc_logging_started_ns")
            access_logger.info(f"{request.method} {request.path} {response.status_code}", extra={
                "http.request.method": request.method,
                "url.path": request.path,
                "http.response.status_code": response.status_code,
                "event.duration": time.perf_counter_ns() - started_ns if started_ns else None,
            })
        return response

    app.before_request(start_timer)
    app.after_request(log_request)
