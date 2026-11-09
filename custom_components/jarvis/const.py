"""Constants for the Jarvis integration (Phase 9, spec 2026-11-09-1)."""

from __future__ import annotations

import aiohttp

DOMAIN = "jarvis"

CONF_URL = "url"
CONF_BEARER = "bearer"
CONF_LANGUAGE = "language"

LANGUAGES = ("hu", "en")
# O3: Hungarian unless the operator changes the option.
DEFAULT_LANGUAGE = "hu"

# The gateway's response header naming its request id (`lib/asgi.py`
# `REQUEST_ID_HEADER`). Copied, not imported: nothing here may import `lib`.
REQUEST_ID_HEADER = "x-jarvis-request-id"

# §6.3 item 6. A whole turn is not capped, because a browse alone may take
# 270 s. A silent gap of 300 s ends it, and a gateway that does not accept the
# connection is spoken after 10 s.
TURN_TIMEOUT = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=300)

# The config flow's two probes answer at once or not at all; nothing in them
# waits on a model.
VALIDATE_TIMEOUT = aiohttp.ClientTimeout(total=15, sock_connect=10)
