from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import common, new_test_user

NOMINATIM = {
    "display_name": "Privada Cocoyoc, San Juan, Tenango del Valle, México",
    "address": {
        "road": "Privada Cocoyoc",
        "village": "San Juan",
        "town": "Tenango del Valle",
        "county": "Tenango del Valle",
        "state": "Estado de México",
        "country_code": "mx",
    },
}


class TestCurrentAddress(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        profile = cls.env["device.profile"].create({"name": "Address Test"})
        cls.device = cls.env["device.device"].create(
            {
                "name": "Address Tracker",
                "identifier": "ADDR-001",
                "config_id": profile.id,
                "comm_protocol": "http",
            }
        )
        cls.Geocoder = type(cls.env["geocoder"])

    def _place(self, latitude, longitude):
        log = self.env["device.data.log.gps"].create(
            {"device_id": self.device.id, "latitude": latitude, "longitude": longitude}
        )
        self.device.log_gps_last_id = log

    def _reverse(self, **kw):
        return patch.object(self.Geocoder, "_call_openstreetmap_reverse", **kw)

    def test_address_of_the_last_position(self):
        self._place(19.1030, -99.5900)
        with self._reverse(return_value=NOMINATIM) as reverse:
            address = self.device.get_current_address()
        reverse.assert_called_once_with(19.1030, -99.5900)
        self.assertEqual(
            address,
            "Privada Cocoyoc, San Juan, Tenango del Valle, Estado de México",
            "street, settlement, municipality and state, one of each",
        )

    def test_parked_vehicle_is_not_looked_up_again(self):
        self._place(19.1030, -99.5900)
        with self._reverse(return_value=NOMINATIM):
            self.device.get_current_address()
        self._place(19.10302, -99.59001)
        with self._reverse(return_value=NOMINATIM) as reverse:
            self.device.get_current_address()
        reverse.assert_not_called()

    def test_moved_vehicle_is_looked_up_again(self):
        self._place(19.1030, -99.5900)
        with self._reverse(return_value=NOMINATIM):
            self.device.get_current_address()
        self._place(19.2000, -99.6000)
        moved = {"address": {"road": "Carretera Toluca", "state": "Estado de México"}}
        with self._reverse(return_value=moved):
            address = self.device.get_current_address()
        self.assertEqual(
            address,
            "Carretera Toluca, Estado de México",
            "the address follows the vehicle, it is not the first one found",
        )

    def test_geocoder_down_gives_no_address(self):
        self._place(19.1030, -99.5900)
        with self._reverse(side_effect=UserError("timeout")):
            self.assertFalse(self.device.get_current_address())
        self.assertFalse(self.device.current_address_key, "nothing cached")

    def test_no_position_no_lookup(self):
        with self._reverse() as reverse:
            self.assertFalse(self.device.get_current_address())
        reverse.assert_not_called()

    def test_a_gps_user_caches_the_address_and_writes_nothing_else(self):
        user = new_test_user(
            self.env, login="gps_locator", groups="device_gps.group_device_gps_user"
        )
        self._place(19.1030, -99.5900)
        with self._reverse(return_value=NOMINATIM):
            address = self.device.with_user(user).get_current_address()

        self.assertTrue(address)
        self.assertEqual(self.device.current_address, address)
        self.assertEqual(self.device.write_uid, user)
        self.assertFalse(self.device.with_user(user).env.su)
        with self.assertRaises(AccessError):
            self.device.with_user(user).write({"current_address": "Elsewhere"})

    def test_a_device_reader_without_the_verb_looks_nothing_up(self):
        reader = new_test_user(
            self.env, login="device_reader", groups="device.group_device_user"
        )
        self._place(19.1030, -99.5900)
        self.device.with_user(reader).check_access("read")
        with self._reverse(return_value=NOMINATIM) as reverse:
            with self.assertRaises(AccessError):
                self.device.with_user(reader).get_current_address()
        reverse.assert_not_called()
        self.assertFalse(self.device.current_address_key)

    def test_an_employee_without_device_read_looks_nothing_up(self):
        outsider = new_test_user(self.env, "address-outsider", groups="base.group_user")
        self._place(19.1030, -99.5900)
        with self._reverse(return_value=NOMINATIM) as reverse:
            with self.assertRaises(AccessError):
                self.device.with_user(outsider).get_current_address()
        reverse.assert_not_called()
        self.assertFalse(self.device.current_address_key)

    def test_a_gps_user_cannot_locate_another_companys_device(self):
        company = self.env["res.company"].create({"name": "Address Other Company"})
        user = new_test_user(
            self.env, "address-other-company", groups="device_gps.group_device_gps_user"
        )
        self.device.company_id = company
        self._place(19.1030, -99.5900)
        device = self.device.with_user(user).with_context(
            allowed_company_ids=user.company_ids.ids
        )
        with self._reverse(return_value=NOMINATIM) as reverse:
            with self.assertRaises(AccessError):
                device.get_current_address()
        reverse.assert_not_called()
        self.assertFalse(self.device.current_address_key)
        with self.assertRaises(AccessError):
            device.with_privilege(
                "device_gps_geoengine.privilege_cache_current_address",
                reason="verify the cache privilege preserves the company guard",
            ).write({"current_address": "Elsewhere"})

    def test_the_cache_privilege_does_not_write_a_device_without_a_position(self):
        user = new_test_user(
            self.env, "address-no-position", groups="device_gps.group_device_gps_user"
        )
        with self.assertRaises(AccessError):
            self.device.with_user(user).with_privilege(
                "device_gps_geoengine.privilege_cache_current_address",
                reason="verify only devices with a recorded position can be cached",
            ).write({"current_address": "Elsewhere"})
