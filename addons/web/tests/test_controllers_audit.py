import io
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

from lxml import etree

from odoo import http
from odoo.http._protocols import RoutedMethod
from odoo.libs.json import dumps as json_dumps
from odoo.tests.common import BaseCase, HttpCase, TransactionCase, tagged
from odoo.tools import file_path, mute_logger

from odoo.addons.web.controllers.home import Home


def _skip_unless_web_serves(case: HttpCase, path: str, route: RoutedMethod) -> None:
    # A module installed after web may take the path over (website serves its
    # own / and /robots.txt), and at_install tests wait for every installed
    # module: web's behaviour of the path is then not what is served.
    endpoint, _args = case.env["ir.http"].routing_map().bind("").match(path)
    served = endpoint.original_endpoint
    if served is not route.original_endpoint:
        case.skipTest(f"{path} is served by {served.__module__}.{served.__qualname__}")


@tagged("web_http", "web_controllers_audit")
class TestBarcodeInvalidType(HttpCase):
    def test_barcode_invalid_type_returns_400(self):
        response = self.url_open("/report/barcode/TOTALLY_INVALID_TYPE/testvalue")
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)


@tagged("web_controllers_audit")
class TestBarcodeDimensionClamp(BaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.web.controllers.report import (
            _MAX_BARCODE_DIM,
            _clamp_barcode_dimension,
        )

        cls._clamp = staticmethod(_clamp_barcode_dimension)
        cls._max = _MAX_BARCODE_DIM

    def test_oversized_is_clamped_to_max(self):
        self.assertEqual(self._clamp(100_000, 600), self._max)
        self.assertEqual(self._clamp(self._max + 1, 100), self._max)

    def test_reasonable_value_passes_through(self):
        self.assertEqual(self._clamp(200, 600), 200)
        self.assertEqual(self._clamp("300", 600), 300)

    def test_invalid_or_nonpositive_falls_back_to_default(self):
        self.assertEqual(self._clamp("not-a-number", 600), 600)
        self.assertEqual(self._clamp(None, 100), 100)
        self.assertEqual(self._clamp(0, 600), 600)
        self.assertEqual(self._clamp(-5, 100), 100)


@tagged("web_http", "web_controllers_audit")
class TestBarcodeDimensionClampHttp(HttpCase):
    def test_huge_dimensions_do_not_500(self):
        response = self.url_open(
            "/report/barcode/Code128/hello?width=100000&height=100000"
        )
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

    def test_clamped_single_dimension_renders(self):
        response = self.url_open(
            "/report/barcode/Code128/hello?width=100000&height=100"
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.headers.get("Content-Type"), "image/png")

    def test_oversized_value_rejected(self):
        huge = "A" * 40000
        response = self.url_open(f"/report/barcode/Code128/{huge}")
        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)

    def test_normal_value_still_renders(self):
        response = self.url_open("/report/barcode/Code128/HELLO-12345")
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.headers.get("Content-Type"), "image/png")


@tagged("web_http", "web_controllers_audit")
class TestImageDimensionGuard(HttpCase):
    def test_garbage_width_does_not_500(self):
        response = self.url_open("/web/image/99999999?width=abc&height=xyz")
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.headers.get("Content-Type"), "image/png")


@tagged("web_controllers_audit")
class TestCsvFormulaNeutralization(BaseCase):
    def test_dangerous_leading_chars_are_prefixed(self):
        from odoo.addons.web.controllers.export import CSVExport

        rows = [["=cmd"], ["+cmd"], ["-cmd"], ["@cmd"], ["\t=x"]]
        out = CSVExport().from_data([], ["header"], rows).decode()
        for payload in ("=cmd", "+cmd", "-cmd", "@cmd"):
            self.assertIn(
                f"'{payload}",
                out,
                f"{payload!r} must be apostrophe-prefixed to defuse the formula",
            )

    def test_benign_values_are_not_mangled(self):
        from odoo.addons.web.controllers.export import CSVExport

        out = CSVExport().from_data([], ["header"], [["a=b"], ["safe"]]).decode()
        self.assertIn("a=b", out)
        self.assertNotIn("'a=b", out)
        self.assertNotIn("'safe", out)


@tagged("web_http", "web_controllers_audit")
class TestPivotNegativeInputs(HttpCase):
    def test_export_xlsx_negative_measure_count(self):
        self.authenticate("admin", "admin")
        jdata = {
            "title": "Test",
            "model": "res.partner",
            "measure_count": -5,
            "origin_count": 1,
            "col_group_headers": [],
            "measure_headers": [],
            "origin_headers": [],
            "rows": [],
        }
        response = self.url_open(
            "/web/pivot/export_xlsx",
            data={
                "data": json_dumps(jdata),
                "csrf_token": http.Request.csrf_token(self),
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_export_xlsx_negative_header_width(self):
        self.authenticate("admin", "admin")
        jdata = {
            "title": "Test",
            "model": "res.partner",
            "measure_count": 1,
            "origin_count": 1,
            "col_group_headers": [[{"title": "A", "width": -3, "height": 1}]],
            "measure_headers": [],
            "origin_headers": [],
            "rows": [],
        }
        response = self.url_open(
            "/web/pivot/export_xlsx",
            data={
                "data": json_dumps(jdata),
                "csrf_token": http.Request.csrf_token(self),
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_export_xlsx_huge_indent_is_clamped(self):
        self.authenticate("admin", "admin")
        jdata = {
            "title": "Test",
            "model": "res.partner",
            "measure_count": 1,
            "origin_count": 1,
            "col_group_headers": [],
            "measure_headers": [],
            "origin_headers": [],
            "rows": [{"indent": 400_000_000, "title": "row", "values": []}],
        }
        response = self.url_open(
            "/web/pivot/export_xlsx",
            data={
                "data": json_dumps(jdata),
                "csrf_token": http.Request.csrf_token(self),
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertLess(len(response.content), 1_000_000)


@tagged("web_http", "web_controllers_audit")
class TestWebClientOpenRedirect(HttpCase):
    def test_backslash_redirect_rejected(self):
        self.authenticate("admin", "admin")
        response = self.url_open(
            "/odoo?redirect=%2F%5Cevil.com",
            allow_redirects=False,
        )
        location = response.headers.get("Location", "")
        self.assertNotIn("evil.com", location)

    def test_local_path_redirect_accepted(self):
        self.authenticate("admin", "admin")
        response = self.url_open(
            "/odoo?redirect=/odoo/contacts",
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, HTTPStatus.SEE_OTHER)
        self.assertIn("/odoo/contacts", response.headers.get("Location", ""))


@tagged("web_http", "web_controllers_audit")
class TestCompanyLogoFallback(HttpCase):
    def test_a_failing_lookup_serves_the_odoo_logo(self):
        odoo_logo = Path(file_path("web/static/img/logo.png")).read_bytes()
        with (
            patch(
                "odoo.addons.web.controllers.binary.guess_mimetype",
                side_effect=RuntimeError("simulated"),
            ),
            mute_logger("odoo.addons.web.controllers.binary"),
        ):
            response = self.url_open("/logo?company=1")
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.content, odoo_logo)


@tagged("web_http", "web_controllers_audit")
class TestDatabaseRestoreLogging(HttpCase):
    def test_restore_logs_exception_on_failure(self):
        with (
            patch(
                "odoo.tools.config.configmanager.has_default_admin_password",
                return_value=False,
            ),
            patch("odoo.service.db.check_super"),
            patch(
                "odoo.service.db.restore_db",
                side_effect=Exception("simulated restore error"),
            ),
            self.assertLogs(
                "odoo.addons.web.controllers.database", level="ERROR"
            ) as log_cm,
        ):
            response = self.url_open(
                "/web/database/restore",
                data={
                    "master_pwd": "admin",
                    "name": "test_audit_nonexistent_db",
                    "copy": "false",
                    "neutralize_database": "false",
                },
                files={
                    "backup_file": (
                        "test.zip",
                        io.BytesIO(b"fake content"),
                        "application/zip",
                    )
                },
            )
        self.assertIn("Database restore error", response.text)
        self.assertTrue(
            any("Database restore error" in msg for msg in log_cm.output),
            f"Expected 'Database restore error' in logs, got: {log_cm.output}",
        )


@tagged("web_http", "web_controllers_audit")
class TestExportGroupbyValidation(HttpCase):
    @mute_logger("odoo.addons.web.controllers.export")
    def test_invalid_groupby_field_returns_descriptive_error(self):
        self.authenticate("admin", "admin")
        data = json_dumps(
            {
                "model": "res.partner",
                "fields": [{"name": "name", "label": "Name"}],
                "ids": [],
                "domain": [],
                "import_compat": False,
                "groupby": ["totally_nonexistent_xyz"],
            }
        )
        response = self.url_open(
            "/web/export/xlsx",
            data={"data": data, "csrf_token": http.Request.csrf_token(self)},
        )
        self.assertEqual(response.status_code, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertIn("Unknown groupby fields", response.text)
        self.assertIn("totally_nonexistent_xyz", response.text)


@tagged("web_controllers_audit")
class TestIsLocalUrl(BaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from odoo.addons.web.controllers.utils import _is_local_url

        cls._is_local_url = staticmethod(_is_local_url)

    def test_local_paths_accepted(self):
        self.assertTrue(self._is_local_url("/odoo"))
        self.assertTrue(self._is_local_url("/odoo/contacts"))
        self.assertTrue(self._is_local_url("/web"))
        self.assertTrue(self._is_local_url("/web/login"))

    def test_protocol_relative_rejected(self):
        self.assertFalse(self._is_local_url("//evil.com"))

    def test_backslash_trick_rejected(self):
        self.assertFalse(self._is_local_url("/\\evil.com"))

    def test_absolute_url_rejected(self):
        self.assertFalse(self._is_local_url("https://evil.com"))
        self.assertFalse(self._is_local_url("http://evil.com/odoo"))

    def test_unparseable_url_rejected_rather_than_raising(self):
        for vector in ("http://[", "http://[x", "http://a[b"):
            with self.subTest(vector=vector):
                self.assertFalse(self._is_local_url(vector))

    def test_a_bracket_outside_an_authority_is_an_ordinary_path(self):
        self.assertTrue(self._is_local_url("/["))
        self.assertTrue(self._is_local_url("/a[b"))

    def test_embedded_tab_newline_rejected(self):
        for vector in (
            "/\t\t//evil.com",
            "/\r\r//evil.com",
            "/\n\n//evil.com",
            "/\t/\t/evil.com",
            "\t//evil.com",
        ):
            with self.subTest(vector=vector):
                self.assertFalse(self._is_local_url(vector))

    def test_multiple_leading_slashes_rejected(self):
        self.assertFalse(self._is_local_url("///evil.com"))
        self.assertFalse(self._is_local_url("////evil.com"))

    def test_whitespace_only_rejected(self):
        self.assertFalse(self._is_local_url("\t"))
        self.assertFalse(self._is_local_url("\r\n"))

    def test_empty_and_none_rejected(self):
        self.assertFalse(self._is_local_url(""))
        self.assertFalse(self._is_local_url(None))


@tagged("web_controllers_audit")
class TestJsonHelpers(TransactionCase):
    def test_get_groupby_with_default_group_by(self):
        from odoo.addons.web.controllers.json_helpers import get_groupby

        tree = etree.fromstring(
            '<kanban default_group_by="partner_id"><templates/></kanban>'
        )
        groupby, fields = get_groupby(tree)
        self.assertIsNone(groupby)
        self.assertEqual(fields, ["partner_id"])

    def test_get_groupby_no_default_group_by(self):
        from odoo.addons.web.controllers.json_helpers import get_groupby

        tree = etree.fromstring("<kanban><templates/></kanban>")
        groupby, fields = get_groupby(tree)
        self.assertIsNone(groupby)
        self.assertIsNone(fields)

    def test_get_groupby_explicit_param_overrides_view(self):
        from odoo.addons.web.controllers.json_helpers import get_groupby

        tree = etree.fromstring(
            '<kanban default_group_by="stage_id"><templates/></kanban>'
        )
        groupby, fields = get_groupby(tree, groupby="partner_id,user_id")
        self.assertEqual(groupby, ["partner_id", "user_id"])
        self.assertIsNone(fields)

    def test_get_view_id_and_type_returns_false_for_unset_view(self):
        from odoo.addons.web.controllers.json_helpers import get_view_id_and_type

        action = self.env["ir.actions.act_window"].create(
            {
                "name": "_AuditTest",
                "res_model": "res.partner",
                "view_mode": "list,form",
            }
        )
        view_id, view_type = get_view_id_and_type(action, "list")
        self.assertIs(
            view_id, False, "Must be False (Odoo 'no ID' convention), not None"
        )
        self.assertEqual(view_type, "list")


@tagged("web_http", "web_controllers_audit")
class TestActionLoadEdges(HttpCase):
    def _rpc(self, path, params):
        return self.url_open(
            path,
            headers={"Content-Type": "application/json"},
            data=json_dumps({"params": params}),
        ).json()

    def test_load_with_a_null_id_is_a_missing_action_not_a_type_error(self):
        self.authenticate("admin", "admin")
        with mute_logger("odoo.http"):
            body = self._rpc("/web/action/load", {"action_id": None})
        self.assertIn("error", body)
        self.assertIn("MissingActionError", body["error"]["data"]["name"])

    def test_breadcrumb_of_a_report_action_with_a_record_has_no_res_model(self):
        self.authenticate("admin", "admin")
        report = self.env["ir.actions.report"].search([], limit=1)
        body = self._rpc(
            "/web/action/load_breadcrumbs",
            {"actions": [{"action": report.id, "resId": 1}]},
        )
        self.assertEqual(body["result"], [{"display_name": report.name}])


@tagged("web_http", "web_controllers_audit")
class TestSignFonts(HttpCase):
    def _rpc(self, path):
        return self.url_open(
            path,
            headers={"Content-Type": "application/json"},
            data=json_dumps({"params": {}}),
        ).json()

    def test_unknown_font_is_not_found(self):
        with mute_logger("odoo.http"):
            body = self._rpc("/web/sign/get_fonts/no_such_font.ttf")
        self.assertIn("NotFound", body["error"]["data"]["name"])

    def test_wrong_extension_is_not_found(self):
        with mute_logger("odoo.http"):
            body = self._rpc("/web/sign/get_fonts/__manifest__.py")
        self.assertIn("NotFound", body["error"]["data"]["name"])

    def test_listing_answers_every_sign_font(self):
        body = self._rpc("/web/sign/get_fonts")
        self.assertGreater(len(body["result"]), 0)
        fonts_dir = Path(file_path("web/static/fonts/sign"))
        first = min(
            p.name
            for p in fonts_dir.iterdir()
            if p.suffix in (".ttf", ".otf", ".woff", ".woff2")
        )
        one = self._rpc(f"/web/sign/get_fonts/{first}")
        self.assertEqual(one["result"], body["result"][:1])


@tagged("web_http", "web_controllers_audit")
class TestBaseSetupData(HttpCase):
    def test_pending_users_are_the_internal_ones_that_never_logged_in(self):
        never = self.env["res.users"].create(
            {"name": "Never Logged", "login": "never_logged_audit"}
        )
        self.authenticate("admin", "admin")
        body = self.url_open(
            "/base_setup/data",
            headers={"Content-Type": "application/json"},
            data=json_dumps({"params": {}}),
        ).json()["result"]
        self.assertEqual(body["pending_users"][0], [never.id, never.login])
        self.assertEqual(body["pending_count"], len(body["pending_users"]))
        self.assertGreaterEqual(body["active_users"], body["pending_count"] + 1)
        self.assertEqual(body["action_pending_users"]["res_model"], "res.users")


@tagged("web_controllers_audit")
class TestObservabilityHelpers(BaseCase):
    def test_clamped_metric_rejects_bool_nan_negative_and_oversized(self):
        from odoo.addons.web.controllers.observability import _get_clamped_metric

        self.assertIsNone(_get_clamped_metric(True, 10))
        self.assertIsNone(_get_clamped_metric(float("nan"), 10))
        self.assertIsNone(_get_clamped_metric(-1, 10))
        self.assertIsNone(_get_clamped_metric(11, 10))
        self.assertIsNone(_get_clamped_metric("5", 10))
        self.assertEqual(_get_clamped_metric(5, 10), 5.0)

    def test_capped_str_and_positive_int(self):
        from odoo.addons.web.controllers.observability import (
            _get_capped_str,
            _get_positive_int,
        )

        self.assertEqual(_get_capped_str("abcdef", 3), "abc")
        self.assertEqual(_get_capped_str(42, 3), "")
        self.assertEqual(_get_positive_int(-1), 0)
        self.assertEqual(_get_positive_int(3.9), 3)
        self.assertEqual(_get_positive_int("3"), 0)

    def test_positive_int_stays_inside_a_postgres_integer(self):
        from odoo.addons.web.controllers.observability import _get_positive_int

        self.assertEqual(_get_positive_int(2**31 - 1), 2**31 - 1)
        self.assertEqual(_get_positive_int(2**31), 0)
        self.assertEqual(_get_positive_int(1e300), 0)
        self.assertEqual(_get_positive_int(float("inf")), 0)
        self.assertEqual(_get_positive_int(float("nan")), 0)
        self.assertEqual(_get_positive_int(True), 0)


@tagged("web_controllers_audit")
class TestReportHelpers(BaseCase):
    def test_parse_docids_keeps_digits_only(self):
        from odoo.addons.web.controllers.report import _parse_docids

        self.assertIsNone(_parse_docids(None))
        self.assertIsNone(_parse_docids(""))
        self.assertEqual(_parse_docids("1,x,3"), [1, 3])

    def test_id_list_keeps_positive_ascii_integers_only(self):
        from odoo.addons.web.controllers.utils import parse_id_list

        self.assertEqual(parse_id_list(None), [])
        self.assertEqual(parse_id_list("\u00b2,\u0661,2, 3,0,00,-4,x,"), [2, 3])

    def test_download_url_splits_report_docids_and_query(self):
        from odoo.http import BadRequest

        from odoo.addons.web.controllers.report import ReportController

        parse = ReportController()._parse_report_download_url
        self.assertEqual(
            parse("/report/pdf/base.report_x/1,2?context=%7B%7D", "pdf"),
            ("base.report_x", "1,2", {"context": "{}"}),
        )
        self.assertEqual(
            parse("/report/text/base.report_x?a=1&a=2", "text"),
            ("base.report_x", None, {"a": "1"}),
        )
        with self.assertRaises(BadRequest):
            parse("/report/pdf/base.report_x", "text")


@tagged("web_controllers_audit")
class TestCappedWorksheet(BaseCase):
    def test_write_counts_and_refuses_past_the_cap(self):
        from odoo.http import UnprocessableEntity

        from odoo.addons.web.controllers.pivot import _CappedWorksheet

        class Sheet:
            written = []

            def write(self, *args, **kwargs):
                self.written.append(args)

            def freeze_panes(self, *args):
                return args

        sheet = Sheet()
        capped = _CappedWorksheet(sheet, 2, "t")
        capped.write(0, 0, "a")
        capped.write(0, 1, "b")
        self.assertEqual(capped.cells_written, 2)
        self.assertEqual(capped.freeze_panes(1, 0), (1, 0))
        with self.assertRaises(UnprocessableEntity):
            capped.write(0, 2, "c")
        self.assertEqual(len(sheet.written), 2)


@tagged("web_http", "web_controllers_audit")
class TestReportConverters(HttpCase):
    def test_unknown_converter_is_a_client_error(self):
        self.authenticate("admin", "admin")
        with mute_logger("odoo.http"):
            resp = self.url_open("/report/docx/web.report_irmodulereference/1")
        self.assertEqual(resp.status_code, HTTPStatus.BAD_REQUEST)

    def test_describing_a_mixin_on_the_read_only_route_writes_nothing(self):
        self.authenticate("admin", "admin")
        module = self.env.ref("base.module_base")
        with self.assertNoLogs(
            "odoo.addons.web.reports.report_web_report_irmodulereference",
            level="WARNING",
        ):
            resp = self.url_open(
                f"/report/html/web.report_irmodulereference/{module.id}"
            )
        self.assertEqual(resp.status_code, HTTPStatus.OK)

    def test_text_converter_answers_plain_text(self):
        self.authenticate("admin", "admin")
        resp = self.url_open(
            f"/report/text/web.preview_internalreport/{self.env.company.id}"
        )
        self.assertEqual(resp.status_code, HTTPStatus.OK)
        self.assertEqual(resp.headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(int(resp.headers["Content-Length"]), len(resp.content))


@tagged("web_http", "web_controllers_audit")
class TestUncoveredRoutes(HttpCase):
    def _rpc(self, path, params=None):
        return self.url_open(
            path,
            headers={"Content-Type": "application/json"},
            data=json_dumps({"params": params or {}}),
        ).json()

    def test_robots_disallows_everything_by_default(self):
        _skip_unless_web_serves(self, "/robots.txt", Home.robots)
        resp = self.url_open("/robots.txt")
        self.assertEqual(resp.status_code, HTTPStatus.OK)
        self.assertEqual(resp.headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(resp.text.splitlines(), ["User-agent: *", "Disallow: /"])

    def test_filestore_is_never_served_by_odoo(self):
        with mute_logger("odoo.http"):
            resp = self.url_open("/web/filestore/odoo7f/00/deadbeef")
        self.assertEqual(resp.status_code, HTTPStatus.NOT_FOUND)

    def test_become_promotes_a_system_user_and_nobody_else(self):
        self.authenticate("admin", "admin")
        resp = self.url_open("/web/become", allow_redirects=False)
        self.assertEqual(resp.status_code, HTTPStatus.SEE_OTHER)
        self.assertEqual(self._rpc("/web/session/get_session_info")["result"]["uid"], 1)

        user = self.env["res.users"].create(
            {
                "name": "Plain Internal",
                "login": "plain_internal_audit",
                "password": "plain_internal_audit",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.authenticate("plain_internal_audit", "plain_internal_audit")
        resp = self.url_open("/web/become", allow_redirects=False)
        self.assertEqual(resp.status_code, HTTPStatus.SEE_OTHER)
        self.assertEqual(
            self._rpc("/web/session/get_session_info")["result"]["uid"], user.id
        )

    def test_openapi_document_is_for_system_users_only(self):
        self.authenticate("admin", "admin")
        resp = self.url_open("/web/openapi.json")
        self.assertEqual(resp.status_code, HTTPStatus.OK)
        document = resp.json()
        self.assertEqual(document["info"]["title"], "Odoo HTTP API")
        self.assertIsInstance(document["paths"], dict)

        self.env["res.users"].create(
            {
                "name": "Plain Internal",
                "login": "plain_internal_audit",
                "password": "plain_internal_audit",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.authenticate("plain_internal_audit", "plain_internal_audit")
        with mute_logger("odoo.http"):
            resp = self.url_open("/web/openapi.json")
        self.assertEqual(resp.status_code, HTTPStatus.FORBIDDEN)

    def test_a_gated_door_states_what_it_asks_of_its_caller(self):
        self.authenticate("admin", "admin")
        document = self.url_open("/web/openapi.json").json()
        gated = {
            path: operation
            for path, item in document["paths"].items()
            for operation in item.values()
            if any(
                name.startswith("receiver")
                for requirement in operation.get("security", ())
                for name in requirement
            )
        }
        if not gated:
            self.assertFalse(
                [
                    path
                    for path, item in document["paths"].items()
                    for operation in item.values()
                    if operation.get("x-odoo-auth") == "receiver"
                ],
                "a receiver route is described with no scheme",
            )
            self.skipTest("this database installs no receiver route")
        schemes = document["components"]["securitySchemes"]
        for path, operation in gated.items():
            for requirement in operation["security"]:
                for name in requirement:
                    self.assertIn(name, schemes, f"{path} requires an undefined {name}")

    def test_edit_custom_writes_only_the_owner_s_view(self):
        view = self.env.ref("base.view_partner_form")
        admin = self.env.ref("base.user_admin")
        other = self.env["res.users"].create(
            {
                "name": "Other Internal",
                "login": "other_internal_audit",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        own = self.env["ir.ui.view.custom"].create(
            {"ref_id": view.id, "user_id": admin.id, "arch": "<form/>"}
        )
        theirs = self.env["ir.ui.view.custom"].create(
            {"ref_id": view.id, "user_id": other.id, "arch": "<form/>"}
        )
        self.authenticate("admin", "admin")
        body = self._rpc(
            "/web/view/edit_custom",
            {"custom_id": own.id, "arch": "<form><sheet/></form>"},
        )
        self.assertEqual(body["result"], {"result": True})
        self.assertEqual(own.arch, "<form><sheet/></form>")
        with mute_logger("odoo.http"):
            body = self._rpc(
                "/web/view/edit_custom", {"custom_id": theirs.id, "arch": "<form/>"}
            )
        self.assertIn("AccessError", body["error"]["data"]["name"])

    def test_scoped_app_icon_is_rasterised_with_padding(self):
        resp = self.url_open("/scoped_app_icon_png?app_id=web")
        self.assertEqual(resp.status_code, HTTPStatus.OK)
        self.assertEqual(resp.headers["Content-Type"], "image/png")
        self.assertTrue(resp.content.startswith(b"\x89PNG"))

    def test_esm_library_url_without_an_attachment_is_not_found(self):
        with mute_logger("odoo.http"):
            resp = self.url_open("/web/assets/lib/nope/vendor/thing.js")
        self.assertEqual(resp.status_code, HTTPStatus.NOT_FOUND)


@tagged("web_controllers_audit")
class TestGroupedXlsxHeaderTolerance(BaseCase):
    def test_a_field_without_a_type_gets_the_plain_bold_header(self):
        from unittest.mock import MagicMock

        from odoo.addons.web.controllers.export_writers import GroupExportXlsxWriter

        writer = GroupExportXlsxWriter.__new__(GroupExportXlsxWriter)
        writer.fields = [{"name": "name"}, {"name": "id"}]
        writer.monetary_decimal_places = 2
        writer.header_bold_style = "bold"
        writer.header_bold_style_float = "float"
        writer.header_bold_style_monetary = "monetary"
        writer.write = MagicMock()
        group = MagicMock(count=2, aggregated_values={"id": 7})
        self.assertEqual(writer._write_group_header(0, 0, "G", group), (1, 0))
        writer.write.assert_any_call(0, 1, "7", "bold")


@tagged("web_http", "web_controllers_audit")
class TestMalformedInputIsNotAServerError(HttpCase):
    def _rpc(self, path, params):
        return self.url_open(
            path,
            headers={"Content-Type": "application/json"},
            data=json_dumps({"params": params}),
        ).json()

    def test_a_js_error_beacon_line_past_int4_is_recorded(self):
        before = self.env["web.js.error"].search_count([])
        resp = self.url_open(
            "/web/observability/js_error",
            data=json_dumps({"message": "overflow probe", "line": 2**40, "col": 1e300}),
        )
        self.assertEqual(resp.status_code, HTTPStatus.NO_CONTENT)
        self.assertEqual(self.env["web.js.error"].search_count([]), before + 1)

    def test_a_non_ascii_digit_in_report_docids_is_not_a_server_error(self):
        self.authenticate("admin", "admin")
        resp = self.url_open("/report/html/web.report_irmodulereference/%C2%B2")
        self.assertEqual(resp.status_code, HTTPStatus.OK)

    def test_an_unknown_report_is_not_found(self):
        self.authenticate("admin", "admin")
        with mute_logger("odoo.http"):
            resp = self.url_open("/report/html/web.no_such_report/1")
        self.assertEqual(resp.status_code, HTTPStatus.NOT_FOUND)

    def test_a_non_ascii_digit_in_vcard_ids_resolves_no_partner(self):
        self.authenticate("admin", "admin")
        with mute_logger("odoo.http"):
            resp = self.url_open("/web/partner/vcard?partner_ids=%C2%B2")
        self.assertEqual(resp.status_code, HTTPStatus.NOT_FOUND)

    def test_scoped_assets_ignore_an_assets_params_query_argument(self):
        self.authenticate("admin", "admin")
        url = "/web/assets/scope/web/any/web.assets_unit_tests_setup.min.css"
        plain = self.url_open(url, allow_redirects=False)
        forged = self.url_open(f"{url}?assets_params=x", allow_redirects=False)
        self.assertEqual(plain.status_code, HTTPStatus.OK)
        self.assertEqual(forged.status_code, HTTPStatus.OK)
        self.assertEqual(forged.content, plain.content)

    def test_translations_answers_are_revalidated(self):
        resp = self.url_open("/web/webclient/translations?hash=&lang=en_US")
        self.assertEqual(resp.status_code, HTTPStatus.OK)
        self.assertEqual(resp.headers["Cache-Control"], "no-cache")
        current = resp.json()["hash"]
        again = self.url_open(f"/web/webclient/translations?hash={current}&lang=en_US")
        self.assertEqual(again.json(), {"lang": "en_US", "hash": current})
        self.assertEqual(again.headers["Cache-Control"], "no-cache")

    def test_an_any_asset_url_is_not_cached_as_immutable(self):
        any_css = self.url_open("/web/assets/any/web.assets_web.min.css")
        self.assertEqual(any_css.status_code, HTTPStatus.OK)
        self.assertNotIn("immutable", any_css.headers["Cache-Control"])

        [versioned] = self.env["ir.qweb"]._get_asset_links(
            "web.assets_web", css=True, js=False
        )
        pinned = self.url_open(versioned, allow_redirects=False)
        self.assertEqual(pinned.status_code, HTTPStatus.OK)
        self.assertIn("immutable", pinned.headers["Cache-Control"])

    def test_a_breadcrumb_on_an_unknown_model_fails_alone(self):
        self.authenticate("admin", "admin")
        partner = self.env["res.partner"].create({"name": "Crumb"})
        body = self._rpc(
            "/web/action/load_breadcrumbs",
            {
                "actions": [
                    {"model": "res.partner", "resId": partner.id},
                    {"model": "no.such.model", "resId": 1},
                ]
            },
        )
        first, second = body["result"]
        self.assertEqual(first, {"display_name": "Crumb"})
        self.assertIn("no.such.model", second["error"])


@tagged("web_http", "web_controllers_audit")
class TestUploadAttachment(HttpCase):
    def _upload(self, res_id, names):
        return self.url_open(
            "/web/binary/upload_attachment",
            data={
                "model": "res.partner",
                "id": res_id,
                "csrf_token": http.Request.csrf_token(self),
            },
            files=[
                ("ufile", (name, io.BytesIO(b"content"), "text/plain"))
                for name in names
            ],
        )

    def test_a_failing_file_does_not_undo_the_files_before_it(self):
        self.authenticate("admin", "admin")
        partner = self.env["res.partner"].create({"name": "Uploader"})
        Attachment = type(self.env["ir.attachment"])
        original = Attachment._post_add_create

        def post_add_create(records, **kwargs):
            if records.name == "poison.txt":
                records.env.cr.execute("SELECT 1 / 0")
            return original(records, **kwargs)

        with (
            patch.object(Attachment, "_post_add_create", post_add_create),
            mute_logger("odoo.addons.web.controllers.binary", "odoo.db.cursor"),
        ):
            results = self._upload(
                partner.id, ["kept.txt", "poison.txt", "after.txt"]
            ).json()
        self.assertEqual([bool(r.get("id")) for r in results], [True, False, True])
        kept = self.env["ir.attachment"].browse([results[0]["id"], results[2]["id"]])
        self.assertEqual(kept.exists().mapped("name"), ["kept.txt", "after.txt"])

    def test_an_unparsable_record_id_is_a_bad_request(self):
        self.authenticate("admin", "admin")
        with mute_logger("odoo.http"):
            resp = self._upload("undefined", ["a.txt"])
        self.assertEqual(resp.status_code, HTTPStatus.BAD_REQUEST)


@tagged("web_http", "web_controllers_audit")
class TestBaseSetupPendingCount(HttpCase):
    def test_pending_count_counts_past_the_ten_listed(self):
        self.env["res.users"].create(
            [{"name": f"Pending {i}", "login": f"pending_count_{i}"} for i in range(11)]
        )
        self.authenticate("admin", "admin")
        body = self.url_open(
            "/base_setup/data",
            headers={"Content-Type": "application/json"},
            data=json_dumps({"params": {}}),
        ).json()["result"]
        self.assertEqual(len(body["pending_users"]), 10)
        self.assertGreaterEqual(body["pending_count"], 11)
        self.assertEqual(
            body["pending_count"],
            self.env["res.users"].search_count(
                [("share", "=", False), ("log_ids", "=", False)]
            ),
        )


@tagged("web_controllers_audit")
class TestControllerIntrospection(BaseCase):
    def test_every_web_controller_annotation_resolves(self):
        import annotationlib
        import inspect
        import sys

        prefix = "odoo.addons.web.controllers."
        modules = [m for n, m in list(sys.modules.items()) if n.startswith(prefix)]
        self.assertTrue(modules)
        for module in modules:
            for cls in vars(module).values():
                if not inspect.isclass(cls) or cls.__module__ != module.__name__:
                    continue
                for name, member in vars(cls).items():
                    if inspect.isfunction(member):
                        with self.subTest(method=f"{cls.__qualname__}.{name}"):
                            annotationlib.get_annotations(member)

    def test_a_call_kw_url_naming_its_target_leaves_the_thread_untagged(self):
        import threading

        from odoo.addons.web.controllers.dataset import _tag_thread_with_rpc_target

        thread = threading.current_thread()
        with patch.object(thread, "rpc_model_method", "", create=True):
            _tag_thread_with_rpc_target("res.partner", "read", "res.partner/read")
            self.assertEqual(thread.rpc_model_method, "")
            _tag_thread_with_rpc_target("res.partner", "read", "res.users/unlink")
            self.assertEqual(thread.rpc_model_method, "res.partner.read")


@tagged("web_http", "web_controllers_audit")
class TestMalformedRequestsAreClientErrors(HttpCase):
    NAVIGATE = {
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
    }

    def setUp(self):
        super().setUp()
        self.authenticate("admin", "admin")

    def _rpc(self, path, params):
        return self.url_open(
            path,
            headers={"Content-Type": "application/json"},
            data=json_dumps({"params": params}),
        ).json()

    def test_a_json_listing_refuses_a_negative_window_and_an_unknown_groupby(self):
        self.env["ir.config_parameter"].sudo().set_param("web.json.enabled", "1")
        url = "/json/1/action-base.action_partner_form"
        with mute_logger("odoo.http"):
            for query in (
                "limit=-1&offset=0",
                "limit=5&offset=-3",
                "limit=5&offset=0&groupby=no_such_field",
            ):
                with self.subTest(query=query):
                    resp = self.url_open(
                        f"{url}?{query}", headers=self.NAVIGATE, allow_redirects=False
                    )
                    self.assertEqual(resp.status_code, HTTPStatus.BAD_REQUEST)
        resp = self.url_open(
            f"{url}?limit=5&offset=0", headers=self.NAVIGATE, allow_redirects=False
        )
        self.assertEqual(resp.status_code, HTTPStatus.OK)

    def test_a_pivot_export_payload_that_is_not_a_json_object_is_refused(self):
        with mute_logger("odoo.http"):
            for payload in ("not json", "[1, 2]"):
                with self.subTest(payload=payload):
                    resp = self.url_open(
                        "/web/pivot/export_xlsx",
                        data={
                            "data": payload,
                            "csrf_token": http.Request.csrf_token(self),
                        },
                    )
                    self.assertEqual(resp.status_code, HTTPStatus.BAD_REQUEST)

    def test_model_definitions_want_a_list_of_names(self):
        with mute_logger("odoo.http"):
            for names in ("not json", '"res.partner"', "[1]"):
                with self.subTest(names=names):
                    resp = self.url_open(
                        "/web/model/get_definitions",
                        data={
                            "model_names": names,
                            "csrf_token": http.Request.csrf_token(self),
                        },
                    )
                    self.assertEqual(resp.status_code, HTTPStatus.BAD_REQUEST)

    def test_malformed_call_kw_params_are_a_json_rpc_bad_request(self):
        with mute_logger("odoo.http"):
            for params in ([1, 2], {"model": ["x"], "method": "read"}):
                with self.subTest(params=params):
                    error = self._rpc("/web/dataset/call_kw", params)["error"]
                    self.assertEqual(error["code"], 400)

    def test_a_failed_report_download_answers_a_server_error_status(self):
        with mute_logger("odoo.addons.web.controllers.report", "odoo.http"):
            resp = self.url_open(
                "/report/download",
                data={"data": "not json", "csrf_token": http.Request.csrf_token(self)},
            )
        self.assertEqual(resp.status_code, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertIn("Odoo Server Error", resp.text)

    def test_an_import_compatible_relation_is_named_through_the_relation(self):
        entries = self._rpc(
            "/web/export/get_fields",
            {
                "model": "res.partner.bank.account",
                "domain": [],
                "prefix": "main_bank_account_id",
                "parent_name": "Bank",
                "import_compat": True,
                "parent_field_type": "many2one",
                "exclude": [],
            },
        )["result"]
        values = {entry["id"]: entry["value"] for entry in entries}
        self.assertEqual(
            values,
            {
                "main_bank_account_id/acc_number": "main_bank_account_id",
                "main_bank_account_id/id": "main_bank_account_id/id",
            },
        )

    def test_a_repeated_vcard_id_downloads_one_card(self):
        partner = self.env["res.partner"].create({"name": "Card Holder"})
        resp = self.url_open(
            f"/web/partner/vcard?partner_ids={partner.id},{partner.id}"
        )
        self.assertEqual(resp.status_code, HTTPStatus.OK)
        self.assertEqual(resp.headers["Content-Type"], "text/vcard")
        self.assertEqual(int(resp.headers["Content-Length"]), len(resp.content))
        self.assertIn(b"Card Holder", resp.content)

    def test_a_scoped_app_path_is_decoded_once(self):
        resp = self.url_open(
            "/web/manifest.scoped_app_manifest?app_id=web&path=/odoo/a%2541"
        )
        self.assertEqual(resp.json()["scope"], "/odoo/a%41")
        page = self.url_open("/scoped_app?app_id=web&path=odoo/a%2541")
        self.assertIn("path=%2Fodoo%2Fa%2541", page.text)


@tagged("web_controllers_audit")
class TestActionPathWords(TransactionCase):
    def test_the_failing_word_is_counted_from_the_first_word(self):
        from odoo.addons.web.controllers.utils import get_action_triples

        for path in ("bogus", "/bogus", "bogus/"):
            with self.subTest(path=path), self.assertRaises(ValueError) as caught:
                list(get_action_triples(self.env, path))
            self.assertIn("at word 0 ", str(caught.exception))

    def test_a_non_ascii_digit_is_a_word_not_a_record_id(self):
        from odoo.addons.web.controllers.utils import get_action_triples

        with self.assertRaises(ValueError) as caught:
            list(get_action_triples(self.env, "action-base.action_partner_form/\u00b2"))
        self.assertIn("expected action at word 1", str(caught.exception))


@tagged("web_http", "web_controllers_audit")
class TestDatabaseListingHonoursListDb(HttpCase):
    def _list(self):
        return self.url_open(
            "/web/database/list",
            headers={"Content-Type": "application/json"},
            data=json_dumps({"params": {}}),
        ).json()

    def test_the_database_list_is_refused_when_list_db_is_off(self):
        from odoo.tools import config

        with config.patch(list_db=False), mute_logger("odoo.http"):
            body = self._list()
            manager = self.url_open("/web/database/manager")
        self.assertEqual(body["error"]["data"]["name"], "odoo.exceptions.AccessDenied")
        self.assertEqual(manager.status_code, HTTPStatus.OK)

    def test_the_database_list_is_served_when_list_db_is_on(self):
        from odoo.tools import config

        with config.patch(list_db=True):
            body = self._list()
        self.assertIn(self.env.cr.dbname, body["result"])


@tagged("web_http", "web_controllers_audit")
class TestClientNamedModelsAndShapes(HttpCase):
    def setUp(self):
        super().setUp()
        self.authenticate("admin", "admin")

    def _rpc(self, path, params):
        return self.url_open(
            path,
            headers={"Content-Type": "application/json"},
            data=json_dumps({"params": params}),
        ).json()

    def test_an_export_of_an_unknown_model_is_a_missing_error(self):
        with mute_logger("odoo.http"):
            for path, params in (
                ("/web/export/get_fields", {"model": "no.such.model", "domain": []}),
                ("/web/export/namelist", {"model": "no.such.model", "export_id": 1}),
            ):
                with self.subTest(path=path):
                    error = self._rpc(path, params)["error"]
                    self.assertEqual(
                        error["data"]["name"], "odoo.exceptions.MissingError"
                    )
                    self.assertIn("no.such.model", error["data"]["message"])

    def test_breadcrumbs_that_are_not_a_list_of_objects_are_a_bad_request(self):
        with mute_logger("odoo.http"):
            for actions in ({"a": 1}, [1, "x"]):
                with self.subTest(actions=actions):
                    error = self._rpc(
                        "/web/action/load_breadcrumbs", {"actions": actions}
                    )["error"]
                    self.assertEqual(error["code"], 400)

    def test_a_parent_field_without_its_type_still_lists_the_children(self):
        body = self._rpc(
            "/web/export/get_fields",
            {
                "model": "res.partner",
                "domain": [],
                "import_compat": False,
                "parent_field": {"string": "Partner"},
            },
        )
        self.assertIn("result", body)


@tagged("web_http", "web_controllers_audit")
class TestSmallRoutes(HttpCase):
    def _rpc(self, path, params=None):
        return self.url_open(
            path,
            headers={"Content-Type": "application/json"},
            data=json_dumps({"params": params or {}}),
        ).json()

    def test_the_root_forwards_its_query_to_the_web_client(self):
        _skip_unless_web_serves(self, "/", Home.index)
        resp = self.url_open("/?debug=1&foo=bar", allow_redirects=False)
        self.assertEqual(resp.status_code, HTTPStatus.SEE_OTHER)
        self.assertTrue(resp.headers["Location"].endswith("/odoo?debug=1&foo=bar"))

    def test_the_root_sends_a_portal_user_to_the_login_landing(self):
        _skip_unless_web_serves(self, "/", Home.index)
        self.env["res.users"].create(
            {
                "name": "Portal Root",
                "login": "portal_root_audit",
                "password": "portal_root_audit",
                "group_ids": [(6, 0, [self.env.ref("base.group_portal").id])],
            }
        )
        self.authenticate("portal_root_audit", "portal_root_audit")
        resp = self.url_open("/", allow_redirects=False)
        self.assertEqual(resp.status_code, HTTPStatus.SEE_OTHER)
        self.assertIn("/web/login_successful", resp.headers["Location"])

    def test_the_export_formats_are_xlsx_and_csv(self):
        self.authenticate("admin", "admin")
        self.assertEqual(
            self._rpc("/web/export/formats")["result"],
            [{"tag": "xlsx", "label": "XLSX"}, {"tag": "csv", "label": "CSV"}],
        )

    def test_the_account_link_names_this_database(self):
        self.authenticate("admin", "admin")
        url = self._rpc("/web/session/account")["result"]
        self.assertTrue(url.startswith("https://accounts.odoo.com/oauth2/auth?"))
        self.assertIn(self.env.cr.dbname, url)

    def test_demo_active_answers_whether_demo_data_is_loaded(self):
        self.authenticate("admin", "admin")
        demo = bool(
            self.env["ir.module.module"].search_count([("demo", "=", True)], limit=1)
        )
        self.assertIs(self._rpc("/base_setup/demo_active")["result"], demo)

    def test_version_info_needs_no_session(self):
        info = self._rpc("/web/webclient/version_info")["result"]
        self.assertEqual(info["server_serie"], "19.0")
        self.assertIn("protocol_version", info)


@tagged("web_http", "web_controllers_audit")
class TestActionLoadCost(HttpCase):
    def _statements(self, action_id):
        before = self.cr.sql_statement_count
        body = self.url_open(
            "/web/action/load",
            headers={"Content-Type": "application/json"},
            data=json_dumps({"params": {"action_id": action_id}}),
        ).json()
        self.assertIn("result", body)
        return self.cr.sql_statement_count - before

    def test_loading_by_xml_id_costs_no_more_than_by_id(self):
        self.authenticate("admin", "admin")
        action = self.env.ref("base.action_partner_form")
        for _warmup in range(2):
            self._statements(action.id)
            self._statements("base.action_partner_form")
        self.assertEqual(
            self._statements("base.action_partner_form"), self._statements(action.id)
        )
