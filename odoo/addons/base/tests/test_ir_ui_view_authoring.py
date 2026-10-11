from contextlib import contextmanager

from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import convert_file
from odoo.tools.convert import convert_csv_import, xml_import
from odoo.tools.misc import file_path

from odoo.addons.base.models.ir_qweb import template_trust_digest

SAMPLE = "This is a sample of an internal report."


def digest(arch):
    return template_trust_digest(etree.fromstring(arch))


@tagged("post_install", "-at_install")
class TestIrUiViewAuthoring(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = new_test_user(
            cls.env, login="view_author", groups="base.group_user"
        )
        cls.env["ir.access"].create(
            {
                "name": "Probe: the author reads qweb views, like a website designer",
                "model_id": cls.env["ir.model"]._get_id("ir.ui.view"),
                "group_id": cls.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "r",
                "domain": "[('type', '=', 'qweb')]",
            }
        )
        cls.privileged = "env['res.users'].search([]).login"
        cls.view = cls.env["ir.ui.view"].create(
            {
                "name": "authoring",
                "type": "qweb",
                "key": "base.test_authoring",
                "arch": f'<t t-name="base.test_authoring"><p t-out="{cls.privileged}"/></t>',
            }
        )
        cls.shipped = cls.env.ref("web.preview_internalreport")

    def check_as(self, user, arch):
        self.view.write({"arch": arch})
        self.view.with_user(user)._check_template_authoring()

    def website_copy(self):
        return self.shipped.copy({"key": self.shipped.key})

    def edited_copy(self, old, new):
        copy = self.website_copy()
        self.assertIn(old, copy.arch_db)
        copy.arch = copy.arch_db.replace(old, new)
        return copy

    def test_a_new_expression_below_settings_must_obey_the_grammar(self):
        with self.assertRaisesRegex(AccessError, "the name 'env' is not available"):
            self.check_as(
                self.author,
                '<t t-name="base.test_authoring"><p t-out="env.user.password"/></t>',
            )

    def test_an_expression_the_view_already_held_vouches_for_nothing(self):
        with self.assertRaisesRegex(AccessError, "the name 'env' is not available"):
            self.check_as(
                self.author,
                f'<t t-name="base.test_authoring"><p t-out="{self.privileged}"/>'
                '<p t-out="user.name"/></t>',
            )

    def test_a_template_a_module_ships_is_trusted(self):
        self.shipped.with_user(self.author)._check_template_authoring()

    def test_the_key_of_a_shipped_template_lends_no_trust(self):
        borrower = self.env["ir.ui.view"].create(
            {
                "name": "borrower",
                "type": "qweb",
                "key": self.shipped.key,
                "arch": f'<t t-name="{self.shipped.key}">'
                '<t t-set="company" t-value="env.company"/>'
                '<p t-out="company.name"/></t>',
            }
        )
        with self.assertRaisesRegex(AccessError, "the name 'env' is not available"):
            borrower.with_user(self.author)._check_template_authoring()

    def test_an_extension_of_a_shipped_template_borrows_nothing(self):
        extension = self.env["ir.ui.view"].create(
            {
                "name": "borrowing extension",
                "type": "qweb",
                "inherit_id": self.shipped.id,
                "arch": '<xpath expr="//div[hasclass(\'page\')]" position="inside">'
                '<p t-out="env.company"/></xpath>',
            }
        )
        with self.assertRaisesRegex(AccessError, "the name 'env' is not available"):
            extension.with_user(self.author)._check_template_authoring()

    def test_a_copy_keeps_the_trust_of_its_text(self):
        self.website_copy().with_user(self.author)._check_template_authoring()
        edited = self.edited_copy(SAMPLE, "Edited by a designer.")
        edited.with_user(self.author)._check_template_authoring()

    def test_a_copy_edited_where_it_evaluates_is_authored(self):
        for old, new in (
            ('t-value="res_company"', 't-value="user.company_id"'),
            ("<p>", '<p t-if="user">'),
            ("<p>", '<p t-out="env.company">'),
        ):
            copy = self.edited_copy(old, new)
            with (
                self.subTest(edit=new),
                self.assertRaisesRegex(AccessError, "the name 'env' is not available"),
            ):
                copy.with_user(self.author)._check_template_authoring()

    def test_a_translation_keeps_the_trust_of_its_text(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        copy = self.website_copy()
        copy.update_field_translations(
            "arch_db", {"fr_FR": {SAMPLE: "Ceci est un exemple."}}
        )
        translated = copy.with_context(lang="fr_FR")
        self.assertIn("Ceci est un exemple.", translated.arch_db)
        translated.with_user(self.author)._check_template_authoring()

    def test_an_unknown_directive_is_refused(self):
        for body in (
            '<p t-foo="user.name"/>',
            '<p t-esc-options="{}"/>',
            '<p t-out="1" t-call-options="env.cr.dbname"/>',
        ):
            with (
                self.subTest(body=body),
                self.assertRaisesRegex(AccessError, "the directive is not available"),
            ):
                self.check_as(
                    self.author, f'<t t-name="base.test_authoring">{body}</t>'
                )
        extension = self.env["ir.ui.view"].create(
            {
                "name": "unknown directive extension",
                "type": "qweb",
                "inherit_id": self.view.id,
                "arch": '<xpath expr="//p" position="attributes">'
                '<attribute name="t-foo">user.name</attribute></xpath>',
            }
        )
        with self.assertRaisesRegex(AccessError, "the directive is not available"):
            extension.with_user(self.author)._check_template_authoring()

    def load(self, mode, arch):
        xml_import(
            self.env,
            "web",
            {},
            mode,
            xml_filename=file_path("web/views/report_templates.xml"),
        ).parse(
            etree.fromstring(
                '<odoo><record id="test_loaded" model="ir.ui.view">'
                '<field name="name">loaded</field><field name="type">qweb</field>'
                '<field name="key">base.test_loaded</field>'
                f'<field name="arch" type="xml">{arch}</field></record></odoo>'
            )
        )
        return self.env.ref("web.test_loaded")

    def test_a_module_file_records_the_digest_of_what_it_loads(self):
        first = '<t t-name="base.test_loaded"><p t-out="env.cr.dbname"/></t>'
        second = '<t t-name="base.test_loaded"><p t-out="env.company.name"/></t>'
        loaded = self.load("init", first)
        self.assertEqual(loaded.shipped_digests, {"arch_db": digest(first)})
        authored = self.env["ir.ui.view"].create(
            {
                "name": "same text",
                "type": "qweb",
                "key": "base.test_same",
                "arch": first,
            }
        )
        self.assertFalse(authored.sudo().shipped_digests)
        authored.with_user(self.author)._check_template_authoring()
        self.assertEqual(self.load("update", second), loaded)
        self.assertEqual(loaded.shipped_digests, {"arch_db": digest(second)})
        with self.assertRaisesRegex(AccessError, "the name 'env' is not available"):
            authored.with_user(self.author)._check_template_authoring()

    def test_a_module_csv_file_records_the_digest_of_what_it_loads(self):
        arch = "<t t-name='base.test_csv'><p t-out='env.cr.dbname'/></t>"
        convert_csv_import(
            self.env,
            "base",
            "base/tests/ir.ui.view.csv",
            f'id,name,type,key,arch_db\ntest_csv,csv,qweb,base.test_csv,"{arch}"\n'.encode(),
        )
        self.assertEqual(
            self.env.ref("base.test_csv").shipped_digests, {"arch_db": digest(arch)}
        )

    def test_a_context_key_does_not_make_a_write_the_loaders(self):
        forged = (
            self.env["ir.ui.view"]
            .sudo()
            .with_context(
                install_mode=True,
                install_module="web",
                install_filename=file_path("web/views/report_templates.xml"),
                install_xmlid="test_forged",
            )
        )
        arch = f'<t t-name="base.test_forged"><p t-out="{self.privileged}"/></t>'
        created = forged.create(
            {"name": "forged", "type": "qweb", "key": "base.test_forged", "arch": arch}
        )
        rewritten = '<t t-name="base.test_authoring"><p t-out="env.cr.dbname"/></t>'
        forged.browse(self.view.id).arch = rewritten
        self.assertFalse(created.shipped_digests)
        self.assertFalse(self.view.sudo().shipped_digests)
        with self.assertRaisesRegex(AccessError, "the name 'env' is not available"):
            created.with_user(self.author)._check_template_authoring()
        with self.assertRaisesRegex(AccessError, "the name 'env' is not available"):
            self.check_as(self.author, rewritten)

    def test_an_author_cannot_vouch_for_a_text(self):
        self.env["ir.access"].create(
            {
                "name": "Probe: the author writes qweb views, like a website designer",
                "model_id": self.env["ir.model"]._get_id("ir.ui.view"),
                "group_id": self.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "cru",
                "domain": "[('type', '=', 'qweb')]",
            }
        )
        arch = '<t t-name="base.test_vouched"><p t-out="env.cr.dbname"/></t>'
        with self.assertRaisesRegex(AccessError, 'the field "shipped_digests"'):
            self.env["ir.ui.view"].with_user(self.author).create(
                {
                    "name": "vouched",
                    "type": "qweb",
                    "key": "base.test_vouched",
                    "arch": arch,
                    "shipped_digests": {"arch_db": digest(arch)},
                }
            )
        with self.assertRaisesRegex(AccessError, 'the field "shipped_digests"'):
            self.view.with_user(self.author).write(
                {"shipped_digests": {"arch_db": digest(self.view.arch_db)}}
            )

    def test_a_rebound_formatter_is_refused(self):
        with self.assertRaisesRegex(AccessError, "cannot be rebound"):
            self.check_as(
                self.author,
                '<t t-name="base.test_authoring">'
                '<t t-set="format_date" t-value="user.name"/></t>',
            )

    def test_settings_users_are_not_restricted(self):
        self.check_as(
            self.env.ref("base.user_admin"),
            '<t t-name="base.test_authoring"><p t-out="env.user.password"/></t>',
        )

    def test_a_privileged_view_created_below_settings_is_refused(self):
        with self.assertRaises(AccessError):
            self.view.with_user(self.author).sudo(False)._check_template_authoring()
        self.assertTrue(
            self.view.with_user(self.author)._is_restricted_template_author()
        )
        self.assertFalse(self.view.sudo()._is_restricted_template_author())

    def test_the_audit_lists_every_stored_text_no_module_ships(self):
        borrower = self.env["ir.ui.view"].create(
            {
                "name": "borrower",
                "type": "qweb",
                "key": self.shipped.key,
                "arch": f'<t t-name="{self.shipped.key}"><p t-out="env.company"/></t>',
            }
        )
        copy = self.edited_copy(SAMPLE, "Edited by a designer.")
        findings = self.env["ir.ui.view"]._audit_template_authoring()
        entry = f"base.test_authoring ({self.view.id})"
        self.assertIn(entry, findings)
        self.assertIn("the name 'env' is not available", findings[entry][0])
        self.assertIn(f"{self.shipped.key} ({borrower.id})", findings)
        self.assertNotIn(f"{self.shipped.key} ({self.shipped.id})", findings)
        self.assertNotIn(f"{copy.key} ({copy.id})", findings)

    def test_every_form_that_compiles_an_expression_obeys_the_grammar(self):
        for body in (
            "<t t-set=\"{'x': env.cr.dbname}\"/>",
            '<t t-set="x" t-valuef.translate="{{ env.cr.dbname }}"/>',
        ):
            with (
                self.subTest(body=body),
                self.assertRaisesRegex(AccessError, "the name 'env' is not available"),
            ):
                self.check_as(
                    self.author, f'<t t-name="base.test_authoring">{body}</t>'
                )

    def test_a_mapping_cannot_rebind_a_formatter_or_hide_what_it_binds(self):
        for body, refusal in (
            ("<t t-set=\"{'format_date': user.name}\"/>", "cannot be rebound"),
            (
                '<t t-call="base.test_authoring" t-args="{\'format_date\': 1}"/>',
                "cannot be rebound",
            ),
            ('<t t-call="base.test_authoring" t-args="user"/>', "spell out"),
        ):
            with (
                self.subTest(body=body),
                self.assertRaisesRegex(AccessError, refusal),
            ):
                self.check_as(
                    self.author, f'<t t-name="base.test_authoring">{body}</t>'
                )

    def test_an_extension_setting_a_directive_obeys_the_grammar(self):
        extension = self.env["ir.ui.view"].create(
            {
                "name": "authoring extension",
                "type": "qweb",
                "inherit_id": self.view.id,
                "arch": '<xpath expr="//p" position="attributes">'
                '<attribute name="class">btn btn-primary</attribute>'
                '<attribute name="t-if">user.name</attribute></xpath>',
            }
        )
        extension.with_user(self.author)._check_template_authoring()
        for spec in (
            '<attribute name="t-out">env.cr.dbname</attribute>',
            '<attribute name="t-attf-class" add="{{ env.cr.dbname }}" separator=" "/>',
            '<attribute name="label">env.cr.dbname</attribute>',
        ):
            extension.arch = f'<xpath expr="//p" position="attributes">{spec}</xpath>'
            with (
                self.subTest(spec=spec),
                self.assertRaisesRegex(AccessError, "the name 'env' is not available"),
            ):
                extension.with_user(self.author)._check_template_authoring()

    def test_every_directive_the_compiler_knows_is_classified(self):
        qweb = self.env["ir.qweb"]
        directives = qweb._get_authoring_directives()
        prefix = "_compile_directive_"
        unclassified = sorted(
            f"t-{name.removeprefix(prefix).replace('_', '-')}"
            for name in dir(type(qweb))
            if name.startswith(prefix)
            and f"t-{name.removeprefix(prefix).replace('_', '-')}" not in directives
        )
        self.assertEqual(
            unclassified,
            [],
            "a directive the authoring check cannot classify is one it cannot check",
        )


@tagged("post_install", "-at_install")
class TestTemplateContextAuthoring(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = new_test_user(
            cls.env, login="context_author", groups="base.group_user"
        )
        cls.env["ir.access"].create(
            {
                "name": "Probe: the author reads qweb views, like a website designer",
                "model_id": cls.env["ir.model"]._get_id("ir.ui.view"),
                "group_id": cls.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "r",
                "domain": "[('type', '=', 'qweb')]",
            }
        )

        convert_file(
            cls.env,
            module="base",
            filename="tests/test_ir_ui_view_context.xml",
            idref={},
            mode="init",
            noupdate=False,
        )
        cls.page = cls.env.ref("base.test_context_page")
        cls.module_extension = cls.env.ref("base.test_context_module_extension")
        cls.guard = cls.env.ref("base.test_context_guard")
        cls.option = cls.env.ref("base.test_context_option")

    def create_authored(self, arch, priority=16):
        return self.env["ir.ui.view"].create(
            {
                "name": "authored extension",
                "type": "qweb",
                "inherit_id": self.page.id,
                "priority": priority,
                "arch": arch,
            }
        )

    @contextmanager
    def authored(self, arch, priority=16):
        extension = self.create_authored(arch, priority)
        try:
            yield extension
        finally:
            extension.unlink()

    def check(self, extension):
        extension.with_user(self.author)._check_template_authoring()
        extension.with_user(self.author)._check_template_contexts()

    def assertRefused(self, arch, reason, priority=16):
        with (
            self.authored(arch, priority) as extension,
            self.assertRaisesRegex(AccessError, reason),
        ):
            self.check(extension)

    def test_the_module_text_alone_is_not_checked(self):
        self.page.with_user(self.author)._check_template_contexts()
        self.module_extension.with_user(self.author)._check_template_contexts()

    def test_an_extension_cannot_change_what_a_shipped_element_evaluates(self):
        for target, spec in (
            ("//t[@t-set='partner']", '<attribute name="t-value">user</attribute>'),
            ("//t[@t-set='partner']", '<attribute name="t-set">guest</attribute>'),
            ("//div[@id='guard']", '<attribute name="t-if">True</attribute>'),
            ("//div[@id='guard']", '<attribute name="t-if"></attribute>'),
            (
                "//span[hasclass('greeting')]",
                '<attribute name="t-out">partner.email</attribute>',
            ),
            (
                "//span[hasclass('greeting')]",
                '<attribute name="t-att-title">partner.email</attribute>',
            ),
            (
                "//span[hasclass('greeting')]",
                '<attribute name="t-attf-title">{{ partner.email }}</attribute>',
            ),
            (
                "//span[hasclass('greeting')]",
                "<attribute name=\"t-options\">{'widget': 'contact'}</attribute>",
            ),
            ("//li", '<attribute name="t-foreach">user.partner_id</attribute>'),
            ("//li", '<attribute name="t-as">partner</attribute>'),
            (
                "//t[@t-call]",
                '<attribute name="t-call">base.test_context_page</attribute>',
            ),
            ("//t[@t-call]", '<attribute name="card">user</attribute>'),
            ("//p[@id='free']", '<attribute name="t-field">partner.email</attribute>'),
            ("//p[@id='free']", '<attribute name="t-esc">partner.email</attribute>'),
            (
                "//p[hasclass('phone')]",
                '<attribute name="t-out">partner.email</attribute>',
            ),
        ):
            with self.subTest(target=target, spec=spec):
                self.assertRefused(
                    f'<xpath expr="{target}" position="attributes">{spec}</xpath>',
                    "Only administrators may change how a template a module ships evaluates",
                )

    def test_an_extension_cannot_replace_a_shipped_element_that_evaluates(self):
        for target, replacement in (
            (
                "//span[hasclass('greeting')]",
                '<span class="greeting" t-out="partner.email"/>',
            ),
            ("//span[hasclass('greeting')]", '<span class="greeting">Hello</span>'),
            ("//t[@t-set='partner']", '<t t-set="partner" t-value="user.partner_id"/>'),
            ("//div[@id='guard']", '<div id="guard"><p class="secret">x</p></div>'),
            ("//p[hasclass('phone')]", ""),
        ):
            with self.subTest(target=target, replacement=replacement):
                self.assertRefused(
                    f'<xpath expr="{target}" position="replace">{replacement}</xpath>',
                    "it is removed or replaced",
                )

    def test_an_extension_cannot_rebind_a_name_a_shipped_element_reads(self):
        for target, position, binding in (
            ("//div[@id='guard']", "before", '<t t-set="partner" t-value="user"/>'),
            (
                "//span[hasclass('greeting')]",
                "before",
                "<t t-set=\"{'partner': user}\"/>",
            ),
            ("//t[@t-call]", "before", '<t t-set="card" t-value="user"/>'),
            ("//t[@t-call]", "inside", '<t t-set="card" t-value="user"/>'),
            ("//t[@t-call]", "inside", '<t t-set="anything" t-value="1"/>'),
            ("//p[@id='slot']", "inside", '<t t-set="partner">guest</t>'),
        ):
            with self.subTest(target=target, position=position, binding=binding):
                self.assertRefused(
                    f'<xpath expr="{target}" position="{position}">{binding}</xpath>',
                    "a name it reads is bound differently",
                )

    def test_an_extension_cannot_move_a_shipped_element_out_of_its_guard(self):
        self.assertRefused(
            '<xpath expr="//div[@id=\'guard\']" position="before">'
            '<xpath expr="//p[hasclass(\'secret\')]" position="move"/></xpath>',
            "it is moved or wrapped",
        )

    def test_an_extension_cannot_wrap_a_shipped_element_in_directives(self):
        for target, wrapper in (
            ("//t[@t-set='partner']", '<t t-if="False">$0</t>'),
            (
                "//span[hasclass('greeting')]",
                '<t t-foreach="[user.partner_id]" t-as="partner">$0</t>',
            ),
        ):
            with self.subTest(target=target, wrapper=wrapper):
                self.assertRefused(
                    f'<xpath expr="{target}" position="replace">{wrapper}</xpath>',
                    "it is moved or wrapped",
                )

    def test_an_extension_cannot_move_the_anchor_of_a_module_extension(self):
        for arch in (
            (
                '<xpath expr="//t[@t-set=\'partner\']" position="before">'
                '<xpath expr="//p[@id=\'slot\']" position="move"/></xpath>'
            ),
            (
                '<xpath expr="//t[@t-set=\'partner\']" position="before">'
                '<p id="slot"/></xpath>'
            ),
            (
                '<xpath expr="//p[@id=\'slot\']" position="replace">'
                '<t t-foreach="[user.partner_id]" t-as="partner"><p id="slot"/></t>'
                "</xpath>"
            ),
        ):
            with self.subTest(arch=arch):
                self.assertRefused(
                    arch,
                    "Only administrators may change how a template a module ships evaluates",
                    priority=1,
                )

    def test_a_module_extension_cannot_hang_from_an_authored_one(self):
        extension = self.create_authored(
            '<xpath expr="//p[@id=\'free\']" position="after"><p id="mine"/></xpath>'
        )
        self.env["ir.ui.view"].create(
            {
                "name": "module extension of an authored one",
                "type": "qweb",
                "inherit_id": extension.id,
                "arch": '<xpath expr="//p[@id=\'mine\']" position="inside">'
                '<t t-out="user.login"/></xpath>',
                "shipped_digests": {
                    "arch_db": digest(
                        '<xpath expr="//p[@id=\'mine\']" position="inside">'
                        '<t t-out="user.login"/></xpath>'
                    )
                },
            }
        )
        with self.assertRaisesRegex(
            AccessError, "evaluates only where an author put it"
        ):
            self.check(extension)

    def test_an_author_edits_around_what_a_module_ships(self):
        for arch in (
            '<xpath expr="//p[@id=\'free\']" position="replace"><p id="free">Other text</p></xpath>',
            (
                '<xpath expr="//span[hasclass(\'greeting\')]" position="attributes">'
                '<attribute name="class" add="text-center" separator=" "/>'
                '<attribute name="style">color: red</attribute></xpath>'
            ),
            (
                '<xpath expr="//div[hasclass(\'page\')]" position="inside">'
                "<section><h2>Title</h2><p>Text</p></section></xpath>"
            ),
            (
                '<xpath expr="//div[hasclass(\'page\')]" position="inside">'
                '<section t-if="True"><t t-out="\'Hello\'"/></section></xpath>'
            ),
            (
                '<xpath expr="//div[hasclass(\'page\')]" position="inside">'
                '<t t-set="mine" t-value="1"/><p t-out="mine"/></xpath>'
            ),
            (
                '<xpath expr="//div[@id=\'guard\']" position="before">'
                '<xpath expr="//p[@id=\'free\']" position="move"/></xpath>'
            ),
            '<xpath expr="//p[@id=\'anchor\']" position="replace"><p id="anchor">Edited</p></xpath>',
            '<xpath expr="//div[@id=\'guard\']" position="inside"><p>Only for some</p></xpath>',
        ):
            for priority in (1, 16):
                with (
                    self.subTest(arch=arch, priority=priority),
                    self.authored(arch, priority) as extension,
                ):
                    self.check(extension)

    def test_an_author_edits_a_translated_template(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        self.page.update_field_translations(
            "arch_db", {"fr_FR": {"Some text": "Du texte"}}
        )
        extension = self.create_authored(
            '<xpath expr="//p[@id=\'anchor\']" position="replace"><p id="anchor">Edited</p></xpath>'
        ).with_context(lang="fr_FR")
        self.assertIn("Du texte", self.page.with_context(lang="fr_FR").arch_db)
        self.check(extension)

    def test_settings_users_are_not_restricted_where_a_template_evaluates(self):
        extension = self.create_authored(
            '<xpath expr="//div[@id=\'guard\']" position="attributes">'
            '<attribute name="t-if">True</attribute></xpath>'
        )
        extension.with_user(self.env.ref("base.user_admin"))._check_template_contexts()

    def test_the_audit_lists_a_template_an_extension_reaches_into(self):
        extension = self.create_authored(
            '<xpath expr="//div[@id=\'guard\']" position="attributes">'
            '<attribute name="t-if">True</attribute></xpath>'
        )
        findings = self.env["ir.ui.view"]._audit_template_authoring()
        entry = f"base.test_context_page ({self.page.id})"
        self.assertIn(entry, findings)
        self.assertIn("what it evaluates changes", findings[entry][0])
        self.assertNotIn(f"authored extension ({extension.id})", findings)

    def test_an_authored_template_cannot_take_the_key_of_a_shipped_one(self):
        shadow = self.env["ir.ui.view"].create(
            {
                "name": "shadow",
                "type": "qweb",
                "key": "base.test_context_card",
                "priority": 1,
                "arch": '<t t-name="base.test_context_card">'
                '<p t-out="card.email"/></t>',
            }
        )
        with self.assertRaisesRegex(
            AccessError, "base.test_context_card: it takes the key of a template"
        ):
            shadow.with_user(self.author)._check_template_contexts()
        shadow.unlink()
        card = self.env.ref("base.test_context_card")
        copy = card.copy({"key": card.key})
        copy.arch = card.arch_db.replace("<p ", '<p class="lead" ')
        copy.with_user(self.author)._check_template_contexts()
        mine = card.copy({"key": "base.test_context_mine"})
        mine.arch = card.arch_db.replace("card.name", "card.email").replace(
            "base.test_context_card", "base.test_context_mine"
        )
        mine.with_user(self.author)._check_template_contexts()

    def test_an_author_cannot_remove_a_module_guard(self):
        with self.assertRaisesRegex(AccessError, "what it evaluates changes"):
            self.guard.with_user(self.author)._check_template_removal(deactivated=True)
        self.module_extension.with_user(self.author)._check_template_removal(
            deactivated=True
        )

    def test_an_author_turns_off_an_option_a_module_ships_off(self):
        self.option.active = True
        self.option.with_user(self.author)._check_template_removal(deactivated=True)

    def test_a_view_the_author_cannot_read_takes_part_all_the_same(self):
        reader = new_test_user(
            self.env, login="context_partial_reader", groups="base.group_portal"
        )
        self.env["ir.access"].create(
            {
                "name": "Probe: the author reads the qweb views but the guard",
                "model_id": self.env["ir.model"]._get_id("ir.ui.view"),
                "group_id": self.env.ref("base.group_portal").id,
                "kind": "permission",
                "operation": "r",
                "domain": "[('type', '=', 'qweb'), "
                "('key', '!=', 'base.test_context_guard')]",
            }
        )
        with (
            self.authored(
                '<xpath expr="//p[hasclass(\'notice\')]" position="attributes">'
                '<attribute name="t-if"></attribute></xpath>'
            ) as extension,
            self.assertRaisesRegex(AccessError, "what it evaluates changes"),
        ):
            extension.with_user(reader)._check_template_contexts()
