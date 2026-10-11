from unittest.mock import MagicMock, patch
from zlib import crc32

from odoo.tests.common import BaseCase
from odoo.tools import file_open


class MockSocket:
    def __init__(self, f):
        self.f = f

    def recv(self, num_bytes):
        return self.f.read(num_bytes)


class TestIncomingTransactionResponse(BaseCase):
    @patch.dict(
        "sys.modules",
        {
            "odoo.addons.iot_drivers": MagicMock(),
            "odoo.addons.iot_drivers.driver": MagicMock(),
            "odoo.addons.iot_drivers.event_manager": MagicMock(),
            "odoo.addons.iot_drivers.iot_handlers.interfaces.SocketInterface": MagicMock(),
        },
    )
    def setUp(self):
        from odoo.addons.iot_ingenico.iot_handlers.drivers.IngenicoDriver import (
            IncomingIngenicoMessage,
        )

        self.IncomingIngenicoMessage = IncomingIngenicoMessage

    def test_parse_ticketdata(self):
        with file_open("iot_ingenico/tests/data/TransactionResponse", "rb") as f:
            dev = MockSocket(f)
            msg = self.IncomingIngenicoMessage(dev)
            ticket_data = msg.getTransactionTicket()

            assert b"KOPIE" in ticket_data
            assert b"Chip" in ticket_data


class TestOutgoingIngenicoMessage(BaseCase):
    @patch.dict(
        "sys.modules",
        {
            "odoo.addons.iot_drivers": MagicMock(),
            "odoo.addons.iot_drivers.driver": MagicMock(),
            "odoo.addons.iot_drivers.event_manager": MagicMock(),
            "odoo.addons.iot_drivers.iot_handlers.interfaces.SocketInterface": MagicMock(),
        },
    )
    def setUp(self):
        from odoo.addons.iot_ingenico.iot_handlers.drivers.IngenicoDriver import (
            OutgoingIngenicoMessage,
        )

        self.OutgoingIngenicoMessage = OutgoingIngenicoMessage
        self.dev = MagicMock()
        self.msg = self.OutgoingIngenicoMessage(
            dev=self.dev,
            terminalId=b"1",
            ecrId="1",
            protocolId=b"1",
            messageType="TransactionRequest",
            sequence=b"1",
            transactionId=1,
            amount=1,
        )

    def test_mdc_tag_length(self):
        self.assertEqual(len(self.msg._generateMDC(b"dummy")), 6)

    def test_unpadded_crc(self):
        content = bytes(11)

        crc = format(crc32(content), "x")
        self.assertEqual(crc, "6b87b1ec")
        self.assertEqual(len(crc), 8)

        self.assertEqual(len(self.msg._getCRC32(content)), 4)

    def test_padded_crc(self):
        content = bytes(13)

        crc = format(crc32(content), "x")
        self.assertEqual(crc, "f744682")
        self.assertEqual(len(crc), 7)

        self.assertEqual(len(self.msg._getCRC32(content)), 4)
