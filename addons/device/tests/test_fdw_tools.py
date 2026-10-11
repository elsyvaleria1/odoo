from datetime import timedelta
from unittest.mock import patch

import psycopg

from odoo import fields
from odoo.db import schema as sql
from odoo.exceptions import UserError
from odoo.modules import neutralize
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.device.tests.common import DeviceTransactionCase
from odoo.addons.device.tools import fdw

LOG_TABLE = "device_data_log"


class TestFdwHelpers(DeviceTransactionCase):
    def test_without_dblink_the_schema_sync_hands_the_ddl_to_a_person(self):
        model = self.env["device.data.log"]
        ddl = ["ALTER TABLE remote_log ADD COLUMN x_new varchar"]
        with (
            patch.object(fdw, "foreign_server", return_value="device_remote"),
            patch.object(fdw, "user_mapping_exists", return_value=True),
            patch.object(fdw, "remote_table", return_value="remote_log"),
            patch.object(fdw, "missing_columns", return_value=[("x_new", "varchar")]),
            patch.object(fdw, "remote_column_ddl", return_value=ddl),
            patch.object(fdw, "remote_index_ddl", return_value=[]),
            patch.object(fdw, "dblink_available", return_value=False),
            patch.object(fdw, "remote_exec") as remote_exec,
            self.assertRaises(UserError) as caught,
        ):
            fdw.sync_foreign_schema(model)
        remote_exec.assert_not_called()
        message = str(caught.exception)
        self.assertIn("device.data.log", message)
        self.assertIn(ddl[0], message)

    def test_a_regular_table_is_not_foreign(self):
        self.assertFalse(fdw.is_foreign(self.env.cr, LOG_TABLE))
        self.assertIsNone(fdw.foreign_server(self.env.cr, LOG_TABLE))

    def test_an_installed_model_misses_no_column(self):
        model = self.env["device.data.log"]
        existing = sql.get_table_columns(self.env.cr, LOG_TABLE)
        self.assertEqual(fdw.missing_columns(model, existing), [])

    def test_missing_columns_names_the_column_with_its_sql_type(self):
        model = self.env["device.data.log"]
        existing = sql.get_table_columns(self.env.cr, LOG_TABLE)
        existing.pop("raw_payload")
        self.assertEqual(
            fdw.missing_columns(model, existing), [("raw_payload", "text")]
        )

    def test_remote_name_follows_the_foreign_table_options(self):
        self.assertEqual(
            fdw.qualified_remote_name(
                "device_data_log_gps",
                ["schema_name=public", "table_name=remote_data_log_gps"],
            ),
            "public.remote_data_log_gps",
        )
        self.assertEqual(
            fdw.qualified_remote_name("device_data_log_gps", None),
            "public.device_data_log_gps",
        )

    def test_remote_ddl_targets_the_remote_table(self):
        model = self.env["device.data.log"]
        ddl = fdw.remote_column_ddl([("raw_payload", "text")], "public.remote_data_log")
        ddl += [
            create
            for _name, create in fdw.remote_index_ddl(model, "public.remote_data_log")
        ]
        self.assertEqual(len(ddl), 2)
        for statement in ddl:
            self.assertIn("public.remote_data_log ", statement)
            self.assertNotIn(f"public.{LOG_TABLE} ", statement)

    def test_checked_references_resolve_to_tables(self):
        model = self.env["device.data.log"]
        self.assertEqual(
            fdw.checked_references(model),
            [("device_id", "device_device", True)],
        )

    def test_trigger_statements_carry_the_three_guards_and_no_placeholder(self):
        stmts = fdw.trigger_statements(
            LOG_TABLE,
            [("device_id", "device_device", True)],
            [("device_device", "log_last_id")],
        )
        joined = "\n".join(stmts)
        self.assertIn("trg_device_data_log_fdw_fk_check BEFORE INSERT", joined)
        self.assertIn("trg_device_data_log_fdw_unlink_pointer AFTER DELETE", joined)
        self.assertIn(
            "trg_device_device_fdw_no_delete_device_data_log BEFORE DELETE", joined
        )
        # "%" would be read as a parameter placeholder by the cursor.
        self.assertNotIn("%", joined)


class TestRemoteDdlFollowsTheLocalTransaction(DeviceTransactionCase):
    COLUMN_DDL = "ALTER TABLE public.remote_log ADD COLUMN IF NOT EXISTS x_new varchar"
    INDEX_DDL = (
        "CREATE INDEX IF NOT EXISTS remote_log_x_new ON public.remote_log (x_new)"
    )
    DROP_DDL = "DROP INDEX CONCURRENTLY IF EXISTS public.remote_log_x_new"

    def _sync(self):
        with (
            patch.object(fdw, "foreign_server", return_value="device_remote"),
            patch.object(fdw, "user_mapping_exists", return_value=True),
            patch.object(fdw, "remote_table", return_value="public.remote_log"),
            patch.object(fdw, "missing_columns", return_value=[]),
            patch.object(fdw, "remote_column_ddl", return_value=[self.COLUMN_DDL]),
            patch.object(
                fdw,
                "remote_index_ddl",
                return_value=[("remote_log_x_new", self.INDEX_DDL)],
            ),
            patch.object(fdw, "remote_index_exists", return_value=False),
            patch.object(fdw, "holds_remote_lock", return_value=False),
            patch.object(fdw, "dblink_available", return_value=True),
        ):
            fdw.sync_foreign_schema(self.env["device.data.log"])

    def _remote_statements(self, remote_exec):
        return [call.args[2] for call in remote_exec.call_args_list]

    def test_the_remote_index_is_built_once_the_transaction_commits(self):
        with patch.object(fdw, "remote_exec") as remote_exec:
            self._sync()
            self._sync()
            self.assertEqual(
                self._remote_statements(remote_exec), [self.COLUMN_DDL] * 2
            )
            self.env.cr.postcommit.run()
        self.assertEqual(
            self._remote_statements(remote_exec),
            [self.COLUMN_DDL, self.COLUMN_DDL, self.DROP_DDL, self.INDEX_DDL],
        )

    def test_the_column_ddl_waits_for_its_lock_no_longer_than_the_backstop(self):
        with patch.object(fdw, "remote_exec") as remote_exec:
            self._sync()
        self.assertEqual(
            remote_exec.call_args.kwargs,
            {"lock_timeout": fdw.REMOTE_COLUMN_LOCK_TIMEOUT},
        )

    def test_column_ddl_is_refused_when_this_transaction_holds_the_lock(self):
        with (
            patch.object(fdw, "remote_exec") as remote_exec,
            patch.object(fdw, "holds_remote_lock", return_value=True),
            self.assertRaises(UserError) as caught,
        ):
            with (
                patch.object(fdw, "foreign_server", return_value="device_remote"),
                patch.object(fdw, "user_mapping_exists", return_value=True),
                patch.object(fdw, "remote_table", return_value="public.remote_log"),
                patch.object(fdw, "missing_columns", return_value=[]),
                patch.object(fdw, "remote_column_ddl", return_value=[self.COLUMN_DDL]),
                patch.object(fdw, "remote_index_ddl", return_value=[]),
                patch.object(fdw, "dblink_available", return_value=True),
            ):
                fdw.sync_foreign_schema(self.env["device.data.log"])
        remote_exec.assert_not_called()
        self.assertIn(self.COLUMN_DDL, str(caught.exception))

    @mute_logger("odoo.sql_db")
    def test_a_column_the_remote_has_takes_no_lock_there(self):
        with (
            patch.object(fdw, "foreign_server", return_value="device_remote"),
            patch.object(fdw, "user_mapping_exists", return_value=True),
            patch.object(fdw, "remote_table", return_value="public.remote_log"),
            patch.object(fdw, "missing_columns", return_value=[("x_new", "varchar")]),
            patch.object(fdw, "remote_column_names", return_value={"id", "x_new"}),
            patch.object(fdw, "remote_index_ddl", return_value=[]),
            patch.object(fdw, "holds_remote_lock", return_value=True),
            patch.object(fdw, "dblink_available", return_value=True),
            patch.object(fdw, "remote_exec") as remote_exec,
            # past the remote, the local ALTER FOREIGN TABLE refuses this
            # regular table: the remote phase let the run through
            self.assertRaises(psycopg.errors.WrongObjectType),
            self.env.cr.savepoint(),
        ):
            fdw.sync_foreign_schema(self.env["device.data.log"])
        remote_exec.assert_not_called()

    def test_a_valid_remote_index_is_left_alone(self):
        with (
            patch.object(fdw, "remote_index_exists", return_value=True),
            patch.object(fdw, "remote_exec") as remote_exec,
        ):
            fdw.build_remote_index_after_commit(
                self.env,
                "device_remote",
                "public.remote_log",
                "remote_log_x_new",
                self.INDEX_DDL,
            )
            self.env.cr.postcommit.run()
        remote_exec.assert_not_called()

    def test_a_rolled_back_transaction_builds_no_remote_index(self):
        with patch.object(fdw, "remote_exec") as remote_exec:
            savepoint = self.env.cr.savepoint()
            try:
                self._sync()
            finally:
                savepoint.close(rollback=True)
            self.env.cr.postcommit.run()
        self.assertEqual(self._remote_statements(remote_exec), [self.COLUMN_DDL])

    @mute_logger(fdw.__name__)
    def test_a_failed_remote_index_does_not_stop_the_next(self):
        second = "CREATE INDEX IF NOT EXISTS remote_log_y ON public.remote_log (y)"
        with patch.object(
            fdw, "remote_exec", side_effect=[psycopg.errors.UndefinedTable(), None]
        ) as remote_exec:
            fdw.remote_exec_after_commit(self.env, "device_remote", self.INDEX_DDL)
            fdw.remote_exec_after_commit(self.env, "device_remote", second)
            self.env.cr.postcommit.run()
        self.assertEqual(self._remote_statements(remote_exec), [self.INDEX_DDL, second])


class TestRemoteIndexValidity(DeviceTransactionCase):
    def test_an_invalid_index_counts_as_absent(self):
        query = fdw.valid_index_query(
            f"public.{LOG_TABLE}", f"{LOG_TABLE}_device_timestamp_idx"
        )
        self.env.cr.execute(query)
        self.assertTrue(self.env.cr.fetchone())
        # what a failed CREATE INDEX CONCURRENTLY leaves behind
        self.env.cr.execute(
            "UPDATE pg_index SET indisvalid = false WHERE indexrelid = %s::regclass",
            [f"{LOG_TABLE}_device_timestamp_idx"],
        )
        self.env.cr.execute(query)
        self.assertIsNone(self.env.cr.fetchone())

    def test_an_index_of_that_name_in_another_schema_does_not_count(self):
        self.env.cr.execute(
            fdw.valid_index_query(
                f"elsewhere.{LOG_TABLE}", f"{LOG_TABLE}_device_timestamp_idx"
            )
        )
        self.assertIsNone(self.env.cr.fetchone())


class TestOwnRemoteLockOverLoopback(DeviceTransactionCase):
    """A postgres_fdw server pointing back at this database.

    Its connection is a second backend that sees only committed rows, which
    suffices: it reads the committed ``res_lang`` and holds the lock that
    read took until this test's transaction ends.
    """

    SERVER = "device_loopback_srv"

    def setUp(self):
        super().setUp()
        cr = self.env.cr
        cr.execute("SELECT current_database()")
        dbname = cr.fetchone()[0]
        cr.execute(
            f"""
            CREATE EXTENSION IF NOT EXISTS postgres_fdw;
            CREATE EXTENSION IF NOT EXISTS dblink;
            CREATE SERVER {self.SERVER} FOREIGN DATA WRAPPER postgres_fdw
                OPTIONS (dbname '{dbname}');
            CREATE USER MAPPING FOR CURRENT_USER SERVER {self.SERVER};
            CREATE FOREIGN TABLE device_loopback_lang (id int) SERVER {self.SERVER}
                OPTIONS (schema_name 'public', table_name 'res_lang');
            """
        )

    def test_a_foreign_read_is_a_lock_the_column_ddl_would_wait_on(self):
        cr = self.env.cr
        self.assertFalse(fdw.holds_remote_lock(cr, self.SERVER, "public.res_lang"))
        cr.execute("SELECT count(*) FROM device_loopback_lang")
        self.assertTrue(fdw.holds_remote_lock(cr, self.SERVER, "public.res_lang"))
        self.assertFalse(fdw.holds_remote_lock(cr, self.SERVER, "public.res_partner"))

    @mute_logger("odoo.sql_db")
    def test_a_lock_wait_past_the_backstop_fails_naming_the_statement(self):
        cr = self.env.cr
        cr.execute("SELECT count(*) FROM device_loopback_lang")
        statement = (
            "BEGIN; LOCK TABLE public.res_lang IN ACCESS EXCLUSIVE MODE; ROLLBACK"
        )
        with self.assertRaises(psycopg.errors.LockNotAvailable) as caught:
            with cr.savepoint():
                fdw.remote_exec(cr, self.SERVER, statement, lock_timeout="1s")
        self.assertIn(statement, "\n".join(caught.exception.__notes__))


class TestNeutralizedCopyReachesNoForeignServer(DeviceTransactionCase):
    SERVER = "device_test_srv"

    def setUp(self):
        super().setUp()
        self.env.cr.execute(
            f"""
            CREATE EXTENSION IF NOT EXISTS postgres_fdw;
            CREATE SERVER {self.SERVER} FOREIGN DATA WRAPPER postgres_fdw
                OPTIONS (dbname 'device_test_nowhere');
            """
        )

    def test_neutralizing_drops_every_user_mapping(self):
        self.env.cr.execute(
            f"""
            CREATE USER MAPPING FOR CURRENT_USER SERVER {self.SERVER};
            CREATE USER MAPPING FOR PUBLIC SERVER {self.SERVER};
            """
        )
        self.assertTrue(fdw.user_mapping_exists(self.env.cr, self.SERVER))
        neutralize.neutralize_database(self.env.cr)
        self.env.cr.execute(
            "SELECT usename FROM pg_user_mappings WHERE srvname = %s", [self.SERVER]
        )
        self.assertEqual(self.env.cr.fetchall(), [])

    def test_an_unmapped_server_stops_the_schema_sync_naming_the_repoint(self):
        with (
            patch.object(fdw, "foreign_server", return_value=self.SERVER),
            patch.object(fdw, "remote_exec") as remote_exec,
            self.assertRaises(UserError) as caught,
        ):
            fdw.sync_foreign_schema(self.env["device.data.log"])
        remote_exec.assert_not_called()
        message = str(caught.exception)
        self.assertIn(f"ALTER SERVER {self.SERVER} OPTIONS (SET host", message)
        self.assertIn(
            f"CREATE USER MAPPING FOR CURRENT_USER SERVER {self.SERVER}", message
        )


class TestFdwGuardsOnARegularTable(DeviceTransactionCase):
    """The triggers behave like the foreign keys they replace.

    Installed here on the regular ``device_data_log`` table, inside the test
    transaction, so what is verified is the trigger logic itself and not the
    FK Postgres still enforces on this table.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls._create_device_profile(name="FDW Config")
        cls.device = cls._create_device_device(config=cls.config, identifier="FDW-1")
        model = cls.env["device.data.log"]
        for statement in fdw.trigger_statements(
            LOG_TABLE,
            fdw.checked_references(model),
            [("device_device", "log_last_id")],
        ):
            cls.env.cr.execute(statement)

    def _log(self, **vals):
        vals.setdefault("device_id", self.device.id)
        vals.setdefault("timestamp", fields.Datetime.now())
        return self.env["device.data.log"].create(vals)

    @mute_logger("odoo.sql_db")
    def test_a_device_with_history_cannot_be_deleted(self):
        self._log()
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "DELETE FROM device_device WHERE id = %s", [self.device.id]
                )

    def test_a_device_without_history_can_be_deleted(self):
        spare = self._create_device_device(config=self.config, identifier="FDW-2")
        with self.env.cr.savepoint():
            self.env.cr.execute("DELETE FROM device_device WHERE id = %s", [spare.id])
            self.assertEqual(self.env.cr.rowcount, 1)

    def test_deleting_a_log_clears_the_pointer(self):
        log = self._log()
        self.device.log_last_id = log
        self.env.flush_all()
        self.env.cr.execute("DELETE FROM device_data_log WHERE id = %s", [log.id])
        self.env.cr.execute(
            "SELECT log_last_id FROM device_device WHERE id = %s", [self.device.id]
        )
        self.assertIsNone(self.env.cr.fetchone()[0])

    def test_pointer_constraints_are_found_and_dropped(self):
        # rolled back, so the constraint is there for the tests that follow
        savepoint = self.env.cr.savepoint()
        try:
            dropped = fdw.drop_pointer_foreign_keys(
                self.env.cr, [("device_device", "log_last_id")]
            )
            self.assertEqual(len(dropped), 1)
            self.assertIn("log_last_id", dropped[0])
        finally:
            savepoint.close(rollback=True)

    def test_an_installed_guard_is_not_dropped_and_recreated(self):
        statements = fdw.trigger_statements(
            LOG_TABLE,
            fdw.checked_references(self.env["device.data.log"]),
            [("device_device", "log_last_id")],
        )
        table_ddl = [s for s in statements if "TRIGGER" in s.split("(")[0]]
        functions = [s for s in statements if s.startswith("CREATE OR REPLACE")]
        self.assertTrue(table_ddl)
        self.assertTrue(
            all(fdw._installs_existing_trigger(self.env.cr, s) for s in table_ddl)
        )
        # a function body may change, and replacing it locks no table
        self.assertFalse(
            any(fdw._installs_existing_trigger(self.env.cr, s) for s in functions)
        )

    def test_a_guard_for_a_reference_no_longer_checked_is_stale(self):
        self.env.cr.execute(
            f"""
            CREATE FUNCTION res_company_fdw_no_delete_{LOG_TABLE}() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RETURN OLD; END $$;
            CREATE TRIGGER trg_res_company_fdw_no_delete_{LOG_TABLE} BEFORE DELETE
            ON res_company FOR EACH ROW
            EXECUTE FUNCTION res_company_fdw_no_delete_{LOG_TABLE}();
            """
        )
        references = fdw.checked_references(self.env["device.data.log"])
        self.assertEqual(
            fdw.stale_guard_triggers(self.env.cr, LOG_TABLE, references),
            [(f"trg_res_company_fdw_no_delete_{LOG_TABLE}", "res_company")],
        )

    def test_guards_left_by_a_rename_of_the_log_table_are_stale(self):
        # A rename carries the log's guards along under the old name, and a
        # referenced table keeps a guard naming a log table that is gone.
        self.env.cr.execute(
            f"""
            CREATE FUNCTION old_log_fdw_fk_check() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$;
            CREATE TRIGGER trg_old_log_fdw_fk_check BEFORE INSERT
            ON {LOG_TABLE} FOR EACH ROW EXECUTE FUNCTION old_log_fdw_fk_check();
            CREATE FUNCTION device_device_fdw_no_delete_old_log() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN RETURN OLD; END $$;
            CREATE TRIGGER trg_device_device_fdw_no_delete_old_log BEFORE DELETE
            ON device_device FOR EACH ROW
            EXECUTE FUNCTION device_device_fdw_no_delete_old_log();
            """
        )
        references = fdw.checked_references(self.env["device.data.log"])
        self.assertCountEqual(
            fdw.stale_guard_triggers(self.env.cr, LOG_TABLE, references),
            [
                ("trg_old_log_fdw_fk_check", LOG_TABLE),
                ("trg_device_device_fdw_no_delete_old_log", "device_device"),
            ],
        )


class TestGcOrdersLocalWritesFirst(DeviceTransactionCase):
    """Pointers are cleared before the rows go, never after.

    On a foreign table the two writes commit in different databases, so the
    order is what keeps a crash in between from leaving a dangling pointer.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls._create_device_profile(name="GC Config")
        cls.device = cls._create_device_device(config=cls.config, identifier="GC-1")

    def test_the_pointer_is_null_by_the_time_unlink_runs(self):
        old = self.env["device.data.log"].create(
            {
                "device_id": self.device.id,
                "timestamp": fields.Datetime.now() - timedelta(days=400),
            }
        )
        self.device.log_last_id = old
        self.env.flush_all()
        seen = []
        model_cls = type(self.env["device.data.log"])
        original_unlink = model_cls.unlink

        def unlink_spy(records):
            records.env.cr.execute(
                "SELECT log_last_id FROM device_device WHERE id = %s",
                [self.device.id],
            )
            seen.append(records.env.cr.fetchone()[0])
            return original_unlink(records)

        with patch.object(
            model_cls, "_fdw_pointer_columns", (("device_device", "log_last_id"),)
        ):
            with patch.object(model_cls, "unlink", unlink_spy):
                deleted = self.env["device.data.log"]._gc_old_logs(
                    fields.Datetime.now() - timedelta(days=30)
                )
        self.assertEqual(deleted, 1)
        self.assertEqual(seen, [None])
        self.assertFalse(old.exists())


@tagged("post_install", "-at_install")
class TestRawPayloadGcBatches(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls._create_device_profile(name="Batch Config")
        cls.device = cls._create_device_device(config=cls.config, identifier="BATCH-1")

    def test_every_batch_is_bounded_by_id_and_all_rows_are_reached(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "device.raw_payload_retention_days", "30"
        )
        logs = self.env["device.data.log"].create(
            [
                {
                    "device_id": self.device.id,
                    "timestamp": fields.Datetime.now() - timedelta(days=90),
                    "raw_payload": f'{{"n": {n}}}',
                }
                for n in range(3)
            ]
        )
        model_cls = type(self.env["device.data.log"])
        with patch.object(model_cls, "_RAW_PAYLOAD_BATCH_SIZE", 1):
            cleared = self.env["device.data.log"]._gc_old_raw_payloads()
        self.assertEqual(cleared, 3)
        self.assertFalse(any(logs.mapped("raw_payload")))
