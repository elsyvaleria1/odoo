from unittest.mock import MagicMock

import defusedxml.ElementTree as ET

from odoo.tests import tagged

from ..tools import find_element, find_text
from odoo.addons.device.tests.common import DeviceTransactionCase

NS = "http://www.isapi.org/ver20/XMLSchema"

DEVICE_INFO_NAMESPACED = (
    f'<DeviceInfo xmlns="{NS}">'
    "<deviceName>Factory Default</deviceName>"
    "<model>DS-K1T341CMFW</model>"
    "<serialNumber>SN-42</serialNumber>"
    "</DeviceInfo>"
)
DEVICE_INFO_PLAIN = (
    "<DeviceInfo>"
    "<deviceName>Factory Default</deviceName>"
    "<model>DS-K1T341CMFW</model>"
    "<serialNumber>SN-42</serialNumber>"
    "</DeviceInfo>"
)


@tagged("post_install", "-at_install")
class TestIsapiXmlHelpers(DeviceTransactionCase):
    def test_a_namespaced_leaf_is_found(self):
        for label, payload in (
            ("namespaced", DEVICE_INFO_NAMESPACED),
            ("plain", DEVICE_INFO_PLAIN),
        ):
            with self.subTest(document=label):
                root = ET.fromstring(payload)
                self.assertEqual(find_text(root, "model"), "DS-K1T341CMFW")
                self.assertEqual(find_text(root, "serialNumber"), "SN-42")
                self.assertIsNotNone(find_element(root, "model"))

    def test_a_descendant_path_is_namespaced_step_by_step(self):
        root = ET.fromstring(
            f'<r xmlns="{NS}"><a><fingerData>QUJD</fingerData></a></r>'
        )
        self.assertEqual(
            find_text(root, ".//fingerData"),
            "QUJD",
            "a blanket ns: prefix produces 'ns:.//fingerData', which matches "
            "nothing and raises nothing",
        )

    def test_a_missing_element_yields_the_default(self):
        root = ET.fromstring(f'<DeviceInfo xmlns="{NS}"/>')
        self.assertEqual(find_text(root, "model"), "")
        self.assertIsNone(find_element(root, "model"))


@tagged("post_install", "-at_install")
class TestDeviceInfoUpdate(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["device.kind"].create(
            {"name": "Access", "code": "access_control"}
        )
        cls.device = cls._create_device_device(
            identifier="ISAPI-INFO", device_category_id=cls.category.id
        )

    def _response(self, payload):
        response = MagicMock()
        response.content = payload.encode()
        return response

    def test_a_namespaced_device_info_reaches_the_record(self):
        self.device._update_device_info_from_response(
            self._response(DEVICE_INFO_NAMESPACED)
        )
        self.assertEqual(self.device.device_model, "DS-K1T341CMFW")
        self.assertEqual(self.device.serial_number, "SN-42")

    def test_the_operator_chosen_name_survives(self):
        chosen = self.device.name
        self.device._update_device_info_from_response(
            self._response(DEVICE_INFO_NAMESPACED)
        )
        self.assertEqual(
            self.device.name,
            chosen,
            "deviceName used to overwrite the device's name, so a connection "
            "check renamed it to whatever the panel shipped with",
        )
