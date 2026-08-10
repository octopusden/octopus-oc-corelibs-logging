"""
Structlog Configuration Wrapper Library

A flexible wrapper for configuring structlog with different output formats
and common configurations.
"""
import logging
import sys
import threading
import structlog
from typing import Optional, List
from enum import Enum

class LogFormat(Enum):
    JSON = "json"
    TEXT = "text"

class LogLevel(Enum):
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

def rename_event_to_message_processor(_, __, event_dict):
    """
    Processor that renames the 'event' key to 'message',
    mimicking structlog.processors.EventRenamer("message").
    """
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict

def merge_exception_into_message_processor(_, __, event_dict):
    """
    Processor that appends the formatted traceback to the 'message' key
    Log consumers that read only 'message' still get the whole traceback.
    """
    exception = event_dict.pop("exception", None)

    if not exception:
        return event_dict

    message = event_dict.get("message", "")
    # The event passed to the logger may be a non-str (e.g. log.exception(err)
    # with an exception object), so coerce before joining with the traceback.
    if not isinstance(message, str):
        message = str(message)
    event_dict["message"] = "\n".join([message, exception]) if message else exception

    return event_dict

class StructlogWrapper:
    """
    A wrapper class for configuring structlog with different formats and options.

    Usage:
        # JSON format
        logger_config = StructlogWrapper(format=LogFormat.JSON)
        logger_config.configure()

        # Text format with custom timestamp
        logger_config = StructlogWrapper(
            format=LogFormat.TEXT,
            timestamp_format="%Y-%m-%d %H:%M:%S %z",
            log_level=LogLevel.DEBUG
        )
        logger_config.configure()

        # Get logger anywhere in your app
        log = structlog.get_logger()
        log.info("Hello world", key="value")
    """

    def __init__(
            self,
            format: LogFormat = LogFormat.JSON,
            log_level: LogLevel = LogLevel.INFO,
            timestamp_format: str = "%Y-%m-%d %H:%M:%S",
            utc: bool = True,
            custom_processors: Optional[List] = None,
            context_class=dict,
            **kwargs
    ):
        """
        Initialize the structlog wrapper.

        Args:
            format: Output format (JSON, TEXT, or CONSOLE)
            log_level: Minimum log level to output
            timestamp_format: strftime format for timestamps
            utc: Use UTC timestamps
            include_stack_info: Include stack information in logs
            include_exc_info: Include exception information in logs
            custom_processors: Additional custom processors to include
            context_class: Context class for structlog
            **kwargs: Additional keyword arguments
        """
        self.format = format
        self.log_level = log_level
        self.timestamp_format = timestamp_format
        self.utc = utc
        self.custom_processors = custom_processors or []
        self.context_class = context_class
        self.kwargs = kwargs

    def _get_base_processors(self) -> List:
        """Get the base processors common to all formats"""
        processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            rename_event_to_message_processor,
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(
                fmt=self.timestamp_format,
                utc=self.utc
            )
        ]

        # Add any custom processors
        processors.extend(self.custom_processors)

        return processors

    def _get_json_processors(self) -> List:
        """Get processors for JSON output format"""
        processors = self._get_base_processors()

        # Text format renders the traceback on its own line by itself,
        # for JSON it has to be merged into "message" explicitly
        processors.append(merge_exception_into_message_processor)
        processors.append(structlog.processors.JSONRenderer())
        return processors

    def _get_text_processors(self) -> List:
        """Get processors for plain text output format"""
        processors = self._get_base_processors()

        # Custom text renderer that formats like your example
        def text_renderer(logger, method_name, event_dict):
            timestamp = event_dict.pop("timestamp", "")
            level = event_dict.pop("level", "").upper()
            # "event" has already been renamed to "message" by rename_event_to_message_processor
            event = event_dict.pop("message", "")
            # The event may be a non-str (e.g. log.exception(err) with an exception object)
            if not isinstance(event, str):
                event = str(event)
            # Traceback is multiline, so it is printed after the key=value tail
            exception = event_dict.pop("exception", None)

            # Format: [timestamp] [level] message key=value key2=value2
            parts = [f"[{timestamp}]", f"[{level}]", event]

            # Add context variables, all the well-known keys are already popped
            for key, value in event_dict.items():
                parts.append(f"{key}={value}")

            line = " ".join(parts)

            if exception:
                line = f"{line}\n{exception}"

            return line

        processors.append(text_renderer)
        return processors

    def _get_processors(self) -> List:
        """Get appropriate processors based on format"""
        if self.format == LogFormat.JSON:
            return self._get_json_processors()
        elif self.format == LogFormat.TEXT:
            return self._get_text_processors()
        else:
            raise ValueError(f"Unsupported format: {self.format}")

    def _get_logger_factory(self):
        """Get appropriate logger factory based on format"""
        return structlog.stdlib.LoggerFactory()

    def _get_wrapper_class(self):
        """Get appropriate wrapper class"""
        return structlog.make_filtering_bound_logger(self.log_level.value)

    def _install_excepthooks(self):
        """Route uncaught exceptions through structlog instead of raw stderr."""
        log = structlog.get_logger("uncaught")

        def _excepthook(exc_type, exc_value, exc_tb):
            # Ctrl-C is not a crash: keep the default terse behaviour
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_tb)
                return

            try:
                log.critical(
                    "uncaught exception",
                    exc_info=(exc_type, exc_value, exc_tb)
                )
            except Exception:
                # A crash must never be lost because logging itself failed
                sys.__excepthook__(exc_type, exc_value, exc_tb)

        # Assign, never wrap: configure() may be called more than once
        sys.excepthook = _excepthook

        def _thread_excepthook(args):
            # SystemExit in a thread is a normal termination
            if issubclass(args.exc_type, SystemExit):
                return

            try:
                log.critical(
                    "uncaught exception in thread",
                    thread=args.thread.name if args.thread else None,
                    exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
                )
            except Exception:
                # threading.__excepthook__ is python3.10+, so fall back to the sys one
                sys.__excepthook__(args.exc_type, args.exc_value, args.exc_traceback)

        # threading.excepthook exists since python3.8, which is the declared minimum
        threading.excepthook = _thread_excepthook

    def configure(self):
        """Configure structlog with the specified settings"""
        # Since force=true only available for python3.8+, here is workaround to remove all handler first for fresh log settings
        root = logging.getLogger()
        if root.handlers:
            for handler in root.handlers[:]:
                root.removeHandler(handler)

        # Configure standard library logging since structlog is a logging wrapper
        logging.basicConfig(
            level=self.log_level.value,
            format="%(message)s",  # structlog handles formatting
            handlers=[logging.StreamHandler()]
        )

        # Configure structlog
        structlog.configure(
            processors=self._get_processors(),
            wrapper_class=self._get_wrapper_class(),
            context_class=self.context_class,
            logger_factory=self._get_logger_factory()
        )

        # Hooks log through structlog, so they are installed once the configuration is in place
        self._install_excepthooks()

    @classmethod
    def quick_setup(
            cls,
            format = "json",
            level = "info",
            **kwargs
    ):
        """
        Quick setup method with string parameters for convenience.

        Args:
            format: "json", "text", or "console"
            level: "debug", "info", "warning", "error", "critical" or integer (10=debug, 20=info, 30=warning, 40=error, 50=critical)
            **kwargs: Additional configuration options

        Returns:
            Configured StructlogWrapper instance
        """
        # Convert string format to enum
        format_map = {
            "json": LogFormat.JSON,
            "text": LogFormat.TEXT
        }

        # Convert string level to enum
        level_map = {
            "debug": LogLevel.DEBUG,
            "info": LogLevel.INFO,
            "warning": LogLevel.WARNING,
            "error": LogLevel.ERROR,
            "critical": LogLevel.CRITICAL
        }

        # Convert integer level to enum
        int_level_map = {
            10: LogLevel.DEBUG,
            20: LogLevel.INFO,
            30: LogLevel.WARNING,
            40: LogLevel.ERROR,
            50: LogLevel.CRITICAL
        }

        format_enum = format_map.get(format.lower())
        if not format_enum:
            raise ValueError(f"Invalid format: {format}. Use: {list(format_map.keys())}")

        # Handle both string and integer levels
        if isinstance(level, int):
            level_enum = int_level_map.get(level)
            if level_enum is None:
                raise ValueError(f"Invalid level: {level}. Use: {list(int_level_map.keys())}")
        else:
            level_enum = level_map.get(level.lower())
            if not level_enum:
                raise ValueError(
                    f"Invalid level: {level}. Use: {list(level_map.keys())} or integers {list(int_level_map.keys())}")

        wrapper = cls(format=format_enum, log_level=level_enum, **kwargs)
        wrapper.configure()
        return wrapper