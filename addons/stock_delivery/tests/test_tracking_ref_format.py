from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestTrackingRefFormat(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        product = cls.env["product.product"].create(
            {
                "name": "Freight",
                "type": "service",
                "categ_id": cls.env.ref("delivery.product_category_deliveries").id,
            }
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Branch Freight",
                "delivery_type": "fixed",
                "product_id": product.id,
                "tracking_ref_pattern": "[A-Z]{3}[0-9]{8}",
                "tracking_ref_example": "TOL01584639",
            }
        )
        cls.free_carrier = cls.env["delivery.carrier"].create(
            {"name": "Any Freight", "delivery_type": "fixed", "product_id": product.id}
        )
        warehouse = cls.env.ref("stock.warehouse0")
        cls.picking = cls.env["stock.picking"].create(
            {
                "picking_type_id": warehouse.out_type_id.id,
                "location_id": warehouse.lot_stock_id.id,
                "location_dest_id": cls.env.ref("stock.stock_location_customers").id,
                "partner_id": cls.env["res.partner"].create({"name": "Customer"}).id,
                "carrier_id": cls.carrier.id,
            }
        )

    def test_matching_reference_is_saved(self):
        self.picking.carrier_tracking_ref = "TOL01584639"
        self.assertEqual(self.picking.carrier_tracking_ref, "TOL01584639")

    def test_malformed_reference_is_refused_with_the_example(self):
        # One digit short, lowercase letters, a stray character: what a hand
        # copying the slip gets wrong.
        for wrong in ("TOL0158463", "tol01584639", "TOL-01584639", "TO01584639"):
            with (
                self.subTest(wrong=wrong),
                self.assertRaisesRegex(ValidationError, "TOL01584639"),
            ):
                self.picking.carrier_tracking_ref = wrong

    def test_every_reference_of_a_list_is_checked(self):
        self.picking.carrier_tracking_ref = "TOL01584639, MEX00000001"
        with self.assertRaisesRegex(ValidationError, "MEX0000001"):
            self.picking.carrier_tracking_ref = "TOL01584639,MEX0000001"

    def test_switching_to_a_formatted_carrier_checks_the_reference(self):
        picking = self.picking.copy({"carrier_id": self.free_carrier.id})
        picking.carrier_tracking_ref = "12345"
        with self.assertRaises(ValidationError):
            picking.carrier_id = self.carrier

    def test_carrier_without_format_accepts_any_reference(self):
        self.picking.carrier_id = self.free_carrier
        self.picking.carrier_tracking_ref = "anything goes 123"
        self.assertEqual(self.picking.carrier_tracking_ref, "anything goes 123")

    def test_the_form_refuses_a_malformed_reference_on_save(self):
        form = Form(self.picking)
        form.carrier_tracking_ref = "TOL0158463"
        with self.assertRaises(ValidationError):
            form.save()

    def test_carrier_format_must_compile(self):
        with self.assertRaisesRegex(ValidationError, "regular expression"):
            self.free_carrier.tracking_ref_pattern = "[A-Z"

    def test_carrier_example_must_match_its_format(self):
        with self.assertRaisesRegex(ValidationError, "TOL1"):
            self.carrier.tracking_ref_example = "TOL1"
