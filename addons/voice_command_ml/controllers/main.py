from odoo import http
from odoo.http import request

from odoo.addons.voice_command.controllers.utterance import check_may_speak, may_speak
from odoo.addons.voice_command_ml.tools.intent import (
    can_interpret,
    interpret_sentence,
)


class VoiceAiController(http.Controller):
    @http.route("/voice_command_ml/available", type="jsonrpc", auth="user")
    def available(self) -> dict:
        return {"available": may_speak(request.env) and can_interpret(request.env)}

    @http.route("/voice_command_ml/interpret", type="jsonrpc", auth="user")
    def interpret(self, text: str, choices: list) -> dict:
        check_may_speak(request.env)
        return {"actions": interpret_sentence(request.env, text, choices)}
