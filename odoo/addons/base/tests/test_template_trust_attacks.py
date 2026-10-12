from contextlib import contextmanager

from lxml import etree

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import convert_file

PRIV = "env.cr.dbname"


@tagged("post_install", "-at_install")
class TestTemplateTrustAttacks(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = new_test_user(
            cls.env, login="av_red_author", groups="base.group_user"
        )
        cls.env["ir.access"].create(
            {
                "name": "av_red: author reads qweb views",
                "model_id": cls.env["ir.model"]._get_id("ir.ui.view"),
                "group_id": cls.env.ref("base.group_user").id,
                "kind": "permission",
                "operation": "r",
                "domain": "[('type', '=', 'qweb')]",
            }
        )
        cls.view = cls.env["ir.ui.view"].create(
            {
                "name": "trust attack host",
                "type": "qweb",
                "key": "base.av_red_host",
                "arch": '<t t-name="base.av_red_host"><p t-out="user.name"/></t>',
            }
        )

    def _refuse(self, arch, needle="not available"):
        self.view.write({"arch": arch})
        with self.assertRaisesRegex(AccessError, needle):
            self.view.with_user(self.author)._check_template_authoring()

    def _allow(self, arch):
        self.view.write({"arch": arch})
        self.view.with_user(self.author)._check_template_authoring()

    def test_t_att_dict_spread(self):
        self._refuse(
            f'<t t-name="base.av_red_host"><p t-att="{{\'x\': {PRIV}}}"/></t>',
            "the name 'env' is not available",
        )

    def test_t_options_dict(self):
        self._refuse(
            '<t t-name="base.av_red_host">'
            f'<span t-out="1" t-options="{{\'widget\': {PRIV}}}"/></t>',
            "the name 'env' is not available",
        )

    def test_t_options_suffix(self):
        self._refuse(
            '<t t-name="base.av_red_host">'
            f'<span t-out="1" t-options-widget="{PRIV}"/></t>',
            "the name 'env' is not available",
        )

    def test_t_att_name_trick(self):
        self._refuse(
            f'<t t-name="base.av_red_host"><p t-att-t-out="{PRIV}"/></t>',
            "the name 'env' is not available",
        )

    def test_t_call_with_t_set_body(self):
        self._refuse(
            '<t t-name="base.av_red_host">'
            '<t t-call="base.av_red_host">'
            f'<t t-set="x" t-value="{PRIV}"/></t></t>',
            "the name 'env' is not available",
        )

    def test_t_set_body_element(self):
        self._refuse(
            f'<t t-name="base.av_red_host"><t t-set="x"><p t-out="{PRIV}"/></t></t>',
            "the name 'env' is not available",
        )

    def test_t_field_object_part_checked(self):
        self._refuse(
            f'<t t-name="base.av_red_host"><span t-field="({PRIV}).name"/></t>',
            "the name 'env' is not available",
        )

    def test_entity_encoded_expression_still_checked(self):
        self._refuse(
            '<t t-name="base.av_red_host"><p t-out="&#x65;nv.cr.dbname"/></t>',
            "the name 'env' is not available",
        )

    def test_homoglyph_directive_name_is_invalid_xml(self):
        arch = '<t t-name="base.av_red_host"><p t‑out="env.cr.dbname">x</p></t>'
        with self.assertRaises(ValidationError):
            self.view.write({"arch": arch})

    def test_namespaced_directive_is_inert(self):
        arch = (
            '<t t-name="base.av_red_host" xmlns:z="urn:z">'
            '<p z:t-out="env.cr.dbname">y</p></t>'
        )
        self._allow(arch)
        rendered = self.env["ir.qweb"]._render(etree.fromstring(arch)).strip()
        self.assertIn("y", rendered)
        self.assertNotIn(self.env.cr.dbname, rendered)

    def test_author_cannot_write_shipped_digests(self):
        with self.assertRaises(AccessError):
            self.view.with_user(self.author).write(
                {"shipped_digests": {"arch_db": "deadbeef"}}
            )

    def test_author_cannot_create_with_shipped_digests(self):
        with self.assertRaises(AccessError):
            self.env["ir.ui.view"].with_user(self.author).create(
                {
                    "name": "trust attack vouch",
                    "type": "qweb",
                    "key": "base.av_red_vouch",
                    "arch": '<t t-name="base.av_red_vouch"><p>x</p></t>',
                    "shipped_digests": {"arch_db": "deadbeef"},
                }
            )

    def test_author_cannot_read_shipped_digests(self):
        with self.assertRaises(AccessError):
            self.view.with_user(self.author).read(["shipped_digests"])

    def test_copy_does_not_carry_shipped_digests(self):
        shipped = self.env.ref("web.preview_internalreport")
        self.assertTrue(shipped.shipped_digests)
        copy = shipped.copy({"key": shipped.key})
        self.assertFalse(copy.shipped_digests)


@tagged("post_install", "-at_install")
class TestTemplateContextAttacks(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = new_test_user(
            cls.env, login="av_ctx_author", groups="base.group_user"
        )
        cls.env["ir.access"].create(
            {
                "name": "av_ctx: author reads qweb views",
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

    @contextmanager
    def authored(self, arch, priority=16):
        ext = self.env["ir.ui.view"].create(
            {
                "name": "context attack authored",
                "type": "qweb",
                "inherit_id": self.page.id,
                "priority": priority,
                "arch": arch,
            }
        )
        try:
            yield ext
        finally:
            ext.unlink()

    def check(self, ext):
        ext.with_user(self.author)._check_template_authoring()
        ext.with_user(self.author)._check_template_contexts()

    def assertRefused(self, arch, reason, priority=16):
        with (
            self.authored(arch, priority) as ext,
            self.assertRaisesRegex(AccessError, reason),
        ):
            self.check(ext)

    def test_parameter_injected_into_a_trusted_t_call(self):
        self.assertRefused(
            '<xpath expr="//t[@t-call]" position="inside">'
            '<t t-set="card" t-value="user"/></xpath>',
            "bound differently|what it evaluates changes|moved or wrapped",
        )

    def test_moving_a_trusted_secret_out_of_its_guard(self):
        self.assertRefused(
            '<xpath expr="//div[@id=\'guard\']" position="after">'
            '<xpath expr="//p[hasclass(\'secret\')]" position="move"/></xpath>',
            "moved or wrapped|removed or replaced|evaluates",
            priority=1,
        )

    def test_impostor_anchor_among_siblings_is_harmless(self):
        with self.authored(
            '<xpath expr="//p[@id=\'anchor\']" position="before">'
            '<p id="anchor">impostor</p></xpath>',
            priority=1,
        ) as ext:
            self.check(ext)

    def test_wrap_trusted_set_in_authored_foreach(self):
        self.assertRefused(
            '<xpath expr="//span[hasclass(\'greeting\')]" position="replace">'
            '<t t-foreach="user.partner_id.child_ids" t-as="x">'
            '<span class="greeting" t-out="partner.name"/></t></xpath>',
            "moved or wrapped|removed or replaced",
        )

    def test_a_plain_section_added_is_allowed(self):
        with self.authored(
            '<xpath expr="//p[@id=\'free\']" position="after">'
            "<section><p>Legitimate authored content</p></section></xpath>"
        ) as ext:
            self.check(ext)
