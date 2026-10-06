import io
import zipfile
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import xsd
from odoo.tests.common import TransactionCase

_SCHEMA = (
    b"<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'>"
    b"<xs:element name='a' type='xs:string'/></xs:schema>"
)
_BROKEN_SCHEMA = (
    b"<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'>"
    b"<xs:element name='a' type='NO_SUCH_TYPE'/></xs:schema>"
)


def _zip(*names):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name in names:
            archive.writestr(name, _SCHEMA)
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


class TestValidateXmlFromAttachment(TransactionCase):
    def test_a_schema_that_cannot_be_parsed_is_not_a_pass(self):
        self.env["ir.attachment"].create({"name": "broken.xsd", "raw": _BROKEN_SCHEMA})
        with self.assertRaises(FileNotFoundError) as caught:
            xsd.check_xml_from_attachment(self.env, "<b/>", "broken.xsd")
        self.assertIn("could not be parsed", str(caught.exception))

    def test_required_false_still_accepts_an_unparseable_schema(self):
        self.env["ir.attachment"].create({"name": "broken.xsd", "raw": _BROKEN_SCHEMA})
        with self.assertLogs("odoo.tests.xsd", "WARNING"):
            xsd.check_xml_from_attachment(
                self.env, "<b/>", "broken.xsd", required=False
            )

    def test_a_valid_schema_still_validates(self):
        self.env["ir.attachment"].create({"name": "good.xsd", "raw": _SCHEMA})
        xsd.check_xml_from_attachment(self.env, "<a>x</a>", "good.xsd")


class TestCheckXml(TransactionCase):
    def _serve(self, content):
        patcher = patch.object(
            xsd.requests, "get", lambda *a, **k: _FakeResponse(content)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_an_archive_of_several_schemas_asks_which_one(self):
        self._serve(_zip("one.xsd", "two.xsd"))
        with self.assertRaises(ValueError) as caught:
            xsd.check_xml(self.env, "http://example/s.zip", None, "<a>x</a>")
        message = str(caught.exception)
        self.assertIn("pass xsd_name=", message)
        self.assertIn("one.xsd", message)
        self.assertIn("two.xsd", message)

    def test_naming_the_root_schema_validates_against_it(self):
        self._serve(_zip("one.xsd", "two.xsd"))
        xsd.check_xml(self.env, "http://example/s.zip", None, "<a>x</a>", "one.xsd")

    def test_a_name_no_member_carries_is_reported(self):
        self._serve(_zip("one.xsd"))
        with self.assertRaises(FileNotFoundError):
            xsd.check_xml(
                self.env, "http://example/s.zip", None, "<a>x</a>", "absent.xsd"
            )

    def test_it_does_not_delete_a_schema_it_did_not_create(self):
        self._serve(_zip("only.xsd"))
        pre_existing = self.env["ir.attachment"].create(
            {"name": "only.xsd", "raw": _SCHEMA, "public": True}
        )
        xsd.check_xml(self.env, "http://example/s.zip", None, "<a>x</a>")
        self.assertTrue(
            pre_existing.exists(),
            "_check_xml deleted an attachment it merely found",
        )

    def test_a_record_attachment_sharing_the_name_is_not_overwritten(self):
        self._serve(_zip("only.xsd"))
        partner = self.env["res.partner"].create({"name": "probe"})
        document = self.env["ir.attachment"].create(
            {
                "name": "only.xsd",
                "raw": b"somebody's document",
                "res_model": "res.partner",
                "res_id": partner.id,
            }
        )
        xsd.check_xml(self.env, "http://example/s.zip", None, "<a>x</a>")
        self.assertEqual(document.raw, b"somebody's document")

    def test_a_record_attachment_sharing_the_name_is_not_a_schema(self):
        partner = self.env["res.partner"].create({"name": "probe"})
        self.env["ir.attachment"].create(
            {
                "name": "shadow.xsd",
                "raw": _SCHEMA,
                "res_model": "res.partner",
                "res_id": partner.id,
            }
        )
        with self.assertRaises(FileNotFoundError):
            xsd.check_xml_from_attachment(self.env, "<a>x</a>", "shadow.xsd")

    def test_the_loader_takes_only_what_a_caller_passes(self):
        code = xsd.load_xsd_files_from_url.__code__
        self.assertEqual(
            code.co_varnames[: code.co_argcount + code.co_kwonlyargcount],
            ("env", "url"),
        )


class TestSchemaImports(TransactionCase):
    def test_an_absolute_import_resolves_to_the_schema_of_that_file_name(self):
        self.env["ir.attachment"].create(
            {
                "name": "types.xsd",
                "raw": b"<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'"
                b" targetNamespace='urn:types'>"
                b"<xs:simpleType name='code'><xs:restriction base='xs:string'>"
                b"<xs:pattern value='[0-9]{3}'/></xs:restriction></xs:simpleType>"
                b"</xs:schema>",
            }
        )
        self.env["ir.attachment"].create(
            {
                "name": "root.xsd",
                "raw": b"<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'"
                b" xmlns:t='urn:types'>"
                b"<xs:import namespace='urn:types'"
                b" schemaLocation='http://example.org/schemas/types/types.xsd'/>"
                b"<xs:element name='a' type='t:code'/></xs:schema>",
            }
        )
        xsd.check_xml_from_attachment(self.env, "<a>101</a>", "root.xsd")
        with self.assertRaises(UserError):
            xsd.check_xml_from_attachment(self.env, "<a>x</a>", "root.xsd")
