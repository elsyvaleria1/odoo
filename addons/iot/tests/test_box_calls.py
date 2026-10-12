from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged

CALLS = {
    "/iot/box/update_certificate_status": lambda identifier: {
        "identifier": identifier,
        "ssl_certificate_end_date": "2099-01-01 00:00:00",
    },
    "/iot/box/webrtc_answer": lambda identifier: {
        "iot_box_identifier": identifier,
        "answer": {"sdp": "v=0"},
    },
    "/iot/box/send_websocket": lambda identifier: {
        "session_id": "a-session",
        "iot_box_identifier": identifier,
        "device_identifier": identifier,
        "status": "success",
    },
}


@tagged("post_install", "-at_install")
class TestBoxCalls(HttpCase):
    def _new_box(self, identifier):
        return (
            self.env["iot.box"]
            .sudo()
            .create({"name": identifier, "identifier": identifier, "ip": "10.0.0.8"})
        )

    def _call(self, route, identifier, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = self.url_open(
            route,
            data=json_dumps({"params": CALLS[route](identifier)}),
            headers=headers,
        )
        answer = response.json()
        error = answer.get("error") or {}
        return (
            response.status_code,
            answer.get("result"),
            error.get("code"),
            (error.get("data") or {}).get("name"),
        )

    def _certificate_date(self, box):
        box.invalidate_recordset(["ssl_certificate_end_date"])
        return box.ssl_certificate_end_date

    def test_a_box_that_sends_no_token_is_heard(self):
        box = self._new_box("calls-plain")
        status, result, error, _name = self._call(
            "/iot/box/update_certificate_status", "calls-plain"
        )
        self.assertEqual((status, result, error), (200, None, None))
        self.assertTrue(self._certificate_date(box))

    def test_a_box_presenting_its_own_token_is_heard(self):
        box = self._new_box("calls-own")
        self._call("/iot/box/update_certificate_status", "calls-own", box.token)
        self.assertTrue(self._certificate_date(box))

    def test_a_box_presenting_another_token_changes_nothing(self):
        box = self._new_box("calls-other")
        _status, _result, _code, error = self._call(
            "/iot/box/update_certificate_status", "calls-other", "not-the-box-token"
        )
        self.assertEqual(error, "werkzeug.exceptions.Unauthorized")
        self.assertFalse(self._certificate_date(box), "a wrong token was heard")

    def test_an_unknown_box_is_answered_as_a_known_one(self):
        self._new_box("calls-known")
        for route in CALLS:
            for token in (None, "not-the-box-token"):
                with self.subTest(route=route, token=token):
                    self.assertEqual(
                        self._call(route, "calls-unknown", token),
                        self._call(route, "calls-known", token),
                        "the answer tells a stranger whether the box exists",
                    )

    def test_an_unverified_box_is_reported_once_per_route(self):
        self._new_box("calls-reported")
        with self.assertLogs("odoo.addons.iot.models.iot_box", "WARNING") as logs:
            for _ in range(3):
                self._call("/iot/box/update_certificate_status", "calls-reported")
        reports = [line for line in logs.output if "calls-reported" in line]
        self.assertEqual(len(reports), 1, logs.output)
        self.assertIn("/iot/box/update_certificate_status", reports[0])
