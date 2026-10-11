from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.orm.runtime._loading_phase import LoadingPhase
from odoo.tests import common, tagged

from odoo.addons.base.models.ir_ui_view import IrUiView


@tagged("post_install", "-at_install")
class TestQwebViewCompiles(common.TransactionCase):
    def _create_template(self, key, arch, **values):
        return self.env["ir.ui.view"].create(
            {"name": key, "type": "qweb", "key": key, "arch": arch, **values}
        )

    def test_broken_expression_refused_on_create(self):
        with self.assertRaises(ValidationError) as caught:
            self._create_template(
                "base.qweb_validation_broken", '<t t-name="x"><p t-out="1 +"/></t>'
            )
        message = str(caught.exception)
        self.assertIn("base.qweb_validation_broken", message)
        self.assertIn("SyntaxError", message)
        self.assertIn("Path: /t/p", message)

    def test_directive_misuse_refused_on_save(self):
        for arch, expected in (
            ('<t t-name="x"><t t-foreach="[1, 2]"><p/></t></t>', "t-as"),
            ('<t t-name="x"><p t-set="a" t-out="b"/></t>', "Path: /t/p"),
            ('<t t-name="x"><p t-if="a" t-elif="b"/></t>', "Path: /t/p"),
        ):
            with (
                self.subTest(arch=arch),
                self.assertRaises(ValidationError) as caught,
            ):
                self._create_template("base.qweb_validation_directive", arch)
            self.assertIn(expected, str(caught.exception))

    def test_valid_template_accepted(self):
        view = self._create_template(
            "base.qweb_validation_valid",
            '<t t-name="x"><p t-if="a" t-out="a + 1"/></t>',
        )
        view.write({"arch": '<t t-name="x"><p t-out="(a or 0) * 2"/></t>'})
        self.assertIn("* 2", view.arch)

    def test_a_source_write_from_a_translation_aware_context_compiles(self):
        view = self._create_template(
            "base.qweb_validation_source", '<t t-name="x"><p>before</p></t>'
        ).with_context(edit_translations=False)
        view.with_context(lang=None).write({"arch": '<t t-name="x"><p>after</p></t>'})
        self.assertIn("after", view.arch)

    def test_broken_arch_refused_on_write(self):
        view = self._create_template(
            "base.qweb_validation_write", '<t t-name="x"><p t-out="a"/></t>'
        )
        with self.assertRaises(ValidationError):
            view.write({"arch": '<t t-name="x"><p t-foreach="items"/></t>'})
        self.assertIn('t-out="a"', view.arch)

    def test_extension_breaking_its_root_refused(self):
        root = self._create_template(
            "base.qweb_validation_root", '<t t-name="x"><div class="c"/></t>'
        )
        with self.assertRaises(ValidationError) as caught:
            self._create_template(
                "base.qweb_validation_extension",
                '<xpath expr="//div" position="inside"><span t-out="a b"/></xpath>',
                inherit_id=root.id,
            )
        message = str(caught.exception)
        self.assertIn("base.qweb_validation_extension", message)
        self.assertIn(f"base.qweb_validation_root (id {root.id})", message)

    def test_extension_breaking_a_primary_child_refused(self):
        root = self._create_template(
            "base.qweb_validation_parent", '<t t-name="x"><div class="c"/></t>'
        )
        self._create_template(
            "base.qweb_validation_primary_child",
            '<xpath expr="//div" position="attributes">'
            '<attribute name="title">child</attribute></xpath>',
            inherit_id=root.id,
            mode="primary",
        )
        with self.assertRaises(ValidationError) as caught:
            self._create_template(
                "base.qweb_validation_parent_extension",
                '<xpath expr="//div" position="attributes">'
                '<attribute name="t-att-data-x">a +</attribute></xpath>',
                inherit_id=root.id,
            )
        message = str(caught.exception)
        self.assertIn("base.qweb_validation_parent (id", message)
        self.assertIn("base.qweb_validation_primary_child (id", message)

    def test_missing_called_template_refused(self):
        with self.assertRaises(ValidationError) as caught:
            self._create_template(
                "base.qweb_validation_caller",
                '<t t-name="x"><t t-call="base.qweb_validation_nowhere"/></t>',
            )
        self.assertIn("base.qweb_validation_nowhere", str(caught.exception))

        callee = self._create_template(
            "base.qweb_validation_callee", '<t t-name="y"><p>callee</p></t>'
        )
        caller = self._create_template(
            "base.qweb_validation_caller",
            '<t t-name="x"><t t-call="base.qweb_validation_callee"/>'
            '<t t-call="{{ dynamic }}"/></t>',
        )
        self.assertEqual(
            self.env["ir.qweb"]
            ._render(caller.id, {"dynamic": callee.key})
            .count("callee"),
            2,
        )

    def test_a_save_compiles_with_the_savers_rights(self):
        self._create_template(
            "base.qweb_validation_rights_callee", '<t t-name="y"><p>callee</p></t>'
        )
        admin = common.new_test_user(
            self.env, login="qweb_validation_admin", groups="base.group_system"
        )
        IrQweb = type(self.env["ir.qweb"])
        compile_template = IrQweb._compile
        elevated = []

        def spy(qweb, template):
            elevated.append(qweb.env.su)
            return compile_template(qweb, template)

        with patch.object(IrQweb, "_compile", spy):
            self.env["ir.ui.view"].with_user(admin).create(
                {
                    "name": "rights caller",
                    "type": "qweb",
                    "key": "base.qweb_validation_rights_caller",
                    "arch": '<t t-name="x">'
                    '<t t-call="base.qweb_validation_rights_callee"/></t>',
                }
            )
        self.assertTrue(elevated)
        self.assertNotIn(True, elevated)

    def test_loading_defers_to_the_end_of_the_load(self):
        View = self.env["ir.ui.view"].with_context(install_mode=True)
        with patch.object(self.registry, "_loading", LoadingPhase()):
            view = View.create(
                {
                    "name": "deferred",
                    "type": "qweb",
                    "key": "base.qweb_validation_deferred",
                    "arch": '<t t-name="x"><t t-call="base.qweb_validation_later"/>'
                    '<p t-out="a"/></t>',
                }
            )
            View.create(
                {
                    "name": "later",
                    "type": "qweb",
                    "key": "base.qweb_validation_later",
                    "arch": '<t t-name="y"><p>later</p></t>',
                }
            )
            View._check_loaded_qweb_templates()

            view.write({"arch": '<t t-name="x"><p t-out="a b"/></t>'})
            with self.assertRaises(ValidationError) as caught:
                View._check_loaded_qweb_templates()
        self.assertIn("base.qweb_validation_deferred", str(caught.exception))

    def test_a_stale_extension_the_load_deletes_does_not_fail_it(self):
        root = self._create_template(
            "base.qweb_validation_upgraded", '<t t-name="x"><div class="c"/></t>'
        )
        with patch.object(IrUiView, "_check_qweb_compiles", lambda self: None):
            stale = self._create_template(
                "base.qweb_validation_stale",
                '<xpath expr="//div" position="inside"><p t-out="a b"/></xpath>',
                inherit_id=root.id,
            )
        View = self.env["ir.ui.view"].with_context(install_mode=True)
        with patch.object(self.registry, "_loading", LoadingPhase()):
            View.browse(root.id).write({"arch": '<t t-name="x"><div class="c d"/></t>'})
            stale.unlink()
            View._check_loaded_qweb_templates()
        with self.assertRaises(ValidationError):
            self._create_template(
                "base.qweb_validation_stale",
                '<xpath expr="//div" position="inside"><p t-out="a b"/></xpath>',
                inherit_id=root.id,
            )

    def test_a_deferred_block_validates_what_it_holds_before_a_commit(self):
        view = self._create_template(
            "base.qweb_validation_deferred_now", '<t t-name="x"><p t-out="a"/></t>'
        )
        with self.env["ir.ui.view"]._validation_deferred() as views:
            views.browse(view.id).write({"arch": '<t t-name="x"><p t-out="a b"/></t>'})
            with self.assertRaises(ValidationError) as caught:
                views._check_deferred_now()
            self.assertIn("base.qweb_validation_deferred_now", str(caught.exception))
            views.browse(view.id).write({"arch": '<t t-name="x"><p t-out="a"/></t>'})
            views._check_deferred_now()
        self.assertIn('t-out="a"', view.arch)


@tagged("post_install", "-at_install")
class TestInstalledQwebTemplatesCompile(common.TransactionCase):
    def test_every_active_template_compiles(self):
        View = self.env["ir.ui.view"]
        templates = View.search(
            [
                ("type", "=", "qweb"),
                "|",
                ("inherit_id", "=", False),
                ("mode", "=", "primary"),
            ]
        )
        failures = templates._get_qweb_compile_errors()
        self.assertFalse(
            failures,
            f"{len(failures)} of {len(templates)} active QWeb templates do not "
            "compile:\n\n" + "\n\n".join(failures),
        )
