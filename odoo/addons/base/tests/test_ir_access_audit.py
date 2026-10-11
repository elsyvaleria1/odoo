from contextlib import contextmanager
from unittest.mock import patch

import psycopg

from odoo.api import MODULE_UNINSTALL_FLAG
from odoo.exceptions import AccessError, UserError
from odoo.fields import Command, Domain
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.base.models.ir_access_audit import MODULE_CHANGES


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

    def test_a_sealed_row_changed_behind_the_database_breaks_the_chain(self):
        Log = self.env["ir.access.log"]
        rows = Log._record(
            [{"event": "grant_created", "reason": f"probe {n}"} for n in range(3)]
        )
        Log._seal()
        self.assertIsNone(Log._get_seal_chain_error())

        self.env.cr.execute(
            "ALTER TABLE ir_access_log DISABLE TRIGGER ir_access_log_append_only"
        )
        self.env.cr.execute(
            "UPDATE ir_access_log SET reason = 'rewritten' WHERE id = %s", [rows[1].id]
        )
        self.assertEqual(
            Log._get_seal_chain_error(), f"row {rows[1].id} changed after it was sealed"
        )
        with mute_logger("odoo.addons.base.models.ir_access_log"):
            Log._cron_check_seal_chain()
        self.assertTrue(Log.search([("event", "=", "log_chain_broken")]))

        self.env.cr.execute(
            "UPDATE ir_access_log SET reason = 'probe 1' WHERE id = %s", [rows[1].id]
        )
        self.assertIsNone(Log._get_seal_chain_error())
        self.env.cr.execute("DELETE FROM ir_access_log WHERE id = %s", [rows[2].id])
        self.assertIn("the end of the chain was deleted", Log._get_seal_chain_error())
        self.env.cr.execute("DELETE FROM ir_access_log WHERE id = %s", [rows[0].id])
        self.assertIn(
            "is missing: a sealed row was deleted", Log._get_seal_chain_error()
        )
        self.env.cr.execute(
            "ALTER TABLE ir_access_log ENABLE TRIGGER ir_access_log_append_only"
        )
