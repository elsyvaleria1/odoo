import threading
import time
from collections import Counter
from datetime import timedelta

import psycopg.errors

from odoo import fields
from odoo.db import db_connect
from odoo.service.transaction import retrying
from odoo.tests import TransactionCase, tagged
from odoo.tools import SQL, mute_logger

from odoo.addons.base.models.mixin_access_graph_reach import REACH_COLUMNS

NODE = "test_access_right.graph_node"
GRANT = "test_access_right.graph_grant"


@tagged("post_install", "-at_install")
class TestAccessGraphRaces(TransactionCase):
    def setUp(self):
        super().setUp()
        self.admin = self.env.ref("base.user_admin")
        self.addCleanup(self.drop_committed)

    def cursor(self):
        return db_connect(self.env.cr.dbname).cursor()

    def drop_committed(self):
        with self.cursor() as cr:
            cr.execute(
                "DELETE FROM test_access_right_graph_node WHERE name LIKE 'race %%'"
            )
            cr.commit()

    def committed_folder(self):
        with self.cursor() as cr:
            env = self.env(cr=cr, su=True)
            folder = env[NODE].create({"name": "race folder"})
            grant = env[GRANT].create(
                {
                    "node_id": folder.id,
                    "partner_id": self.admin.partner_id.id,
                    "role": "manage",
                }
            )
            cr.commit()
            return folder.id, grant.id

    def run_as_a_request(self, cr, work, failures=None):
        env = self.env(cr=cr, su=True)
        attempts = []

        def attempt():
            attempts.append(len(attempts) + 1)
            try:
                return work(env, attempts[-1])
            except Exception as exc:
                if failures is not None:
                    failures.append(type(exc))
                raise

        with mute_logger("odoo.db.cursor", "odoo.service.model"):
            result = retrying(attempt, env)
        return result, len(attempts)

    def create_child(self, env, folder_id):
        return env[NODE].create({"name": "race child", "parent_id": folder_id}).id

    def admin_role(self, node_id):
        with self.cursor() as cr:
            nodes = self.env(cr=cr, user=self.admin)[NODE]
            node = nodes.browse(node_id)
            return (
                node.access_role,
                node.has_access("read"),
                bool(nodes.search([("id", "=", node_id)])),
            )

    def insert_child_while(self, folder_id, other_write):
        with self.cursor() as cr_insert, self.cursor() as cr_other:

            def insert(env, attempt):
                env[NODE].browse(folder_id).name
                if attempt == 1:
                    other_write(self.env(cr=cr_other, su=True))
                    cr_other.commit()
                return self.create_child(env, folder_id)

            return self.run_as_a_request(cr_insert, insert)

    def test_a_revoke_committed_before_an_insert_leaves_the_child_unreached(self):
        folder_id, grant_id = self.committed_folder()
        child_id, attempts = self.insert_child_while(
            folder_id, lambda env: env[GRANT].browse(grant_id).unlink()
        )
        self.assertEqual(self.admin_role(child_id), (False, False, False))
        self.assertEqual(attempts, 2, "the insert must fail to serialize, and rerun")

    def test_an_insert_committed_before_a_revoke_leaves_the_child_unreached(self):
        folder_id, grant_id = self.committed_folder()
        children = []
        with self.cursor() as cr_revoke, self.cursor() as cr_insert:

            def revoke(env, attempt):
                env[GRANT].browse(grant_id).role
                if attempt == 1:
                    inserting = self.env(cr=cr_insert, su=True)
                    children.append(self.create_child(inserting, folder_id))
                    cr_insert.commit()
                env[GRANT].browse(grant_id).unlink()

            _result, attempts = self.run_as_a_request(cr_revoke, revoke)
        self.assertEqual(self.admin_role(children[0]), (False, False, False))
        self.assertEqual(attempts, 2, "the revoke must fail to serialize, and rerun")

    def test_a_revoke_waits_for_an_insert_in_flight(self):
        folder_id, grant_id = self.committed_folder()
        with self.cursor() as cr_insert, self.cursor() as cr_revoke:
            inserting = self.env(cr=cr_insert, su=True)
            child_id = self.create_child(inserting, folder_id)
            inserting.flush_all()
            cr_revoke.execute("SET LOCAL lock_timeout = '300ms'")
            with (
                mute_logger("odoo.db.cursor"),
                self.assertRaises(psycopg.errors.LockNotAvailable),
            ):
                self.env(cr=cr_revoke, su=True)[GRANT].browse(grant_id).unlink()
            cr_revoke.rollback()
            cr_insert.commit()
            self.run_as_a_request(
                cr_revoke, lambda env, attempt: env[GRANT].browse(grant_id).unlink()
            )
        self.assertEqual(self.admin_role(child_id), (False, False, False))

    def test_a_grant_moved_away_under_an_insert_leaves_the_child_unreached(self):
        folder_id, grant_id = self.committed_folder()
        with self.cursor() as cr:
            elsewhere = self.env(cr=cr, su=True)[NODE].create({"name": "race away"})
            cr.commit()
        child_id, attempts = self.insert_child_while(
            folder_id,
            lambda env: env[GRANT].browse(grant_id).write({"node_id": elsewhere.id}),
        )
        self.assertEqual(self.admin_role(child_id), (False, False, False))
        self.assertEqual(attempts, 2, "the insert must fail to serialize, and rerun")
        self.assertEqual(self.admin_role(elsewhere.id), ("manage", True, True))

    def test_a_grant_changed_under_an_insert_is_read_as_it_now_stands(self):
        root = self.env.ref("base.partner_root")
        past = fields.Datetime.now() - timedelta(minutes=1)
        for change, expected in (
            ({"role": "view"}, ("view", True, True)),
            ({"date_to": past}, (False, False, False)),
            ({"partner_id": root.id}, (False, False, False)),
        ):
            with self.subTest(change=change):
                folder_id, grant_id = self.committed_folder()
                child_id, attempts = self.insert_child_while(
                    folder_id,
                    lambda env, change=change, grant_id=grant_id: (
                        env[GRANT].browse(grant_id).write(change)
                    ),
                )
                self.assertEqual(self.admin_role(child_id), expected)
                self.assertEqual(self.admin_role(folder_id), expected)
                self.assertEqual(attempts, 1, "nothing the insert wrote conflicts")

    def test_an_import_racing_another_into_one_folder_reruns_and_lands(self):
        folder_id, _grant_id = self.committed_folder()
        with self.cursor() as cr_import, self.cursor() as cr_other:

            def load(env, attempt):
                env[NODE].browse(folder_id).name
                if attempt == 1:
                    self.create_child(self.env(cr=cr_other, su=True), folder_id)
                    cr_other.commit()
                return env[NODE].load(
                    ["name", "parent_id/.id"], [["race imported", str(folder_id)]]
                )

            result, attempts = self.run_as_a_request(cr_import, load)
        self.assertEqual(result["messages"], [])
        self.assertEqual(attempts, 2, "the import must fail to serialize, and rerun")
        self.assertEqual(self.admin_role(result["ids"][0]), ("manage", True, True))

    def committed_tree(self, *, boundary=False, granted=False):
        with self.cursor() as cr:
            env = self.env(cr=cr, su=True)
            a = env[NODE].create({"name": "race a"})
            b = env[NODE].create(
                {"name": "race b", "parent_id": a.id, "is_boundary": boundary}
            )
            leaf = env[NODE].create({"name": "race l", "parent_id": b.id})
            if granted:
                self.grant(env, a.id)
            cr.commit()
            return a.id, b.id, leaf.id

    def grant(self, env, node_id):
        return env[GRANT].create(
            {"node_id": node_id, "partner_id": self.admin.partner_id.id, "role": "edit"}
        )

    def race(self, early, late):
        with self.cursor() as cr_late, self.cursor() as cr_early:

            def write(env, attempt):
                env.cr.execute("SELECT 1")
                if attempt == 1:
                    early(self.env(cr=cr_early, su=True))
                    cr_early.commit()
                late(env)
                env.flush_all()

            return self.run_as_a_request(cr_late, write)[1]

    def roles(self, *node_ids):
        return [self.admin_role(node_id)[0] for node_id in node_ids]

    def assert_table_is_derived(self):
        with self.cursor() as cr:
            node = self.env(cr=cr, su=True)[NODE]
            table = SQL.identifier(node._access_reach_table())
            columns = SQL(", ").join(SQL.identifier(c) for c in REACH_COLUMNS)
            cr.execute(SQL("SELECT %s FROM %s", columns, table))
            kept = Counter(cr.fetchall())
            cr.execute(SQL("DELETE FROM %s", table))
            cr.execute(node._access_reach_rows(SQL("TRUE")))
            cr.execute(SQL("SELECT %s FROM %s", columns, table))
            rebuilt = Counter(cr.fetchall())
            cr.rollback()
        self.assertEqual(
            kept - rebuilt, Counter(), "rows kept that derive from nothing"
        )
        self.assertEqual(rebuilt - kept, Counter(), "rows derived that were not kept")

    def assert_serial_in_both_orders(self, prepare, first, second, check):
        for early, late in ((first, second), (second, first)):
            with self.subTest(early=early.__name__):
                try:
                    ids = prepare()
                    attempts = self.race(
                        lambda env, early=early, ids=ids: early(env, ids),
                        lambda env, late=late, ids=ids: late(env, ids),
                    )
                    check(ids)
                    self.assert_table_is_derived()
                    self.assertEqual(
                        attempts, 2, "the later write must fail to serialize, and rerun"
                    )
                finally:
                    self.drop_committed()

    def set_boundary(self, value):
        def boundary(env, ids):
            env[NODE].browse(ids[1]).write({"is_boundary": value})

        return boundary

    def grant_on_root(self, env, ids):
        self.grant(env, ids[0])

    def test_a_boundary_set_under_a_new_grant_stops_it(self):
        self.assert_serial_in_both_orders(
            self.committed_tree,
            self.grant_on_root,
            self.set_boundary(True),
            lambda ids: self.assertEqual(self.roles(*ids), ["edit", False, False]),
        )

    def test_a_boundary_set_under_a_grant_moved_onto_it_stops_it(self):
        def prepare():
            ids = self.committed_tree()
            with self.cursor() as cr:
                env = self.env(cr=cr, su=True)
                apart = env[NODE].create({"name": "race apart"})
                self.grant(env, apart.id)
                cr.commit()
            return (*ids, apart.id)

        def move_grant(env, ids):
            env[GRANT].search([("node_id", "=", ids[3])]).node_id = ids[0]

        self.assert_serial_in_both_orders(
            prepare,
            move_grant,
            self.set_boundary(True),
            lambda ids: self.assertEqual(
                self.roles(*ids), ["edit", False, False, False]
            ),
        )

    def test_a_boundary_cleared_under_a_new_grant_lets_it_through(self):
        self.assert_serial_in_both_orders(
            lambda: self.committed_tree(boundary=True),
            self.grant_on_root,
            self.set_boundary(False),
            lambda ids: self.assertEqual(self.roles(*ids), ["edit", "edit", "edit"]),
        )

    def test_a_boundary_cleared_under_a_revoke_lets_nothing_through(self):
        def revoke(env, ids):
            env[GRANT].search([("node_id", "=", ids[0])]).unlink()

        self.assert_serial_in_both_orders(
            lambda: self.committed_tree(boundary=True, granted=True),
            revoke,
            self.set_boundary(False),
            lambda ids: self.assertEqual(self.roles(*ids), [False, False, False]),
        )

    def test_a_node_moved_under_a_new_grant_is_reached(self):
        def prepare():
            ids = self.committed_tree()
            with self.cursor() as cr:
                apart = self.env(cr=cr, su=True)[NODE].create({"name": "race apart"})
                cr.commit()
            return (*ids, apart.id)

        def move(env, ids):
            env[NODE].browse(ids[3]).write({"parent_id": ids[2]})

        self.assert_serial_in_both_orders(
            prepare,
            self.grant_on_root,
            move,
            lambda ids: self.assertEqual(self.roles(*ids), ["edit"] * 4),
        )

    def test_a_node_moved_away_from_a_new_grant_is_left(self):
        def move(env, ids):
            env[NODE].browse(ids[1]).write({"parent_id": False})

        self.assert_serial_in_both_orders(
            self.committed_tree,
            self.grant_on_root,
            move,
            lambda ids: self.assertEqual(self.roles(*ids), ["edit", False, False]),
        )

    def test_a_node_inserted_under_a_new_grant_is_reached(self):
        children = []

        def insert(env, ids):
            children.append(self.create_child(env, ids[1]))

        self.assert_serial_in_both_orders(
            self.committed_tree,
            self.grant_on_root,
            insert,
            lambda ids: self.assertEqual(self.roles(children[-1]), ["edit"]),
        )

    def test_a_node_inserted_under_a_new_boundary_is_not_reached(self):
        children = []

        def insert(env, ids):
            children.append(self.create_child(env, ids[2]))

        self.assert_serial_in_both_orders(
            lambda: self.committed_tree(granted=True),
            self.set_boundary(True),
            insert,
            lambda ids: self.assertEqual(
                self.roles(*ids, children[-1]), ["edit", False, False, False]
            ),
        )

    def test_a_node_deleted_under_a_new_grant_keeps_no_row(self):
        def delete(env, ids):
            env[NODE].browse(ids[2]).unlink()

        def check(ids):
            self.assertEqual(self.roles(ids[0], ids[1]), ["edit", "edit"])
            with self.cursor() as cr:
                table = self.env(cr=cr)[NODE]._access_reach_table()
                cr.execute(
                    SQL(
                        "SELECT count(*) FROM %s WHERE resource_id = %s",
                        SQL.identifier(table),
                        ids[2],
                    )
                )
                self.assertEqual(cr.fetchone()[0], 0, "rows of a deleted node")

        self.assert_serial_in_both_orders(
            self.committed_tree, self.grant_on_root, delete, check
        )

    def test_opposing_writes_in_flight_queue_without_deadlock(self):
        def boundary(env, ids):
            env[NODE].browse(ids[1]).write({"is_boundary": True})

        def grant(env, ids):
            self.grant(env, ids[0])

        for order in ((boundary, grant), (grant, boundary)):
            with self.subTest(first=order[0].__name__):
                try:
                    ids = self.committed_tree()
                    failures = []
                    with self.cursor() as cr_block:
                        self.create_child(self.env(cr=cr_block, su=True), ids[2])
                        threads = [
                            self.in_flight(write, ids, failures) for write in order
                        ]
                        cr_block.rollback()
                        for thread in threads:
                            thread.join(30)
                            self.assertFalse(thread.is_alive())
                    self.assertNotIn(psycopg.errors.DeadlockDetected, failures)
                    self.assertIn(psycopg.errors.SerializationFailure, failures)
                    self.assertEqual(self.roles(*ids), ["edit", False, False])
                    self.assert_table_is_derived()
                finally:
                    self.drop_committed()

    def in_flight(self, write, ids, failures):
        started = threading.Event()
        pids = []

        def run():
            with self.cursor() as cr:
                cr.execute("SELECT pg_backend_pid()")
                pids.append(cr.fetchone()[0])
                started.set()
                self.run_as_a_request(
                    cr,
                    lambda env, attempt: (write(env, ids), env.flush_all()),
                    failures,
                )

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        started.wait(10)
        with self.cursor() as cr:
            for _poll in range(200):
                cr.execute(
                    "SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s",
                    [pids[0]],
                )
                if cr.fetchone()[0] == "Lock":
                    break
                cr.rollback()
                time.sleep(0.05)
            else:
                self.fail(f"{write.__name__} never waited for a lock")
        return thread
