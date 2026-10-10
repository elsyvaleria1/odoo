from unittest.mock import patch

from lxml import html

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, new_test_user, tagged

from .test_tresguerras_tracking import FakeResponse

REFERENCE_A = "TST00000001"
REFERENCE_B = "TST00000002"
DOCUMENT_URL = "https://intranet.tresguerras.com.mx/test/receipt.pdf"


def _response(reference=REFERENCE_A, code="03", text="Shipment in transit"):
    """Build a synthetic carrier response without shipment or customer data."""
    event = {
        "estadoembarque": code,
        "estado": text,
        "sucursal": "Test destination",
        "fecha_corta": "05/01/2026",
        "hora": "03:04",
        "recibio": "Test recipient" if code == "07" else "",
    }
    return {
        "Respuesta": {
            "Error": "",
            "ultimo_estado": event.copy(),
            "estados": {"item": [event]},
            "detalle": {
                "item": {
                    "TALON": reference,
                    "BANDERA_EAD": "S",
                    "entrega_estimada": "Test estimate",
                    "ORIGEN": "Test origin",
                    "DESTINO": "Test destination",
                    "PESO": "12.50",
                    "PIEZAS": "2",
                    "FECHA_DE_EMBARQUE": "04/01/2026",
                },
            },
            "servicio": "Test home delivery",
        },
    }


@tagged("post_install", "-at_install")
class TestTresGuerrasDetails(TransactionCase):
    """Shipment snapshots, document links and access through the tracking action."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        product = cls.env["product.product"].create(
            {"name": "Test parcel freight", "type": "service"}
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Test Tres Guerras",
                "product_id": product.id,
                "tracking_provider": "tresguerras",
                "tracking_notify_user_id": cls.env.user.id,
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Test recipient"})

    def _picking(self, reference=REFERENCE_A):
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

    def test_history_is_chronological_with_utc_dates_and_shipment_details(self):
        """All movements survive normalization in chronological order."""
        response = _response(code="07")
        movements = response["Respuesta"]["estados"]["item"]
        movements.append(
            movements[0]
            | {
                "estadoembarque": "01",
                "estado": "Test shipment documented",
                "fecha_corta": "04/01/2026",
                "hora": "23:10",
                "recibio": "",
            }
        )
        picking = self._picking()
        with self._answering(response):
            picking.action_fetch_carrier_tracking()
        details = picking.carrier_tracking_details[REFERENCE_A]
        self.assertEqual([event["code"] for event in details["events"]], ["01", "07"])
        self.assertEqual(details["events"][0]["date"], "2026-01-05 05:10:00")
        self.assertEqual(details["events"][1]["date"], "2026-01-05 09:04:00")
        self.assertEqual(details["date"], "2026-01-05 09:04:00")
        self.assertEqual(details["events"][1]["received_by"], "Test recipient")
        self.assertEqual(
            details["shipment"],
            {
                "service": "Test home delivery",
                "origin": "Test origin",
                "destination": "Test destination",
                "weight": "12.50",
                "pieces": "2",
                "shipped_on": "04/01/2026",
            },
        )
        self.assertNotEqual(picking.state, "done")

    def test_singleton_history_and_list_details_need_no_documents(self):
        """The carrier's collection variants render without evidence links."""
        response = _response()
        answer = response["Respuesta"]
        answer["estados"]["item"] = answer["estados"]["item"][0]
        answer["detalle"]["item"] = [answer["detalle"]["item"]]
        picking = self._picking()
        with self._answering(response):
            picking.action_fetch_carrier_tracking()
        details = picking.carrier_tracking_details[REFERENCE_A]
        self.assertEqual(len(details["events"]), 1)
        self.assertFalse(details["documents"])
        rendered = html.fromstring(picking.carrier_tracking_details_html)
        self.assertFalse(rendered.xpath(".//a"))
        self.assertIn("Shipment in transit", rendered.text_content())

    def test_only_official_document_urls_survive_and_http_is_upgraded(self):
        """Unsafe schemes, credentials and lookalike hosts never become links."""
        response = _response()
        response["Respuesta"]["evidencia"] = {
            "acuse": {
                "PDF": {
                    "url": [
                        DOCUMENT_URL.replace("https:", "http:") + "#preview",
                        DOCUMENT_URL,
                        "javascript:alert(1)",
                        "https://intranet.tresguerras.com.mx.example.org/a.pdf",
                        "https://intranet.tresguerras.com.mx@evil.example/a.pdf",
                        "https://user:password@intranet.tresguerras.com.mx/a.pdf",
                        "https://intranet.tresguerras.com.mx:8080/a.pdf",
                        "https://intranet.tresguerras.com.mx\\@evil.example/a.pdf",
                        "https://intranet.tresguerras.com.mx/a\nb.pdf",
                    ],
                },
            },
        }
        picking = self._picking()
        with self._answering(response):
            picking.action_fetch_carrier_tracking()
        self.assertEqual(
            picking.carrier_tracking_details[REFERENCE_A]["documents"],
            [{"kind": "receipt", "format": "PDF", "url": DOCUMENT_URL}],
        )
        rendered = html.fromstring(picking.carrier_tracking_details_html)
        self.assertEqual(rendered.xpath(".//a/@href"), [DOCUMENT_URL])
        self.assertFalse(rendered.xpath(".//img | .//iframe"))

    def test_remote_text_is_escaped_and_stored_document_links_are_rechecked(self):
        """Neither provider text nor an unsafe stored URL injects active HTML."""
        payload = '<script>alert("test")</script><img src=x onerror="alert(1)">'
        response = _response(text=payload)
        response["Respuesta"]["detalle"]["item"]["ORIGEN"] = payload
        picking = self._picking()
        with self._answering(response):
            picking.action_fetch_carrier_tracking()
        details = picking.carrier_tracking_details
        details[REFERENCE_A]["documents"] = [
            {"kind": "evidence", "format": "IMG", "url": "javascript:alert(1)"},
            {"kind": "evidence", "format": "IMG", "url": "https://evil.example/x"},
        ]
        picking.carrier_tracking_details = details
        rendered = html.fromstring(picking.carrier_tracking_details_html)
        self.assertFalse(rendered.xpath(".//script | .//img | .//a"))
        self.assertIn(payload, rendered.text_content())

    def test_history_display_follows_the_viewers_timezone(self):
        """Reading the same snapshot in another zone recomputes its display."""
        picking = self._picking()
        with self._answering(_response()):
            picking.action_fetch_carrier_tracking()
        mexico = picking.with_context(lang="en_US", tz="America/Mexico_City")
        utc = picking.with_context(lang="en_US", tz="UTC")
        mexico_dates = html.fromstring(mexico.carrier_tracking_details_html).xpath(
            ".//tbody/tr/td[1]/text()"
        )
        utc_dates = html.fromstring(utc.carrier_tracking_details_html).xpath(
            ".//tbody/tr/td[1]/text()"
        )
        self.assertEqual(len(mexico_dates), 1)
        self.assertEqual(len(utc_dates), 1)
        self.assertNotEqual(mexico_dates, utc_dates)
        self.assertEqual(mexico.carrier_tracking_details, utc.carrier_tracking_details)

    def test_multiple_references_share_requests_without_early_delivery(self):
        """Every distinct reference is read once across all selected transfers."""
        picking = self._picking(f"{REFERENCE_A}, {REFERENCE_B}, {REFERENCE_A}")
        second = self._picking(REFERENCE_B)
        with self._answering(_response(code="07"), _response(REFERENCE_B)) as request:
            (picking | second).action_fetch_carrier_tracking()
        self.assertEqual(request.call_count, 2)
        self.assertEqual(
            [call.kwargs["params"]["rastreo"] for call in request.call_args_list],
            [REFERENCE_A, REFERENCE_B],
        )
        self.assertEqual(
            set(picking.carrier_tracking_details), {REFERENCE_A, REFERENCE_B}
        )
        self.assertEqual(set(second.carrier_tracking_details), {REFERENCE_B})
        self.assertEqual(picking.carrier_tracking_state, "in_transit")
        self.assertEqual(second.carrier_tracking_state, "in_transit")
        self.assertFalse(picking.activity_ids | second.activity_ids)

    def test_all_references_must_be_delivered_before_notification(self):
        """A multi-guide delivery produces one activity after its last delivery."""
        picking = self._picking(f"{REFERENCE_A},{REFERENCE_B}")
        with self._answering(_response(code="07"), _response(REFERENCE_B)):
            picking.action_fetch_carrier_tracking()
        self.assertFalse(picking.activity_ids)
        with self._answering(_response(code="07"), _response(REFERENCE_B, code="07")):
            picking.action_fetch_carrier_tracking()
        self.assertEqual(picking.carrier_tracking_state, "delivered")
        self.assertEqual(len(picking.activity_ids), 1)
        self.assertNotEqual(picking.state, "done")

    def test_missing_reference_prevents_delivery_and_keeps_successful_snapshot(self):
        """A failed second guide cannot turn the whole shipment into delivered."""
        picking = self._picking(f"{REFERENCE_A},{REFERENCE_B}")
        with self._answering(_response(code="07"), FakeResponse({}, status_code=500)):
            picking.action_fetch_carrier_tracking()
        self.assertNotEqual(picking.carrier_tracking_state, "delivered")
        self.assertFalse(picking.activity_ids)
        self.assertEqual(set(picking.carrier_tracking_details), {REFERENCE_A})
        self.assertIn(REFERENCE_B, picking.carrier_tracking_error)

    def test_a_failed_refresh_preserves_the_previous_history_and_documents(self):
        """An unavailable carrier leaves the last successful snapshot readable."""
        response = _response()
        response["Respuesta"]["evidencia"] = {
            "evidencia": {"IMG": {"url": DOCUMENT_URL}},
        }
        picking = self._picking()
        with self._answering(response):
            picking.action_fetch_carrier_tracking()
        previous = picking.carrier_tracking_details
        with self._answering(FakeResponse({}, status_code=503)):
            picking.action_fetch_carrier_tracking()
        self.assertEqual(picking.carrier_tracking_details, previous)
        self.assertEqual(picking.carrier_tracking_state, "in_transit")
        self.assertIn("HTTP 503", picking.carrier_tracking_error)

    def test_malformed_document_collection_preserves_the_last_successful_snapshot(self):
        """An invalid document container records an error without losing good data."""
        response = _response()
        response["Respuesta"]["evidencia"] = {
            "acuse": {"PDF": {"url": DOCUMENT_URL}},
        }
        picking = self._picking()
        with self._answering(response):
            picking.action_fetch_carrier_tracking()
        previous = picking.carrier_tracking_details
        for malformed in (42, {"unexpected": DOCUMENT_URL}):
            with self.subTest(documents=malformed):
                invalid = _response(code="07")
                invalid["Respuesta"]["evidencia"] = {
                    "evidencia": {"IMG": {"url": malformed}},
                }
                with self._answering(invalid):
                    picking.action_fetch_carrier_tracking()
                self.assertEqual(picking.carrier_tracking_details, previous)
                self.assertEqual(picking.carrier_tracking_state, "in_transit")
                self.assertTrue(picking.carrier_tracking_error)
                self.assertIn(REFERENCE_A, picking.carrier_tracking_error)
                self.assertFalse(picking.activity_ids)

    def test_unchanged_carrier_and_reference_preserve_details_but_new_guide_clears(
        self,
    ):
        """Saving the existing identity retains data; replacing its guide resets it."""
        picking = self._picking()
        with self._answering(_response()):
            picking.action_fetch_carrier_tracking()
        previous = picking.carrier_tracking_details
        picking.write(
            {"carrier_id": self.carrier.id, "carrier_tracking_ref": REFERENCE_A}
        )
        self.assertEqual(picking.carrier_tracking_details, previous)
        picking.carrier_tracking_ref = REFERENCE_B
        self.assertFalse(picking.carrier_tracking_details)
        self.assertNotIn(REFERENCE_A, picking.carrier_tracking_details_html)
        self.assertNotIn("Shipment in transit", picking.carrier_tracking_details_html)
        self.assertFalse(picking.carrier_tracking_state)
        self.assertFalse(picking.date_carrier_tracking_sync)

    def test_switching_carrier_clears_the_previous_providers_snapshot(self):
        """A carrier change must not display the previous carrier's documents."""
        picking = self._picking()
        with self._answering(_response()):
            picking.action_fetch_carrier_tracking()
        other = self.carrier.copy({"name": "Another test carrier"})
        picking.carrier_id = other
        self.assertFalse(picking.carrier_tracking_details)
        self.assertFalse(picking.carrier_status_text)
        self.assertNotIn(REFERENCE_A, picking.carrier_tracking_details_html)
        self.assertNotIn("Shipment in transit", picking.carrier_tracking_details_html)

    def test_a_transfer_copy_does_not_inherit_the_shipment_snapshot(self):
        """Duplicating a transfer cannot attach another shipment's history."""
        picking = self._picking()
        with self._answering(_response()):
            picking.action_fetch_carrier_tracking()
        duplicate = picking.copy()
        self.assertFalse(duplicate.carrier_tracking_details)
        self.assertNotIn(REFERENCE_A, duplicate.carrier_tracking_details_html)
        self.assertNotIn("Shipment in transit", duplicate.carrier_tracking_details_html)
        self.assertFalse(duplicate.carrier_tracking_ref)
        self.assertFalse(duplicate.carrier_tracking_state)

    def test_a_user_without_stock_write_cannot_trigger_the_external_request(self):
        """The public action rejects access before contacting the carrier."""
        user = new_test_user(
            self.env,
            login="tresguerras_without_stock",
            groups="base.group_user",
        )
        picking = self._picking().with_user(user)
        self.assertFalse(picking.has_access("write"))
        with self._answering() as request:
            with self.assertRaises(AccessError):
                picking.action_fetch_carrier_tracking()
        request.assert_not_called()
