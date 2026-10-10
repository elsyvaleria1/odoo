from threading import Event
from unittest.mock import patch

from odoo.libs.json import dumps as json_dumps
from odoo.tests import new_test_user, tagged

from ..models.ir_websocket import IrWebsocket
from .common import WebsocketCase


@tagged("-at_install", "post_install")
class TestWebsocketRequest(WebsocketCase):
    def _connect_as(self, login):
        self.authenticate(login, "Password!1")
        return self.websocket_connect(cookie=f"session_id={self.session.sid}")

    def test_message_is_served_in_the_session_language(self):
        self.env["res.lang"]._activate_lang("es_MX")
        new_test_user(self.env, login="hablante", password="Password!1", lang="es_MX")
        served = Event()
        seen = {}
        serve = IrWebsocket._serve_ir_websocket

        def _serve(model, event_name, data):
            seen["lang"] = model.env.lang
            serve(model, event_name, data)
            served.set()

        with patch.object(IrWebsocket, "_serve_ir_websocket", _serve):
            ws = self._connect_as("hablante")
            ws.send(json_dumps({"event_name": "noop", "data": {}}))
            self.assertTrue(served.wait(5))
        self.assertEqual(seen["lang"], "es_MX")
