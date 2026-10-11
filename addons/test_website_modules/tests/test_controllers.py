from lxml import etree

from odoo import Command, tests
from odoo.tools import mute_logger
from odoo.tools.json import scriptsafe as json_safe

from odoo.addons.base.tests.common import HttpCaseWithUserDemo, HttpCaseWithUserPortal


@tests.tagged("-at_install", "post_install")
class TestWebEditorController(HttpCaseWithUserDemo, HttpCaseWithUserPortal):
    def test_modify_image(self):
        gif_base64 = b"R0lGODdhAQABAIAAAP///////ywAAAAAAQABAAACAkQBADs="
        attachment = self.env["ir.attachment"].create(
            {
                "name": "test.gif",
                "mimetype": "image/gif",
                "datas": gif_base64,
                "public": True,
                "res_model": "ir.ui.view",
                "res_id": 0,
            }
        )

        def modify(login, name, expect_fail=False):
            self.authenticate(login, login)
            params = {
                "name": name,
                "data": gif_base64.decode("ascii"),
                "shape": {"id": "html_builder/geometric/geo_diamond"},
            }
            if attachment.res_id:
                params["res_model"] = attachment.res_model
                params["res_id"] = attachment.res_id
            response = self.url_open(
                f"/html_editor/modify_image/{attachment.id}",
                headers={"Content-Type": "application/json"},
                data=json_safe.dumps(
                    {
                        "params": params,
                    }
                ),
            )
            self.assertEqual(200, response.status_code, "Expect response")
            if expect_fail:
                return json_safe.loads(response.content)
            content = json_safe.loads(response.content)
            self.assertFalse(content.get("error"), "An error should not happen")
            url = content.get("result")
            self.assertTrue(
                url.partition("?unique=")[0].endswith(name), "Expect name in URL"
            )
            response = self.url_open(url)
            self.assertEqual(200, response.status_code, "Expect response")
            self.assertTrue(
                "image/svg+xml" in response.headers.get("Content-Type"),
                "Expect SVG mimetype",
            )
            image = etree.fromstring(response.content).find(
                ".//{http://www.w3.org/2000/svg}image"
            )
            self.assertEqual(
                image.get("{http://www.w3.org/1999/xlink}href"),
                f"data:image/gif;base64,{gif_base64.decode('ascii')}",
                "Expect the shape built around the image",
            )
            return True

        modify("admin", "page-admin.gif")

        self.user_demo.write(
            {
                "group_ids": [
                    Command.clear(),
                    Command.link(self.env.ref("base.group_user").id),
                ],
            }
        )
        with mute_logger("odoo.http"):
            json = modify("demo", "page-demofail.gif", True)
        self.assertFalse(
            json.get("result"), "Expect no URL when called with insufficient rights"
        )

        self.user_demo.write(
            {
                "group_ids": [
                    Command.clear(),
                    Command.link(self.env.ref("base.group_user").id),
                    Command.link(
                        self.env.ref("website.group_website_restricted_editor").id
                    ),
                    Command.link(self.env.ref("event.group_event_manager").id),
                ],
            }
        )
        with mute_logger("odoo.http"):
            json = modify("demo", "page-demofail2.gif", True)
        self.assertFalse(
            json.get("result"), "Expect no URL when called with insufficient rights"
        )

        self.user_demo.write(
            {
                "group_ids": [
                    Command.clear(),
                    Command.link(self.env.ref("base.group_user").id),
                    Command.link(self.env.ref("website.group_website_designer").id),
                ],
            }
        )
        modify("demo", "page-demo.gif")

        attachment.url = "/page-logo-unique.gif"
        modify("demo", "page-logo-unique.gif")
        attachment.url = False

        event = self.env["event.event"].create({"name": "test event"})
        attachment.res_model = "event.event"
        attachment.res_id = event.id

        modify("admin", "event-admin.gif")

        self.user_demo.write(
            {
                "group_ids": [
                    Command.clear(),
                    Command.link(self.env.ref("base.group_user").id),
                ],
            }
        )
        with mute_logger("odoo.http"):
            json = modify("demo", "event-demofail.gif", True)
        self.assertFalse(
            json.get("result"), "Expect no URL when called with insufficient rights"
        )

        self.user_demo.write(
            {
                "group_ids": [
                    Command.clear(),
                    Command.link(self.env.ref("base.group_user").id),
                    Command.link(
                        self.env.ref("website.group_website_restricted_editor").id
                    ),
                    Command.link(self.env.ref("sale.group_sale_manager").id),
                ],
            }
        )
        with mute_logger("odoo.http"):
            json = modify("demo", "event-demofail2.gif", True)
        self.assertFalse(
            json.get("result"), "Expect no URL when called with insufficient rights"
        )

        self.user_demo.write(
            {
                "group_ids": [
                    Command.clear(),
                    Command.link(self.env.ref("base.group_user").id),
                    Command.link(
                        self.env.ref("website.group_website_restricted_editor").id
                    ),
                    Command.link(self.env.ref("event.group_event_manager").id),
                ],
            }
        )
        modify("demo", "event-demo.gif")

        self.user_demo.write(
            {
                "group_ids": [
                    Command.clear(),
                    Command.link(self.env.ref("base.group_user").id),
                    Command.link(self.env.ref("website.group_website_designer").id),
                ],
            }
        )
        with mute_logger("odoo.http"):
            json = modify("demo", "event-demofail3.gif", True)
        self.assertFalse(
            json.get("result"), "Expect no URL when called with insufficient rights"
        )
