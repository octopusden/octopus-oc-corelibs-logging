import io
import json
import logging
import sys
import threading
import unittest
from contextlib import redirect_stderr

import structlog

from oc_logging import setup_json_logging, setup_text_logging


def _raise_zero_division():
    """Log an explicit exc_info=True record from an except block"""
    log = structlog.get_logger()

    try:
        1 / 0
    except ZeroDivisionError:
        log.error("failed", exc_info=True, key="value")


def _log_exception_object():
    """Log an exception object as the event, the way log.exception(err) is often used"""
    log = structlog.get_logger()

    try:
        raise ValueError("something went wrong")
    except ValueError as err:
        log.exception(err)


class LoggingTestCase(unittest.TestCase):
    """
    Base case restoring the global state touched by configure():
    excepthooks, root logger handlers and structlog configuration.
    """

    def setUp(self):
        self.sys_excepthook = sys.excepthook
        self.thread_excepthook = getattr(threading, "excepthook", None)
        self.root_handlers = logging.getLogger().handlers[:]

    def tearDown(self):
        sys.excepthook = self.sys_excepthook

        if self.thread_excepthook is not None:
            threading.excepthook = self.thread_excepthook

        root = logging.getLogger()

        for handler in root.handlers[:]:
            root.removeHandler(handler)

        for handler in self.root_handlers:
            root.addHandler(handler)

        structlog.reset_defaults()

    @staticmethod
    def capture(setup, action):
        """
        Run setup() and then action() with stderr redirected.
        The handler created by configure() binds to the redirected stream,
        so the returned string is everything the logger has written.
        """
        stream = io.StringIO()

        with redirect_stderr(stream):
            setup()
            action()

        return stream.getvalue()

    def capture_json(self, action, level="debug"):
        """Same as capture(), but for a single JSON record which is parsed back"""
        output = self.capture(lambda: setup_json_logging(level=level), action)

        # A record must never be split across lines, otherwise the log consumer cannot parse it
        self.assertEqual(1, len(output.strip().splitlines()))

        return json.loads(output)


class TestJsonFormat(LoggingTestCase):
    def test_exception_is_appended_to_message(self):
        record = self.capture_json(_raise_zero_division)

        self.assertEqual("error", record["level"])
        self.assertNotIn("exception", record)
        self.assertTrue(record["message"].startswith("failed\nTraceback (most recent call last):"))
        self.assertIn("ZeroDivisionError: division by zero", record["message"])

    def test_context_keys_stay_separate_fields(self):
        record = self.capture_json(_raise_zero_division)

        self.assertEqual("value", record["key"])

    def test_exception_object_as_event_is_serialised(self):
        # log.exception(err) passes the exception object as the event, which must
        # not break the "message" + traceback merge (regression: TypeError in join)
        record = self.capture_json(_log_exception_object)

        self.assertEqual("error", record["level"])
        self.assertTrue(record["message"].startswith("something went wrong\nTraceback"))
        self.assertIn("ValueError: something went wrong", record["message"])

    def test_record_without_exception_is_untouched(self):
        record = self.capture_json(lambda: structlog.get_logger().info("plain", key="value"))

        self.assertEqual("info", record["level"])
        self.assertEqual("plain", record["message"])
        self.assertNotIn("exception", record)


class TestTextFormat(LoggingTestCase):
    def test_message_is_rendered_as_text(self):
        output = self.capture(
            lambda: setup_text_logging(level="debug"),
            lambda: structlog.get_logger().info("hello", key="value")
        )

        # "message=hello" here would mean the renamed event key is not picked up
        self.assertRegex(output, r"^\[[^]]+\] \[INFO\] hello key=value\n$")

    def test_exception_is_rendered_on_its_own_line(self):
        output = self.capture(lambda: setup_text_logging(level="debug"), _raise_zero_division)
        lines = output.splitlines()

        self.assertTrue(lines[0].endswith("[ERROR] failed key=value"))
        self.assertEqual("Traceback (most recent call last):", lines[1])
        self.assertEqual("ZeroDivisionError: division by zero", lines[-1])


class TestUncaughtExceptions(LoggingTestCase):
    @staticmethod
    def raise_through_excepthook(exception):
        """Feed an exception to the installed sys.excepthook the way the interpreter does"""
        try:
            raise exception
        except BaseException:
            sys.excepthook(*sys.exc_info())

    @staticmethod
    def raise_in_thread(exception, name="worker-1"):
        def target():
            raise exception

        thread = threading.Thread(target=target, name=name)
        thread.start()
        thread.join()

    def test_uncaught_exception_is_logged_as_critical(self):
        record = self.capture_json(lambda: self.raise_through_excepthook(RuntimeError("boom")))

        self.assertEqual("critical", record["level"])
        self.assertTrue(record["message"].startswith("uncaught exception\nTraceback (most recent call last):"))
        self.assertIn("RuntimeError: boom", record["message"])

    def test_keyboard_interrupt_is_not_logged(self):
        seen = []
        default_excepthook = sys.__excepthook__
        sys.__excepthook__ = lambda *exc_info: seen.append(exc_info)

        try:
            output = self.capture(
                lambda: setup_json_logging(level="debug"),
                lambda: self.raise_through_excepthook(KeyboardInterrupt())
            )
        finally:
            sys.__excepthook__ = default_excepthook

        self.assertEqual("", output)
        self.assertEqual(1, len(seen))

    def test_thread_exception_is_logged_with_thread_name(self):
        record = self.capture_json(lambda: self.raise_in_thread(ValueError("thread boom")))

        self.assertEqual("critical", record["level"])
        self.assertEqual("worker-1", record["thread"])
        self.assertTrue(record["message"].startswith("uncaught exception in thread\n"))
        self.assertIn("ValueError: thread boom", record["message"])

    def test_system_exit_in_thread_is_not_logged(self):
        output = self.capture(
            lambda: setup_json_logging(level="debug"),
            lambda: self.raise_in_thread(SystemExit(0))
        )

        self.assertEqual("", output)

    def test_repeated_configure_does_not_duplicate_records(self):
        def setup_twice():
            setup_json_logging(level="debug")
            setup_json_logging(level="debug")

        output = self.capture(
            setup_twice,
            lambda: self.raise_through_excepthook(RuntimeError("boom"))
        )

        self.assertEqual(1, len(output.strip().splitlines()))


if __name__ == "__main__":
    unittest.main()
