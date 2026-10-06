import odoo
from odoo.tests import TransactionCase


@odoo.tests.tagged("post_install", "-at_install")
class TestUrbanPiperToggleState(TransactionCase):
    """`pos_urban_piper.toggle_state` is planted as an empty string by the module's
    own post-init hook, and `get_param(key, default)` returns the default only when
    the key is ABSENT. Every reader must therefore treat empty as empty, or closing
    a session raises -- and the write that would repair the parameter sits after the
    raise, so it never happens."""

    def setUp(self):
        super().setUp()
        self.config = self.env["pos.config"].create({"name": "Toggle State Probe"})

    def _set_raw(self, value):
        self.env["ir.config_parameter"].sudo().set_param(
            "pos_urban_piper.toggle_state", value
        )

    def test_an_empty_parameter_is_read_as_no_states(self):
        self._set_raw("")
        self.assertEqual(self.config.get_urban_piper_provider_states(), {})

    def test_an_empty_parameter_does_not_break_writing_states(self):
        self._set_raw("")
        self.config.set_urban_piper_provider_states({})
        self.assertEqual(self.config.get_urban_piper_provider_states(), {})

    def test_the_post_init_hook_plants_a_parsable_value(self):
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("pos_urban_piper.toggle_state")
        )
        self.assertNotEqual(
            raw, "", "the hook must not plant a value its own readers cannot parse"
        )

    def test_writing_one_config_leaves_the_others_alone(self):
        other = self.env["pos.config"].create({"name": "Toggle State Other"})
        self._set_raw("")
        self.config.set_urban_piper_provider_states('{"zomato": true}')
        other.set_urban_piper_provider_states('{"swiggy": true}')
        self.assertEqual(
            self.config.get_urban_piper_provider_states(), {"zomato": True}
        )
        self.assertEqual(other.get_urban_piper_provider_states(), {"swiggy": True})
