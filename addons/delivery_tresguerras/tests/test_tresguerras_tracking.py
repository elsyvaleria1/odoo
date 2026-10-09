from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import SQL

from odoo.addons.delivery_tresguerras.models.delivery_carrier import TRACKING_URL


def _answer(code, event, branch, day, hour, kind, received="", estimated=""):
    """A Tres Guerras answer shaped like the ones read on 2026-10-09, with the
    people's names left out."""
    return {
        "Respuesta": {
            "ultimo_estado": {
                "estado": event,
                "estadoembarque": code,
                "sucursal": branch,
                "fecha_corta": day,
                "hora": hour,
                "recibio": received,
            },
            "detalle": {
                "item": {
                    "TALON": "TOL01583026",
                    "BANDERA_EAD": kind,
                    "entrega_estimada": estimated,
                }
            },
            "Error": "",
        }
    }


DELIVERED_HOME = _answer(
    "07",
    "EMBARQUE ENTREGADO",
    "IGUALA, GRO.",
    "08/10/2026",
    "16:09",
    "S",
    received="Recipient",
    estimated="VIERNES 09 DE OCTUBRE DEL 2026",
)
AT_OCURRE = _answer(
    "09",
    "CLIENTE DE OCURRE AVISADO",
    "SAN CRISTOBAL DE LAS CASAS, CHIPS.",
    "08/10/2026",
    "10:38",
    "O",
)
IN_TRANSIT = _answer(
    "03",
    "TRANSITO ENTRE SUCURSALES",
    "PUEBLA, PUE.",
    "09/10/2026",
    "03:19",
    "O",
    estimated="LUNES 12 DE OCTUBRE DEL 2026",
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


@tagged("post_install", "-at_install")
class TestTresGuerrasTracking(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Tres Guerras",
                "product_id": cls.env["product.product"]
                .create({"name": "Freight", "type": "service"})
                .id,
                "tracking_provider": "tresguerras",
                "tracking_notify_user_id": cls.env.user.id,
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Agro customer"})

    def _picking(self, reference):
        return self.env["stock.picking"].create(
            {
                "picking_type_id": self.env.ref("stock.picking_type_out").id,
                "partner_id": self.partner.id,
                "carrier_id": self.carrier.id,
                "carrier_tracking_ref": reference,
            }
        )

    def _answering(self, *responses):
        return patch.object(
            type(self.env["ir.egress"]),
            "request",
            side_effect=[
                response
                if isinstance(response, FakeResponse)
                else FakeResponse(response)
                for response in responses
            ],
        )

    def test_a_home_delivery_reads_into_the_transfer(self):
        picking = self._picking("TOL01583026")
        with self._answering(DELIVERED_HOME) as request:
            picking.action_fetch_carrier_tracking()
        args, kwargs = request.call_args
        self.assertEqual(args, ("GET", TRACKING_URL))
        self.assertEqual(kwargs["params"], {"rastreo": "TOL01583026"})
        self.assertEqual(picking.carrier_tracking_state, "delivered")
        self.assertEqual(picking.carrier_delivery_kind, "home")
        self.assertEqual(picking.carrier_status_code, "07")
        self.assertEqual(picking.carrier_status_branch, "IGUALA, GRO.")
        # Mexico City keeps UTC-6 all year
        self.assertEqual(picking.date_carrier_status, datetime(2026, 10, 8, 22, 9))
        self.assertEqual(picking.carrier_received_by, "Recipient")
        self.assertFalse(picking.carrier_tracking_error)
        self.assertEqual(len(picking.activity_ids), 1, "an open transfer to validate")
        self.assertEqual(picking.activity_ids.user_id, self.env.user)

    def test_a_pickup_waiting_at_the_branch_is_at_destination(self):
        picking = self._picking("TOL01583030")
        with self._answering(AT_OCURRE):
            picking.action_fetch_carrier_tracking()
        self.assertEqual(picking.carrier_tracking_state, "at_destination")
        self.assertEqual(picking.carrier_delivery_kind, "pickup")
        self.assertFalse(picking.activity_ids)

    def test_transfers_that_share_a_number_take_one_call(self):
        pickings = self._picking("TOL01583030") | self._picking("TOL01583030")
        pickings |= self._picking("TOL01583030")
        with self._answering(IN_TRANSIT) as request:
            pickings.action_fetch_carrier_tracking()
        self.assertEqual(request.call_count, 1)
        self.assertEqual(set(pickings.mapped("carrier_tracking_state")), {"in_transit"})

    def test_a_failed_read_keeps_the_last_status_and_says_why(self):
        picking = self._picking("TOL01584642")
        with self._answering(IN_TRANSIT, FakeResponse({}, status_code=500)):
            picking.action_fetch_carrier_tracking()
            picking.action_fetch_carrier_tracking()
        self.assertEqual(picking.carrier_tracking_state, "in_transit")
        self.assertIn("HTTP 500", picking.carrier_tracking_error)

    def test_the_same_event_twice_posts_nothing_new(self):
        picking = self._picking("TOL01583026")
        with self._answering(DELIVERED_HOME, DELIVERED_HOME):
            picking.action_fetch_carrier_tracking()
            messages = len(picking.message_ids)
            picking.action_fetch_carrier_tracking()
        self.assertEqual(len(picking.message_ids), messages)
        self.assertEqual(len(picking.activity_ids), 1)

    def test_an_unknown_code_or_date_is_kept_as_other(self):
        odd = _answer("99", "EVENTO NUEVO", "TOLUCA", "sin fecha", "", "S")
        picking = self._picking("TOL01583026")
        with self._answering(odd):
            picking.action_fetch_carrier_tracking()
        self.assertEqual(picking.carrier_tracking_state, "other")
        self.assertFalse(picking.date_carrier_status)
        self.assertEqual(picking.carrier_status_text, "EVENTO NUEVO")

    def test_the_schedule_reads_only_open_recent_numbers(self):
        current = self._picking("TOL01584640")
        delivered = self._picking("TOL01583026")
        delivered.write({"carrier_tracking_state": "delivered"})
        cancelled = self._picking("TOL01583031")
        cancelled.action_cancel()
        old = self._picking("TOL01583040")
        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                "UPDATE stock_picking SET create_date = %s WHERE id = %s",
                fields.Datetime.now() - timedelta(days=60),
                old.id,
            )
        )
        old.invalidate_recordset(["create_date"])
        with self._answering(IN_TRANSIT) as request:
            self.env["stock.picking"]._cron_fetch_carrier_tracking()
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.kwargs["params"], {"rastreo": "TOL01584640"})
        self.assertEqual(current.carrier_tracking_state, "in_transit")
