"""Structured logging through the stable m-mdy-m/log.c C ABI."""
from __future__ import annotations

import atexit
import ctypes
import os
import sys
from pathlib import Path
from typing import TextIO


class _LoggerConfig(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32), ("min_level", ctypes.c_uint32),
        ("color_mode", ctypes.c_uint32), ("output", ctypes.c_uint32),
        ("format_flags", ctypes.c_uint32), ("max_message_bytes", ctypes.c_uint32),
    ]


class _LoggerEvent(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_uint32), ("level", ctypes.c_int32),
        ("timestamp_unix_ns", ctypes.c_uint64), ("duration_ns", ctypes.c_uint64),
        ("line", ctypes.c_uint32), ("reserved", ctypes.c_uint32),
        ("layer", ctypes.c_char_p), ("component", ctypes.c_char_p),
        ("file", ctypes.c_char_p), ("function", ctypes.c_char_p),
        ("request_id", ctypes.c_char_p), ("trace_id", ctypes.c_char_p),
        ("status", ctypes.c_char_p), ("message", ctypes.c_char_p),
        ("message_length", ctypes.c_size_t),
    ]


_LEVELS = {"TRACE": 0, "DEBUG": 1, "INFO": 2, "WARN": 3, "ERROR": 4, "FATAL": 5}


class PipelineLogger:
    """One API for native log.c records and deterministic local-test fallback."""

    def __init__(self, library_path: str | None = None, *, fallback_stream: TextIO | None = None,
                 use_environment: bool = True) -> None:
        selected = library_path
        if selected is None and use_environment:
            selected = os.environ.get("PIPELINE_LOG_LIBRARY", "")
        self._stream = fallback_stream or sys.stderr
        self._library = None
        self._handle = ctypes.c_void_p()
        self._min_level = _LEVELS.get(os.environ.get("PIPELINE_LOG_LEVEL", "INFO").upper(), 2)
        if not selected:
            return
        path = Path(selected)
        if not path.is_file():
            raise RuntimeError(f"PIPELINE_LOG_LIBRARY does not exist: {path}")
        self._library = ctypes.CDLL(str(path))
        self._configure_native_api()

    @property
    def using_native_logger(self) -> bool:
        return self._library is not None

    def _configure_native_api(self) -> None:
        lib = self._library
        assert lib is not None
        lib.mmlog_logger_config_init.argtypes = [ctypes.POINTER(_LoggerConfig)]
        lib.mmlog_logger_config_init.restype = ctypes.c_int32
        lib.mmlog_logger_create.argtypes = [ctypes.POINTER(_LoggerConfig), ctypes.POINTER(ctypes.c_void_p)]
        lib.mmlog_logger_create.restype = ctypes.c_int32
        lib.mmlog_logger_destroy.argtypes = [ctypes.c_void_p]
        lib.mmlog_logger_destroy.restype = None
        lib.mmlog_logger_set_min_level.argtypes = [ctypes.c_void_p, ctypes.c_int32]
        lib.mmlog_logger_set_min_level.restype = ctypes.c_int32
        lib.mmlog_logger_set_color_mode.argtypes = [ctypes.c_void_p, ctypes.c_int32]
        lib.mmlog_logger_set_color_mode.restype = ctypes.c_int32
        lib.mmlog_event_init.argtypes = [ctypes.POINTER(_LoggerEvent)]
        lib.mmlog_event_init.restype = ctypes.c_int32
        lib.mmlog_logger_write.argtypes = [ctypes.c_void_p, ctypes.POINTER(_LoggerEvent)]
        lib.mmlog_logger_write.restype = ctypes.c_int32

        config = _LoggerConfig()
        rc = lib.mmlog_logger_config_init(ctypes.byref(config))
        if rc != 0:
            raise RuntimeError(f"log.c config initialization failed with status {rc}")
        config.min_level = self._min_level
        config.color_mode = 2
        config.output = 0
        config.format_flags = (1 << 0) | (1 << 1) | (1 << 2) | (1 << 8)
        rc = lib.mmlog_logger_create(ctypes.byref(config), ctypes.byref(self._handle))
        if rc != 0 or not self._handle:
            raise RuntimeError(f"log.c logger creation failed with status {rc}")
        lib.mmlog_logger_set_min_level(self._handle, self._min_level)
        lib.mmlog_logger_set_color_mode(self._handle, 2)
        atexit.register(self.close)

    def close(self) -> None:
        if self._library is not None and self._handle:
            self._library.mmlog_logger_destroy(self._handle)
            self._handle = ctypes.c_void_p()

    def _write(self, level: str, message: object, *, component: str = "pipeline", status: str = "") -> None:
        numeric_level = _LEVELS[level]
        if numeric_level < self._min_level:
            return
        encoded = str(message).encode("utf-8", errors="replace")
        if self._library is None:
            self._stream.write(f"[{level}] [{component}] {encoded.decode('utf-8', 'replace')}\n")
            self._stream.flush()
            return
        lib = self._library
        event = _LoggerEvent()
        rc = lib.mmlog_event_init(ctypes.byref(event))
        if rc != 0:
            self._stream.write(f"[ERROR] [logger] log.c event initialization failed with status {rc}\n")
            self._stream.flush()
            return
        layer_bytes, component_bytes = b"pipeline", component.encode("utf-8", "replace")
        file_bytes, function_bytes = b"src/pipeline/common/logging.py", level.lower().encode("ascii")
        status_bytes = status.encode("utf-8", "replace") if status else None
        event.level = numeric_level
        event.layer, event.component = layer_bytes, component_bytes
        event.file, event.function, event.status = file_bytes, function_bytes, status_bytes
        event.message, event.message_length = encoded, len(encoded)
        rc = lib.mmlog_logger_write(self._handle, ctypes.byref(event))
        if rc != 0:
            self._stream.write(f"[ERROR] [logger] log.c write failed with status {rc}\n")
            self._stream.flush()

    def trace(self, message: object, *, component: str = "pipeline", status: str = "") -> None:
        self._write("TRACE", message, component=component, status=status)

    def debug(self, message: object, *, component: str = "pipeline", status: str = "") -> None:
        self._write("DEBUG", message, component=component, status=status)

    def info(self, message: object, *, component: str = "pipeline", status: str = "") -> None:
        self._write("INFO", message, component=component, status=status)

    def warning(self, message: object, *, component: str = "pipeline", status: str = "") -> None:
        self._write("WARN", message, component=component, status=status)

    warn = warning

    def error(self, message: object, *, component: str = "pipeline", status: str = "") -> None:
        self._write("ERROR", message, component=component, status=status)

    def fatal(self, message: object, *, component: str = "pipeline", status: str = "") -> None:
        self._write("FATAL", message, component=component, status=status)


logger = PipelineLogger()
