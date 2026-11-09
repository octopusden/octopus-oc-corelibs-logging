import io
import json
import logging
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock

try:
    import ecs_logging  # noqa: F401
except ImportError:
    ecs_logging = None

try:
    import flask
except ImportError:
    flask = None

from oc_logging.ecs import setup_ecs_logging, log_requests


class EcsTestCase(unittest.TestCase):
    """
    Base case restoring the root logger, which setup_ecs_logging() reconfigures
    """

    def setUp(self):
        root = logging.getLogger()
        self.root_handlers = root.handlers[:]
        self.root_level = root.level

    def tearDown(self):
        root = logging.getLogger()

        for handler in root.handlers[:]:
            root.removeHandler(handler)

        for handler in self.root_handlers:
            root.addHandler(handler)

        root.setLevel(self.root_level)

    @staticmethod
    def capture(action, **kwargs):
        """
        Run setup_ecs_logging() and then action() with stdout redirected, and parse every line back.
        The handler binds to sys.stdout when it is configured, so setup runs inside the redirect.
        """
        stream = io.StringIO()

        with redirect_stdout(stream):
            setup_ecs_logging(**kwargs)
            action()

        return [json.loads(line) for line in stream.getvalue().splitlines()]


@unittest.skipIf(ecs_logging is None, "needs the ecs extra: pip install oc-logging[ecs]")
class TestEcsLogging(EcsTestCase):
    def test_record_is_one_ecs_json_line(self):
        with mock.patch.dict(os.environ, {"PYTHON_ENV": "TEST"}):
            records = self.capture(lambda: logging.getLogger("app").info("hello"), service_name="svc")

        self.assertEqual(1, len(records))
        self.assertEqual("hello", records[0]["message"])
        self.assertEqual("info", records[0]["log.level"])
        self.assertEqual("app", records[0]["log"]["logger"])
        self.assertEqual({"name": "svc", "environment": "test"}, records[0]["service"])
        self.assertNotIn("original", records[0]["log"])

    def test_service_name_comes_from_otel_service_name(self):
        with mock.patch.dict(os.environ, {"OTEL_SERVICE_NAME": "from-env"}):
            records = self.capture(lambda: logging.getLogger("app").info("hello"))

        self.assertEqual("from-env", records[0]["service"]["name"])

    def test_environment_is_left_out_without_python_env(self):
        with mock.patch.dict(os.environ, clear=True):
            records = self.capture(lambda: logging.getLogger("app").info("hello"), service_name="svc")

        self.assertEqual({"name": "svc"}, records[0]["service"])

    def test_level_comes_from_log_level(self):
        def log_both():
            logging.getLogger("app").info("dropped")
            logging.getLogger("app").warning("kept")

        with mock.patch.dict(os.environ, {"LOG_LEVEL": "warning"}):
            records = self.capture(log_both)

        self.assertEqual(["kept"], [record["message"] for record in records])

    def test_dotted_extra_fields_are_nested(self):
        records = self.capture(lambda: logging.getLogger("app").info("failed", extra={"error.type": "NotFoundError"}))

        self.assertEqual("NotFoundError", records[0]["error"]["type"])

    def test_exception_is_in_the_same_line(self):
        def log_exception():
            try:
                1 / 0
            except ZeroDivisionError:
                logging.getLogger("app").exception("failed")

        records = self.capture(log_exception)

        self.assertEqual(1, len(records))
        self.assertEqual("ZeroDivisionError", records[0]["error"]["type"])
        self.assertEqual("division by zero", records[0]["error"]["message"])
        self.assertIn("in log_exception", records[0]["error"]["stack_trace"])

    def test_gunicorn_access_line_is_dropped(self):
        records = self.capture(lambda: logging.getLogger("gunicorn.access").info("GET / 200"))

        self.assertEqual([], records)

    def test_repeated_setup_does_not_duplicate_records(self):
        def setup_again_and_log():
            setup_ecs_logging()
            logging.getLogger("app").info("hello")

        records = self.capture(setup_again_and_log)

        self.assertEqual(1, len(records))


@unittest.skipIf(ecs_logging is None or flask is None, "needs the ecs extra and flask")
class TestLogRequests(EcsTestCase):
    @staticmethod
    def app():
        app = flask.Flask(__name__)
        app.add_url_rule("/hosts", "hosts", lambda: "[]")
        app.add_url_rule("/health/liveness", "liveness", lambda: "UP")
        log_requests(app)
        return app

    def test_request_is_logged_with_ecs_http_fields(self):
        records = self.capture(lambda: self.app().test_client().get("/hosts"))

        self.assertEqual(1, len(records))
        self.assertEqual("GET /hosts 200", records[0]["message"])
        self.assertEqual("access", records[0]["log"]["logger"])
        self.assertEqual("GET", records[0]["http"]["request"]["method"])
        self.assertEqual(200, records[0]["http"]["response"]["status_code"])
        self.assertEqual("/hosts", records[0]["url"]["path"])
        self.assertGreater(records[0]["event"]["duration"], 0)

    def test_probes_are_not_logged(self):
        records = self.capture(lambda: self.app().test_client().get("/health/liveness"))

        self.assertEqual([], records)


if __name__ == "__main__":
    unittest.main()
