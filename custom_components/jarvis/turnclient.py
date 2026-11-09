"""The Jarvis integration's logic, standard library only.

Everything here is decidable without Home Assistant, so it is testable without
it: the trust rule, the `/turn` body, the SSE parser, status classification and
the spoken failure lines. The HA glue imports it with a relative import; the
`ops` suite loads it by file path (`testsupport.haintegration`). That is why it
imports nothing outside the standard library, and nothing from `ops/` or `lib/`
(spec `docs/superpowers/specs/2026-11-09-1.md`).
"""

from __future__ import annotations

import json

# O8, §6.3 2a. `satellite_id` alone is forgeable: an automation's
# `assist_satellite.start_conversation`, or any caller of the conversation
# service, can name a satellite while the text is someone else's. A turn is the
# operator's only when a satellite is named AND HA attributes it to no user,
# which is what a spoken utterance heard by the satellite itself looks like.
# Everything else is sent `forwarded`, so the gateway taints the session.
_OTHER_SESSION = "ha:other"


def session_for(satellite_id: str | None, user_id: str | None) -> tuple[str, bool]:
    """Return `(session_id, forwarded)`. Fails toward forwarded."""
    if satellite_id is not None and user_id is None:
        return f"ha:{satellite_id}", False
    return _OTHER_SESSION, True


def turn_body(
    *, session_id: str, text: str, language: str, forwarded: bool
) -> dict[str, object]:
    """The exact `/turn` body (O7).

    `reply_language` is never sent: HA exposes no detected language, and the
    gateway's `follow_spoken_language` is what lets the answer follow the
    speaker. `forwarded` is always present, never omitted, so that an absence
    cannot be read as trust.
    """
    return {
        "session": session_id,
        "text": text,
        "language": language,
        "speak": False,
        "follow_spoken_language": True,
        "forwarded": forwarded,
    }


class SSEParser:
    """Incremental reader for the gateway's `data: <json>\\n\\n` frames.

    It buffers BYTES and decodes only a complete frame: a read boundary can fall
    inside a multibyte character, and decoding per chunk would corrupt it.
    Filtering by `kind` is the caller's job.
    """

    def __init__(self) -> None:
        self._buf = b""
        self._terminal = False
        self.dropped = 0

    def feed(self, chunk: bytes) -> list[dict]:
        self._buf += chunk
        frames: list[dict] = []
        while True:
            # Normalise CRLF so a proxy's line endings cannot hide a boundary.
            self._buf = self._buf.replace(b"\r\n", b"\n")
            end = self._buf.find(b"\n\n")
            if end < 0:
                return frames
            raw, self._buf = self._buf[:end], self._buf[end + 2:]
            obj = self._decode(raw)
            if obj is not None:
                frames.append(obj)
                if obj.get("kind") in ("done", "error"):
                    self._terminal = True

    def _decode(self, raw: bytes) -> dict | None:
        data: list[str] = []
        try:
            for line in raw.decode("utf-8").split("\n"):
                # Comments (`:`) and other fields (`event:`, `id:`) are ignored.
                if line.startswith("data:"):
                    data.append(line[5:].removeprefix(" "))
        except UnicodeDecodeError:
            self.dropped += 1
            return None
        if not data:
            return None
        try:
            obj = json.loads("\n".join(data))
        except ValueError:
            self.dropped += 1
            return None
        if not isinstance(obj, dict):
            self.dropped += 1
            return None
        return obj

    def close(self) -> bool:
        """True iff a `done` or `error` frame was seen: the stream completed."""
        return self._terminal


FAILURES = ("unauthorized", "busy", "unavailable", "timeout")


def failure_for_status(status: int) -> str | None:
    if status == 200:
        return None
    if status == 401:
        return "unauthorized"
    if status == 409:
        return "busy"
    return "unavailable"


_LINES = {
    "unauthorized": (
        "I'm afraid I've been locked out, sir. Home Assistant's key to me needs replacing.",
        "Attól tartok, kizártak, uram. A Home Assistant kulcsát cserélni kell.",
    ),
    "busy": (
        "One moment, sir. I'm still answering the last question.",
        "Egy pillanat, uram, még az előző kérdésen dolgozom.",
    ),
    "unavailable": (
        "I can't reach myself just now, sir. Do try again shortly.",
        "Most nem érem el önmagamat, uram. Kérem, próbálja újra hamarosan.",
    ),
    "timeout": (
        "That took far too long, sir, so I've stopped waiting.",
        "Ez túl sokáig tartott, uram, így felhagytam a várakozással.",
    ),
}


def failure_line(kind: str, language: str) -> str:
    """The spoken line for a failure. Anything but `en` reads as Hungarian."""
    en, hu = _LINES[kind]
    return en if language == "en" else hu
