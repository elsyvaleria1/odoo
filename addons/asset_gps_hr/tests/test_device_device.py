from lxml import etree

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools.safe_eval import safe_eval


@tagged("post_install", "-at_install")
class TestRemoteDeviceHrFields(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.DeviceDevice = cls.env["device.device"]

    def test_device_has_operator_field(self):
        field = self.DeviceDevice._fields.get("asset_operator_id")

        self.assertIsNotNone(field)
        self.assertEqual(field.comodel_name, "hr.employee")

    def test_device_has_license_plate_field(self):
        field = self.DeviceDevice._fields.get("asset_license_plate")

        self.assertIsNotNone(field)
        self.assertEqual(field.type, "char")


@tagged("post_install", "-at_install")
class TestRemoteDeviceHrComputation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.DeviceDevice = cls.env["device.device"]
        cls.config = cls.env["device.profile"].create({"name": "Test Config"})

        cls.km_uom = cls.env.ref("uom.product_uom_km", raise_if_not_found=False)
        if not cls.km_uom:
            cls.km_uom = cls.env["uom.uom"].create(
                {
                    "name": "km",
                    "relative_factor": 1000,
                    "relative_uom_id": cls.env.ref("uom.product_uom_meter").id,
                }
            )

        cls.product = cls.env["product.product"].create(
            {
                "name": "HR Test Vehicle",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("resource_asset.kind_vehicle").id,
            }
        )

        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Test Driver",
                "company_id": cls.company.id,
            }
        )

    def test_operator_computed_from_asset(self):
        device = self.DeviceDevice.create(
            {
                "name": "HR Device",
                "identifier": "GPS-HR-001",
                "config_id": self.config.id,
                "credential_id": False,
            }
        )

        self.env["product.trace"].create(
            {
                "name": "HR-VH",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
                "gps_device_id": device.id,
                "operator_id": self.employee.id,
            }
        )

        self.assertEqual(device.asset_operator_id, self.employee)

    def test_license_plate_computed_from_asset(self):
        device = self.DeviceDevice.create(
            {
                "name": "Plate Device",
                "identifier": "GPS-PLATE-001",
                "config_id": self.config.id,
                "credential_id": False,
            }
        )

        self.env["product.trace"].create(
            {
                "name": "PLATE-VH",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
                "gps_device_id": device.id,
                "license_plate": "ABC-123-XYZ",
            }
        )

        self.assertEqual(device.asset_license_plate, "ABC-123-XYZ")

    def test_operator_empty_when_no_asset(self):
        device = self.DeviceDevice.create(
            {
                "name": "No Asset HR Device",
                "identifier": "GPS-NOASSET-HR",
                "config_id": self.config.id,
                "credential_id": False,
            }
        )

        self.assertFalse(device.asset_operator_id)
        self.assertFalse(device.asset_license_plate)


@tagged("post_install", "-at_install")
class TestRemoteDeviceHrSearch(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.DeviceDevice = cls.env["device.device"]
        cls.config = cls.env["device.profile"].create({"name": "Test Config"})

        cls.km_uom = cls.env.ref("uom.product_uom_km", raise_if_not_found=False)
        if not cls.km_uom:
            cls.km_uom = cls.env["uom.uom"].create(
                {
                    "name": "km",
                    "relative_factor": 1000,
                    "relative_uom_id": cls.env.ref("uom.product_uom_meter").id,
                }
            )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Search Test Vehicle",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("resource_asset.kind_vehicle").id,
            }
        )

        cls.employee = cls.env["hr.employee"].create(
            {
                "name": "Searchable Driver",
                "company_id": cls.company.id,
            }
        )

    def test_search_by_license_plate(self):
        device = self.DeviceDevice.create(
            {
                "name": "Search Plate Device",
                "identifier": "GPS-SEARCH-PLATE",
                "config_id": self.config.id,
                "credential_id": False,
            }
        )

        self.env["product.trace"].create(
            {
                "name": "SEARCH-PLATE-VH",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
                "gps_device_id": device.id,
                "license_plate": "UNIQUE-PLATE-123",
            }
        )

        found = self.DeviceDevice.search(
            [("asset_license_plate", "=", "UNIQUE-PLATE-123")]
        )

        self.assertIn(device, found)

    def test_search_by_operator(self):
        device = self.DeviceDevice.create(
            {
                "name": "Search Operator Device",
                "identifier": "GPS-SEARCH-OP",
                "config_id": self.config.id,
                "credential_id": False,
            }
        )

        self.env["product.trace"].create(
            {
                "name": "SEARCH-OP-VH",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
                "gps_device_id": device.id,
                "operator_id": self.employee.id,
            }
        )

        found = self.DeviceDevice.search([("asset_operator_id", "=", self.employee.id)])

        self.assertIn(device, found)


@tagged("post_install", "-at_install")
class TestRemoteDeviceSearchViewDefault(TransactionCase):
    """One Enter in the search bar has to find a truck.

    Operations types a plate or a model, not a GPS serial. The domain is read
    out of the view itself rather than copied here, so this fails when the
    arch changes and not when a copy of it drifts.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.DeviceDevice = cls.env["device.device"]
        cls.config = cls.env["device.profile"].create({"name": "Search Default Config"})
        cls.product = cls.env["product.product"].create(
            {
                "name": "Search Default Vehicle",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("resource_asset.kind_vehicle").id,
            }
        )
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Genoveva Villalobos", "company_id": cls.env.company.id}
        )
        cls.device = cls.DeviceDevice.create(
            {
                "name": "4590000001",
                "identifier": "GPS-SEARCH-DEFAULT",
                "config_id": cls.config.id,
                "credential_id": False,
            }
        )
        cls.env["product.trace"].create(
            {
                "name": "Toyota/Hilux doble cabina/XYZ0001",
                "product_id": cls.product.id,
                "company_id": cls.env.company.id,
                "gps_device_id": cls.device.id,
                "license_plate": "XYZ0001",
                "operator_id": cls.employee.id,
            }
        )

    def _default_field_search(self, term):
        arch = etree.fromstring(
            self.DeviceDevice.get_view(
                self.env.ref("device_gps.view_device_device_search").id, "search"
            )["arch"]
        )
        node = arch.xpath("//search/field[@name='name']")[0]
        domain = safe_eval(node.get("filter_domain"), {"self": term})
        return self.DeviceDevice.search(domain)

    def test_typing_a_plate_finds_the_vehicle(self):
        self.assertIn(self.device, self._default_field_search("XYZ0001"))

    def test_typing_a_model_finds_the_vehicle(self):
        self.assertIn(self.device, self._default_field_search("Hilux"))

    def test_typing_a_driver_finds_the_vehicle(self):
        self.assertIn(self.device, self._default_field_search("Villalobos"))

    def test_typing_the_serial_still_finds_the_device(self):
        self.assertIn(self.device, self._default_field_search("4590000001"))

    def test_an_unrelated_term_finds_nothing(self):
        self.assertNotIn(self.device, self._default_field_search("Kenworth"))


@tagged("post_install", "-at_install")
class TestRemoteDeviceHrKanban(TransactionCase):
    def test_the_operator_line_follows_the_asset_line(self):
        arch = etree.fromstring(
            self.env.ref(
                "device_gps.view_device_device_kanban_gps_dashboard"
            ).get_combined_arch()
        )
        (asset_line,) = arch.xpath("//div[@name='asset_line']")
        operator_block = asset_line.getnext()

        self.assertIsNotNone(operator_block)
        self.assertEqual(
            operator_block.get("t-if"), "record.asset_operator_id.raw_value"
        )
