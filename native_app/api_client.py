from __future__ import annotations

import contextlib
import json
import threading
from typing import Any

import requests
from PyQt6.QtCore import QThread, pyqtSignal

try:
    import httpx
except ImportError:
    httpx = None

_SSE_DATA_PREFIX = "data:"
_SSE_DONE = "[DONE]"
_CONNECT_TIMEOUT = 10
_READ_TIMEOUT = 120


class ChatWorker(QThread):
    delta_received = pyqtSignal(str)
    error_received = pyqtSignal(str, int, str)
    summary_received = pyqtSignal(str)
    cancelled = pyqtSignal()
    finished_cleanly = pyqtSignal()

    def __init__(
        self,
        url: str,
        payload: dict[str, Any],
        api_key: str,
        *,
        stream: bool,
        summary_mode: bool = False,
        timeout_seconds: int = 30,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._url = url
        self._payload = payload
        self._api_key = api_key
        self._stream = stream
        self._summary_mode = summary_mode
        self._timeout_seconds = timeout_seconds
        self._cancel_event = threading.Event()
        self._response = None
        self._client = None

    def cancel(self) -> None:
        self._cancel_event.set()
        if self._response is not None:
            with contextlib.suppress(Exception):
                self._response.close()
        if self._client is not None:
            with contextlib.suppress(Exception):
                self._client.close()

    def run(self) -> None:
        try:
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            if httpx is not None:
                self._run_with_httpx(headers)
                return
            self._run_with_requests(headers)
        except Exception as exc:
            self.error_received.emit(str(exc), 0, self._exception_detail(exc))

    # -- payload helpers --

    @staticmethod
    def _extract_delta_content(payload: dict) -> str | None:
        choices = payload.get("choices") or []
        if not choices:
            return None
        return choices[0].get("delta", {}).get("content")

    @staticmethod
    def _extract_message_content(payload: dict) -> str:
        choices = payload.get("choices") or []
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "")

    # -- httpx backend --

    def _run_with_httpx(self, headers: dict[str, str]) -> None:
        timeout = httpx.Timeout(float(_READ_TIMEOUT), connect=float(_CONNECT_TIMEOUT))
        try:
            with httpx.Client(timeout=timeout) as client:
                self._client = client
                if self._stream and not self._summary_mode:
                    self._run_stream_httpx(client, headers)
                else:
                    self._run_non_stream_httpx(client, headers)
        except httpx.TimeoutException as exc:
            self.error_received.emit("Request timed out", 0, self._exception_detail(exc))
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            try:
                detail = exc.response.text if exc.response is not None else str(exc)
            except Exception:
                detail = str(exc)
            self._emit_http_error(status_code, detail)
        except json.JSONDecodeError as exc:
            self.error_received.emit("Invalid response from server", 0, self._exception_detail(exc))
        except httpx.RequestError as exc:
            if self._cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.error_received.emit(str(exc), 0, self._exception_detail(exc))
        except Exception as exc:
            if self._cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.error_received.emit(str(exc), 0, self._exception_detail(exc))
        finally:
            self._response = None
            self._client = None

    def _run_stream_httpx(self, client: httpx.Client, headers: dict[str, str]) -> None:
        with client.stream("POST", self._url, headers=headers, json=self._payload) as response:
            self._response = response
            response.raise_for_status()
            for raw_line in response.iter_lines():
                if self._cancel_event.is_set():
                    with contextlib.suppress(Exception):
                        response.read()
                    self.cancelled.emit()
                    return
                if not raw_line or not raw_line.startswith(_SSE_DATA_PREFIX):
                    continue
                data = raw_line[len(_SSE_DATA_PREFIX):].strip()
                if data == _SSE_DONE:
                    self.finished_cleanly.emit()
                    return
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = self._extract_delta_content(payload)
                if delta:
                    self.delta_received.emit(delta)
        self.finished_cleanly.emit()

    def _run_non_stream_httpx(self, client: httpx.Client, headers: dict[str, str]) -> None:
        response = client.post(self._url, headers=headers, json=self._payload)
        self._response = response
        response.raise_for_status()
        if self._cancel_event.is_set():
            self.cancelled.emit()
            return
        content = self._extract_message_content(response.json())
        if self._summary_mode:
            self.summary_received.emit(content)
        else:
            self.delta_received.emit(content)
        self.finished_cleanly.emit()

    # -- requests backend --

    def _run_with_requests(self, headers: dict[str, str]) -> None:
        try:
            if self._stream and not self._summary_mode:
                self._run_stream_requests(headers)
            else:
                self._run_non_stream_requests(headers)
        except requests.Timeout as exc:
            self.error_received.emit("Request timed out", 0, self._exception_detail(exc))
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            detail = exc.response.text.strip() if exc.response is not None else str(exc)
            self._emit_http_error(status_code, detail)
        except json.JSONDecodeError as exc:
            self.error_received.emit("Invalid response from server", 0, self._exception_detail(exc))
        except requests.RequestException as exc:
            if self._cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.error_received.emit(str(exc), 0, self._exception_detail(exc))
        finally:
            self._response = None

    def _run_stream_requests(self, headers: dict[str, str]) -> None:
        self._response = requests.post(
            self._url,
            headers=headers,
            json=self._payload,
            timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
            stream=True,
        )
        self._response.raise_for_status()
        for raw_line in self._response.iter_lines(decode_unicode=True):
            if self._cancel_event.is_set():
                self.cancelled.emit()
                return
            if not raw_line or not raw_line.startswith(_SSE_DATA_PREFIX):
                continue
            data = raw_line[len(_SSE_DATA_PREFIX):].strip()
            if data == _SSE_DONE:
                self.finished_cleanly.emit()
                return
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = self._extract_delta_content(payload)
            if delta:
                self.delta_received.emit(delta)
        self.finished_cleanly.emit()

    def _run_non_stream_requests(self, headers: dict[str, str]) -> None:
        self._response = requests.post(
            self._url,
            headers=headers,
            json=self._payload,
            timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
            stream=False,
        )
        self._response.raise_for_status()
        if self._cancel_event.is_set():
            self.cancelled.emit()
            return
        content = self._extract_message_content(self._response.json())
        if self._summary_mode:
            self.summary_received.emit(content)
        else:
            self.delta_received.emit(content)
        self.finished_cleanly.emit()

    def _exception_detail(self, exc: Exception) -> str:
        return f"{type(exc).__name__}: {exc}"

    def _emit_http_error(self, status_code: int, detail: str) -> None:
        clean_detail = (detail or "").strip()
        if status_code in (401, 403):
            message = "Authentication failed - check API Key"
        elif status_code == 429:
            message = "Rate limited - try again later"
        elif status_code:
            message = f"HTTP {status_code}"
        else:
            lines = clean_detail.splitlines() if clean_detail else []
            message = lines[0][:220] if lines else "Request failed"
        self.error_received.emit(message, status_code, clean_detail or message)
