#!/usr/bin/env python3
"""Small Python client library for clipboardd.

Usage:
    from libclipboadd import ClipboardClient

    client = ClipboardClient()
    latest = client.get_latest()
    print(latest)

The filename intentionally follows the requested spelling: libclipboadd.py.
"""

from __future__ import annotations

import base64
import getpass
import os
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional



from oscore.libipc import add_listener, remove_listener, send  # noqa: E402


DEFAULT_TIMEOUT = 5.0
DEFAULT_SUBSCRIBER_TIMEOUT = 1.0
DEFAULT_MAX_IMAGE_BYTES = 32 * 1024 * 1024


class ClipboardClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class ClipboardValue:
    has_value: bool
    kind: str
    mime_type: str
    timestamp_usec: int
    size_bytes: int
    text: Optional[str] = None
    data_b64: Optional[str] = None

    @classmethod
    def from_reply(cls, data: dict[str, Any]) -> "ClipboardValue":
        return cls(
            has_value=bool(data.get("has_value")),
            kind=str(data.get("kind") or ""),
            mime_type=str(data.get("mime_type") or ""),
            timestamp_usec=int(data.get("timestamp_usec") or 0),
            size_bytes=int(data.get("size_bytes") or 0),
            text=data.get("text") if isinstance(data.get("text"), str) else None,
            data_b64=data.get("data_b64") if isinstance(data.get("data_b64"), str) else None,
        )

    def image_bytes(self, max_bytes: int = DEFAULT_MAX_IMAGE_BYTES) -> bytes:
        if self.kind != "image" or not self.data_b64:
            raise ClipboardClientError("clipboard value is not an image")

        decoded = base64.b64decode(self.data_b64, validate=True)
        if len(decoded) > max_bytes:
            raise ClipboardClientError("image payload exceeds max_bytes")
        return decoded


class ClipboardSubscription:
    def __init__(self, client: "ClipboardClient", ipc_id: str, subscription_id: str):
        self._client = client
        self._ipc_id = ipc_id
        self.subscription_id = subscription_id
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return

        try:
            self._client.unsubscribe(self.subscription_id)
        finally:
            remove_listener(self._ipc_id)
            self._closed = True

    def wait_forever(self) -> None:
        threading.Event().wait()

    def __enter__(self) -> "ClipboardSubscription":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()


class ClipboardClient:
    def __init__(
        self,
        process_name: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.process_name = process_name or f"clipboardd-{getpass.getuser()}"
        self.timeout = timeout

    def ping(self) -> dict[str, Any]:
        return self._send("ping", {}, dict)

    def get_latest(self) -> ClipboardValue:
        return ClipboardValue.from_reply(self._send("get", {}, dict))

    def get_latest_raw(self) -> dict[str, Any]:
        return self._send("get", {}, dict)

    def history(self, limit: int = 20) -> list[ClipboardValue]:
        reply = self._send("history", {"limit": limit}, dict)
        items = reply.get("items") if isinstance(reply, dict) else None
        if not isinstance(items, list):
            return []
        return [ClipboardValue.from_reply(item) for item in items if isinstance(item, dict)]

    def push_text(self, text: str) -> dict[str, Any]:
        payload = text.encode("utf-8")
        return self._send(
            "push_text",
            {
                "kind": "text",
                "mime_type": "text/plain",
                "text": text,
                "size_bytes": len(payload),
            },
            dict,
        )

    def push_image(self, data: bytes, mime_type: str = "image/png") -> dict[str, Any]:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data must be bytes-like")

        raw = bytes(data)
        return self._send(
            "push_text",
            {
                "kind": "image",
                "mime_type": mime_type,
                "data_b64": base64.b64encode(raw).decode("ascii"),
                "size_bytes": len(raw),
            },
            dict,
        )

    def subscribe(
        self,
        callback: Callable[[ClipboardValue, dict[str, Any]], Any],
        *,
        name: str = "clipboard client",
        listener_process_name: str = "clipcli",
        ipc_id: Optional[str] = None,
    ) -> ClipboardSubscription:
        listener_ipc_id = ipc_id or f"c{os.getpid()}{uuid.uuid4().hex[:8]}"

        def _listener(_from_info: Optional[dict], data: dict[str, Any]) -> Any:
            value = ClipboardValue.from_reply({
                "has_value": True,
                **data,
            })
            return callback(value, data)

        add_listener(listener_process_name, listener_ipc_id, _listener, dict)

        try:
            reply = self._send(
                "subscribe",
                {
                    "name": name,
                    "forward_dest": {
                        "process_name": listener_process_name,
                        "pid": os.getpid(),
                        "ipc_id": listener_ipc_id,
                    },
                },
                dict,
            )
        except Exception:
            remove_listener(listener_ipc_id)
            raise

        subscription_id = reply.get("subscription_id") if isinstance(reply, dict) else None
        if not isinstance(subscription_id, str) or not subscription_id:
            remove_listener(listener_ipc_id)
            raise ClipboardClientError("clipboardd returned invalid subscription_id")

        return ClipboardSubscription(self, listener_ipc_id, subscription_id)

    def unsubscribe(self, subscription_id: Optional[str] = None) -> dict[str, Any]:
        data = {}
        if subscription_id:
            data["subscription_id"] = subscription_id
        return self._send("unsubscribe", data, dict)

    def _send(self, ipc_id: str, data: Any, return_type: type | None = None) -> Any:
        try:
            return send(
                self.process_name,
                -1,
                ipc_id,
                data,
                return_type,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise ClipboardClientError(
                f"clipboardd request failed: process={self.process_name!r} ipc_id={ipc_id!r}: {exc}"
            ) from exc


def get_latest() -> ClipboardValue:
    return ClipboardClient().get_latest()


def push_text(text: str) -> dict[str, Any]:
    return ClipboardClient().push_text(text)


def push_image(data: bytes, mime_type: str = "image/png") -> dict[str, Any]:
    return ClipboardClient().push_image(data, mime_type)


def subscribe(
    callback: Callable[[ClipboardValue, dict[str, Any]], Any],
    *,
    name: str = "clipboard client",
) -> ClipboardSubscription:
    return ClipboardClient().subscribe(callback, name=name)

