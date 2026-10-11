import base64
import binascii
import time
from collections import defaultdict, deque

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.voice.tools.utterance import (
    can_hear_commands,
    english_pass,
    transcribe_utterance,
)

MAX_COMMANDS_PER_MINUTE = 30

_recent_commands: defaultdict[int, deque[float]] = defaultdict(deque)


def _throttle(uid: int) -> None:
    now = time.monotonic()
    recent = _recent_commands[uid]
    while recent and now - recent[0] > 60:
        recent.popleft()
    if len(recent) >= MAX_COMMANDS_PER_MINUTE:
        raise UserError(request.env._("Too many voice commands; wait a moment."))
    recent.append(now)


def may_speak(env) -> bool:
    return env.user._is_internal()


def check_may_speak(env) -> None:
    if not may_speak(env):
        raise AccessError(env._("Voice commands are for internal users."))


class VoiceUtteranceController(http.Controller):
    @http.route("/voice/available", type="jsonrpc", auth="user")
    def available(self) -> dict:
        return {
            "available": may_speak(request.env) and can_hear_commands(request.env),
            "english_pass": english_pass(request.env),
        }

    @http.route("/voice/transcribe", type="jsonrpc", auth="user")
    def transcribe(
        self, audio: str, language: str | None = None, prompt: str | None = None
    ) -> dict:
        check_may_speak(request.env)
        _throttle(request.env.uid)
        try:
            data = base64.b64decode(audio, validate=True)
        except (binascii.Error, ValueError) as error:
            raise UserError(request.env._("The recording is not readable.")) from error
        return {"text": transcribe_utterance(request.env, data, language, prompt)}
