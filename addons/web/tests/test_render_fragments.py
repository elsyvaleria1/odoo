from odoo.tests.common import TransactionCase, tagged

from odoo.addons.web.controllers.utils import Fragment, render_fragments


@tagged("web_unit")
class TestRenderFragments(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._template(
            "web.test_fragment_total",
            '<div data-fragment="web.test_fragment_total">Total: <t t-out="total"/></div>',
        )
        cls._template(
            "web.test_fragment_lines",
            """<!-- lines -->
            <ul data-fragment="cart.lines"><li t-foreach="lines" t-as="line" t-out="line"/></ul>""",
        )

    @classmethod
    def _template(cls, key, body):
        cls.env["ir.ui.view"].create(
            {"key": key, "type": "qweb", "arch": f'<t t-name="{key}">{body}</t>'}
        )

    def test_renders_each_fragment_keyed_by_template_or_explicit_key(self):
        response = render_fragments(
            self.env,
            Fragment("web.test_fragment_total", {"total": "$ 5"}),
            Fragment(
                "web.test_fragment_lines",
                {"lines": ["a", "<b>"]},
                key="cart.lines",
                swap="inner",
            ),
        )

        total, lines = response["fragments"]
        self.assertEqual(total["key"], "web.test_fragment_total")
        self.assertEqual(total["swap"], "morph")
        self.assertIn("Total: $ 5", total["html"])
        self.assertIs(type(total["html"]), str)
        self.assertEqual(lines["key"], "cart.lines")
        self.assertEqual(lines["swap"], "inner")
        self.assertIn("<li>&lt;b&gt;</li>", lines["html"])
        self.assertEqual(
            {name: response[name] for name in ("events", "redirect", "data")},
            {"events": [], "redirect": None, "data": {}},
        )

    def test_events_redirect_and_data_pass_through_in_order(self):
        response = render_fragments(
            self.env,
            events={"cart:updated": {"quantity": 3}, "cart:closed": None},
            redirect="/shop/checkout",
            data={"cart_quantity": 3},
        )

        self.assertEqual(response["fragments"], [])
        self.assertEqual(
            response["events"],
            [
                {"name": "cart:updated", "detail": {"quantity": 3}},
                {"name": "cart:closed", "detail": {}},
            ],
        )
        self.assertEqual(response["redirect"], "/shop/checkout")
        self.assertEqual(response["data"], {"cart_quantity": 3})

    def test_a_render_without_its_single_keyed_root_is_refused(self):
        cases = {
            "no attribute": "<div>x</div>",
            "another key": '<div data-fragment="other">x</div>',
            "two roots": '<div data-fragment="{key}">x</div><div>y</div>',
            "stray text": 'loose <div data-fragment="{key}">x</div>',
            "trailing text": '<div data-fragment="{key}">x</div> loose',
            "empty": '<div t-if="False" data-fragment="{key}"/>',
        }
        for label, body in cases.items():
            with self.subTest(label):
                key = f"web.test_fragment_bad_{label.replace(' ', '_')}"
                self._template(key, body.format(key=key))
                with self.assertRaisesRegex(ValueError, "must render one root element"):
                    render_fragments(self.env, Fragment(key))

    def test_a_key_rendered_twice_is_refused(self):
        with self.assertRaisesRegex(ValueError, "rendered twice"):
            render_fragments(
                self.env,
                Fragment("web.test_fragment_total", {"total": 1}),
                Fragment("web.test_fragment_total", {"total": 2}),
            )

    def test_a_redirect_off_this_site_is_refused(self):
        for url in ("https://evil.example/", "//evil.example/", "/\\evil.example"):
            with self.subTest(url), self.assertRaisesRegex(ValueError, "local URL"):
                render_fragments(self.env, redirect=url)
