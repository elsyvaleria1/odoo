from datetime import date, datetime

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.insight_telegram.services import catalog


@tagged("post_install", "-at_install")
class TestTrackingQuery(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Tres Guerras",
                "product_id": cls.env["product.product"]
                .create({"name": "Freight", "type": "service"})
                .id,
            }
        )
        cls.calysil = cls.env["res.partner"].create({"name": "Agroquimicos Calysil"})
        cls.other = cls.env["res.partner"].create({"name": "Agrozihua"})
        cls.query = catalog.QUERIES["tracking"]

    def _picking(self, reference, partner, **status):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.env.ref("stock.picking_type_out").id,
                "partner_id": partner.id,
                "carrier_id": self.carrier.id,
                "carrier_tracking_ref": reference,
            }
        )
        if status:
            picking.write(status)
        return picking

    def _answer(self, **params):
        return catalog.answer(
            self.env,
            self.query,
            params,
            tz="America/Mexico_City",
            today=date(2026, 10, 9),
        )

    def test_one_number_says_where_it_is_and_when(self):
        self._picking(
            "TOL01583026",
            self.other,
            carrier_tracking_state="delivered",
            carrier_status_branch="IGUALA, GRO.",
            date_carrier_status=datetime(2026, 10, 8, 22, 9),
            carrier_received_by="Recipient",
            date_carrier_tracking_sync=datetime(2026, 10, 9, 18, 0),
        )
        text = self._answer(reference="tol01583026")
        self.assertIn("TOL01583026", text)
        self.assertIn("Delivered", text)
        self.assertIn("IGUALA, GRO.", text)
        self.assertIn("16:09", text, "the owner's local time")
        self.assertIn("received by Recipient", text)
        self.assertIn("not validated in Odoo yet", text)
        self.assertIn("carrier status read", text)

    def test_an_unknown_number_says_so(self):
        text = self._answer(reference="TOL00000000")
        self.assertIn("TOL00000000", text)
        self.assertIn("No transfer", text)

    def test_without_a_number_it_lists_what_is_on_the_way_and_what_to_validate(self):
        self._picking(
            "TOL01584640",
            self.calysil,
            carrier_tracking_state="in_transit",
            carrier_estimated_delivery="LUNES 12 DE OCTUBRE DEL 2026",
        )
        self._picking("TOL01584641", self.calysil)
        self._picking("TOL01583026", self.other, carrier_tracking_state="delivered")
        text = self._answer()
        self.assertIn("On the way: **2**", text)
        self.assertIn("not validated: **1**", text)
        self.assertIn("expected LUNES 12 DE OCTUBRE DEL 2026", text)
        self.assertIn("not read yet", text, "a number never read is listed, not hidden")

    def test_a_customer_narrows_the_list(self):
        self._picking("TOL01584640", self.calysil, carrier_tracking_state="in_transit")
        self._picking("TOL01583030", self.other, carrier_tracking_state="in_transit")
        text = self._answer(partner="Calysil")
        self.assertIn("TOL01584640", text)
        self.assertNotIn("TOL01583030", text)

    def test_the_query_is_offered_to_the_bot(self):
        self.assertIn("tracking", catalog.available_queries(self.env))
