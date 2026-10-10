from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSpreadsheetIrWebsocket(TransactionCase):
    def test_check_spreadsheet_channel_missing_res_id_segment(self):
        """A channel with no res_id segment must be ignored, not raise."""
        channel = self.env["ir.websocket"]._check_spreadsheet_channel(
            "spreadsheet_collaborative_session:res.partner"
        )
        self.assertIsNone(channel)

    def test_get_bus_channels_ignores_malformed_spreadsheet_channel(self):
        channel = "spreadsheet_collaborative_session:res.partner"
        channels = self.env["ir.websocket"]._get_bus_channels([channel])
        self.assertIn(channel, channels)

    def test_the_abstract_spreadsheet_mixin_is_refused_alone(self):
        # browse().exists() on a model with no table aborts the transaction
        channel = "spreadsheet_collaborative_session:mixin.spreadsheet:1"
        self.assertIsNone(self.env["ir.websocket"]._check_spreadsheet_channel(channel))
        channels = self.env["ir.websocket"]._get_bus_channels([channel, "other"])
        self.assertIn("other", channels)
