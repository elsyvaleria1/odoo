from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestValidatorThresholds(TransactionCase):

    def setUp(self):
        super().setUp()
        self.validator = self.env["device.gps.data.validator"]

    def test_every_declared_key_resolves_to_its_cast_type(self):
        for name, (_key, _default, cast) in self.validator._THRESHOLDS.items():
            with self.subTest(threshold=name):
                self.assertIsInstance(self.validator._threshold(name), cast)

    def test_an_unknown_key_is_a_keyerror_not_a_silent_default(self):
        with self.assertRaises(KeyError):
            self.validator._threshold("no_such_threshold")

    def test_a_stored_parameter_overrides_the_default(self):
        name = "max_speed"
        key = self.validator._THRESHOLDS[name][0]
        self.env["ir.config_parameter"].sudo().set_param(key, "42.5")
        self.env.registry.clear_cache()
        self.assertEqual(self.validator._threshold(name), 42.5)
