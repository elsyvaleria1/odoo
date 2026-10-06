from odoo.tests import tagged

from .common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestHomeTileDevices(DeviceTransactionCase):
    def _devices(self):
        return self.env["home.tile"].get_tiles(
            [{"id": "devices_1", "type": "devices"}]
        )["devices_1"]["data"]

    def test_the_devices_tile_counts_states_and_lists_the_silent_ones_errors_first(
        self,
    ):
        before = self._devices()
        long_ago = "2000-01-01 00:00:00"
        quiet = self._create_device_device(
            identifier="TILE-DISCONNECTED",
            connection_state="disconnected",
            date_last_data_received=long_ago,
        )
        broken = self._create_device_device(
            identifier="TILE-ERROR",
            connection_state="error",
            date_last_data_received=long_ago,
        )
        self._create_device_device(
            identifier="TILE-CONNECTED", connection_state="connected"
        )
        after = self._devices()
        self.assertEqual(
            {
                state: after[state] - before[state]
                for state in ("connected", "disconnected", "error")
            },
            {"connected": 1, "disconnected": 1, "error": 1},
        )
        ids = [device["id"] for device in after["devices"]]
        self.assertLess(ids.index(broken.id), ids.index(quiet.id))
        self.assertEqual(after["devices"][ids.index(broken.id)]["state"], "error")

    def test_the_devices_tile_keeps_its_statement_count(self):
        request = [{"id": "devices_1", "type": "devices"}]
        self.env["home.tile"].get_tiles(request)
        self.env.invalidate_all()
        with self.assertQueryCount(4):
            self.env["home.tile"].get_tiles(request)
