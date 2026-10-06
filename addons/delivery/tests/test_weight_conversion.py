from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCarrierWeightConversion(TransactionCase):
    def setUp(self):
        super().setUp()
        self.carrier = self.env["delivery.carrier"].new({"name": "Weight conversion"})
        self.parameters = self.env["ir.config_parameter"]

    def test_kilograms_keep_precision_and_sign(self):
        self.parameters.set_param("product.weight_in_lbs", "0")
        for weight in (0.0, 0.000001, 1.23456789, -2.5):
            with self.subTest(weight=weight):
                self.assertEqual(self.carrier._get_weight_in_kg(weight), weight)

    def test_pounds_are_converted_without_rounding(self):
        self.parameters.set_param("product.weight_in_lbs", "1")
        for weight in (0.0, 0.000001, 1.0, 2.5, -2.5):
            with self.subTest(weight=weight):
                self.assertAlmostEqual(
                    self.carrier._get_weight_in_kg(weight), weight * 0.453592, places=12
                )
        self.assertGreater(self.carrier._get_weight_in_kg(0.000001), 0)

    def test_configuration_change_is_read_by_each_call(self):
        self.parameters.set_param("product.weight_in_lbs", "1")
        self.assertAlmostEqual(self.carrier._get_weight_in_kg(1), 0.453592, places=12)
        self.parameters.set_param("product.weight_in_lbs", "0")
        self.assertEqual(self.carrier._get_weight_in_kg(1), 1)

    def test_requires_one_carrier(self):
        carriers = self.carrier | self.env["delivery.carrier"].new({"name": "Second"})
        for records in (self.env["delivery.carrier"], carriers):
            with self.assertRaises(ValueError):
                records._get_weight_in_kg(1.0)
