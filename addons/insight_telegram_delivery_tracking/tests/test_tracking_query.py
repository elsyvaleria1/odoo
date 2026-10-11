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

    def test_partial_number_does_not_disclose_a_different_shipment(self):
        self._picking("XTOL01583026", self.other)
        self._picking("TOL015830260", self.other)
        self.assertIn("No transfer", self._answer(reference="TOL01583026"))
        self._picking("TOL00000000, tol01583026", self.calysil)
        text = self._answer(reference="TOL01583026")
        self.assertIn(self.calysil.name, text)
        self.assertNotIn(self.other.name, text)

    def test_one_guide_uses_its_snapshot_instead_of_the_transfer_summary(self):
        self._picking(
            "TOL01583026, TOL01584639",
            self.other,
            carrier_tracking_state="in_transit",
            carrier_status_branch="SUMMARY BRANCH",
            carrier_tracking_details={
                "TOL01583026": {
                    "state": "delivered",
                    "text": "DELIVERED TO RECIPIENT",
                    "branch": "IGUALA, GRO.",
                    "date": "2026-10-08 22:09:00",
                    "received_by": "Recipient",
                },
                "TOL01584639": {
                    "state": "in_transit",
                    "branch": "OTHER BRANCH",
                },
            },
        )
        text = self._answer(reference="TOL01583026")
        self.assertIn("Delivered", text)
        self.assertIn("DELIVERED TO RECIPIENT", text)
        self.assertIn("IGUALA, GRO.", text)
        self.assertIn("16:09", text)
        self.assertNotIn("SUMMARY BRANCH", text)
        self.assertNotIn("TOL01584639", text)

    def test_a_missing_snapshot_does_not_reuse_a_sibling_status(self):
        self._picking(
            "TOL01583026, TOL01584639",
            self.other,
            carrier_tracking_state="delivered",
            carrier_tracking_details={"TOL01583026": {"state": "delivered"}},
            date_carrier_tracking_sync=datetime(2026, 10, 9, 18, 0),
        )
        text = self._answer(reference="TOL01584639")
        self.assertIn("not read yet", text)
        self.assertNotIn("Delivered", text)
        self.assertNotIn("carrier status read", text)

    def test_failed_refresh_does_not_claim_a_fresh_successful_read(self):
        self._picking(
            "TOL01583026",
            self.other,
            carrier_tracking_state="in_transit",
            date_carrier_tracking_sync=datetime(2026, 10, 9, 18, 0),
            carrier_tracking_error="provider exception with private diagnostics",
        )
        text = self._answer(reference="TOL01583026")
        self.assertIn("In Transit", text)
        self.assertIn("last update attempt", text)
        self.assertIn("12:00", text)
        self.assertIn("showing saved data", text)
        self.assertNotIn("carrier status read", text)
        self.assertNotIn("private diagnostics", text)

    def test_never_read_status_is_explicit(self):
        self._picking("TOL01583026", self.other)
        text = self._answer(reference="TOL01583026")
        self.assertIn("not read yet", text)
        self.assertIn("carrier status has not been read yet", text)

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
