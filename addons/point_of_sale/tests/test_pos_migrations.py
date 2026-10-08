import json
import logging
from uuid import uuid4

from odoo.db import schema
from odoo.modules.module import get_module_path, load_script
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon

_logger = logging.getLogger(__name__)

RESCUE_SCRIPT = "odoo.addons.point_of_sale.migrations.pre_migrate_1_0_13"


def _load_migration(version):
    return load_script(
        f"{get_module_path('point_of_sale')}/migrations/{version}/pre-migrate.py",
        f"odoo.addons.point_of_sale.migrations.pre_migrate_{version.replace('.', '_')}",
    )


@tagged("post_install", "-at_install")
class TestPosRescueSessionMigration(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.script = _load_migration("1.0.13")

    def setUp(self):
        super().setUp()
        self.basic_config.open_ui()
        self.env.flush_all()
        cr = self.env.cr
        # the 1.0.12 schema: a registered rescue column the open-session index exempts
        cr.execute("DROP INDEX pos_session_open_per_config_uniq")
        cr.execute("ALTER TABLE pos_session ADD COLUMN rescue boolean")
        cr.execute(
            """
            CREATE UNIQUE INDEX pos_session_open_per_config_uniq ON pos_session (config_id)
             WHERE state != 'closed' AND rescue IS NOT TRUE
            """
        )
        cr.execute(
            """
            INSERT INTO ir_model_fields (model_id, model, name, field_description,
                                         ttype, state, store)
            SELECT id, model, 'rescue', '{"en_US": "Recovery Session"}', 'boolean',
                   'base', true
              FROM ir_model
             WHERE model = 'pos.session'
         RETURNING id
            """
        )
        self.rescue_field = self.env["ir.model.fields"].browse(cr.fetchone()[0])

    def _rescue_session(self, config):
        self.env.cr.execute(
            """
            INSERT INTO pos_session (config_id, user_id, state, name, rescue)
            VALUES (%s, %s, 'opened', %s, true)
         RETURNING id
            """,
            [config.id, self.env.uid, f"(RESCUE FOR {config.name})"],
        )
        return self.env["pos.session"].browse(self.env.cr.fetchone()[0])

    def _open_session_index(self):
        self.env.cr.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = %s",
            ["pos_session_open_per_config_uniq"],
        )
        return self.env.cr.fetchone()

    def test_a_rescue_session_open_beside_another_refuses_with_a_remedy(self):
        rescue = self._rescue_session(self.basic_config)

        with self.assertRaises(ValueError) as refused:
            self.script.migrate(self.env.cr, "19.0.1.0.12")

        message = str(refused.exception)
        _logger.debug("rescue migration refusal: %s", message)
        self.assertIn("Put the previous point_of_sale code back in place", message)
        self.assertNotIn("current version", message)
        self.assertIn(
            f"(RESCUE FOR {self.basic_config.name}) (id {rescue.id})", message
        )
        self.assertIn(
            f"(id {self.basic_config.current_session_id.id})",
            message.split("beside")[1],
        )
        self.assertTrue(schema.column_exists(self.env.cr, "pos_session", "rescue"))
        self.assertIn("rescue IS NOT TRUE", self._open_session_index()[0])

    def test_a_lone_open_rescue_session_becomes_the_current_one_with_a_warning(self):
        config = self.other_currency_config
        rescue = self._rescue_session(config)

        for _attempt in range(2):
            with self.assertLogs(RESCUE_SCRIPT, "WARNING") as logged:
                self.script.migrate(self.env.cr, "19.0.1.0.12")
            _logger.debug("rescue migration warning: %s", logged.output)
            self.assertEqual(len(logged.output), 1)
            self.assertIn(f"(id {rescue.id})", logged.output[0])
            self.assertIn("count it when closing", logged.output[0])
            self.assertIsNone(self._open_session_index())

        self.env["pos.session"].init()
        self.rescue_field._drop_columns()
        self.env.invalidate_all()

        self.assertFalse(schema.column_exists(self.env.cr, "pos_session", "rescue"))
        self.assertEqual(
            self._open_session_index()[0].split(" WHERE ")[1],
            "((state)::text <> 'closed'::text)",
        )
        self.assertEqual(config.current_session_id, rescue)
        with self.assertNoLogs(RESCUE_SCRIPT, "WARNING"):
            self.script.migrate(self.env.cr, "19.0.1.0.12")


@tagged("post_install", "-at_install")
class TestPosProcessedOperationMigration(TestPoSCommon):
    def test_jsonb_results_become_their_json_text(self):
        operation = str(uuid4())
        cr = self.env.cr
        cr.execute(
            "ALTER TABLE pos_processed_operation ALTER COLUMN result TYPE jsonb "
            "USING result::jsonb"
        )
        cr.execute(
            """
            INSERT INTO pos_processed_operation
                   (operation_uuid, user_id, res_model, method, result, processed_at)
            VALUES (%s, %s, 'pos.session', 'try_cash_in_out', %s::jsonb, now())
            """,
            [operation, self.env.uid, json.dumps({"lines": [1, 2], "name": "é"})],
        )

        for _attempt in range(2):
            _load_migration("1.0.15").migrate(cr, "19.0.1.0.14")

        self.assertEqual(
            schema.get_table_columns(cr, "pos_processed_operation")["result"][
                "udt_name"
            ],
            "text",
        )
        replayed = self.env["pos.processed.operation"]._call_once(
            operation, "pos.session", "try_cash_in_out", lambda: self.fail("replayed")
        )
        self.assertEqual(replayed, {"lines": [1, 2], "name": "é"})
