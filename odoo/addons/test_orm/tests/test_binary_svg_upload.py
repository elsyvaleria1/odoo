import base64
import codecs

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.http import JsonRpcException
from odoo.tools import SQL

from odoo.addons.base.tests.common import (
    HttpCaseWithUserDemo,
    TransactionCaseWithUserDemo,
)

SVG = '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'

SVG_SPELLINGS = {
    "bare": SVG.encode(),
    "utf-8 mark and whitespace": codecs.BOM_UTF8 + b"\n  " + SVG.encode(),
    "utf-16-le": codecs.BOM_UTF16_LE + SVG.encode("utf-16-le"),
    "utf-16-be": codecs.BOM_UTF16_BE + SVG.encode("utf-16-be"),
    "utf-32-le": codecs.BOM_UTF32_LE + SVG.encode("utf-32-le"),
}

COLUMN_FIELDS = ("image_wo_attachment", "image_wo_attachment_related")


class TestSvgWriteGate(TransactionCaseWithUserDemo):
    def _column(self, record, fname):
        record.env.flush_all()
        self.env.cr.execute(
            SQL(
                "SELECT %s FROM test_orm_binary_svg WHERE id = %s",
                SQL.identifier(fname),
                record.id,
            )
        )
        return self.env.cr.fetchone()[0]

    def test_a_user_cannot_write_an_svg_into_a_column(self):
        record = self.env["test_orm.binary_svg"].create({"name": "logo"})
        for spelling, raw in SVG_SPELLINGS.items():
            for fname in COLUMN_FIELDS:
                with (
                    self.subTest(spelling=spelling, field=fname),
                    self.assertRaisesRegex(UserError, "Only admins"),
                ):
                    record.with_user(self.user_demo).write(
                        {fname: base64.b64encode(raw)}
                    )
                self.assertIsNone(self._column(record, fname))

    def test_a_user_cannot_web_save_an_svg(self):
        record = self.env["test_orm.binary_svg"].create({"name": "logo"})
        value = base64.b64encode(SVG_SPELLINGS["utf-16-le"]).decode()
        with self.assertRaisesRegex(UserError, "Only admins"):
            record.with_user(self.user_demo).web_save(
                {"image_wo_attachment": value}, {}
            )
        with self.assertRaisesRegex(UserError, "Only admins"):
            self.env["test_orm.binary_svg"].with_user(self.user_demo).web_save(
                {"name": "new", "image_wo_attachment": value}, {}
            )
        self.assertIsNone(self._column(record, "image_wo_attachment"))

    def test_an_admin_writes_an_svg_into_a_column(self):
        record = self.env["test_orm.binary_svg"].create({"name": "logo"})
        for spelling, raw in SVG_SPELLINGS.items():
            with self.subTest(spelling=spelling):
                value = base64.b64encode(raw)
                record.write({"image_wo_attachment": value})
                self.assertEqual(
                    bytes(self._column(record, "image_wo_attachment")), value
                )
                self.assertEqual(
                    bytes(self._column(record, "image_wo_attachment_related")), value
                )

    def test_a_user_editing_beside_an_admin_svg_is_not_refused(self):
        value = base64.b64encode(SVG.encode())
        record = self.env["test_orm.binary_svg"].create(
            {"name": "logo", "image_wo_attachment": value}
        )
        record.with_user(self.user_demo).write({"name": "renamed"})
        self.assertEqual(bytes(self._column(record, "image_wo_attachment")), value)

    def test_an_attachment_is_downgraded_not_refused(self):
        record = self.env["test_orm.binary_svg"].create({"name": "logo"})
        record.with_user(self.user_demo).write(
            {"image_attachment": base64.b64encode(SVG.encode())}
        )
        attachment = self.env["ir.attachment"].search(
            [
                ("res_model", "=", record._name),
                ("res_field", "=", "image_attachment"),
                ("res_id", "=", record.id),
            ]
        )
        self.assertEqual(attachment.mimetype, "text/plain")


@tagged("post_install", "-at_install")
class TestSvgWriteGateOverRpc(HttpCaseWithUserDemo):
    def _call(self, method, args):
        return self.call_jsonrpc(
            "/web/dataset/call_kw",
            {
                "model": "test_orm.binary_svg",
                "method": method,
                "args": args,
                "kwargs": {},
            },
        )

    def _served_type(self, record_id):
        response = self.url_open(
            f"/web/content/test_orm.binary_svg/{record_id}/image_wo_attachment"
        )
        return response.headers.get("Content-Type", "")

    def test_a_user_cannot_write_an_svg_over_rpc(self):
        record = self.env["test_orm.binary_svg"].create({"name": "logo"})
        self.authenticate("demo", "demo")
        for spelling, raw in SVG_SPELLINGS.items():
            value = base64.b64encode(raw).decode()
            calls = {
                "write": ("write", [[record.id], {"image_wo_attachment": value}]),
                "web_save": (
                    "web_save",
                    [[record.id], {"image_wo_attachment": value}, {}],
                ),
                "web_save a new record": (
                    "web_save",
                    [[], {"name": "new", "image_wo_attachment": value}, {}],
                ),
            }
            for name, (method, args) in calls.items():
                with (
                    self.subTest(spelling=spelling, call=name),
                    self.assertRaisesRegex(JsonRpcException, "UserError"),
                ):
                    self._call(method, args)
        self.assertFalse(record.image_wo_attachment)
        self.assertFalse(self._served_type(record.id).startswith("image/svg"))

    def test_an_admin_writes_an_svg_over_rpc(self):
        record = self.env["test_orm.binary_svg"].create({"name": "logo"})
        self.authenticate("admin", "admin")
        value = base64.b64encode(SVG_SPELLINGS["bare"]).decode()
        self._call("write", [[record.id], {"image_wo_attachment": value}])
        self._call("web_save", [[record.id], {"image_wo_attachment": value}, {}])
        self.assertTrue(self._served_type(record.id).startswith("image/svg+xml"))
