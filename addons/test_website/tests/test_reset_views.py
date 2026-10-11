import re

import odoo.tests
from odoo.libs.json import dumps as json_dumps
from odoo.tools import mute_logger


def break_view(view, fr="<p>placeholder</p>", to='<p t-field="no_record.exist"/>'):
    view.arch = view.arch.replace(fr, to)


@odoo.tests.common.tagged("post_install", "-at_install")
class TestWebsiteResetViews(odoo.tests.HttpCase):
    def fix_it(self, page, mode="soft"):
        self.authenticate("admin", "admin")
        resp = self.url_open(page)
        self.assertEqual(resp.status_code, 500, "Waiting 500")
        self.assertTrue(
            '<button data-mode="soft" class="reset_templates_button' in resp.text
        )
        data = {"params": {"view_id": self.find_template(resp), "mode": mode}}
        self.url_open(
            "/website/reset_template",
            data=json_dumps(data),
            headers={"Content-Type": "application/json"},
        )
        resp = self.url_open(page)
        self.assertTrue(resp.url.endswith(page), "We should be checking the test page")
        self.assertEqual(resp.status_code, 200, "Waiting 200")

    def find_template(self, response):
        find = re.search(
            r'<input.*type="hidden".*name="view_id".*value="([0-9]+)?"', response.text
        )
        return find and find.group(1)

    def setUp(self):
        super().setUp()
        self.Website = self.env["website"]
        self.View = self.env["ir.ui.view"]
        self.test_view = self.Website.viewref("test_website.test_view")

    @mute_logger("odoo.http")
    def test_01_reset_specific_page_view(self):
        self.test_page_view = self.Website.viewref("test_website.test_page_view")
        total_views = self.View.search_count([("type", "=", "qweb")])
        break_view(self.test_page_view.with_context(website_id=1))
        self.assertEqual(
            total_views + 1,
            self.View.search_count([("type", "=", "qweb")]),
            "Missing COW view",
        )
        self.fix_it("/test_page_view")

    @mute_logger("odoo.http")
    def test_02_reset_specific_view_controller(self):
        total_views = self.View.search_count([("type", "=", "qweb")])
        break_view(
            self.test_view.with_context(website_id=1),
            to='<p t-att-data="no_record.exist" />',
        )
        self.assertEqual(
            total_views + 1,
            self.View.search_count([("type", "=", "qweb")]),
            "Missing COW view",
        )
        self.fix_it("/test_view")

    @mute_logger("odoo.http")
    def test_03_reset_specific_view_controller_t_called(self):
        self.test_view_to_be_t_called = self.Website.viewref(
            "test_website.test_view_to_be_t_called"
        )

        total_views = self.View.search_count([("type", "=", "qweb")])
        break_view(self.test_view_to_be_t_called.with_context(website_id=1))
        break_view(
            self.test_view, to='<t t-call="test_website.test_view_to_be_t_called"/>'
        )
        self.assertEqual(
            total_views + 1,
            self.View.search_count([("type", "=", "qweb")]),
            "Missing COW view",
        )
        self.fix_it("/test_view")

    @mute_logger("odoo.http")
    def test_04_reset_specific_view_controller_inherit(self):
        self.test_view_child_broken = self.Website.viewref(
            "test_website.test_view_child_broken"
        )

        self.test_view_child_broken.active = True
        break_view(
            self.test_view_child_broken.with_context(website_id=1, load_all_views=True)
        )

        self.fix_it("/test_view")


    @mute_logger("odoo.http", "odoo.addons.website.models.ir_ui_view")
    def test_06_reset_specific_view_controller_inexisting_template(self):
        called = self.View.create(
            {
                "type": "qweb",
                "key": "test_website.test_view_called",
                "name": "test_view_called",
                "arch": '<t t-name="test_website.test_view_called"><p/></t>',
            }
        )
        total_views = self.View.search_count([("type", "=", "qweb")])
        break_view(
            self.test_view.with_context(website_id=1),
            to='<t t-call="test_website.test_view_called"/>',
        )
        self.assertEqual(
            total_views + 1,
            self.View.search_count([("type", "=", "qweb")]),
            "Missing COW view (2)",
        )
        called.unlink()
        self.fix_it("/test_view")

    @mute_logger("odoo.http")
    def test_07_reset_page_view_complete_flow(self):
        self.start_tour(
            self.env["website"].get_client_action_url("/test_page_view"),
            "test_reset_page_view_complete_flow_part1",
            login="admin",
        )
        self.fix_it("/test_page_view")
        self.start_tour(
            self.env["website"].get_client_action_url("/test_page_view"),
            "test_reset_page_view_complete_flow_part2",
            login="admin",
        )
        self.fix_it("/test_page_view")

    @mute_logger("odoo.http")
    def test_08_reset_specific_page_view_hard_mode(self):
        self.test_page_view = self.Website.viewref("test_website.test_page_view")
        total_views = self.View.search_count([("type", "=", "qweb")])
        break_view(self.test_page_view.with_context(website_id=1))
        break_view(self.test_page_view.with_context(website_id=1))
        self.assertEqual(
            total_views + 1,
            self.View.search_count([("type", "=", "qweb")]),
            "Missing COW view",
        )

        with self.assertRaises(AssertionError):
            self.fix_it("/test_page_view")
        self.fix_it("/test_page_view", "hard")
        self.assertFalse(self.test_page_view.arch_updated)
