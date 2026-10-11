from lxml import etree

from odoo.tests.common import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestMobileDeviceForm(TransactionCase):
    def _form(self, user):
        views = (
            self.env["device.device"]
            .with_user(user)
            .get_views([(False, "form")])["views"]["form"]
        )
        return etree.fromstring(views["arch"])

    def test_a_phones_token_is_on_the_form_without_debug_mode(self):
        manager = new_test_user(
            self.env, login="mobile_form_manager", groups="device.group_device_manager"
        )
        form = self._form(manager)
        credential = [
            node
            for node in form.iter("field")
            if node.get("name") == "credential_id"
            and not any(page.tag == "page" for page in node.iterancestors())
        ]
        self.assertEqual(len(credential), 1, "the token sits with the phone's fields")
        self.assertIn("mobile_phone", credential[0].get("invisible") or "")

    def test_the_category_comes_right_after_the_name(self):
        form = self._form(self.env.user)
        title = form.xpath("//div[hasclass('oe_title')]//group")[0]
        first = next(node for node in title.iter("field"))
        self.assertEqual(first.get("name"), "device_category_id")

    def test_what_a_phone_does_not_use_is_hidden_for_a_phone(self):
        form = self._form(self.env.user)
        for name in ("plate", "comm_protocol", "link_mode"):
            (node,) = form.xpath(f"//field[@name='{name}']")
            self.assertIn("mobile_phone", node.get("invisible") or "", name)
        for page in ("connection", "api_auth"):
            for node in form.xpath(f"//page[@name='{page}']"):
                invisible = node.get("invisible") or ""
                self.assertTrue(invisible == "1" or "mobile_phone" in invisible, page)
