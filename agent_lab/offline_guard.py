"""Controlled Python network guard for the standalone Lesson 51 process."""

import http.client
import socket
import urllib.request
from collections.abc import Callable
from typing import Any


class NetworkGuard:
    def __init__(self) -> None:
        self.attempts = 0
        self.originals: list[tuple[Any, str, Callable[..., Any]]] = []

    def _deny(self, *_args: Any, **_kwargs: Any) -> Any:
        self.attempts += 1
        raise RuntimeError("Lesson 51 standalone network guard denied a connection")

    def install(self) -> "NetworkGuard":
        for owner, name in ((socket.socket, "connect"),
                            (socket.socket, "connect_ex"),
                            (socket, "create_connection"),
                            (http.client.HTTPConnection, "connect"),
                            (http.client.HTTPSConnection, "connect"),
                            (urllib.request, "urlopen")):
            original = getattr(owner, name)
            self.originals.append((owner, name, original))
            setattr(owner, name, self._deny)
        return self

    def restore(self) -> None:
        for owner, name, original in reversed(self.originals):
            setattr(owner, name, original)
        self.originals.clear()

    def __enter__(self) -> "NetworkGuard":
        return self.install()

    def __exit__(self, *_exc: Any) -> None:
        self.restore()
