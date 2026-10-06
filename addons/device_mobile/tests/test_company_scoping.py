from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install", "device_mobile")
class TestCompanyScoping(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "Scoping A"})
        cls.company_b = cls.env["res.company"].create({"name": "Scoping B"})
        cls.config = cls.env["device.profile"].search([], limit=1) or cls.env[
            "device.profile"
        ].create({"name": "scoping cfg"})
        cls.user_b = cls.env["res.users"].create(
            {
                "name": "Scoping B user",
                "login": "scoping_b_user",
                "company_id": cls.company_b.id,
                "company_ids": [(6, 0, [cls.company_b.id])],
                "group_ids": [(4, cls.env.ref("device.group_device_user").id)],
            }
        )

    def _device(self, company):
        return self.env["device.device"].create(
            {
                "name": f"phone-{(company and company.id) or 'none'}",
                "identifier": f"IMEI-SCOPING-{(company and company.id) or 'NONE'}",
                "config_id": self.config.id,
                "company_id": (company and company.id) or False,
            }
        )

    def test_company_less_device_is_not_visible_to_another_company(self):
        device = self._device(False)
        seen = (
            self.env["device.device"]
            .with_user(self.user_b)
            .search([("id", "=", device.id)])
        )
        self.assertFalse(seen)
