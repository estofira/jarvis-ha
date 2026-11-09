"""The Jarvis conversation agent (Phase 9, spec 2026-11-09-1 §6.3).

One turn: decide who said it (O8), post `user_input.text` and nothing else to
the gateway's `POST /turn`, and stream the answer into HA's chat log. HA's own
TTS speaks it, and HA's own `?` rule decides the follow-up (§6.3 item 4).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
import logging
import time
from typing import Literal

import aiohttp

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_BEARER,
    CONF_LANGUAGE,
    CONF_URL,
    DEFAULT_LANGUAGE,
    DOMAIN,
    REQUEST_ID_HEADER,
    TURN_TIMEOUT,
)
from .turnclient import (
    SSEParser,
    failure_for_status,
    failure_line,
    session_for,
    turn_body,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([JarvisConversationEntity(entry)])


class JarvisConversationEntity(conversation.ConversationEntity):
    """Jarvis, reached through `jarvis-gateway`."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supports_streaming = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
        )
        # §6.3 item 5: a 401 is a persistent refusal, an outcome rather than a
        # deferral (CLAUDE.md §4.2). It is logged at ERROR once, and only a 200
        # re-arms it, so a revoked bearer never writes a line per turn.
        self._unauthorized_logged = False

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        # The gateway answers in the language it is spoken to (O7).
        return MATCH_ALL

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        session_id, forwarded = session_for(
            user_input.satellite_id, user_input.context.user_id
        )
        language = self._entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
        # `user_input.text` and nothing else. Never `extra_system_prompt` and
        # never earlier chat-log content: an automation's
        # `assist_satellite.start_conversation` can template outside text into
        # both, and the turn would still count as the operator's (plan review).
        body = turn_body(
            session_id=session_id,
            text=user_input.text,
            language=language,
            forwarded=forwarded,
        )
        async for _content in chat_log.async_add_delta_content_stream(
            self.entity_id, self._answer(session_id, body, language)
        ):
            pass
        return conversation.async_get_result_from_chat_log(user_input, chat_log)

    async def _answer(
        self, session_id: str, body: dict, language: str
    ) -> AsyncIterator[conversation.AssistantContentDeltaDict]:
        """The whole answer, as ONE assistant content.

        HA speaks only the last `AssistantContent`, and once more than 60
        characters have streamed it speaks only the deltas. So a failure after
        partial text is a further delta here, never a second content: a second
        `role` would lose either the line or the partial answer.
        """
        yield {"role": "assistant"}

        started = time.monotonic()
        parser = SSEParser()
        status: int | str = "-"
        request_id = "-"
        chars = 0
        failure: str | None = None
        url = self._entry.data[CONF_URL]
        headers = {
            "Authorization": f"Bearer {self._entry.data[CONF_BEARER]}",
            "Accept": "text/event-stream",
        }

        try:
            async with async_get_clientsession(self.hass).post(
                f"{url}/turn", json=body, headers=headers, timeout=TURN_TIMEOUT
            ) as resp:
                status = resp.status
                request_id = resp.headers.get(REQUEST_ID_HEADER) or "-"
                self._note_status(resp.status, session_id, request_id)
                failure = failure_for_status(resp.status)
                if failure is None:
                    async for frame in _frames(resp, parser):
                        kind = frame.get("kind")
                        if kind == "text":
                            piece = frame.get("delta")
                        elif kind == "error":
                            # Already one sentence in character, in the right
                            # language (`turn.run`), so it is spoken as is.
                            piece = frame.get("message")
                            if not (isinstance(piece, str) and piece):
                                failure = "unavailable"
                                continue
                            if chars:
                                piece = " " + piece
                        else:
                            continue
                        if isinstance(piece, str) and piece:
                            chars += len(piece)
                            yield {"content": piece}
                    if not parser.close():
                        failure = "unavailable"
        except aiohttp.ConnectionTimeoutError:
            # `sock_connect`: the gateway never accepted the connection.
            failure = "unavailable"
        except TimeoutError:
            # `sock_read`: 300 s with nothing from a gateway that did answer.
            failure = "timeout"
        except aiohttp.ClientError as err:
            _LOGGER.debug("turn session=%s client error %s", session_id, type(err).__name__)
            failure = "unavailable"

        if failure is None and not chars:
            # A stream that completed with nothing to say would leave HA
            # silent, and a voice that stops responding reads as a broken one.
            failure = "unavailable"
        if failure is not None:
            line = failure_line(failure, language)
            piece = " " + line if chars else line
            chars += len(piece)
            yield {"content": piece}

        elapsed_ms = int((time.monotonic() - started) * 1000)
        # Lengths, timings and ids only, never the words or the bearer (§6.3 7).
        log = _LOGGER.debug if failure is None else _LOGGER.warning
        if failure == "unauthorized":
            log = _LOGGER.debug  # already said once at ERROR
        log(
            "turn session=%s status=%s failure=%s chars=%d elapsed_ms=%d "
            "dropped=%d request_id=%s",
            session_id, status, failure or "-", chars, elapsed_ms,
            parser.dropped, request_id,
        )

    def _note_status(self, status: int, session_id: str, request_id: str) -> None:
        if status == 200:
            self._unauthorized_logged = False
        elif status == 401 and not self._unauthorized_logged:
            self._unauthorized_logged = True
            _LOGGER.error(
                "jarvis-gateway refused Home Assistant's bearer (401); every turn "
                "will fail until it is replaced. session=%s request_id=%s",
                session_id, request_id,
            )


async def _frames(
    resp: aiohttp.ClientResponse, parser: SSEParser
) -> AsyncIterator[dict]:
    """Frames until `done` or `error`. What follows a terminal frame is ignored."""
    async for chunk in resp.content.iter_any():
        for frame in parser.feed(chunk):
            yield frame
            if frame.get("kind") in ("done", "error"):
                return
