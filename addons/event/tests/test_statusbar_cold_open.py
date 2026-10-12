from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestStatusBarColdOpen(HttpCase):
    def test_a_cold_form_open_renders_and_fills_its_statusbar(self):
        self.assertEqual(
            self.env["event.event"]._fields["stage_id"].type,
            "many2one",
            "this test only exercises the defect while stage_id is a many2one",
        )
        stages = self.env["event.stage"].search([], limit=4)
        self.assertTrue(stages, "the statusbar needs stages to render")
        event = self.env["event.event"].create({"name": "cold open"})
        code = """
            (async () => {
                const deadline = performance.now() + 20000;
                const ready = () =>
                    document.querySelector('.o_form_view') &&
                    document.querySelectorAll('.o_statusbar_status .o_arrow_button').length;
                while (!ready() && performance.now() < deadline) {
                    await new Promise((r) => setTimeout(r, 200));
                }
                if (!document.querySelector('.o_form_view')) {
                    throw new Error('the form never rendered on a cold open');
                }
                const labels = [...document.querySelectorAll('.o_statusbar_status .o_arrow_button')]
                    .map((el) => el.textContent.trim());
                if (!labels.length) {
                    throw new Error('the statusbar rendered no items: special data never arrived');
                }
                if (!labels.includes(%(stage)s)) {
                    throw new Error('statusbar is missing its stage, got: ' + JSON.stringify(labels));
                }
                console.log('test successful');
            })()
        """ % {"stage": repr(stages[0].name).replace("'", '"')}
        self.browser_js(
            "/odoo/event.event/%d" % event.id,
            code,
            "odoo.isReady === true",
            login="admin",
            timeout=90,
        )
