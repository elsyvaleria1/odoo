from unittest.mock import patch

import odoo.http
from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase

from odoo.addons.iot.controllers.main import IoTController
from odoo.addons.iot.models.iot_channel import IotChannel


class IotCommonTest(HttpCase):
    iot_websocket_messages = []

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shop_iot_box = (
            cls.env["iot.box"]
            .sudo()
            .create(
                {
                    "name": "Shop",
                    "identifier": "test_iot_box",
                    "ip": "10.10.10.10",
                    "version": "25.07",
                }
            )
        )

        cls.iot_receipt_printer = (
            cls.env["iot.device"]
            .sudo()
            .create(
                {
                    "name": "Receipt Printer",
                    "identifier": "printer_identifier",
                    "iot_id": cls.shop_iot_box.id,
                    "type": "printer",
                    "subtype": "receipt_printer",
                    "connection": "network",
                    "connection_state": "connected",
                }
            )
        )

    def setUp(self):
        super().setUp()
        original_send_message = IotChannel._send_message

        answerable = {"session_id", "iot_identifiers", "device_identifiers"}

        def mock_send_message(
            iot_channel_record, message, message_type="iot_action", reply_key=None
        ):
            self.iot_websocket_messages.append({message_type: message})
            if message_type == "iot_action" and answerable <= message.keys():
                session_id = message["session_id"]
                if reply_key:
                    session_id = iot_channel_record._wrap_session_id(
                        reply_key, session_id, message["iot_identifiers"][0]
                    )
                answer = {
                    "session_id": session_id,
                    "iot_box_identifier": message["iot_identifiers"][0],
                    "device_identifier": message["device_identifiers"][0],
                    "status": "success",
                }
                if odoo.http.request:
                    return IoTController().iot_box_send_websocket(**answer)
                return self.url_open(
                    "/iot/box/send_websocket",
                    headers={"Content-Type": "application/json"},
                    data=json_dumps({"params": answer}),
                )
            return original_send_message(
                iot_channel_record, message, message_type, reply_key=reply_key
            )

        original_send_reply = IotChannel._send_reply

        def record_reply(iot_channel_record, message, message_type, **kwargs):
            self.iot_websocket_messages.append({message_type: message})
            return original_send_reply(
                iot_channel_record, message, message_type, **kwargs
            )

        for name, mock in (
            ("_send_message", mock_send_message),
            ("_send_reply", record_reply),
        ):
            patcher = patch.object(IotChannel, name, mock)
            self.addCleanup(patcher.stop)
            patcher.start()
