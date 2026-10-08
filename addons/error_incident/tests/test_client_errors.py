from unittest.mock import patch

from odoo.db import db_connect
from odoo.libs.json import dumps as json_dumps
from odoo.libs.sourcemap import encode_vlq
from odoo.tests.common import HttpCase, TransactionCase, new_test_user, tagged
from odoo.tools import SQL

from odoo.addons.error_incident.controllers import main as controllers
from odoo.addons.error_incident.models.error_incident import client_capture_payload
from odoo.addons.error_incident.tools.client_errors import parse_frames, split_head

PROBE = "layout/error_incident/static/src/probe.js"
OWL = "layout/web/static/lib/owl/owl.js"


def _source_map(failing_line="    const id = record.data.id;", at=10):
    probe = ["// probe"] * at + [failing_line]
    # Generated line 0: columns 0-99 are owl (a library), 100 on the probe.
    mappings = ",".join([encode_vlq(0, 1, 3, 0), encode_vlq(100, -1, at - 3, 4)])
    return json_dumps(
        {
            "version": 3,
            "sources": [PROBE, OWL],
            "sourcesContent": ["\n".join(probe), "a\nb\nc\nowl internals"],
            "names": [],
            "mappings": mappings,
        }
    )


class ClientErrorCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.addClassCleanup(cls._forget_probe_bundles)

    @classmethod
    def _forget_probe_bundles(cls):
        # the asset pipeline commits a bundle beside the test transaction, so
        # its rows outlive the rollback: drop them the same way
        with db_connect(cls.env.cr.dbname).cursor() as cr:
            cr.execute(
                SQL(
                    "DELETE FROM ir_attachment WHERE url LIKE %s",
                    "/web/assets/esm/%/error_incident.%",
                )
            )
            cr.commit()

    def _bundle(self, name="error_incident.probe", **kwargs):
        return self.env["ir.qweb"]._save_esm_attachment(
            name, "/* minified */", sourcemap=_source_map(**kwargs)
        )

    def _stack(self, url, message="Cannot read properties of undefined (reading 'id')"):
        return (
            f"TypeError: {message}\n"
            f"    at t (http://127.0.0.1:8069{url}:1:5)\n"
            f"    at Probe.onClick (http://127.0.0.1:8069{url}:1:150)\n"
            f"    at r (http://127.0.0.1:8069{url}:1:7)"
        )

    def _payload(self, stack):
        return client_capture_payload(self.env, stack, user_id=self.env.uid)


@tagged("post_install", "-at_install")
class TestClientErrors(ClientErrorCase):
    def test_the_head_names_the_type_and_the_message(self):
        self.assertEqual(
            split_head("TypeError: x is null\n at f"), ("TypeError", "x is null")
        )
        self.assertEqual(split_head("Script error."), ("Error", "Script error."))

    def test_frames_read_in_both_dialects_and_stop_at_the_cause(self):
        stack = (
            "Error: outer\n"
            "    at A.b (http://h/x.js:3:9)\n"
            "c@http://h/y.js:4:2\n"
            "\n\nCaused by: Error: inner\n"
            "    at d (http://h/z.js:1:1)"
        )
        self.assertEqual(
            [(f.function, f.url, f.line, f.column) for f in parse_frames(stack)],
            [("A.b", "http://h/x.js", 3, 9), ("c", "http://h/y.js", 4, 2)],
        )

    def test_the_origin_is_our_innermost_frame_through_the_source_map(self):
        payload = self._payload(self._stack(self._bundle()))
        self.assertEqual(payload["source"], "client")
        self.assertEqual(payload["exception_type"], "TypeError")
        self.assertEqual(payload["origin_module"], "error_incident")
        self.assertEqual(payload["origin_path"], "static/src/probe.js")
        self.assertEqual(payload["origin_line"], 11)
        self.assertEqual(payload["origin_function"], "onClick")
        self.assertEqual(payload["title"], "TypeError in onClick (error_incident)")
        self.assertIn(
            "at Probe.onClick (error_incident/static/src/probe.js:11)",
            payload["traceback"],
        )

    def test_the_failing_line_moving_is_the_same_incident(self):
        here = self._payload(self._stack(self._bundle()))
        moved = self._payload(self._stack(self._bundle("error_incident.moved", at=40)))
        self.assertEqual(here["fingerprint"], moved["fingerprint"])

    def test_another_failing_line_is_another_incident(self):
        here = self._payload(self._stack(self._bundle()))
        other = self._payload(
            self._stack(
                self._bundle("error_incident.other", failing_line="return record.id;")
            )
        )
        self.assertNotEqual(here["fingerprint"], other["fingerprint"])

    def test_without_a_map_the_message_identifies_it_less_its_data(self):
        url = "/web/assets/esm/0000/nowhere.esm.js"
        first = self._payload(self._stack(url, "Record 12 'Acme' is gone"))
        second = self._payload(self._stack(url, "Record 345 'Other' is gone"))
        self.assertEqual(first["origin_module"], "")
        self.assertEqual(first["fingerprint"], second["fingerprint"])

    def test_a_file_served_as_is_is_read_from_the_module(self):
        stack = (
            "TypeError: boom\n"
            "    at x (http://h/error_incident/static/src/incident_words.js:10:3)"
        )
        payload = self._payload(stack)
        self.assertEqual(payload["origin_path"], "static/src/incident_words.js")
        self.assertEqual(payload["origin_line"], 10)


@tagged("post_install", "-at_install")
class TestReportRoute(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        new_test_user(cls.env, "report.employee", groups="base.group_user")
        new_test_user(cls.env, "report.portal", groups="base.group_portal")
        cls.stack = "TypeError: boom\n    at x (http://h/error_incident/static/src/incident_words.js:10:3)"

    def setUp(self):
        super().setUp()
        controllers._reports.clear()
        self.addCleanup(controllers._reports.clear)

    def _report(self, login, **params):
        self.authenticate(login, login)
        return self.call_jsonrpc("/error_incident/report", params)

    def test_a_browser_error_becomes_the_users_incident(self):
        answer = self._report("report.employee", stack=self.stack, location="/odoo/x")
        self.assertEqual(answer["state"], "found")
        self.assertEqual(answer["step"], "recorded")
        occurrence = self.env["error.occurrence"].search(
            [("occurrence_ref", "=", answer["occurrence"])]
        )
        self.assertEqual(occurrence.incident_id.id, answer["incident"])
        self.assertEqual(occurrence.source, "client")
        self.assertEqual(occurrence.location, "/odoo/x")
        self.assertEqual(occurrence.user_id.login, "report.employee")

    def test_the_same_error_again_counts_on_the_same_incident(self):
        first = self._report("report.employee", stack=self.stack)
        second = self._report("report.employee", stack=self.stack)
        self.assertEqual(first["incident"], second["incident"])
        self.assertEqual(second["details"]["count"], 2)

    def test_a_portal_user_is_not_answered(self):
        self.assertEqual(
            self._report("report.portal", stack=self.stack), {"state": "unavailable"}
        )

    def test_a_stack_that_is_not_text_is_refused(self):
        self.assertEqual(
            self._report("report.employee", stack={"x": 1}), {"state": "unavailable"}
        )

    def test_a_flood_is_limited(self):
        with patch.object(controllers._reports, "limit", 2):
            states = [
                self._report("report.employee", stack=self.stack)["state"]
                for _ in range(3)
            ]
        self.assertEqual(states, ["found", "found", "limited"])
