import hashlib
import json
from contextlib import contextmanager
from unittest.mock import patch

import psycopg

from odoo.api import MODULE_UNINSTALL_FLAG
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command, Domain
from odoo.modules.module import get_module_path, load_script
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import SQL, config, mute_logger

from odoo.addons.base.models.ir_access_audit import MODULE_CHANGES
from odoo.addons.base.models.ir_access_log import (
    LEGACY_CONTENT,
    SEAL_BASE,
    SEAL_HEAD,
    SEAL_LEGACY,
    _chained,
    _content_hash,
)

SEAL_KEY = "a seal key of the test run, long enough to be accepted"
OTHER_KEY = "another seal key of the test run, long enough as well"


def behind_the_trigger(env, statement, *params):
    cr = env.cr
    cr.execute("ALTER TABLE ir_access_log DISABLE TRIGGER ir_access_log_append_only")
    cr.execute(statement, params or None)
    cr.execute("ALTER TABLE ir_access_log ENABLE TRIGGER ir_access_log_append_only")
    env["ir.access.log"].invalidate_model()


@tagged("post_install", "-at_install")
class TestSecurityChangeLog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(
            cls.env, login="access_admin", groups="base.group_erp_manager"
        )
        cls.clerk = new_test_user(cls.env, login="clerk", groups="base.group_user")
        cls.group = cls.env["res.groups"].create({"name": "Probe: audited group"})
        cls.row = cls.env["ir.access"].create(
            {
                "name": "Probe: audited row",
                "model_id": cls.env["ir.model"]._get_id("res.partner.industry"),
                "group_id": cls.group.id,
                "kind": "permission",
                "operation": "r",
                "domain": "[('name', '=like', 'a%')]",
            }
        )

    def logged(self, model, record, event="security_changed"):
        return self.env["ir.access.log"].search(
            Domain("event", "=", event)
            & Domain("model_name", "=", model)
            & Domain("res_ids", "=", str(record.id))
        )

    def test_a_person_changing_a_row_is_logged_with_what_changed(self):
        self.row.with_user(self.admin).write({"domain": "[('name', '=like', 'b%')]"})
        log = self.logged("ir.access", self.row).filtered(
            lambda log: log.operation == "write"
        )
        self.assertEqual(len(log), 1)
        self.assertEqual(log.actor_id, self.admin)
        self.assertEqual(
            log.values,
            {"domain": ["[('name', '=like', 'a%')]", "[('name', '=like', 'b%')]"]},
        )

    def test_a_write_that_changes_nothing_audited_is_not_logged(self):
        self.row.write({"note": "<p>why</p>"})
        self.row.write({"domain": self.row.domain})
        self.assertFalse(
            self.logged("ir.access", self.row).filtered(
                lambda log: log.operation == "write"
            )
        )

    def test_creating_and_deleting_a_row_are_logged(self):
        created = self.logged("ir.access", self.row)
        self.assertEqual(created.operation, "create")
        self.assertEqual(created.values["group_id"], [None, self.group.id])
        row_id = self.row.id
        self.row.unlink()
        deleted = (
            self.env["ir.access.log"].search(
                [("model_name", "=", "ir.access"), ("res_ids", "=", str(row_id))]
            )
            - created
        )
        self.assertEqual(deleted.operation, "unlink")
        self.assertEqual(deleted.values["name"], ["Probe: audited row", None])

    def test_a_group_implication_is_logged_and_a_membership_is_not(self):
        implied = self.env.ref("base.group_partner_manager")
        self.group.implied_ids = [Command.link(implied.id)]
        log = self.logged("res.groups", self.group).filtered(
            lambda log: log.operation == "write"
        )
        self.assertEqual(log.values, {"implied_ids": [[], [implied.id]]})
        self.group.user_ids = [Command.link(self.clerk.id)]
        self.assertEqual(
            self.logged("res.groups", self.group).filtered(
                lambda log: log.operation == "write"
            ),
            log,
            "a membership is the grant's event, not a security change",
        )

    def test_a_module_load_is_counted_per_module_not_logged_per_row(self):
        Access = self.env["ir.access"].with_context(install_module="probe_module")
        row = Access.create(
            {
                "name": "Probe: shipped row",
                "model_id": self.env["ir.model"]._get_id("res.partner.industry"),
                "group_id": self.group.id,
                "kind": "permission",
                "operation": "r",
            }
        )
        row.write({"operation": "r"})
        row.write({"operation": "ru"})
        self.assertFalse(self.logged("ir.access", row))
        changes = self.env.cr.precommit.data[MODULE_CHANGES]
        self.assertEqual(
            dict(changes["probe_module", "ir.access"]), {"create": 1, "write": 1}
        )
        row._access_audit_flush_modules()
        summary = self.env["ir.access.log"].search(
            [("event", "=", "module_security_updated"), ("reason", "=", "probe_module")]
        )
        self.assertEqual(summary.values, {"ir.access": {"create": 1, "write": 1}})

    def test_a_module_load_records_an_active_change_set_holding_its_diff(self):
        parameters = self.env["ir.config_parameter"]
        version = int(parameters.get_param("base.access_policy_version", "0"))
        Access = self.env["ir.access"].with_context(install_module="probe_module")
        row = Access.create(
            {
                "name": "Probe: shipped row",
                "model_id": self.env["ir.model"]._get_id("res.partner.industry"),
                "group_id": self.group.id,
                "kind": "permission",
                "operation": "r",
            }
        )
        row.write({"operation": "r"})
        row.write({"operation": "ru"})
        self.row.with_context(install_module="other_module").write(
            {"domain": "[('name', '=like', 'z%')]"}
        )
        self.env["ir.model.data"].create(
            {
                "module": "probe_module",
                "name": "probe_row",
                "model": "ir.access",
                "res_id": row.id,
            }
        )
        row.with_context(**{MODULE_UNINSTALL_FLAG: True}).unlink()
        row._access_audit_flush_modules()
        Changeset = self.env["ir.access.changeset"]
        probe = Changeset.search([("module", "=", "probe_module")])
        self.assertEqual((probe.cause, probe.state), ("module_update", "active"))
        self.assertEqual(
            [(line.operation, line.res_id) for line in probe.line_ids],
            [("create", row.id), ("write", row.id), ("unlink", row.id)],
        )
        create, write, unlink = probe.line_ids
        self.assertEqual(create.values_after["operation"], "r")
        self.assertEqual(
            (write.values_before, write.values_after),
            ({"operation": "r"}, {"operation": "ru"}),
            "a write that changed nothing is no line",
        )
        self.assertEqual(unlink.values_before["operation"], "ru")
        other = Changeset.search([("module", "=", "other_module")])
        self.assertEqual(
            other.line_ids.values_after, {"domain": "[('name', '=like', 'z%')]"}
        )
        self.assertEqual(
            sorted((probe | other).mapped("policy_version")), [version + 1, version + 2]
        )
        summary = self.env["ir.access.log"].search(
            [("event", "=", "module_security_updated"), ("reason", "=", "probe_module")]
        )
        self.assertEqual(summary.changeset_id, probe)

    def test_a_module_updates_rollback_restores_what_it_changed(self):
        self.row.with_context(install_module="probe_module").write(
            {"domain": "[('name', '=like', 'z%')]"}
        )
        self.row._access_audit_flush_modules()
        changeset = self.env["ir.access.changeset"].search(
            [("module", "=", "probe_module")]
        )
        action = changeset.with_user(self.admin).action_rollback()
        rollback = self.env["ir.access.changeset"].browse(action["res_id"])
        rollback.action_activate()
        self.assertEqual(self.row.domain, "[('name', '=like', 'a%')]")


@tagged("post_install", "-at_install")
class TestDenialLog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clerk = new_test_user(cls.env, login="clerk", groups="base.group_user")
        cls.Log = type(cls.env["ir.access.log"])

    @contextmanager
    def denials(self):
        calls = []
        original = self.Log._record_denial

        def spy(log, model_name, operation, ids, refusing):
            calls.append((model_name, operation, refusing))
            return original(log, model_name, operation, ids, refusing)

        with patch.object(self.Log, "_record_denial", spy):
            yield calls

    def test_a_refused_change_of_security_is_logged(self):
        row = self.env.ref("base.access_ir_access_log_erp_manager")
        with self.denials() as calls, self.assertRaises(AccessError):
            row.with_user(self.clerk).write({"name": "mine now"})
        self.assertEqual(calls, [("ir.access", "write", [])])

    def test_a_refused_record_change_names_the_refusing_rows(self):
        grant = self.env["res.users.grant"].search(
            [("user_id", "=", self.clerk.id)], limit=1
        )
        other = new_test_user(self.env, login="other", groups="base.group_user")
        with self.denials() as calls, self.assertRaises(AccessError):
            self.env["res.users.grant"].with_user(self.clerk).create(
                {"user_id": other.id, "group_id": grant.group_id.id}
            )
        [(model_name, operation, refusing)] = calls
        self.assertEqual((model_name, operation), ("res.users.grant", "create"))
        self.assertIn(
            "res.users.grant: the members of a group's admin group give and end "
            "its grants",
            refusing,
        )

    def test_a_refused_read_is_not_logged(self):
        with self.denials() as calls, self.assertRaises(AccessError):
            self.env["ir.access"].with_user(self.clerk).search([], limit=1)
        self.assertEqual(calls, [])

    def test_a_refusal_is_written_on_a_cursor_of_its_own(self):
        self.env["ir.access.log"].with_user(self.clerk)._record_denial(
            "ir.access", "unlink", [7], ["some guard"]
        )
        denial = self.env["ir.access.log"].search(
            [("event", "=", "denial"), ("actor_id", "=", self.clerk.id)]
        )
        self.assertEqual(denial.res_ids, "7")
        self.assertEqual(denial.values, {"refused_by": ["some guard"]})


@tagged("post_install", "-at_install")
class TestAccessLogIntegrity(TransactionCase):
    def setUp(self):
        super().setUp()
        self.enterContext(config.patch(access_log_seal_key=SEAL_KEY))

    def test_a_row_keeps_its_actor_s_login(self):
        user = new_test_user(self.env, login="log_actor", groups="base.group_user")

        row = (
            self.env["ir.access.log"]
            .with_user(user)
            ._record([{"event": "grant_created", "subject_user_id": user.id}])
        )

        self.assertEqual(row.actor_id, user)
        self.assertEqual(row.actor_login, "log_actor")

    def test_a_row_names_an_actor_whose_login_is_known_without_a_lookup(self):
        user = new_test_user(self.env, login="log_known", groups="base.group_user")
        Log = self.env["ir.access.log"].with_user(user)
        Log._record([{"event": "grant_created"}])
        self.env.flush_all()

        with self.assertQueryCount(1):
            row = Log._record([{"event": "grant_created"}])

        self.assertEqual(row.actor_login, "log_known")

    def test_nobody_deletes_the_log_but_a_logged_purge(self):
        Log = self.env["ir.access.log"]
        user = new_test_user(self.env, login="log_eraser", groups="base.group_user")
        row = Log._record([{"event": "grant_created"}])

        with self.assertRaises(UserError):
            row.with_user(user).sudo().unlink()
        with self.assertRaises(UserError):
            row.unlink()
        with self.assertRaises(UserError):
            Log._remove_rows([("id", "=", row.id)], "")
        with self.assertRaises(UserError):
            Log.with_user(user).sudo()._remove_rows([("id", "=", row.id)], "mine")

        self.assertEqual(Log._remove_rows([("id", "=", row.id)], "retention: probe"), 1)
        self.assertFalse(row.exists())
        purge = Log.search([("event", "=", "log_purged")], limit=1)
        self.assertEqual((purge.count, purge.reason), (1, "retention: probe"))

    def test_the_database_refuses_changing_or_deleting_a_row(self):
        row = self.env["ir.access.log"]._record(
            [{"event": "grant_created", "reason": "kept"}]
        )
        self.env.flush_all()
        for statement in (
            "UPDATE ir_access_log SET reason = 'rewritten' WHERE id = %s",
            "UPDATE ir_access_log SET actor_login = NULL WHERE id = %s",
            "DELETE FROM ir_access_log WHERE id = %s",
        ):
            with (
                self.subTest(statement=statement),
                mute_logger("odoo.db.cursor"),
                self.assertRaises(psycopg.errors.InsufficientPrivilege),
                self.env.cr.savepoint(),
            ):
                self.env.cr.execute(statement, [row.id])
        with (
            mute_logger("odoo.db.cursor"),
            self.assertRaises(psycopg.errors.InsufficientPrivilege),
            self.env.cr.savepoint(),
        ):
            self.env.cr.execute("TRUNCATE ir_access_log")

    def test_a_deleted_user_s_rows_keep_their_login_and_their_seal(self):
        Log = self.env["ir.access.log"]
        user = new_test_user(self.env, login="log_leaver", groups="base.group_user")
        row = Log.with_user(user)._record([{"event": "grant_created"}])
        Log._seal()

        user.unlink()
        row.invalidate_recordset()

        self.assertFalse(row.actor_id)
        self.assertEqual(row.actor_login, "log_leaver")
        self.assertIsNone(Log._get_seal_chain_error())

    def test_a_deleted_change_set_leaves_its_rows_sealed(self):
        Log = self.env["ir.access.log"]
        changeset = self.env["ir.access.changeset"].create({"name": "Probe: set"})
        Log._record([{"event": "grant_created", "changeset_id": changeset.id}])
        Log._seal()

        changeset.unlink()

        self.assertIsNone(Log._get_seal_chain_error())

    def test_a_sealed_row_changed_behind_the_database_breaks_the_chain(self):
        Log = self.env["ir.access.log"]
        rows = Log._record(
            [{"event": "grant_created", "reason": f"probe {n}"} for n in range(3)]
        )
        Log._seal()
        self.assertIsNone(Log._get_seal_chain_error())

        behind_the_trigger(
            self.env,
            "UPDATE ir_access_log SET reason = 'rewritten' WHERE id = %s",
            rows[1].id,
        )
        self.assertEqual(
            Log._get_seal_chain_error(), f"row {rows[1].id} changed after it was sealed"
        )
        with mute_logger("odoo.addons.base.models.ir_access_log"):
            Log._cron_check_seal_chain()
        self.assertTrue(Log.search([("event", "=", "log_chain_broken")]))

        behind_the_trigger(
            self.env,
            "UPDATE ir_access_log SET reason = 'probe 1' WHERE id = %s",
            rows[1].id,
        )
        self.assertIsNone(Log._get_seal_chain_error())
        behind_the_trigger(
            self.env, "DELETE FROM ir_access_log WHERE id = %s", rows[2].id
        )
        self.assertIn("the end of the chain was deleted", Log._get_seal_chain_error())
        behind_the_trigger(
            self.env, "DELETE FROM ir_access_log WHERE id = %s", rows[0].id
        )
        self.assertIn(
            "is missing: a sealed row was deleted", Log._get_seal_chain_error()
        )

    def test_a_chain_rebuilt_without_the_key_is_reported(self):
        Log = self.env["ir.access.log"]
        rows = Log._record(
            [{"event": "grant_created", "reason": f"probe {n}"} for n in range(3)]
        )
        Log._seal()
        behind_the_trigger(
            self.env,
            "UPDATE ir_access_log SET reason = 'rewritten' WHERE id = %s",
            rows[1].id,
        )
        guess = b"a key guessed by whoever does not hold it"
        cr = self.env.cr
        cr.execute(
            "SELECT seal FROM ir_access_log WHERE seal_seq = %s", [rows[1].seal_seq - 1]
        )
        (previous,) = cr.fetchone()
        cr.execute(
            SQL(
                "SELECT id, %s, seal_seq FROM ir_access_log log "
                "WHERE seal_seq >= %s ORDER BY seal_seq",
                Log._sealed_content(),
                rows[1].seal_seq,
            )
        )
        rebuilt = cr.fetchall()
        for row_id, content, _seq in rebuilt:
            content_hash = _content_hash(guess, content)
            previous = _chained(guess, previous, content_hash)
            behind_the_trigger(
                self.env,
                SQL(
                    "UPDATE ir_access_log SET content_hash = %s, seal = %s WHERE id = %s",
                    content_hash,
                    previous,
                    row_id,
                ),
            )
        self.env["ir.config_parameter"].set_param(
            SEAL_HEAD, f"{rebuilt[-1][2]}:{previous}"
        )

        self.assertEqual(
            Log._get_seal_chain_error(), f"row {rows[1].id} changed after it was sealed"
        )

    def test_a_purge_of_the_oldest_sealed_rows_keeps_the_chain(self):
        Log = self.env["ir.access.log"]
        rows = Log._record(
            [{"event": "grant_created", "reason": f"probe {n}"} for n in range(3)]
        )
        Log._seal()
        purged = rows[1].seal_seq

        Log._remove_rows([("seal_seq", "<=", purged)], "retention: probe")

        self.assertIsNone(Log._get_seal_chain_error())
        Log._seal()
        self.assertIsNone(Log._get_seal_chain_error())

    def test_a_purge_inside_the_chain_is_refused(self):
        Log = self.env["ir.access.log"]
        rows = Log._record(
            [{"event": "grant_created", "reason": f"probe {n}"} for n in range(3)]
        )
        Log._seal()

        with self.assertRaises(UserError):
            Log._remove_rows([("id", "=", rows[1].id)], "retention: probe")

        self.assertTrue(rows[1].exists())
        self.assertIsNone(Log._get_seal_chain_error())

    def test_a_chain_base_moved_past_kept_rows_is_reported(self):
        Log = self.env["ir.access.log"]
        rows = Log._record(
            [{"event": "grant_created", "reason": f"probe {n}"} for n in range(3)]
        )
        Log._seal()
        behind_the_trigger(
            self.env,
            "UPDATE ir_access_log SET reason = 'rewritten' WHERE id = %s",
            rows[1].id,
        )
        Parameters = self.env["ir.config_parameter"]
        Parameters.set_param(SEAL_BASE, Parameters.get_param(SEAL_HEAD))

        self.assertIn("the start of the chain was moved", Log._get_seal_chain_error())

    def test_an_erased_row_keeps_the_chain_and_loses_its_content(self):
        Log = self.env["ir.access.log"]
        user = new_test_user(self.env, login="log_erased", groups="base.group_user")
        rows = Log.with_user(user)._record(
            [
                {
                    "event": "grant_created",
                    "subject_user_id": user.id,
                    "reason": f"probe {n}",
                }
                for n in range(3)
            ]
        )
        Log._seal()
        erased = rows[1]
        content_hash, seal, seq = erased.content_hash, erased.seal, erased.seal_seq

        self.assertEqual(
            Log._erase_rows([("id", "=", erased.id)], "erasure request: probe"), 1
        )

        self.assertIsNone(Log._get_seal_chain_error())
        self.assertEqual(
            (erased.event, erased.content_hash, erased.seal, erased.seal_seq),
            ("grant_created", content_hash, seal, seq),
        )
        self.assertFalse(
            erased.actor_id
            or erased.actor_login
            or erased.subject_user_id
            or erased.reason
        )
        self.assertTrue(erased.create_date)
        self.assertEqual(rows[0].actor_login, "log_erased")
        erasure = erased.erasure_id
        self.assertEqual(
            (erasure.event, erasure.res_ids, erasure.count, erasure.reason),
            ("log_erased", str(erased.id), 1, "erasure request: probe"),
        )
        self.assertEqual(erasure.actor_id, self.env.user)
        self.assertGreater(erasure.seal_seq, seq)
        self.assertEqual(
            Log._erase_rows([("id", "in", (erased | erasure).ids)], "erasure: probe"), 0
        )
        Log._record([{"event": "grant_created", "reason": "after the erasure"}])
        Log._seal()
        self.assertIsNone(Log._get_seal_chain_error())

    def test_an_erasure_names_its_rows_a_hundred_at_a_time(self):
        Log = self.env["ir.access.log"]
        rows = Log._record(
            [{"event": "grant_created", "reason": "bulk probe"} for _n in range(150)]
        )

        self.assertEqual(Log._erase_rows([("reason", "=", "bulk probe")], "probe"), 150)

        erasures = rows.erasure_id
        self.assertEqual(sorted(erasures.mapped("count")), [50, 100])
        self.assertIsNone(Log._get_seal_chain_error())

    def test_an_erasure_forged_behind_the_database_is_reported(self):
        Log = self.env["ir.access.log"]
        rows = Log._record(
            [{"event": "grant_created", "reason": f"probe {n}"} for n in range(3)]
        )
        Log._erase_rows([("id", "=", rows[0].id)], "erasure request: probe")
        erasure = rows[0].erasure_id

        behind_the_trigger(
            self.env,
            SQL(
                "UPDATE ir_access_log SET reason = NULL, erasure_id = %s WHERE id = %s",
                erasure.id,
                rows[2].id,
            ),
        )
        self.assertEqual(
            Log._get_seal_chain_error(),
            f"row {rows[2].id} was erased by no erasure naming it",
        )
        self.env.cr.execute(
            SQL(
                "INSERT INTO ir_access_log (event, res_ids, count) "
                "VALUES ('log_erased', %s, 1) RETURNING id",
                str(rows[2].id),
            )
        )
        (forged,) = self.env.cr.fetchone()
        behind_the_trigger(
            self.env,
            SQL(
                "UPDATE ir_access_log SET erasure_id = %s WHERE id = %s",
                forged,
                rows[2].id,
            ),
        )
        self.assertEqual(
            Log._get_seal_chain_error(),
            f"row {rows[2].id} was erased by no erasure naming it",
        )
        behind_the_trigger(
            self.env,
            SQL(
                "UPDATE ir_access_log SET reason = 'probe 2', erasure_id = NULL "
                "WHERE id = %s",
                rows[2].id,
            ),
        )
        behind_the_trigger(self.env, "DELETE FROM ir_access_log WHERE id = %s", forged)
        self.assertIsNone(Log._get_seal_chain_error())
        behind_the_trigger(
            self.env,
            "UPDATE ir_access_log SET reason = 'planted' WHERE id = %s",
            rows[0].id,
        )
        self.assertEqual(
            Log._get_seal_chain_error(), f"row {rows[0].id} changed after it was erased"
        )

    def test_only_the_superuser_erases_for_a_reason_under_the_key(self):
        Log = self.env["ir.access.log"]
        user = new_test_user(self.env, login="log_eraser", groups="base.group_user")
        row = Log._record([{"event": "grant_created", "reason": "kept"}])
        erase = [("id", "=", row.id)]

        with self.assertRaises(UserError):
            Log._erase_rows(erase, "")
        with self.assertRaises(UserError):
            Log.with_user(user).sudo()._erase_rows(erase, "mine")
        with config.patch(access_log_seal_key=""), self.assertRaises(UserError):
            Log._erase_rows(erase, "erasure request: probe")
        with (
            mute_logger("odoo.db.cursor"),
            self.assertRaises(psycopg.errors.InsufficientPrivilege),
            self.env.cr.savepoint(),
        ):
            self.env.cr.execute(
                "UPDATE ir_access_log SET reason = NULL WHERE id = %s", [row.id]
            )

        self.assertEqual(row.reason, "kept")
        self.assertFalse(row.erasure_id)

    def test_without_a_key_the_rows_wait_unsealed(self):
        Log = self.env["ir.access.log"]
        Log._seal()
        row = Log._record([{"event": "grant_created"}])

        with config.patch(access_log_seal_key=""):
            with self.assertLogs("odoo.addons.base.models.ir_access_log", "WARNING"):
                self.assertEqual(Log._seal(), 0)
            with self.assertLogs("odoo.addons.base.models.ir_access_log", "WARNING"):
                Log._cron_check_seal_chain()
            with self.assertRaises(UserError):
                Log._get_seal_chain_error()

        self.assertFalse(row.seal)
        self.assertFalse(Log.search([("event", "=", "log_chain_broken")]))
        self.assertEqual(Log._seal(), 1)
        self.assertIsNone(Log._get_seal_chain_error())

    def test_a_key_too_short_is_refused(self):
        with config.patch(access_log_seal_key="short"), self.assertRaises(UserError):
            self.env["ir.access.log"]._seal()

    def test_a_chain_is_never_extended_under_another_key(self):
        Log = self.env["ir.access.log"]
        Log._record([{"event": "grant_created"}])
        Log._seal()
        row = Log._record([{"event": "grant_created"}])

        with config.patch(access_log_seal_key=OTHER_KEY):
            with self.assertLogs("odoo.addons.base.models.ir_access_log", "ERROR"):
                self.assertEqual(Log._seal(), 0)
            self.assertTrue(Log._get_seal_chain_error())

        self.assertFalse(row.seal)
        self.assertEqual(Log._seal(), 1)

    def test_a_rotated_key_seals_again_the_chain_it_verifies(self):
        Log = self.env["ir.access.log"]
        rows = Log._record(
            [{"event": "grant_created", "reason": f"probe {n}"} for n in range(3)]
        )
        Log._erase_rows([("id", "=", rows[1].id)], "erasure request: probe")

        with config.patch(access_log_seal_key=OTHER_KEY):
            with self.assertRaises(UserError):
                Log._reseal("not the key that sealed the chain, at all")
            self.assertTrue(Log._get_seal_chain_error())

            self.assertGreater(Log._reseal(SEAL_KEY), 3)

            self.assertIsNone(Log._get_seal_chain_error())
            Log._record([{"event": "grant_created"}])
            self.assertEqual(Log._seal(), 1)
            self.assertIsNone(Log._get_seal_chain_error())
        self.assertTrue(Log._get_seal_chain_error())

    def test_sealing_takes_one_statement_per_batch(self):
        Log = self.env["ir.access.log"]
        Log._seal()
        Log._record(
            [{"event": "grant_created", "reason": f"probe {n}"} for n in range(40)]
        )
        self.env.flush_all()
        with self.assertQueryCount(8):
            self.assertEqual(Log._seal(), 40)

    def test_an_erasure_takes_the_same_statements_for_one_row_or_forty(self):
        Log = self.env["ir.access.log"]
        rows = Log._record(
            [{"event": "grant_created", "reason": f"probe {n}"} for n in range(41)]
        )
        Log._seal()
        self.env.flush_all()
        for erased in (rows[:1], rows[1:]):
            self.env.invalidate_all()
            with self.assertQueryCount(21):
                Log._erase_rows([("id", "in", erased.ids)], "erasure request: probe")
        self.assertIsNone(Log._get_seal_chain_error())


@tagged("post_install", "-at_install")
class TestAccessLogSealMigration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.script = load_script(
            f"{get_module_path('base')}/migrations/1.152/post-seal.py",
            "base_1_150_post_seal",
        )

    def setUp(self):
        super().setUp()
        self.enterContext(config.patch(access_log_seal_key=SEAL_KEY))

    def seal_unkeyed(self):
        Log = self.env["ir.access.log"]
        self.env.flush_all()
        cr = self.env.cr
        cr.execute(
            "SELECT seal, seal_seq FROM ir_access_log "
            "WHERE seal_seq IS NOT NULL ORDER BY seal_seq DESC LIMIT 1"
        )
        previous, seq = cr.fetchone() or ("", 0)
        cr.execute(
            SQL(
                "SELECT id, %s FROM ir_access_log log WHERE seal IS NULL ORDER BY id",
                LEGACY_CONTENT,
            )
        )
        for row_id, content in cr.fetchall():
            seq += 1
            text = json.dumps(
                content, sort_keys=True, separators=(",", ":"), default=str
            )
            previous = hashlib.sha256((previous + text).encode()).hexdigest()
            cr.execute(
                "UPDATE ir_access_log SET seal = %s, seal_seq = %s WHERE id = %s",
                [previous, seq, row_id],
            )
        self.env["ir.config_parameter"].set_param(SEAL_HEAD, f"{seq}:{previous}")
        Log.invalidate_model()
        return seq, previous

    def test_an_unkeyed_chain_is_sealed_again_under_the_key(self):
        Log = self.env["ir.access.log"]
        rows = Log._record(
            [{"event": "grant_created", "reason": f"probe {n}"} for n in range(5)]
        )
        self.seal_unkeyed()
        self.env["ir.config_parameter"].set_param(
            SEAL_BASE, f"{rows[1].seal_seq}:{rows[1].seal}"
        )
        behind_the_trigger(
            self.env,
            SQL("DELETE FROM ir_access_log WHERE seal_seq <= %s", rows[1].seal_seq),
        )
        later = Log._record([{"event": "grant_created", "reason": "not sealed yet"}])
        seqs = rows[2:].mapped("seal_seq")

        self.script.migrate(self.env.cr, "1.149")

        self.assertIsNone(Log._get_seal_chain_error())
        self.assertEqual(Log._seal(), 1)
        rows.invalidate_recordset()
        self.assertEqual(rows[2:].mapped("seal_seq"), seqs)
        self.assertTrue(all(rows[2:].mapped("content_hash")))
        self.assertTrue(later.seal)
        self.assertFalse(self.env["ir.config_parameter"].get_param(SEAL_LEGACY))
        self.assertIsNone(Log._get_seal_chain_error())

    def test_a_broken_unkeyed_chain_is_not_sealed_again(self):
        Log = self.env["ir.access.log"]
        rows = Log._record(
            [{"event": "grant_created", "reason": f"probe {n}"} for n in range(3)]
        )
        seq, _seal = self.seal_unkeyed()
        behind_the_trigger(
            self.env,
            "UPDATE ir_access_log SET reason = 'rewritten' WHERE id = %s",
            rows[1].id,
        )
        seals = rows.mapped("seal")
        self.script.migrate(self.env.cr, "1.149")

        with self.assertLogs("odoo.addons.base.models.ir_access_log", "CRITICAL"):
            self.assertEqual(Log._seal(), 0)

        rows.invalidate_recordset()
        self.assertEqual(rows.mapped("seal"), seals)
        broken = Log.search([("event", "=", "log_chain_broken")])
        self.assertEqual(
            broken.reason,
            f"before the key: row {rows[1].id} changed after it was sealed",
        )
        self.assertEqual(
            Log._get_seal_chain_error(),
            f"before the key: row {rows[1].id} changed after it was sealed",
        )
        self.assertEqual(
            Log._remove_rows(
                [("seal_seq", "!=", False)], "retention: sealed before the key"
            ),
            seq,
        )
        self.assertTrue(broken.exists())
        self.assertGreater(Log._seal(), 0)
        self.assertFalse(self.env["ir.config_parameter"].get_param(SEAL_LEGACY))
        self.assertIsNone(Log._get_seal_chain_error())

    def test_a_broken_unkeyed_chain_is_recorded_once(self):
        Log = self.env["ir.access.log"]
        rows = Log._record(
            [{"event": "grant_created", "reason": f"probe {n}"} for n in range(2)]
        )
        self.seal_unkeyed()
        behind_the_trigger(
            self.env,
            "UPDATE ir_access_log SET reason = 'rewritten' WHERE id = %s",
            rows[0].id,
        )
        self.script.migrate(self.env.cr, "1.149")

        with self.assertLogs("odoo.addons.base.models.ir_access_log", "ERROR") as logs:
            Log._seal()
            Log._seal()
        with self.assertLogs("odoo.addons.base.models.ir_access_log", "CRITICAL"):
            Log._cron_check_seal_chain()

        self.assertEqual(
            [record.levelname for record in logs.records], ["CRITICAL", "ERROR"]
        )
        self.assertEqual(Log.search_count([("event", "=", "log_chain_broken")]), 1)

    def test_a_rotation_before_the_unkeyed_chain_is_adopted_adopts_it(self):
        Log = self.env["ir.access.log"]
        Log._record([{"event": "grant_created", "reason": "probe"}])
        self.seal_unkeyed()
        self.script.migrate(self.env.cr, "1.149")

        Log._reseal(OTHER_KEY)

        self.assertFalse(self.env["ir.config_parameter"].get_param(SEAL_LEGACY))
        self.assertIsNone(Log._get_seal_chain_error())
        Log._record([{"event": "grant_created", "reason": "after the rotation"}])
        self.assertEqual(Log._seal(), 1)
        self.assertIsNone(Log._get_seal_chain_error())

    def test_an_upgrade_without_the_key_waits_for_it(self):
        Log = self.env["ir.access.log"]
        Log._record([{"event": "grant_created", "reason": "probe"}])
        seq, seal = self.seal_unkeyed()
        with config.patch(access_log_seal_key=""):
            self.script.migrate(self.env.cr, "1.149")
            with self.assertLogs("odoo.addons.base.models.ir_access_log", "WARNING"):
                self.assertEqual(Log._seal(), 0)
            self.assertIsNone(Log._get_seal_chain_error())
        self.env.cr.execute("SELECT seal FROM ir_access_log WHERE seal_seq = %s", [seq])
        self.assertEqual(self.env.cr.fetchone()[0], seal)
        Log._record([{"event": "grant_created", "reason": "after the key"}])
        self.assertEqual(Log._seal(), 1)
        self.assertIsNone(Log._get_seal_chain_error())
