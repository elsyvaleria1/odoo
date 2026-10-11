from urllib.parse import urlencode

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request


class TrainingSimulatorController(http.Controller):
    @http.route(
        "/training_simulator/<int:simulator_id>/play",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def play(self, simulator_id, **kwargs):
        simulator = request.env["training.simulator"].browse(simulator_id).exists()
        if not simulator:
            raise NotFound
        session = request.env["training.simulator.session"].create(
            {"simulator_id": simulator.id}
        )
        session.snapshot = simulator._training_snapshot(session)
        query = urlencode(
            {
                "session": session.id,
                **{k: v for k, v in kwargs.items() if k != "session"},
            }
        )
        return request.redirect(f"{simulator.play_route}?{query}", local=True)

    @http.route(
        "/training_simulator/session/<int:session_id>/finish",
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def finish(self, session_id, result):
        session = request.env["training.simulator.session"].browse(session_id).exists()
        if not session:
            raise NotFound
        session._training_finish(result or {})
        return {"session_id": session.id}
