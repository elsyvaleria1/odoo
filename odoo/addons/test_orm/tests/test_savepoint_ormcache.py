from odoo.tests.common import TransactionCase


class TestSavepointOrmcache(TransactionCase):
    def test_a_rolled_back_savepoint_leaves_no_cached_value_behind(self):
        Parameter = self.env["ir.config_parameter"].sudo()
        for flush in (True, False):
            with self.subTest(flush=flush):
                key = f"test_orm.savepoint_ormcache.{flush}"
                self.assertFalse(Parameter.get_param(key))
                # not assertRaises: it wraps the block in a flushing savepoint of its own
                try:
                    with self.env.cr.savepoint(flush=flush):
                        Parameter.set_param(key, "ghost")
                        self.assertEqual(Parameter.get_param(key), "ghost")
                        raise ValueError
                except ValueError:
                    pass
                self.env.cr.execute(
                    "SELECT count(*) FROM ir_config_parameter WHERE key = %s", [key]
                )
                self.assertEqual(self.env.cr.fetchone()[0], 0)
                self.assertFalse(
                    Parameter.get_param(key),
                    "the cache kept a value its savepoint rolled back",
                )
