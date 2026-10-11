import inspect
import io
import logging
import os
import sys
import threading
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import psycopg.errors

from odoo import api
from odoo.api import SUPERUSER_ID
from odoo.exceptions import AccessError, UserError
from odoo.modules.db import _AUTO_INSTALL_CANDIDATES_QUERY
from odoo.modules.loading import (
    _DATA_FILE_CHECKSUM_VERSION,
    _MODULE_OPERATIONS_LOCK_KEY,
)
from odoo.modules.registry import Registry
from odoo.tests.common import (
    BaseCase,
    TransactionCase,
    get_db_name,
    new_test_user,
    tagged,
)
from odoo.tools import SQL, config, mute_logger, translate
from odoo.tools.files import file_open_temporary_directory

from odoo.addons.base.models.ir_cron import CRON_ADVISORY_LOCK_NAMESPACE
from odoo.addons.base.models.ir_job import (
    JOB_ADMISSION_LOCK,
    IrJob,
    _advisory_key_sql,
)
from odoo.addons.base.models.ir_module import (
    GROUP_HIERARCHY_FIELDS,
    localize_description_images,
)


class IrModuleCase(TransactionCase):
    @mute_logger("odoo.modules.module")
    def test_missing_module_icon(self):
        module = self.env["ir.module.module"].create({"name": "missing"})
        base = self.env["ir.module.module"].search([("name", "=", "base")])
        self.assertEqual(base.icon_image, module.icon_image)

    @mute_logger("odoo.modules.module")
    def test_new_module_icon(self):
        module = self.env["ir.module.module"].new({"name": "missing"})
        self.assertFalse(module.icon_image)

    @mute_logger("odoo.modules.module")
    def test_new_module_icon_flag(self):
        module = self.env["ir.module.module"].new({"name": "missing"})
        self.assertFalse(module.icon_flag)
        self.assertFalse(module.icon_image)

    def test_description_html_tolerates_malformed_index_html(self):
        module = self.env["ir.module.module"].search([("name", "=", "base")])

        with patch(
            "odoo.tools.file_open",
            side_effect=lambda *a, **kw: io.BytesIO(b"\x89PNG\xff\xfe broken \xff"),
        ):
            module.invalidate_recordset(["description_html"])
            self.assertIsNotNone(module.description_html)

        with patch(
            "odoo.tools.file_open",
            side_effect=lambda *a, **kw: io.BytesIO(b""),
        ):
            module.invalidate_recordset(["description_html"])
            self.assertIsNotNone(module.description_html)
        module.invalidate_recordset(["description_html"])

    @mute_logger("odoo.modules.module")
    def test_module_wrong_icon(self):
        module = self.env["ir.module.module"].create(
            {"name": "wrong_icon", "icon": "/not/valid.png"}
        )
        self.assertFalse(module.icon_image)

    def test_get_id_reflects_freshly_created_module(self):
        Module = self.env["ir.module.module"]
        self.assertIsNone(Module._get_id("irmod_l2_probe"))
        module = Module.create({"name": "irmod_l2_probe"})
        self.assertEqual(Module._get_id("irmod_l2_probe"), module.id)

    def test_update_list_returns_named_result(self):
        result = self.env["ir.module.module"].update_list()
        updated, added = result
        self.assertEqual(result.updated, updated)
        self.assertEqual(result.added, added)
        self.assertIsInstance(result.updated, int)
        self.assertIsInstance(result.added, int)

    @mute_logger("odoo.addons.base.models.ir_module")
    def test_button_install_blocked_for_erp_manager_without_system(self):
        user = new_test_user(
            self.env,
            login="irmod_erp_manager",
            groups="base.group_erp_manager",
        )
        module = self.env["ir.module.module"].create(
            {"name": "irmod_l1_probe", "state": "uninstalled"}
        )
        with self.assertRaises(AccessError):
            module.with_user(user).button_install()
        self.assertEqual(module.state, "uninstalled")

    @mute_logger("odoo.addons.base.models.ir_module")
    def test_upgrade_cascade_refuses_a_module_that_is_not_installed(self):
        module = self.env["ir.module.module"].search(
            [("state", "=", "uninstalled")], limit=1
        )
        with self.assertRaisesRegex(UserError, "not installed"):
            module._upgrade_cascade()

    def test_button_uninstall_refuses_server_wide_and_uninstalled_modules(self):
        Module = self.env["ir.module.module"]
        with self.assertRaisesRegex(UserError, "cannot be uninstalled: base"):
            Module.search([("name", "=", "base")]).button_uninstall()
        with self.assertRaisesRegex(UserError, "already been uninstalled"):
            Module.search([("state", "=", "uninstalled")], limit=1).button_uninstall()

    def test_button_upgrade_sweeps_reverse_dependencies(self):
        Module = self.env["ir.module.module"]
        base_mod = Module.create({"name": "irmod_base", "state": "installed"})
        dependent = Module.create({"name": "irmod_dependent", "state": "installed"})
        self.env["ir.module.module.dependency"].create(
            {"module_id": dependent.id, "name": "irmod_base"}
        )
        base_mod.button_upgrade()
        self.assertEqual(base_mod.state, "to upgrade")
        self.assertEqual(
            dependent.state,
            "to upgrade",
            "reverse-dependency sweep should mark dependents to upgrade",
        )

    def test_sync_auto_install_required_batched(self):
        Module = self.env["ir.module.module"]
        Dependency = self.env["ir.module.module.dependency"]
        mod_x = Module.create({"name": "irmod_sync_x", "state": "uninstalled"})
        mod_y = Module.create({"name": "irmod_sync_y", "state": "uninstalled"})
        dep_xa, dep_xb, dep_ya = Dependency.create(
            [
                {"module_id": mod_x.id, "name": "irmod_sync_dep_a"},
                {"module_id": mod_x.id, "name": "irmod_sync_dep_b"},
                {"module_id": mod_y.id, "name": "irmod_sync_dep_a"},
            ]
        )
        Module._sync_auto_install_required(
            {mod_x.id: ["irmod_sync_dep_a"], mod_y.id: ()}
        )
        self.assertTrue(dep_xa.auto_install_required)
        self.assertFalse(dep_xb.auto_install_required)
        self.assertFalse(dep_ya.auto_install_required)
        Module._sync_auto_install_required(
            {mod_x.id: ["irmod_sync_dep_a"], mod_y.id: ()}
        )
        self.assertEqual(self.env.cr.rowcount, 0)
        Module._sync_auto_install_required({mod_x.id: ["irmod_sync_dep_b"]})
        self.assertFalse(dep_xa.auto_install_required)
        self.assertTrue(dep_xb.auto_install_required)

    @mute_logger("odoo.addons.base.models.ir_module", "odoo.modules.module")
    def test_button_install_exclusive_category_closure(self):
        Module = self.env["ir.module.module"]
        category = self.env["ir.module.category"].create(
            {"name": "irmod excl cat", "exclusive": True}
        )
        Module.create(
            {"name": "irmod_excl_a", "state": "installed", "category_id": category.id}
        )
        mod_b = Module.create(
            {"name": "irmod_excl_b", "state": "installed", "category_id": category.id}
        )
        self.env["ir.module.module.dependency"].create(
            {"module_id": mod_b.id, "name": "irmod_excl_a"}
        )
        mod_b.button_install()
        Module.create(
            {"name": "irmod_excl_c", "state": "installed", "category_id": category.id}
        )
        with self.assertRaises(UserError):
            mod_b.button_install()

    def test_has_iap_transitive_dependents(self):
        Module = self.env["ir.module.module"]
        if not Module._get_id("iap"):
            self.skipTest("iap module not present in the addons path")
        direct = Module.create({"name": "irmod_iap_dep", "state": "uninstalled"})
        indirect = Module.create({"name": "irmod_iap_dep2", "state": "uninstalled"})
        self.env["ir.module.module.dependency"].create(
            [
                {"module_id": direct.id, "name": "iap"},
                {"module_id": indirect.id, "name": "irmod_iap_dep"},
            ]
        )
        unrelated = Module.create({"name": "irmod_no_iap", "state": "uninstalled"})
        self.assertTrue(direct.has_iap)
        self.assertTrue(indirect.has_iap)
        self.assertFalse(unrelated.has_iap)


class TestModuleDependencyClosure(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Module = cls.env["ir.module.module"]
        cls.mod_a = Module.create({"name": "tclos_a", "state": "installed"})
        cls.mod_b = Module.create({"name": "tclos_b", "state": "installed"})
        cls.mod_c = Module.create({"name": "tclos_c", "state": "uninstalled"})
        cls.mod_d = Module.create({"name": "tclos_d", "state": "installed"})
        cls.env["ir.module.module.dependency"].create(
            [
                {"module_id": cls.mod_b.id, "name": "tclos_a"},
                {"module_id": cls.mod_c.id, "name": "tclos_b"},
                {"module_id": cls.mod_d.id, "name": "tclos_c"},
            ]
        )

    def test_downstream_full_closure(self):
        got = self.mod_a.downstream_dependencies(exclude_states=())
        self.assertEqual(set(got.ids), {self.mod_b.id, self.mod_c.id, self.mod_d.id})
        self.assertNotIn(self.mod_a.id, got.ids)

    def test_downstream_state_pruning_blocks_paths(self):
        got = self.mod_a.downstream_dependencies()
        self.assertEqual(set(got.ids), {self.mod_b.id})

    def test_upstream_full_closure(self):
        got = self.mod_d.upstream_dependencies(exclude_states=())
        self.assertEqual(set(got.ids), {self.mod_a.id, self.mod_b.id, self.mod_c.id})
        self.assertNotIn(self.mod_d.id, got.ids)

    def test_upstream_default_excludes_installed(self):
        got = self.mod_d.upstream_dependencies()
        self.assertEqual(set(got.ids), {self.mod_c.id})

    def test_empty_string_exclude_matches_no_state(self):
        got = self.mod_d.upstream_dependencies(exclude_states=("",))
        self.assertEqual(set(got.ids), {self.mod_a.id, self.mod_b.id, self.mod_c.id})

    def test_known_deps_blocks_traversal_and_unions_result(self):
        got = self.mod_a.downstream_dependencies(
            known_deps=self.mod_b, exclude_states=()
        )
        self.assertEqual(set(got.ids), {self.mod_b.id})

    def test_seed_traversed_regardless_of_state(self):
        self.mod_a.state = "to remove"
        got = self.mod_a.downstream_dependencies()
        self.assertEqual(set(got.ids), {self.mod_b.id})

    def test_empty_recordset_closure(self):
        empty = self.env["ir.module.module"]
        self.assertFalse(empty.downstream_dependencies(exclude_states=()))
        self.assertFalse(empty.upstream_dependencies(exclude_states=()))


class IrModuleUnsavedRecordCase(TransactionCase):
    def test_get_module_info_without_name(self):
        self.assertIsNone(self.env["ir.module.module"].get_module_info(False))
        self.assertIsNone(self.env["ir.module.module"].get_module_info(""))

    def test_manifest_version_on_unsaved_record(self):
        module = self.env["ir.module.module"].new({})
        self.assertTrue(module.manifest_version)

    def test_get_module_info_still_reads_real_manifest(self):
        manifest = self.env["ir.module.module"].get_module_info("base")
        self.assertTrue(manifest)
        self.assertTrue(manifest.get("version"))


class IrModuleAutoInstallCase(TransactionCase):
    def _make(self, name, **kw):
        return self.env["ir.module.module"].create(
            {"name": name, "state": "uninstalled", **kw}
        )

    def _depend(self, module, name, required=True):
        return self.env["ir.module.module.dependency"].create(
            {"module_id": module.id, "name": name, "auto_install_required": required}
        )

    @mute_logger("odoo.addons.base.models.ir_module")
    def test_uninstallable_non_trigger_dependency_blocks_auto_install(self):
        trigger = self._make("airm_trigger")
        self._make("airm_bad", state="uninstallable")
        victim = self._make("airm_victim", auto_install=True)
        self._depend(victim, "airm_trigger", required=True)
        self._depend(victim, "airm_bad", required=False)

        trigger.button_install()

        self.assertEqual(trigger.state, "to install")
        self.assertEqual(
            victim.state,
            "uninstalled",
            "a module whose hard dependency is uninstallable can never load; "
            "marking it 'to install' strands it and blocks every later "
            "module operation until the cron safety net fires",
        )

    @mute_logger("odoo.addons.base.models.ir_module")
    def test_unknown_non_trigger_dependency_does_not_abort_the_users_install(self):
        trigger = self._make("airm_trigger2")
        victim = self._make("airm_victim2", auto_install=True)
        self._depend(victim, "airm_trigger2", required=True)
        self._depend(victim, "airm_no_such_module", required=False)

        trigger.button_install()

        self.assertEqual(trigger.state, "to install")
        self.assertEqual(victim.state, "uninstalled")

    @mute_logger("odoo.addons.base.models.ir_module")
    def test_direct_install_refuses_an_uninstallable_dependency(self):
        self._make("airm_direct_bad", state="uninstallable")
        victim = self._make("airm_direct_victim")
        self._depend(victim, "airm_direct_bad")

        with self.assertRaises(UserError) as caught:
            victim.button_install()

        self.assertIn("airm_direct_bad", str(caught.exception))
        self.assertIn("cannot be installed", str(caught.exception))
        self.assertEqual(victim.state, "uninstalled")

    @mute_logger("odoo.addons.base.models.ir_module")
    def test_direct_install_refuses_an_unknown_dependency(self):
        victim = self._make("airm_direct_victim2")
        self._depend(victim, "airm_no_such_module_at_all")

        with self.assertRaises(UserError) as caught:
            victim.button_install()

        self.assertIn("not available in your system", str(caught.exception))
        self.assertEqual(victim.state, "uninstalled")

    @mute_logger("odoo.addons.base.models.ir_module")
    def test_a_transitively_unsatisfiable_dependency_is_refused_too(self):
        self._make("airm_chain_bad", state="uninstallable")
        middle = self._make("airm_chain_middle")
        self._depend(middle, "airm_chain_bad")
        top = self._make("airm_chain_top")
        self._depend(top, "airm_chain_middle")

        with self.assertRaises(UserError):
            top.button_install()

        self.assertEqual(top.state, "uninstalled")
        self.assertEqual(middle.state, "uninstalled")

    @mute_logger("odoo.addons.base.models.ir_module")
    def test_satisfiable_auto_install_still_happens(self):
        trigger = self._make("airm_trigger3")
        other = self._make("airm_other3")
        victim = self._make("airm_victim3", auto_install=True)
        self._depend(victim, "airm_trigger3", required=True)
        self._depend(victim, "airm_other3", required=False)

        trigger.button_install()

        self.assertEqual(victim.state, "to install")
        self.assertEqual(other.state, "to install")

    def test_predicate_matches_the_sql_rule_in_modules_db(self):
        trigger = self._make("airm_sql_trigger")
        self._make("airm_sql_bad", state="uninstallable")
        victim = self._make("airm_sql_victim", auto_install=True)
        self._depend(victim, "airm_sql_trigger", required=True)
        self._depend(victim, "airm_sql_bad", required=False)
        trigger.state = "to install"
        self.env.flush_all()

        self.env.cr.execute(_AUTO_INSTALL_CANDIDATES_QUERY)
        sql_says = {row[0] for row in self.env.cr.fetchall()}

        self.assertNotIn("airm_sql_victim", sql_says)
        self.assertFalse(victim._is_auto_install_satisfiable())


class IrModuleConcurrencyGuardCase(TransactionCase):
    registry_test_mode = False
    PROBE = "airm_committed_elsewhere"

    def _side_execute(self, sql, params):
        with self.registry.cursor() as side_cr:
            side_cr.execute(sql, params)
            side_cr.commit()

    def _snapshot_sees_probe(self):
        self.env.cr.execute(
            "SELECT FROM ir_module_module WHERE name = %s AND state = %s",
            [self.PROBE, "to install"],
        )
        return bool(self.env.cr.rowcount)

    def test_guard_sees_a_pending_state_its_own_snapshot_cannot(self):
        Module = self.env["ir.module.module"]
        Module.search_count([])

        if Module._has_pending_module_operation():
            self.skipTest("a module operation is already pending in this database")

        self._side_execute(
            "INSERT INTO ir_module_module (name, state) VALUES (%s, %s)",
            [self.PROBE, "to install"],
        )
        self.addCleanup(
            self._side_execute,
            "DELETE FROM ir_module_module WHERE name = %s",
            [self.PROBE],
        )

        self.assertFalse(
            self._snapshot_sees_probe(),
            "precondition: this transaction's frozen snapshot is blind to it",
        )
        self.assertTrue(
            Module._has_pending_module_operation(),
            "the guard must read committed state, not the request snapshot",
        )

    def test_guard_does_not_deadlock_against_the_lock_it_runs_under(self):
        self.env.cr.execute("SET LOCAL lock_timeout = '5s'")
        self.env.cr.execute("LOCK ir_module_module IN EXCLUSIVE MODE")
        self.assertIsInstance(
            self.env["ir.module.module"]._has_pending_module_operation(), bool
        )


@tagged("post_install", "-at_install")
class IrModuleOperationGuardCase(BaseCase):
    def setUp(self):
        super().setUp()
        self.db_name = get_db_name()
        self.registry = Registry(self.db_name)
        with self.registry.cursor() as cr:
            if api.Environment(cr, SUPERUSER_ID, {})[
                "ir.module.module"
            ]._has_pending_module_operation():
                self.skipTest("a module operation is already pending in this database")

    @contextmanager
    def _operation(self):
        with self.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            with env["ir.module.module"]._lock_against_concurrent_module_operations():
                yield env

    def _enter_guard(self):
        with self._operation():
            pass

    def _guard_while_another_connection_holds(self, statement, expected):
        with self.registry.cursor() as side_cr:
            side_cr.execute(statement)
            with self.assertRaisesRegex(UserError, expected):
                self._enter_guard()
            side_cr.rollback()
        self.assertTrue(self._is_queue_open(), "the refusal let go of the queue")

    def test_a_held_table_lock_reads_as_a_busy_module_operation(self):
        self._guard_while_another_connection_holds(
            "LOCK ir_module_module IN EXCLUSIVE MODE", "another module operation"
        )

    def test_a_locked_cron_row_reads_as_a_running_scheduled_action(self):
        self._guard_while_another_connection_holds(
            "SELECT id FROM ir_cron FOR UPDATE", "scheduled action"
        )

    def test_a_job_the_cron_runner_holds_reads_as_a_running_scheduled_action(self):
        with self.registry.cursor() as cr:
            cron_id = (
                api.Environment(cr, SUPERUSER_ID, {})["ir.cron"]
                .with_context(active_test=False)
                .search([], limit=1)
                .id
            )
        self._guard_while_another_connection_holds(
            f"SELECT pg_advisory_xact_lock({CRON_ADVISORY_LOCK_NAMESPACE}, {cron_id})",
            "scheduled action",
        )

    def test_an_operation_of_another_process_is_refused_at_once(self):
        with self._wait_for_jobs(10), self._job_running_elsewhere():
            started = time.monotonic()
            self._guard_while_another_connection_holds(
                f"SELECT pg_advisory_xact_lock({_MODULE_OPERATIONS_LOCK_KEY})",
                "another module operation",
            )
            self.assertLess(
                time.monotonic() - started, 5, "it waited for jobs it would not run"
            )

    @contextmanager
    def _job_running_elsewhere(self, finishes_after=None, last_step=None):
        side = self.registry.cursor()
        side.execute(
            "INSERT INTO ir_job (channel, state, priority, model_name,"
            " method_name, user_id, max_retries, retry, worker_ident, started_at,"
            " create_uid, create_date, write_uid, write_date) VALUES"
            " ('modop', 'started', 10, 'ir.job', '_job_ping', 1, 5, 0,"
            " 'elsewhere:1', now() AT TIME ZONE 'UTC', 1, now(), 1, now())"
            " RETURNING id"
        )
        job_id = side.fetchone()[0]
        side.execute(SQL("SELECT pg_advisory_lock_shared(%s)", JOB_ADMISSION_LOCK))
        side.execute(SQL("SELECT pg_advisory_lock(%s)", _advisory_key_sql(job_id)))
        side.commit()

        def finish():
            side.execute("SELECT pg_advisory_unlock_all()")
            side.commit()

        def run_to_its_end():
            if last_step is not None:
                last_step(side)
            finish()

        timer = (
            threading.Timer(finishes_after, run_to_its_end) if finishes_after else None
        )
        try:
            if timer:
                timer.start()
            yield job_id
        finally:
            if timer:
                timer.join()
            finish()
            side.execute("DELETE FROM ir_job WHERE id = %s", [job_id])
            side.commit()
            side.close()

    def _wait_for_jobs(self, seconds):
        return config.patch(module_operation_job_wait=seconds)

    def _is_queue_open(self):
        with self.registry.cursor() as worker:
            worker.execute(
                SQL("SELECT pg_try_advisory_xact_lock_shared(%s)", JOB_ADMISSION_LOCK)
            )
            return worker.fetchone()[0]

    def test_a_module_operation_waits_for_a_running_job_to_finish(self):
        with self._wait_for_jobs(10), self._job_running_elsewhere(finishes_after=0.5):
            started = time.monotonic()
            self._enter_guard()
            waited = time.monotonic() - started
        self.assertGreaterEqual(waited, 0.4, "it did not wait for the job")
        self.assertLess(waited, 9, "it waited out its budget, not the job")

    def test_a_module_operation_refuses_naming_the_jobs_still_running(self):
        with self._wait_for_jobs(1), self._job_running_elsewhere() as job_id:
            with self.assertRaisesRegex(
                UserError, rf"(?s)background jobs.*{job_id}.*ir\.job\._job_ping"
            ):
                self._enter_guard()
            self.assertTrue(
                self._is_queue_open(),
                "the refused operation still holds new jobs off",
            )

    def test_a_refusal_wakes_the_job_workers_it_held_off(self):
        with (
            self._wait_for_jobs(1),
            self._job_running_elsewhere(),
            patch.object(IrJob, "_notify_workers") as notify,
            self.assertRaisesRegex(UserError, "background jobs"),
        ):
            self._enter_guard()
        notify.assert_called_once_with(self.db_name)

    def test_the_wait_for_jobs_locks_no_module_row(self):
        outcome = []

        def operate():
            try:
                self._enter_guard()
                outcome.append("done")
            except Exception as exc:
                outcome.append(exc)

        with self._wait_for_jobs(10), self._job_running_elsewhere(finishes_after=2):
            operation = threading.Thread(target=operate)
            operation.start()
            try:
                time.sleep(0.5)
                with self.registry.cursor() as writer:
                    writer.execute("SET LOCAL lock_timeout = '500ms'")
                    try:
                        writer.execute(
                            "SELECT id FROM ir_module_module LIMIT 1 FOR UPDATE"
                        )
                        locked_out = False
                    except psycopg.errors.LockNotAvailable:
                        locked_out = True
                    writer.rollback()
            finally:
                operation.join()
        self.assertFalse(
            locked_out, "a writer of ir_module_module waited on the job wait"
        )
        self.assertEqual(outcome, ["done"])

    def test_no_job_is_admitted_while_a_module_operation_runs(self):
        with self._wait_for_jobs(5), self._operation():
            self.assertFalse(self._is_queue_open(), "a job could start mid-operation")
        self.assertTrue(self._is_queue_open(), "the operation let go of the queue")

    def test_the_thread_of_a_module_operation_runs_its_own_jobs(self):
        with self.registry.cursor() as cr:
            job_id = (
                api.Environment(cr, SUPERUSER_ID, {})["ir.job"]
                .delayed(channel="modop")
                ._job_ping("own")
                .id
            )
        self.addCleanup(self._delete_job, job_id)
        refused_elsewhere = []

        def run_elsewhere():
            with self.registry.cursor() as cr:
                job = api.Environment(cr, SUPERUSER_ID, {})["ir.job"].browse(job_id)
                try:
                    job.action_run_now()
                except UserError:
                    refused_elsewhere.append(True)
                cr.rollback()

        with self._wait_for_jobs(5), self._operation():
            elsewhere = threading.Thread(target=run_elsewhere)
            elsewhere.start()
            elsewhere.join()
            with self.registry.cursor() as cr:
                job = api.Environment(cr, SUPERUSER_ID, {})["ir.job"].browse(job_id)
                job.action_run_now()
                self.assertEqual(job.state, "done")
        self.assertEqual(
            refused_elsewhere, [True], "another thread ran a job mid-operation"
        )

    def _delete_job(self, job_id):
        with self.registry.cursor() as cr:
            cr.execute("DELETE FROM ir_job WHERE id = %s", [job_id])

    def test_a_draining_job_can_still_reach_the_crons(self):
        reached = []

        def touch_a_cron(side):
            try:
                with side.savepoint(flush=False):
                    side.execute("SET LOCAL lock_timeout = '2s'")
                    side.execute("SELECT id FROM ir_cron LIMIT 1 FOR KEY SHARE")
                reached.append(True)
            except psycopg.errors.LockNotAvailable, psycopg.errors.DeadlockDetected:
                reached.append(False)

        with (
            self._wait_for_jobs(10),
            self._job_running_elsewhere(finishes_after=0.5, last_step=touch_a_cron),
        ):
            self._enter_guard()
        self.assertEqual(
            reached,
            [True],
            "the job waited on a cron row the module operation had locked "
            "while it waited on the job",
        )

    def test_a_dead_worker_does_not_hold_up_a_module_operation(self):
        with self._wait_for_jobs(10), self._job_running_elsewhere(finishes_after=0.01):
            time.sleep(0.1)
            started = time.monotonic()
            self._enter_guard()
            self.assertLess(time.monotonic() - started, 5)


class IrModuleDescriptionRenderingCase(TransactionCase):
    def test_rst_warnings_never_reach_stderr(self):
        module = self.env["ir.module.module"].create(
            {
                "name": "airm_rst",
                "description": "Too short\n===\n\nbody\n",
            }
        )
        read_fd, write_fd = os.pipe()
        saved = os.dup(2)
        os.dup2(write_fd, 2)
        os.close(write_fd)
        logging.disable(logging.CRITICAL)
        try:
            module.invalidate_recordset(["description_html"])
            self.assertTrue(module.description_html)
        finally:
            logging.disable(logging.NOTSET)
            sys.stderr.flush()
            os.dup2(saved, 2)
            os.close(saved)
        os.set_blocking(read_fd, False)
        try:
            leaked = os.read(read_fd, 65536)
        except BlockingIOError:
            leaked = b""
        os.close(read_fd)
        self.assertEqual(leaked, b"", "docutils must not write to stderr")

    def test_description_images_are_localized(self):
        html = localize_description_images("airm_mod", '<img src="banner.png"/>')
        self.assertIn("/airm_mod/static/description/banner.png", html)

    def test_absolute_and_static_image_sources_are_left_alone(self):
        html = localize_description_images(
            "airm_mod", '<img src="//cdn/x.png"/><img src="static/y.png"/>'
        )
        self.assertIn("//cdn/x.png", html)
        self.assertNotIn("/airm_mod/static/description/", html)


class IrModuleLinkModelCase(TransactionCase):
    def test_dependency_and_exclusion_share_one_implementation(self):
        for model in ("ir.module.module.dependency", "ir.module.module.exclusion"):
            self.assertIn("mixin.module.link", self.env[model]._inherit)

    def test_exclusion_table_has_no_log_access_columns(self):
        self.assertFalse(self.env["ir.module.module.exclusion"]._log_access)

    def test_linked_id_search_tolerates_deleted_ids(self):
        Dependency = self.env["ir.module.module.dependency"]
        self.assertFalse(Dependency.search([("linked_id", "in", [2147483000])]))

    def test_linked_id_search_by_name_agrees_with_search_by_id(self):
        Dependency = self.env["ir.module.module.dependency"]
        base = self.env["ir.module.module"].search([("name", "=", "base")])
        by_id = Dependency.search([("linked_id", "in", base.ids)])
        by_name = Dependency.search([("linked_id", "in", ["base"])])
        self.assertTrue(by_id)
        self.assertEqual(by_id, by_name)

    def test_linked_id_false_matches_the_unknown_dependencies(self):
        Module = self.env["ir.module.module"]
        Dependency = self.env["ir.module.module.dependency"]
        host = Module.create({"name": "airm_host", "state": "uninstalled"})
        unknown = Dependency.create(
            {"module_id": host.id, "name": "airm_definitely_absent"}
        )
        known = Dependency.create({"module_id": host.id, "name": "base"})
        self.assertEqual(unknown.state, "unknown")
        found = Dependency.search([("linked_id", "=", False)])
        self.assertIn(unknown, found)
        self.assertNotIn(known, found)


class IrModuleUpdateListStateCase(TransactionCase):
    def test_a_module_whose_manifest_turned_uninstallable_becomes_uninstallable(self):
        module = self.env["ir.module.module"].search([("name", "=", "iot_drivers")])
        self.assertTrue(module, "need a module whose manifest says installable False")
        module.state = "uninstalled"
        self.env["ir.module.module"].update_list()
        self.assertEqual(module.state, "uninstallable")

    def test_an_uninstalled_installable_module_stays_installable(self):
        Module = self.env["ir.module.module"]
        module = Module.search([("state", "=", "uninstalled")]).filtered(
            lambda m: Module._is_installable(m.name)
        )[:1]
        self.assertTrue(module, "need an uninstalled installable module")
        Module.update_list()
        self.assertEqual(module.state, "uninstalled")


class IrModuleUpdateListCountCase(TransactionCase):
    def test_a_module_that_was_never_installed_is_not_counted(self):
        Module = self.env["ir.module.module"]
        never_installed = Module.search(
            [("state", "=", "uninstalled"), ("name", "!=", "base")], limit=1
        )
        self.assertTrue(never_installed, "need an uninstalled module")

        never_installed.db_version = False
        Module.invalidate_model()
        without = Module.update_list().updated

        never_installed.db_version = "0.1"
        Module.invalidate_model()
        with_stamp = Module.update_list().updated

        self.assertEqual(
            with_stamp - without,
            1,
            "only a module carrying an installed version can be 'updated'",
        )

    def test_an_outdated_installed_module_is_counted(self):
        Module = self.env["ir.module.module"]
        base = Module.search([("name", "=", "base")])
        base.db_version = "0.1"
        Module.invalidate_model()
        with_outdated = Module.update_list().updated
        base.db_version = "99.0.99"
        Module.invalidate_model()
        without_outdated = Module.update_list().updated
        self.assertEqual(with_outdated - without_outdated, 1)


class IrModuleUninstallStateCase(TransactionCase):
    def test_module_uninstall_clears_every_installed_version_stamp(self):
        module = self.env["ir.module.module"].create(
            {
                "name": "airm_uninstall",
                "state": "installed",
                "db_version": "19.0.1.0",
                "content_checksum": "DEADBEEF",
                "data_file_checksums": {"v": 1},
            }
        )
        module.module_uninstall()
        self.assertEqual(module.state, "uninstalled")
        self.assertFalse(module.db_version)
        self.assertFalse(module.content_checksum)
        self.assertFalse(module.data_file_checksums)


class IrModuleHasIapCase(TransactionCase):
    def test_has_iap_tracks_a_new_dependency_without_a_manual_invalidation(self):
        Module = self.env["ir.module.module"]
        if not Module._get_id("iap"):
            self.skipTest("iap module not present in the addons path")
        module = Module.create({"name": "airm_iap", "state": "uninstalled"})
        self.assertFalse(module.has_iap)
        self.env["ir.module.module.dependency"].create(
            {"module_id": module.id, "name": "iap"}
        )
        self.assertTrue(module.has_iap)

    def test_iap_itself_reports_iap(self):
        Module = self.env["ir.module.module"]
        iap = Module.search([("name", "=", "iap")])
        if not iap:
            self.skipTest("iap module not present in the addons path")
        self.assertTrue(iap.has_iap)


class IrModuleTranslationDiagnosticCase(TransactionCase):
    def _missing_lines(self, order, translated):
        Module = self.env["ir.module.module"]

        def fake_load_file(importer, path, lang, **kwargs):
            return 1 if path.startswith(translated) else 0

        with (
            patch(
                "odoo.addons.base.models.ir_module.get_po_paths",
                side_effect=lambda module, lang: [f"{module}/i18n/{lang}.po"],
            ),
            patch(
                "odoo.addons.base.models.ir_module.get_datafile_translation_path",
                side_effect=lambda module: [],
            ),
            patch(
                "odoo.addons.base.models.ir_module.Manifest.for_addon",
                side_effect=lambda name, **kw: object(),
            ),
            patch(
                "odoo.tools.translate.TranslationImporter.load_file",
                autospec=True,
                side_effect=fake_load_file,
            ),
            patch("odoo.tools.translate.TranslationImporter.save"),
            patch("odoo.addons.base.models.ir_module.code_translations.clear"),
            self.assertLogs("odoo.addons.base.models.ir_module", level="INFO") as logs,
        ):
            Module._load_module_terms(order, ["fr_FR"])
        return {
            line.split("module ")[1].split(":")[0]
            for line in logs.output
            if "no translation for language" in line
        }

    def test_reported_module_does_not_depend_on_position_in_the_list(self):
        first = self._missing_lines(["alpha", "beta"], translated="alpha")
        second = self._missing_lines(["beta", "alpha"], translated="alpha")
        self.assertEqual(first, {"beta"})
        self.assertEqual(
            first,
            second,
            "the module without a translation must be reported either way",
        )

    def test_a_language_an_earlier_module_imported_is_not_missing_from_a_later_one(
        self,
    ):
        self.assertEqual(
            self._missing_lines(["alpha", "beta"], translated=("alpha", "beta")),
            set(),
        )

    def test_each_data_file_is_read_once_for_all_languages(self):
        langs = ["fr_FR", "de_DE", "es_ES"]
        for code in langs:
            self.env["res.lang"]._activate_lang(code)
        data_paths = set(translate.get_datafile_translation_path("base"))
        opened = Counter()
        real_file_open = translate.file_open

        def counting_file_open(path, *args, **kwargs):
            opened[path] += 1
            return real_file_open(path, *args, **kwargs)

        with patch.object(translate, "file_open", counting_file_open):
            self.env["ir.module.module"]._load_module_terms(["base"], langs)
        self.assertTrue(data_paths & set(opened))
        self.assertEqual(
            {path: n for path, n in opened.items() if path in data_paths and n > 1},
            {},
        )

    def test_a_module_translating_only_code_terms_is_not_missing(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        po_path = Path(self.enterContext(file_open_temporary_directory()), "fr.po")
        po_path.write_text(
            "#. module: alpha\n"
            "#. odoo-javascript\n"
            "#: code:addons/alpha/static/src/app.js:0\n"
            'msgid "Farming"\n'
            'msgstr "Agriculture"\n',
            encoding="utf-8",
        )
        with (
            patch(
                "odoo.addons.base.models.ir_module.get_po_paths",
                side_effect=lambda module, lang: (
                    [str(po_path)] if module == "alpha" else []
                ),
            ),
            patch(
                "odoo.addons.base.models.ir_module.get_datafile_translation_path",
                side_effect=lambda module: [],
            ),
            patch(
                "odoo.addons.base.models.ir_module.Manifest.for_addon",
                side_effect=lambda name, **kw: object(),
            ),
            patch("odoo.addons.base.models.ir_module.code_translations.clear"),
            self.assertLogs("odoo.addons.base.models.ir_module", level="INFO") as logs,
        ):
            self.env["ir.module.module"]._load_module_terms(
                ["alpha", "beta"], ["fr_FR"]
            )
        self.assertEqual(
            [
                line.split(":", 2)[2]
                for line in logs.output
                if "no translation for language" in line
            ],
            ["module beta: no translation for language fr_FR"],
        )


class IrModuleCategoryCacheCase(TransactionCase):
    def _cleared_by(self, vals):
        category = self.env["ir.module.category"].create({"name": "irmod cache"})
        self.env["res.groups"]._get_view_group_hierarchy()
        cleared = []
        with patch.object(
            type(self.env.registry),
            "clear_cache",
            lambda registry, *names: cleared.extend(names),
        ):
            category.write(vals)
        return "groups" in cleared

    def test_a_name_change_clears_the_group_hierarchy(self):
        self.assertTrue(self._cleared_by({"name": "irmod cache renamed"}))

    def test_a_sequence_change_does_not(self):
        self.assertFalse(self._cleared_by({"sequence": 42}))

    def test_a_visibility_change_does_not(self):
        self.assertFalse(self._cleared_by({"visible": False}))

    def test_the_guarded_fields_are_the_ones_the_hierarchy_reads(self):
        source = inspect.getsource(
            type(self.env["res.groups"])._get_view_group_hierarchy
        )
        categories = source.split('"categories"')[1]
        for field in GROUP_HIERARCHY_FIELDS:
            self.assertIn(
                f"category.{field}",
                categories,
                f"{field} is guarded but the hierarchy no longer reads it",
            )


class IrModuleStableCacheCase(TransactionCase):
    def _cleared_by(self, vals):
        module = self.env["ir.module.module"].search(
            [("state", "=", "uninstalled")], limit=1
        )
        self.assertTrue(module, "precondition: an uninstalled module to touch")
        cleared = []
        with patch.object(
            type(self.env.registry),
            "clear_cache",
            lambda registry, *names: cleared.extend(names),
        ):
            module.write(vals)
        return "stable" in cleared

    def test_a_state_change_clears_the_installed_map(self):
        self.assertTrue(self._cleared_by({"state": "to install"}))

    def test_a_name_change_clears_the_id_lookup(self):
        self.assertTrue(self._cleared_by({"name": "irmod_stable_renamed"}))

    def test_a_summary_change_does_not(self):
        self.assertFalse(self._cleared_by({"summary": "irmod stable"}))

    def test_rewriting_the_current_state_does_not(self):
        self.assertFalse(self._cleared_by({"state": "uninstalled"}))

    def test_installed_sees_a_state_flip(self):
        Module = self.env["ir.module.module"]
        module = Module.search([("state", "=", "uninstalled")], limit=1)
        self.assertNotIn(module.name, Module._get_installed_module_ids())
        module.write({"state": "installed"})
        self.assertIn(module.name, Module._get_installed_module_ids())


class IrModuleUpgradeCascadeOverrideCase(TransactionCase):

    def _cascade(self, requested, stamped, data_files):
        Module = self.env["ir.module.module"]
        modules = {}
        for name in stamped:
            modules[name] = Module.create(
                {
                    "name": f"airm_{name}",
                    "state": "installed",
                    "content_checksum": stamped[name],
                    "data_file_checksums": data_files.get(name),
                }
            )
        checksums = {f"airm_{n}": v for n, v in stamped.items()}
        with (
            patch(
                "odoo.addons.base.models.ir_module.get_module_content_checksum",
                side_effect=checksums.get,
            ),
            config.patch(skip_unchanged_modules=True),
        ):
            marked = modules[requested]._get_module_ids_to_upgrade(
                list(modules.values())
            )
        return {n for n, m in modules.items() if m.id in marked}

    def test_an_unchanged_dependent_overriding_the_upgraded_module_is_kept(self):
        marked = self._cascade(
            "sale",
            {"sale": "changed", "sale_mgmt": "same", "other": "same"},
            {
                "sale_mgmt": {
                    "v": _DATA_FILE_CHECKSUM_VERSION,
                    "files": {
                        "menus.xml": {"sha": "x", "xmlids": ["airm_sale.menu_root"]}
                    },
                },
                "other": {
                    "v": _DATA_FILE_CHECKSUM_VERSION,
                    "files": {"data.xml": {"sha": "x", "xmlids": ["airm_other.a"]}},
                },
            },
        )
        self.assertEqual(marked, {"sale", "sale_mgmt"})

    def test_the_override_chain_is_followed_to_a_fixpoint(self):
        marked = self._cascade(
            "a",
            {"a": "changed", "b": "same", "c": "same"},
            {
                "b": {
                    "v": _DATA_FILE_CHECKSUM_VERSION,
                    "files": {"f": {"sha": "x", "xmlids": ["airm_a.r"]}},
                },
                "c": {
                    "v": _DATA_FILE_CHECKSUM_VERSION,
                    "files": {"f": {"sha": "x", "xmlids": ["airm_b.r"]}},
                },
            },
        )
        self.assertEqual(marked, {"a", "b", "c"})

    def test_a_module_with_no_stored_checksums_is_not_trusted_to_be_skippable(self):
        marked = self._cascade("a", {"a": "changed", "b": "same"}, {})
        self.assertEqual(marked, {"a", "b"})

    def test_a_stamp_of_another_checksum_version_is_not_trusted_to_be_skippable(
        self,
    ):
        stale = {"f": {"sha": "x", "xmlids": ["airm_b.r"], "refs": {}}}
        marked = self._cascade(
            "a",
            {"a": "changed", "b": "same"},
            {"b": {"v": _DATA_FILE_CHECKSUM_VERSION - 1, "files": stale}},
        )
        self.assertEqual(marked, {"a", "b"})

    def _referencing(self, name, res_id):
        return {
            "v": _DATA_FILE_CHECKSUM_VERSION,
            "files": {
                "view.xml": {
                    "sha": "x",
                    "xmlids": [f"airm_{name}.view"],
                    "refs": {"base.main_company": res_id},
                }
            },
        }

    def test_an_unchanged_dependent_whose_reference_was_recreated_is_kept(self):
        company = self.env.ref("base.main_company").id
        marked = self._cascade(
            "a",
            {"a": "changed", "b": "same", "c": "same"},
            {
                "b": self._referencing("b", company + 1000),
                "c": self._referencing("c", company),
            },
        )
        self.assertEqual(marked, {"a", "b"})
