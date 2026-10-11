from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPosClientFields(TransactionCase):
    CONVERTED = (
        "iface_print_via_proxy",
        "iface_scan_via_proxy",
        "iface_electronic_scale",
    )

    def test_the_converted_flags_still_reach_the_browser(self):
        config = self.env["pos.config"]
        sent = set(config._load_pos_data_fields(config.browse()))
        missing = [name for name in self.CONVERTED if name not in sent]
        self.assertFalse(
            missing,
            "these flags are read by the POS client but are no longer sent to "
            "it; declare them in _get_pos_client_computed_fields: %s" % missing,
        )

    def test_the_flags_are_still_the_computed_ones_this_module_installs(self):
        for name in self.CONVERTED:
            field = self.env["pos.config"]._fields[name]
            self.assertTrue(
                field.compute and not field.store,
                f"{name} is no longer a non-stored computed field, so this "
                "module's declaration of it may now be unnecessary",
            )
