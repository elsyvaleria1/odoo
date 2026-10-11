"""What `mixin.mail.render` promises its callers, asserted rather than assumed.

Each class here pins one contract the 2026-08-18 audit found the module was not
keeping. They are grouped by the promise, not by the method, because the point
of each is what a caller may rely on.
"""

from markupsafe import Markup

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.mail.tests import common


def _get_scanning(original, scanned):
    def scanning(self, source, model, fname=None):
        scanned.append(fname)
        return original(self, source, model, fname=fname)

    return scanning


@tagged("mail_render", "post_install", "-at_install")
class TestEncapsulateContext(common.MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.record = cls.env["mail.test.track"].create(
            {"name": "Rec", "email_from": "rec@test.example.com"}
        )
        cls.body = Markup("<p>the body</p>")
        cls.layouts = ["mail.mail_notification_layout", "mail.mail_notification_light"]

    def test_a_supplied_subtype_does_not_raise(self):
        subtype = self.env.ref("mail.mt_note")
        for layout in self.layouts:
            with self.subTest(layout=layout):
                rendered = self.env["mixin.mail.render"]._render_encapsulate(
                    layout,
                    self.body,
                    add_context={"subtype": subtype},
                    context_record=self.record,
                )
                self.assertIn("the body", rendered)

    def test_an_explicit_none_record_name_does_not_desync_the_subtitle(self):
        ctx = self.env["mixin.mail.render"]._render_encapsulate_context(
            self.body, {"record_name": None}, self.record
        )
        self.assertEqual(ctx["record_name"], "Rec")
        self.assertEqual(ctx["subtitles"], ["Rec"])

        absent = self.env["mixin.mail.render"]._render_encapsulate_context(
            self.body, {}, self.record
        )
        self.assertEqual(absent["record_name"], ctx["record_name"])
        self.assertEqual(absent["subtitles"], ctx["subtitles"])

    def test_a_caller_supplied_record_name_still_wins(self):
        ctx = self.env["mixin.mail.render"]._render_encapsulate_context(
            self.body, {"record_name": "Chosen"}, self.record
        )
        self.assertEqual(ctx["record_name"], "Chosen")
        self.assertEqual(ctx["subtitles"], ["Chosen"])

    def test_the_model_description_comes_from_the_hook(self):
        expected = self.record.with_context(lang=self.env.lang)._get_model_description(
            self.record._name
        )
        ctx = self.env["mixin.mail.render"]._render_encapsulate_context(
            self.body, {}, self.record
        )
        self.assertEqual(ctx["model_description"], expected)

    def test_no_context_record_is_not_an_error(self):
        ctx = self.env["mixin.mail.render"]._render_encapsulate_context(
            self.body, {}, None
        )
        self.assertEqual(ctx["record_name"], "")
        self.assertFalse(ctx["model_description"])
        self.assertEqual(ctx["company"], self.env.company)


@tagged("mail_render", "post_install", "-at_install")
class TestRenderLangContract(common.MailCommon):

    def test_a_template_with_no_model_answers_rather_than_raising(self):
        template = self.env["mail.template"].create({"name": "no model"})
        record = self.env["mail.test.track"].create(
            {"name": "R", "email_from": "r@test.example.com"}
        )
        self.assertEqual(template._render_lang([record.id]), {record.id: False})

    def test_every_id_gets_an_answer(self):
        template = self.env["mail.template"].create(
            {
                "name": "with model",
                "model_id": self.env["ir.model"]._get("mail.test.track").id,
            }
        )
        records = self.env["mail.test.track"].create(
            [
                {"name": "A", "email_from": "a@test.example.com"},
                {"name": "B", "email_from": "b@test.example.com"},
            ]
        )
        self.assertEqual(set(template._render_lang(records.ids)), set(records.ids))


@tagged("mail_render", "post_install", "-at_install")
class TestDynamicFieldNames(common.MailCommon):

    def test_a_declaring_model_is_taken_at_its_word(self):
        from odoo.addons.mail.models.mail_template import DYNAMIC_FIELD_NAMES

        self.assertEqual(
            self.env["mail.template"]._get_dynamic_field_names(),
            set(DYNAMIC_FIELD_NAMES),
        )

    def test_a_silent_model_still_gets_the_inferred_set(self):
        composer = self.env["wizard.mail.message.send"]
        inferred = {
            fname
            for fname, field in composer._fields.items()
            if field.type in ("char", "text", "html") and field.store
        }
        self.assertEqual(composer._get_dynamic_field_names(), inferred)
        self.assertIn("body", inferred)


@tagged("mail_render", "post_install", "-at_install")
class TestRendererSerialisationAgrees(common.MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = "mail.test.track"
        cls.record = cls.env[cls.model].create(
            {"name": "Rec", "email_from": "rec@test.example.com"}
        )

    def _both(self, markup):
        mixin = self.env["mixin.mail.render"]
        static = mixin._render_template_qweb(
            markup + '<b t-out="object.name"/>', self.model, [self.record.id]
        )[self.record.id]
        evaluated = mixin._render_template_qweb(
            markup + '<b t-out="object.name or None"/>', self.model, [self.record.id]
        )[self.record.id]
        return str(static), str(evaluated)

    def test_the_two_renderers_serialise_the_same_html_the_same_way(self):
        for markup in (
            "<p>a<br/>b</p>",
            "<p>a<br>b</p>",
            '<img src="x"/>',
            '<div/aa t-nothing="1"></div/aa>',
            '<input type="checkbox" checked/>',
            "<p>&nbsp;x</p>",
            "<p></p>",
            "<div><span></span></div>",
            "<hr/>",
        ):
            with self.subTest(markup=markup):
                static, evaluated = self._both(markup)
                self.assertEqual(static, evaluated)

    def test_an_empty_body_is_empty_not_a_collapsed_wrapper(self):
        rendered = self.env["mixin.mail.render"]._render_template_qweb(
            '<t t-out="object.user_id.name"/>', self.model, [self.record.id]
        )[self.record.id]
        self.assertEqual(str(rendered), "")

    def test_a_void_element_keeps_its_self_closing_form(self):
        static, evaluated = self._both("<p>x<br/>y</p>")
        self.assertIn("<br/>", static)
        self.assertEqual(static, evaluated)

    def test_the_two_renderers_escape_a_value_the_same_way(self):
        mixin = self.env["mixin.mail.render"]
        for name in ('say "hi"', "it's", "a & b", "<b>x</b>", "ünï", "plain"):
            with self.subTest(name=name):
                record = self.env[self.model].create(
                    {"name": name, "email_from": "v@test.example.com"}
                )
                static = mixin._render_template_qweb(
                    '<p t-out="object.name"/>', self.model, [record.id]
                )[record.id]
                evaluated = mixin._render_template_qweb(
                    '<p t-out="object.name or None"/>', self.model, [record.id]
                )[record.id]
                self.assertEqual(str(static), str(evaluated))

    def test_a_markup_value_is_inserted_as_markup(self):
        mixin = self.env["mixin.mail.render"]
        self.env.user.signature = Markup("<b>Sig &amp; co</b>")
        record = self.env[self.model].create(
            {"name": "M", "email_from": "m@test.example.com", "user_id": self.env.uid}
        )
        static = str(
            mixin._render_template_qweb(
                '<p t-out="object.user_id.signature"/>', self.model, [record.id]
            )[record.id]
        )
        self.assertIn("<b>Sig &amp; co</b>", static)

    def test_a_template_with_no_placeholder_is_still_rendered(self):
        rendered = self.env["mixin.mail.render"]._render_template_qweb(
            "<p>nothing dynamic</p>", self.model, [self.record.id]
        )[self.record.id]
        self.assertEqual(str(rendered), "<p>nothing dynamic</p>")


@tagged("mail_render", "post_install", "-at_install")
class TestStaticMarkerIntegrity(common.MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = "mail.test.track"
        cls.record = cls.env[cls.model].create(
            {"name": "Rec", "email_from": "marker@test.example.com"}
        )

    MARKER = "\ue000{}\ue001"

    def _render(self, src):
        return str(
            self.env["mixin.mail.render"]._render_template_qweb(
                src, self.model, [self.record.id]
            )[self.record.id]
        )

    def test_a_marker_in_the_body_does_not_become_a_placeholder(self):
        marker = self.MARKER.format(0)
        rendered = self._render(f'<p>{marker}</p><b t-out="object.name">d</b>')
        self.assertIn(marker, rendered)
        self.assertEqual(rendered.count("Rec"), 1)

    def test_a_marker_naming_a_slot_that_does_not_exist_is_not_a_crash(self):
        rendered = self._render(
            f'<p>{self.MARKER.format(5)}</p><b t-out="object.name">d</b>'
        )
        self.assertIn("Rec", rendered)


@tagged("mail_render", "post_install", "-at_install")
class TestEmptyRelationRendersTheDefault(common.MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = "mail.test.track"
        cls.record = cls.env[cls.model].create(
            {"name": "NoUser", "email_from": "nouser@test.example.com"}
        )
        cls.force_evaluation = '<i t-out="1 + 1"/>'

    def test_every_engine_answers_the_default(self):
        mixin = self.env["mixin.mail.render"]
        cases = [
            ("inline_template", "{{ object.user_id ||| nobody}}", "nobody"),
            ("qweb", '<p t-out="object.user_id">nobody</p>', "<p>nobody</p>"),
            (
                "qweb",
                '<p t-out="object.user_id">nobody</p>' + self.force_evaluation,
                "<p>nobody</p><i>2</i>",
            ),
        ]
        for engine, src, expected in cases:
            with self.subTest(engine=engine, src=src):
                self.assertEqual(
                    str(
                        mixin._render_template(
                            src, self.model, [self.record.id], engine=engine
                        )[self.record.id]
                    ),
                    expected,
                )

    def test_a_filled_relation_still_renders_its_display_name(self):
        record = self.env[self.model].create(
            {
                "name": "WithUser",
                "email_from": "withuser@test.example.com",
                "user_id": self.env.uid,
            }
        )
        mixin = self.env["mixin.mail.render"]
        for src in (
            '<p t-out="object.user_id">nobody</p>',
            '<p t-out="object.user_id">nobody</p>' + self.force_evaluation,
        ):
            with self.subTest(src=src):
                rendered = str(
                    mixin._render_template_qweb(src, self.model, [record.id])[record.id]
                )
                self.assertIn(self.env.user.display_name, rendered)
                self.assertNotIn("nobody", rendered)


@tagged("mail_render", "post_install", "-at_install")
class TestStaticExpressionRoots(common.MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = "mail.test.track"
        cls.record = cls.env[cls.model].create(
            {"name": "Roots", "email_from": "roots@test.example.com"}
        )

    def test_an_unreachable_root_does_not_raise_and_does_not_diverge(self):
        model_cls = type(self.env[self.model])
        original = model_cls.mail_allowed_qweb_expressions
        self.patch(
            model_cls,
            "mail_allowed_qweb_expressions",
            lambda self: (*original(self), "env.uid"),
        )
        mixin = self.env["mixin.mail.render"]
        evaluation_free = str(
            mixin._render_template_qweb(
                '<p t-out="env.uid"/>', self.model, [self.record.id]
            )[self.record.id]
        )
        evaluated = str(
            mixin._render_template_qweb(
                '<p t-out="env.uid"/><i t-out="1 + 1"/>', self.model, [self.record.id]
            )[self.record.id]
        )
        self.assertEqual(evaluation_free, "<p></p>")
        self.assertEqual(evaluated, "<p></p><i>2</i>")


@tagged("mail_render", "post_install", "-at_install")
class TestRenderOptionsStayInMail(common.MailCommon):

    def test_a_mail_only_option_does_not_reach_the_qweb_context(self):
        record = self.env["mail.test.track"].create(
            {"name": "Opt", "email_from": "opt@test.example.com"}
        )
        seen = []
        qweb_cls = type(self.env["ir.qweb"])
        original = qweb_cls._render_prepare
        self.patch(
            qweb_cls,
            "_render_prepare",
            lambda self, values, options: (
                seen.append(dict(options)) or original(self, values, options)
            ),
        )
        self.env["mixin.mail.render"]._render_template(
            '<p t-out="1 + 1"/>',
            "mail.test.track",
            [record.id],
            engine="qweb",
            options={"post_process": True, "preserve_comments": True},
        )
        self.assertTrue(seen, "precondition: the render must reach QWeb")
        for options in seen:
            self.assertNotIn("post_process", options)
            self.assertIn("preserve_comments", options)


@tagged("mail_render", "post_install", "-at_install")
class TestStaticProgramIsCompiledOnce(common.MailCommon):

    def test_the_decision_survives_across_renders(self):
        model = "mail.test.track"
        record = self.env[model].create(
            {"name": "Once", "email_from": "once@test.example.com"}
        )
        src = '<p t-out="object.name"/><span>%s</span>' % record.id
        calls = []
        mixin_cls = type(self.env["mixin.mail.render"])
        original = mixin_cls._has_unsafe_expression_template_qweb
        self.patch(
            mixin_cls,
            "_has_unsafe_expression_template_qweb",
            lambda self, template_src, model, fname=None: (
                calls.append(template_src)
                or original(self, template_src, model, fname=fname)
            ),
        )
        for _index in range(5):
            self.env["mixin.mail.render"]._render_template_qweb(src, model, [record.id])
        self.assertEqual(len(calls), 1, "the safety probe ran once per render")


@tagged("mail_render", "post_install", "-at_install")
class TestTheTwoRenderersAgreeOnAllowListedPlaceholders(common.MailCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = "mail.test.track"
        cls.filled = cls.env[cls.model].create(
            {
                "name": "Filled",
                "email_from": "filled@test.example.com",
                "user_id": cls.env.uid,
            }
        )
        cls.empty = cls.env[cls.model].create(
            {"name": "Empty", "email_from": "empty@test.example.com"}
        )
        cls.force_evaluation = '<i t-out="1 + 1"/>'

    def _both(self, source, record):
        mixin = self.env["mixin.mail.render"]

        def go(src):
            rendered = str(
                mixin._render_template_qweb(src, self.model, [record.id])[record.id]
            )
            return rendered.removesuffix("<i>2</i>")

        self.assertFalse(
            mixin._has_unsafe_expression_template_qweb(source, self.model),
            "precondition: the bare body must take the evaluation-free path",
        )
        self.assertTrue(
            mixin._has_unsafe_expression_template_qweb(
                source + self.force_evaluation, self.model
            ),
            "precondition: the forced body must take the QWeb path",
        )
        return go(source), go(source + self.force_evaluation)

    def test_every_allow_listed_placeholder_reads_the_same_on_both(self):
        cases = [
            ('<p t-out="object.name"/>', "filled", "a field the model has"),
            ('<p t-out="object.contact_name"/>', "filled", "a field it does not"),
            ('<p t-out="object.contact_name">cn</p>', "filled", "…with a default"),
            ('<p t-out="object.partner_id">no partner</p>', "filled", "a m2o it lacks"),
            ('<p t-out="object.user_id"/>', "empty", "an unset m2o"),
            ('<p t-out="object.user_id">nobody</p>', "empty", "…with a default"),
            ('<p t-out="object.user_id"/>', "filled", "a set m2o"),
            ('<p t-out="object.user_id.name"/>', "filled", "a path through a m2o"),
            (
                '<p t-out="object.user_id.name">nn</p>',
                "empty",
                "…unset, with a default",
            ),
            ('<p t-out="object.user_id.signature"/>', "filled", "an html value"),
        ]
        for source, which, label in cases:
            with self.subTest(case=label, source=source):
                evaluation_free, evaluated = self._both(source, getattr(self, which))
                self.assertEqual(evaluation_free, evaluated)

    def test_an_allow_listed_field_the_model_lacks_is_not_an_error(self):
        evaluation_free, evaluated = self._both(
            '<p t-out="object.contact_name">cn</p>', self.filled
        )
        self.assertEqual(evaluation_free, "<p>cn</p>")
        self.assertEqual(evaluated, "<p>cn</p>")

    def test_a_valueless_placeholder_keeps_its_element_on_both(self):
        evaluation_free, evaluated = self._both(
            '<p t-out="object.user_id"/>', self.empty
        )
        self.assertEqual(evaluation_free, "<p></p>")
        self.assertEqual(evaluated, "<p></p>")

    def test_a_non_allow_listed_expression_still_reaches_the_evaluator(self):
        rendered = self.env["mixin.mail.render"]._render_template_qweb(
            '<p t-out="object.name.upper()"/>', self.model, [self.filled.id]
        )[self.filled.id]
        self.assertEqual(str(rendered), "<p>FILLED</p>")


@tagged("mail_render", "post_install", "-at_install")
class TestRenderModelIsChecked(common.MailCommon):

    def test_a_template_without_a_model_says_so(self):
        template = self.env["mail.template"].create(
            {"name": "no model", "subject": "Hi {{ object.name }}"}
        )
        record = self.env["mail.test.track"].create(
            {"name": "R", "email_from": "r@test.example.com"}
        )
        self.assertFalse(template.render_model)
        with self.assertRaises(UserError):
            template._render_field("subject", [record.id])

    def test_an_unknown_model_says_so_too(self):
        with self.assertRaises(UserError):
            self.env["mixin.mail.render"]._render_template(
                "x", "no.such.model", [1], engine="inline_template"
            )


@tagged("mail_render", "post_install", "-at_install")
class TestUnsafeExpressionScanScope(common.MailCommon):

    def test_a_qweb_view_field_is_not_scanned_as_a_template_body(self):
        template = self.env["mail.template"].create(
            {
                "name": "view engine",
                "model_id": self.env["ir.model"]._get("mail.test.track").id,
                "subject": "Hi {{ object.name }}",
                "body_html": Markup('<p t-out="object.name"/>'),
            }
        )
        scanned = []
        mixin_cls = type(template)
        for name in (
            "_has_unsafe_expression_template_qweb",
            "_has_unsafe_expression_template_inline_template",
        ):
            self.patch(
                mixin_cls, name, _get_scanning(getattr(mixin_cls, name), scanned)
            )
        self.assertEqual(template._fields["body_html"].render_engine, "qweb")
        self.patch(template._fields["body_html"], "render_engine", "qweb_view")
        template._has_unsafe_expression()
        self.assertIn("subject", scanned, "precondition: the scan ran at all")
        self.assertNotIn(
            "body_html", scanned, "a view reference was scanned as placeholder text"
        )

    def test_the_scan_reports_fields_in_a_stable_order(self):
        template = self.env["mail.template"].create(
            {
                "name": "order",
                "model_id": self.env["ir.model"]._get("mail.test.track").id,
                "subject": "Hi {{ object.name }}",
                "email_to": "{{ object.email_from }}",
            }
        )
        seen = []
        mixin_cls = type(template)
        original = mixin_cls._has_unsafe_expression_template_inline_template
        self.patch(
            mixin_cls,
            "_has_unsafe_expression_template_inline_template",
            lambda self, source, model, fname=None: (
                seen.append(fname) or original(self, source, model, fname=fname)
            ),
        )
        template._has_unsafe_expression()
        self.assertEqual(seen, sorted(seen))
