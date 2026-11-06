import io
import json
import logging
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer

try:
    import flask
    import requests
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from oc_logging.tracing import setup_tracing, instrument_flask
except ImportError:
    flask = None

from oc_logging.ecs import setup_ecs_logging, log_requests

TRACE_ID = "a7d94148d090851c53ab489fba3dc45b"
TRACEPARENT = f"00-{TRACE_ID}-4aa52ad114bd70fd-01"


class HeaderRecorder(BaseHTTPRequestHandler):
    """
    Downstream service that remembers the traceparent of each call
    """
    traceparents = []

    def do_GET(self):
        HeaderRecorder.traceparents.append(self.headers.get("traceparent"))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


@unittest.skipIf(flask is None, "needs the tracing extra and flask: pip install oc-logging[tracing] flask")
class TestTracing(unittest.TestCase):
    """
    The tracer provider can be set once per process, so setup_tracing() runs once for the class
    """

    @classmethod
    def setUpClass(cls):
        setup_tracing()

        cls.downstream = HTTPServer(("127.0.0.1", 0), HeaderRecorder)
        threading.Thread(target=cls.downstream.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.downstream.shutdown()
        cls.downstream.server_close()
        LoggingInstrumentor().uninstrument()
        RequestsInstrumentor().uninstrument()

    def setUp(self):
        root = logging.getLogger()
        self.root_handlers = root.handlers[:]
        HeaderRecorder.traceparents.clear()

    def tearDown(self):
        root = logging.getLogger()

        for handler in root.handlers[:]:
            root.removeHandler(handler)

        for handler in self.root_handlers:
            root.addHandler(handler)

    def app(self):
        downstream_url = f"http://127.0.0.1:{self.downstream.server_port}/"
        app = flask.Flask(__name__)

        def hop():
            logging.getLogger("app").info("calling downstream")
            requests.get(downstream_url, timeout=5)
            return "ok"

        def liveness():
            logging.getLogger("app").info("probe")
            return "UP"

        app.route("/hop")(hop)
        app.route("/health/liveness")(liveness)
        log_requests(app)
        instrument_flask(app)
        return app

    def capture(self, action):
        stream = io.StringIO()

        with redirect_stdout(stream):
            setup_ecs_logging(service_name="svc")
            action()

        return [json.loads(line) for line in stream.getvalue().splitlines()]

    def test_incoming_traceparent_is_continued_in_every_line(self):
        records = self.capture(lambda: self.app().test_client().get("/hop", headers={"traceparent": TRACEPARENT}))

        self.assertEqual(["calling downstream", "GET /hop 200"], [record["message"] for record in records])
        for record in records:
            self.assertEqual(TRACE_ID, record["trace"]["id"])
            self.assertEqual(16, len(record["span"]["id"]))

    def test_outgoing_call_sends_the_same_trace(self):
        self.capture(lambda: self.app().test_client().get("/hop", headers={"traceparent": TRACEPARENT}))

        self.assertEqual(1, len(HeaderRecorder.traceparents))
        version, trace_id, parent_span_id, flags = HeaderRecorder.traceparents[0].split("-")
        self.assertEqual(TRACE_ID, trace_id)
        # the downstream's parent is this service's own span, not the caller's
        self.assertNotEqual("4aa52ad114bd70fd", parent_span_id)

    def test_request_without_traceparent_starts_a_trace(self):
        records = self.capture(lambda: self.app().test_client().get("/hop"))

        self.assertEqual(32, len(records[0]["trace"]["id"]))
        self.assertEqual(records[0]["trace"]["id"], HeaderRecorder.traceparents[0].split("-")[1])

    def test_probe_makes_no_span(self):
        records = self.capture(lambda: self.app().test_client().get("/health/liveness"))

        self.assertEqual(["probe"], [record["message"] for record in records])
        self.assertNotIn("trace", records[0])

    def test_line_outside_a_request_has_no_trace_fields(self):
        records = self.capture(lambda: logging.getLogger("app").info("startup"))

        self.assertNotIn("trace", records[0])
        self.assertNotIn("span", records[0])
        self.assertNotIn("otelTraceID", records[0])


if __name__ == "__main__":
    unittest.main()
