from lxml import etree

from odoo.fields import Command
from odoo.tests import Form, TransactionCase, new_test_user

MODEL = "test_ir_access.document"
LINE_MODEL = "test_ir_access.document_line"


class TestVerbButtons(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        posters = cls.env["res.groups"].create({"name": "Verb buttons: posters"})
        cls.env["ir.access"].create(
            {
                "name": "posters post their own",
                "model_id": cls.env["ir.model"]._get_id(MODEL),
                "group_id": posters.id,
                "kind": "permission",
                "verbs": "post",
                "domain": "[('name', '=', 'mine')]",
            }
        )
        cls.clerk = new_test_user(
            cls.env, login="button_clerk", groups="base.group_user"
        )
        cls.poster = new_test_user(
            cls.env, login="button_poster", groups="base.group_user"
        )
        cls.poster.group_ids = [Command.link(posters.id)]
        cls.admin = new_test_user(
            cls.env, login="button_admin", groups="base.group_user,base.group_system"
        )
        cls.mine = cls.env[MODEL].create({"name": "mine"})
        cls.theirs = cls.env[MODEL].create({"name": "theirs"})
        View = cls.env["ir.ui.view"]
        cls.form = View.create(
            {
                "name": "verb buttons form",
                "model": MODEL,
                "type": "form",
                "arch": """
                    <form>
                        <header>
                            <button name="action_post" type="object" string="Post"
                                    invisible="state != 'draft'"/>
                        </header>
                        <sheet><field name="name"/><field name="state"/></sheet>
                    </form>
                """,
            }
        )
        cls.list = View.create(
            {
                "name": "verb buttons list",
                "model": MODEL,
                "type": "list",
                "arch": """
                    <list>
                        <field name="name"/>
                        <button name="action_post" type="object" string="Post"/>
                    </list>
                """,
            }
        )
        cls.line_list = View.create(
            {
                "name": "verb buttons line list",
                "model": LINE_MODEL,
                "type": "list",
                "arch": """
                    <list>
                        <field name="name"/>
                        <groupby name="document_id">
                            <field name="state"/>
                            <button name="action_post" type="object" string="Post"
                                    invisible="state != 'draft'"/>
                        </groupby>
                    </list>
                """,
            }
        )

    def views(self, user, view):
        result = self.env[MODEL].with_user(user).get_views([(view.id, view.type)])
        arch = etree.fromstring(result["views"][view.type]["arch"])
        return arch, result["models"][MODEL]["fields"]

    def test_a_button_of_a_verb_held_on_no_record_is_dropped(self):
        arch, fields = self.views(self.clerk, self.form)
        self.assertFalse(arch.xpath("//button[@name='action_post']"))
        self.assertFalse(arch.xpath("//field[@name='__verbs']"))
        self.assertNotIn("__verbs", fields)

    def test_a_button_of_a_verb_held_on_every_record_is_left_as_written(self):
        arch, fields = self.views(self.admin, self.form)
        [button] = arch.xpath("//button[@name='action_post']")
        self.assertEqual(button.get("invisible"), "state != 'draft'")
        self.assertIsNone(button.get("__verb__"))
        self.assertNotIn("__verbs", fields)

    def test_a_button_of_a_verb_held_on_some_records_asks_each_record(self):
        arch, fields = self.views(self.poster, self.form)
        [button] = arch.xpath("//button[@name='action_post']")
        self.assertEqual(
            button.get("invisible"),
            "(state != 'draft') or (__verbs and not __verbs.get('post'))",
        )
        [verbs] = arch.xpath("/form/field[@name='__verbs']")
        self.assertEqual(verbs.get("invisible"), "1")
        self.assertIsNone(verbs.get("__verbs_model__"))
        self.assertEqual(fields["__verbs"]["type"], "json")

        arch, fields = self.views(self.poster, self.list)
        [button] = arch.xpath("//button[@name='action_post']")
        self.assertEqual(button.get("invisible"), "__verbs and not __verbs.get('post')")
        [verbs] = arch.xpath("/list/field[@name='__verbs']")
        self.assertEqual(verbs.get("column_invisible"), "1")
        self.assertIn("__verbs", fields)

    def test_a_group_s_button_asks_the_record_the_group_stands_for(self):
        result = (
            self.env[LINE_MODEL]
            .with_user(self.poster)
            .get_views([(self.line_list.id, "list")])
        )
        arch = etree.fromstring(result["views"]["list"]["arch"])
        [button] = arch.xpath("/list/groupby/button[@name='action_post']")
        self.assertEqual(
            button.get("invisible"),
            "(state != 'draft') or (__verbs and not __verbs.get('post'))",
        )
        [verbs] = arch.xpath("//field[@name='__verbs']")
        self.assertEqual(verbs.getparent().tag, "groupby")
        self.assertEqual(verbs.get("invisible"), "1")
        self.assertIsNone(verbs.get("__verbs_model__"))
        self.assertEqual(result["models"][MODEL]["fields"]["__verbs"]["type"], "json")
        self.assertNotIn("__verbs", result["models"][LINE_MODEL]["fields"])

    def test_each_user_gets_the_arch_of_their_own_reach(self):
        self.views(self.admin, self.form)
        clerk_arch, _fields = self.views(self.clerk, self.form)
        admin_arch, _fields = self.views(self.admin, self.form)
        self.assertFalse(clerk_arch.xpath("//button[@name='action_post']"))
        self.assertTrue(admin_arch.xpath("//button[@name='action_post']"))

    def test_a_record_read_answers_the_verbs_it_grants(self):
        documents = (self.mine | self.theirs).with_user(self.poster)
        read = {
            values["id"]: values["__verbs"]
            for values in documents.web_read({"name": {}, "__verbs": {}})
        }
        self.assertEqual(
            read,
            {
                self.mine.id: {"clear": False, "post": True, "retire": False},
                self.theirs.id: {"clear": False, "post": False, "retire": False},
            },
        )
        for document in documents:
            self.assertEqual(read[document.id]["post"], document.has_access("post"))

        searched = documents.web_search_read(
            [("id", "in", documents.ids)], {"name": {}, "__verbs": {}}
        )
        self.assertEqual(
            {values["id"]: values["__verbs"] for values in searched["records"]}, read
        )

    def test_an_onchange_leaves_the_verbs_to_the_read(self):
        with self.assertNoLogs("odoo.addons.web.models.web_onchange", "WARNING"):
            result = (
                self.env[MODEL]
                .with_user(self.poster)
                .onchange({}, [], {"name": {}, "state": {}, "__verbs": {}})
            )
        self.assertNotIn("__verbs", result["value"])

    def test_a_client_sending_back_what_it_read_is_answered(self):
        result = (
            self.env[MODEL]
            .with_user(self.poster)
            .onchange(
                {"name": "mine", "__verbs": {"post": True}},
                ["name"],
                {"name": {}, "__verbs": {}},
            )
        )
        self.assertNotIn("__verbs", result.get("value", {}))
        with Form(self.mine.with_user(self.poster), view=self.form) as form:
            form.name = "mine again"
        self.assertEqual(self.mine.name, "mine again")

    def test_the_verbs_leave_a_parent_s_values_and_a_line_s_too(self):
        values = {
            "name": "line",
            "__verbs": {"post": True},
            "parent_id": {"name": "parent", "__verbs": {"post": False}},
            "child_ids": [(0, "virtual_1", {"name": "l", "__verbs": {}}), (4, 7)],
        }
        self.assertEqual(
            self.env["res.partner"]._prepare_onchange_values(values),
            {
                "name": "line",
                "parent_id": {"name": "parent"},
                "child_ids": [(0, "virtual_1", {"name": "l"}), (4, 7)],
            },
        )
