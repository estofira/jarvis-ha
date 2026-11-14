# Jarvis for Home Assistant

A conversation agent that hands what Home Assistant heard to **Jarvis**, a
personal assistant running as `jarvis-gateway`, and streams Jarvis's answer
back for Home Assistant to speak.

Home Assistant keeps the listening and the speaking: its own speech-to-text and
text-to-speech integrations run the Assist pipeline, and this agent sits in the
middle. It sends the transcript and nothing else. Earlier chat-log content and
an automation's extra system prompt are never forwarded.

## What it needs

A running `jarvis-gateway`, reachable from Home Assistant, configured with a
bearer of Home Assistant's own (`JARVIS_GATEWAY_HA_BEARER`). This integration
does nothing without one; it is not a general-purpose agent.

## Configuration

Add the **Jarvis** integration and fill in three fields:

| Field | What it is |
|---|---|
| Gateway URL | The gateway's base URL, without a trailing slash. |
| Home Assistant bearer | The gateway's `JARVIS_GATEWAY_HA_BEARER` value. |
| Language | `hu` (default) or `en`: the language a new conversation starts in, and the language of the lines spoken when the gateway cannot answer. |

Setup checks the gateway before it saves anything. The language can be changed
afterwards under the integration's options.

Then pick **Jarvis** as the conversation agent of an Assist pipeline, and turn
off *Prefer handling commands locally* on that pipeline, or Home Assistant will
act on simple commands itself without asking Jarvis.

## Who is trusted

Only a turn heard by an Assist satellite, with no logged-in user attached, is
treated as the operator speaking. Text typed into Assist, and any automation or
script calling the agent, is sent to Jarvis marked as forwarded: Jarvis reads it
as data and will not act on it.

## Versions

Each release is numbered when it is published, and only when the integration
itself changed. Home Assistant offers a newer release under Settings › Updates.
