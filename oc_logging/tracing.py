"""
OpenTelemetry tracing whose ids land in the log lines of oc_logging.ecs.

A W3C traceparent header coming in is continued, every call made with requests sends one, and
a line logged inside a request carries the ECS fields trace.id and span.id, so one search on
trace.id finds a request in every service it went through.
Needs the "tracing" extra: pip install oc-logging[tracing]
"""
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from oc_logging.ecs import PROBE_PATHS


def add_trace_fields(span, record):
    """
    Adds trace.id and span.id to a record logged inside a span; records outside one have neither.
    The dotted names make ecs_logging nest them as ECS fields. LoggingInstrumentor's own
    otelTraceID would come out as a top-level non-ECS field.
    """
    ctx = span.get_span_context()
    setattr(record, "trace.id", format(ctx.trace_id, "032x"))
    setattr(record, "span.id", format(ctx.span_id, "016x"))


def setup_tracing():
    """
    Sets up the tracer, trace ids on log records and traceparent on outgoing requests calls.

    Call it once per process before the app is built. Under gunicorn without --preload that is
    wsgi.py, which each worker imports after the fork; a tracer made in the master before the
    fork would not export from the workers.

    Spans are exported over OTLP only when OTEL_EXPORTER_OTLP_ENDPOINT is set, otherwise the
    exporter would log a connection error to localhost:4318 for every batch. Trace ids are made
    and passed on either way. The spans' service.name is OTEL_SERVICE_NAME, the same as the logs'.
    """
    provider = TracerProvider()
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    # Without enable_log_auto_instrumentation=False a handler would also ship logs to an OTel
    # collector; they stay on stdout only
    LoggingInstrumentor().instrument(log_hook=add_trace_fields, enable_log_auto_instrumentation=False)
    RequestsInstrumentor().instrument()


def instrument_flask(app, excluded_paths=PROBE_PATHS):
    """
    Gives every Flask request a span that continues an incoming traceparent.
    Requests to excluded_paths make no span, so the probes add none every few seconds.
    """
    FlaskInstrumentor().instrument_app(app, excluded_urls=",".join(path.lstrip("/") for path in excluded_paths))
