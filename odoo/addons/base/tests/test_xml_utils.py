from pathlib import Path

from lxml import etree

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, test_xsd
from odoo.tools.files import file_open_temporary_directory
from odoo.tools.xml_utils import check_with_xsd_file

_TYPES_SCHEMA = (
    b"<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'"
    b" targetNamespace='urn:types'>"
    b"<xs:simpleType name='code'><xs:restriction base='xs:string'>"
    b"<xs:pattern value='[0-9]{3}'/></xs:restriction></xs:simpleType>"
    b"</xs:schema>"
)
_IMPORTING_SCHEMA = (
    b"<xs:schema xmlns:xs='http://www.w3.org/2001/XMLSchema'"
    b" xmlns:t='urn:types'>"
    b"<xs:import namespace='urn:types'"
    b" schemaLocation='http://example.org/schemas/types/types.xsd'/>"
    b"<xs:element name='a' type='t:code'/></xs:schema>"
)


class TestSchemaFiles(TransactionCase):
    def test_an_absolute_import_resolves_to_the_file_beside_the_schema(self):
        with file_open_temporary_directory() as directory:
            Path(directory, "types.xsd").write_bytes(_TYPES_SCHEMA)
            root = Path(directory, "root.xsd")
            root.write_bytes(_IMPORTING_SCHEMA)
            check_with_xsd_file("<a>101</a>", str(root))
            with self.assertRaises(UserError):
                check_with_xsd_file("<a>x</a>", str(root))

    def test_an_import_named_by_the_caller_resolves_from_another_directory(self):
        with (
            file_open_temporary_directory() as own,
            file_open_temporary_directory() as shared,
        ):
            types = Path(shared, "types.xsd")
            types.write_bytes(_TYPES_SCHEMA)
            root = Path(own, "root.xsd")
            root.write_bytes(_IMPORTING_SCHEMA)
            check_with_xsd_file("<a>101</a>", str(root), str(types))

    def test_an_import_with_no_local_file_is_not_fetched(self):
        with file_open_temporary_directory() as directory:
            root = Path(directory, "root.xsd")
            root.write_bytes(_IMPORTING_SCHEMA)
            with self.assertRaises(etree.XMLSchemaParseError):
                check_with_xsd_file("<a>101</a>", str(root))

    def test_a_test_xsd_path_validates_every_returned_document(self):
        with file_open_temporary_directory() as directory:
            Path(directory, "types.xsd").write_bytes(_TYPES_SCHEMA)
            root = str(Path(directory, "root.xsd"))
            Path(root).write_bytes(_IMPORTING_SCHEMA)
            test_xsd(path=root)(lambda case: ["<a>101</a>", "<a>202</a>"])(self)
            with self.assertRaises(UserError):
                test_xsd(path=root)(lambda case: ["<a>101</a>", "<a>x</a>"])(self)
            with self.assertRaises(UserError):
                test_xsd(path=root)(lambda case: "<a>x</a>")(self)
