import random
from collections import Counter
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.fields import Command, Domain
from odoo.tests import TransactionCase, new_test_user, tagged
from odoo.tools import SQL

from odoo.addons.base.models.mixin_access_graph_reach import REACH_COLUMNS

ROLES = ("view", "edit", "manage")
REACH_TABLE = '"test_access_right_graph_node_access_reach"'
REACH_LOOKUP = f"FROM {REACH_TABLE} WHERE key = ANY("


def oracle_role(nodes, grants, user, groups, scoped, node_id, now, in_use):
    scope = []
    current = node_id
    while current:
        scope.append(current)
        if nodes[current]["boundary"]:
            break
        current = nodes[current]["parent"]
    record_company = nodes[node_id]["company"]
    personal = (
        not record_company
        or record_company in in_use
        or record_company not in user.company_ids.ids
    )
    scope = [
        node for node in scope if node == node_id or nodes[node].get("container", True)
    ]
    rank = 0
    for grant in grants:
        if grant["node"] not in scope:
            continue
        if grant["date_to"] and grant["date_to"] <= now:
            continue
        if grant["partner"]:
            holds = grant["partner"] == user.partner_id.id and personal
        else:
            companies = (
                set(user.company_ids.ids)
                if grant["group"] in groups
                else scoped.get(grant["group"])
            )
            if companies is not None:
                companies &= in_use
            holds = (
                bool(companies)
                and (not record_company or record_company in companies)
                and (not grant["company"] or grant["company"] in companies)
            )
        if holds:
            rank = max(rank, ROLES.index(grant["role"]) + 1)
    if personal and any(nodes[node]["owner"] == user.id for node in scope):
        rank = len(ROLES)
    return rank


@tagged("post_install", "-at_install")
class TestAccessGraph(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Node = cls.env["test_access_right.graph_node"]
        cls.Grant = cls.env["test_access_right.graph_grant"]
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({"name": "Graph B"})
        both = [Command.set((cls.company_a | cls.company_b).ids)]
        cls.group_x = cls.env["res.groups"].create({"name": "Graph X"})
        cls.group_y = cls.env["res.groups"].create({"name": "Graph Y"})
        cls.alice = new_test_user(
            cls.env, login="graph_alice", groups="base.group_user", company_ids=both
        )
        cls.bob = new_test_user(
            cls.env, login="graph_bob", groups="base.group_user", company_ids=both
        )
        cls.carol = new_test_user(
            cls.env, login="graph_carol", groups="base.group_user", company_ids=both
        )
        cls.alice.group_ids = [Command.link(cls.group_x.id)]
        cls.env["res.users.grant"].create(
            {
                "user_id": cls.bob.id,
                "group_id": cls.group_y.id,
                "company_ids": [Command.set(cls.company_a.ids)],
            }
        )
        cls.dave = new_test_user(
            cls.env,
            login="graph_dave",
            groups="base.group_user",
            company_ids=[Command.set(cls.company_a.ids)],
        )
        cls.dave.group_ids = [Command.link(cls.group_x.id)]
        cls.users = cls.alice | cls.bob | cls.carol | cls.dave

    def create_nodes_and_grants(self, seed, size=60, grants=90):
        rng = random.Random(seed)
        now = fields.Datetime.now()
        created = self.Node.browse()
        nodes = {}
        containers = []
        for index in range(size):
            parent = (
                rng.choice(containers) if containers and rng.random() < 0.85 else None
            )
            is_container = rng.random() < 0.6
            values = {
                "name": f"n{seed}-{index}",
                "parent_id": parent,
                "is_container": is_container,
                "is_boundary": rng.random() < 0.12,
                "owner_id": rng.choice(self.users.ids)
                if rng.random() < 0.08
                else False,
                "company_id": rng.choice([False, self.company_a.id, self.company_b.id]),
            }
            node = self.Node.create(values)
            created |= node
            nodes[node.id] = {
                "parent": parent,
                "container": is_container,
                "boundary": values["is_boundary"],
                "owner": values["owner_id"],
                "company": values["company_id"],
            }
            if is_container:
                containers.append(node.id)
        grant_rows = []
        principals = [("partner", user.partner_id.id) for user in self.users]
        principals += [("group", self.group_x.id), ("group", self.group_y.id)]
        for _ in range(grants):
            kind, principal = rng.choice(principals)
            date_to = rng.choice(
                [False, False, False, now - timedelta(days=1), now + timedelta(days=1)]
            )
            grant_rows.append(
                {
                    "node": rng.choice(list(nodes)),
                    "partner": principal if kind == "partner" else False,
                    "group": principal if kind == "group" else False,
                    "company": rng.choice(
                        [False, False, self.company_a.id, self.company_b.id]
                    )
                    if kind == "group"
                    else False,
                    "role": rng.choice(ROLES),
                    "date_to": date_to,
                }
            )
        self.Grant.create(
            [
                {
                    "node_id": row["node"],
                    "partner_id": row["partner"],
                    "group_id": row["group"],
                    "company_id": row["company"],
                    "role": row["role"],
                    "date_to": row["date_to"],
                }
                for row in grant_rows
            ]
        )
        return created, nodes, grant_rows, now

    def principal_groups(self, user):
        scopes = user._get_group_scopes()
        groups = {gid for gid, companies in scopes.items() if companies is None}
        scoped = {
            gid: set(companies)
            for gid, companies in scopes.items()
            if companies is not None
        }
        return groups, scoped

    def assert_agrees(self, seed, companies=None):
        self.assert_state_agrees(
            *self.create_nodes_and_grants(seed), seed=seed, companies=companies
        )

    def stored_state(self, created):
        created = created.exists()
        nodes = {
            node.id: {
                "parent": node.parent_id.id or None,
                "container": node.is_container,
                "boundary": node.is_boundary,
                "owner": node.owner_id.id,
                "company": node.company_id.id,
            }
            for node in created
        }
        grants = [
            {
                "node": grant.node_id.id,
                "partner": grant.partner_id.id,
                "group": grant.group_id.id,
                "company": grant.company_id.id,
                "role": grant.role,
                "date_to": grant.date_to,
            }
            for grant in self.Grant.search([("node_id", "in", created.ids)])
        ]
        return created, nodes, grants, fields.Datetime.now()

    def assert_table_is_derived(self):
        cr = self.env.cr
        self.Node._access_graph_flush()
        table = self.Node._access_reach_table()
        columns = SQL(", ").join(SQL.identifier(column) for column in REACH_COLUMNS)
        cr.execute(SQL("SELECT %s FROM %s", columns, SQL.identifier(table)))
        kept = Counter(cr.fetchall())
        cr.execute("SAVEPOINT rebuilt")
        cr.execute(SQL("DELETE FROM %s", SQL.identifier(table)))
        cr.execute(self.Node._access_reach_rows(SQL("TRUE")))
        cr.execute(SQL("SELECT %s FROM %s", columns, SQL.identifier(table)))
        rebuilt = Counter(cr.fetchall())
        cr.execute("ROLLBACK TO SAVEPOINT rebuilt")
        self.assertEqual(
            kept - rebuilt, Counter(), "rows kept that derive from nothing"
        )
        self.assertEqual(rebuilt - kept, Counter(), "rows derived that were not kept")

    def assert_state_agrees(
        self, created, nodes, grants, now, seed, companies=None, every_band=True
    ):
        mismatches = []
        exercised = set()
        for user in self.users:
            groups, scoped = self.principal_groups(user)
            in_use = set(companies or user.company_ids.ids) & set(user.company_ids.ids)
            if not in_use:
                continue
            expected = {
                node_id: oracle_role(
                    nodes, grants, user, groups, scoped, node_id, now, in_use
                )
                for node_id in nodes
            }
            exercised |= set(expected.values())
            Nodes = self.Node.with_user(user).with_context(
                allowed_company_ids=sorted(in_use)
            )
            as_user = created.with_env(Nodes.env).sudo()
            as_user.invalidate_recordset(["access_role"])
            computed = {
                node.id: (ROLES.index(node.access_role) + 1 if node.access_role else 0)
                for node in as_user
            }
            searched = {}
            for rank, role in enumerate(ROLES, start=1):
                found = Nodes.sudo().search(
                    [("id", "in", created.ids), ("access_role", "=", role)]
                )
                for node_id in found.ids:
                    searched[node_id] = rank
            nothing = Nodes.sudo().search(
                [("id", "in", created.ids), ("access_role", "=", False)]
            )
            for run in (
                ["view", "edit", "manage"],
                ["edit", "manage"],
                [False, "view"],
            ):
                found = Nodes.sudo().search(
                    [("id", "in", created.ids), ("access_role", "in", run)]
                )
                wanted = {
                    node_id
                    for node_id in nodes
                    if (ROLES[expected[node_id] - 1] if expected[node_id] else False)
                    in run
                }
                if set(found.ids) != wanted:
                    mismatches.append((user.login, "run", run))
            for node_id in nodes:
                band = searched.get(node_id, 0)
                if node_id in nothing.ids and band:
                    mismatches.append((user.login, node_id, "both none and", band))
                if not (expected[node_id] == computed[node_id] == band):
                    mismatches.append(
                        (
                            user.login,
                            node_id,
                            expected[node_id],
                            computed[node_id],
                            band,
                        )
                    )
        self.assertFalse(mismatches, f"seed {seed}: {mismatches[:20]}")
        if every_band:
            self.assertEqual(
                exercised, {0, 1, 2, 3}, "the matrix must reach every band"
            )

    def test_the_table_stays_derived_through_any_writes(self):
        for seed in (11, 12):
            rng = random.Random(seed)
            created, *_ = self.create_nodes_and_grants(seed, size=40, grants=60)
            for _batch in range(6):
                for _write in range(8):
                    nodes = created.exists()
                    node = rng.choice(nodes)
                    change = rng.randrange(8)
                    if change == 0:
                        below = self.Node.search([("id", "child_of", node.id)])
                        outside = (nodes - below).filtered("is_container")
                        node.parent_id = rng.choice([False, *outside.ids])
                    elif change == 1:
                        node.is_boundary = not node.is_boundary
                    elif change == 2:
                        node.is_container = not node.is_container
                    elif change == 3:
                        node.owner_id = rng.choice([False, *self.users.ids])
                    elif change == 4:
                        node.company_id = rng.choice(
                            [False, self.company_a.id, self.company_b.id]
                        )
                    elif change == 5 and node.grant_ids:
                        grant = rng.choice(node.grant_ids)
                        grant.write(
                            {
                                "role": rng.choice(ROLES),
                                "node_id": rng.choice(nodes.ids),
                            }
                        )
                    elif change == 6 and node.grant_ids:
                        rng.choice(node.grant_ids).unlink()
                    elif change == 7 and not self.Node.search_count(
                        [("parent_id", "=", node.id)]
                    ):
                        node.unlink()
                self.assert_table_is_derived()
            with self.subTest(seed=seed):
                self.assert_state_agrees(
                    *self.stored_state(created), seed=seed, every_band=False
                )

    def test_a_grant_writes_only_the_rows_it_is_the_source_of(self):
        created, *_ = self.create_nodes_and_grants(14, size=30, grants=40)
        folder = created.filtered(lambda node: node.is_container)[0]
        cr = self.env.cr
        table = SQL.identifier(self.Node._access_reach_table())

        def rows():
            self.Node._access_graph_flush()
            cr.execute(SQL("SELECT ctid, grant_id FROM %s", table))
            return dict(cr.fetchall())

        before = rows()
        grant = self.Grant.create(
            {"node_id": folder.id, "group_id": self.group_y.id, "role": "edit"}
        )
        after = rows()
        self.assertLessEqual(before.keys(), after.keys(), "no row was rewritten")
        added = {after[ctid] for ctid in after.keys() - before.keys()}
        self.assertEqual(added, {grant.id})
        grant.unlink()
        self.assertEqual(rows(), before)
        self.assert_table_is_derived()

    def test_a_rolled_back_write_leaves_the_rows_it_found(self):
        created, *_ = self.create_nodes_and_grants(13, size=20, grants=30)
        self.assert_table_is_derived()
        with self.assertRaises(ValueError), self.env.cr.savepoint():
            created[0].parent_id = self.Node.create({"name": "elsewhere"})
            created.grant_ids.unlink()
            self.Node._access_graph_flush()
            raise ValueError
        self.assert_table_is_derived()

    def test_the_module_owns_its_reach_tables(self):
        reach = self.Node._access_reach_table()
        owned = self.env["ir.model.relation"].search(
            [("name", "in", [reach, f"{reach}_lock"])]
        )
        self.assertEqual(
            sorted(
                owned.mapped(lambda relation: (relation.name, relation.module.name))
            ),
            [(reach, "test_access_rights"), (f"{reach}_lock", "test_access_rights")],
        )

    def test_the_sql_and_the_compute_agree_with_the_formula(self):
        for seed in (1, 2, 3):
            with self.subTest(seed=seed):
                self.assert_agrees(seed)

    def test_they_agree_with_one_company_in_use(self):
        for seed in (4, 5):
            for company in (self.company_a, self.company_b):
                with self.subTest(seed=seed, company=company.name):
                    self.assert_agrees(seed, companies=company.ids)

    def test_a_group_counts_in_the_companies_in_use(self):
        root = self.Node.create({"name": "S"})
        in_b = self.Node.create(
            {"name": "b", "parent_id": root.id, "company_id": self.company_b.id}
        )
        limited = self.Node.create({"name": "limited"})
        self.Grant.create(
            [
                {"node_id": root.id, "group_id": self.group_x.id, "role": "view"},
                {
                    "node_id": limited.id,
                    "group_id": self.group_x.id,
                    "company_id": self.company_b.id,
                    "role": "edit",
                },
            ]
        )

        def as_alice(*companies):
            return self.Node.with_user(self.alice).with_context(
                allowed_company_ids=[company.id for company in companies]
            )

        mine_in_b = self.Node.create(
            {
                "name": "mine in b",
                "company_id": self.company_b.id,
                "owner_id": self.alice.id,
            }
        )
        self.assertFalse(as_alice(self.company_a).browse(in_b.id).access_role)
        self.assertFalse(as_alice(self.company_a).browse(limited.id).access_role)
        self.assertFalse(as_alice(self.company_a).browse(mine_in_b.id).access_role)
        shared = self.Node.create({"name": "shared", "company_id": self.company_b.id})
        self.Grant.create(
            {
                "node_id": shared.id,
                "partner_id": self.dave.partner_id.id,
                "role": "view",
            }
        )
        self.assertEqual(shared.with_user(self.dave).access_role, "view")
        self.assertNotIn(
            in_b,
            as_alice(self.company_a).sudo().search([("access_role", "!=", False)]),
        )
        both = as_alice(self.company_a, self.company_b)
        self.assertEqual(both.browse(in_b.id).access_role, "view")
        self.assertEqual(both.browse(limited.id).access_role, "edit")
        self.assertEqual(both.browse(mine_in_b.id).access_role, "manage")

    def test_a_run_of_bands_is_one_reach(self):
        def reaches(domain):
            query = self.Node.with_user(self.alice).sudo()._search(domain)
            return query.select().code.count(REACH_LOOKUP)

        once = reaches(self.Node.with_user(self.alice)._access_graph_domain("view"))
        self.assertTrue(once)
        self.assertEqual(
            reaches([("access_role", "in", ["view", "edit", "manage"])]), once
        )
        self.assertEqual(reaches([("access_role", "!=", False)]), once)
        self.assertEqual(reaches([("access_role", "=", "edit")]), 2 * once)

    def test_the_graph_reach_predicate(self):
        root = self.Node.create({"name": "P"})
        leaf = self.Node.create({"name": "p", "parent_id": root.id})
        self.Grant.create(
            [
                {"node_id": root.id, "group_id": self.group_x.id, "role": "view"},
                {
                    "node_id": leaf.id,
                    "partner_id": self.bob.partner_id.id,
                    "role": "edit",
                },
            ]
        )
        self.env["ir.model.data"].create(
            {
                "module": "test_access_rights",
                "name": "graph_group_x",
                "model": "res.groups",
                "res_id": self.group_x.id,
            }
        )
        predicate = self.env.ref("base.access_predicate_graph_reach")
        self.assertEqual(
            predicate._arguments(self.Node._name),
            (
                frozenset({"role"}),
                frozenset({"at", "groups", "except_groups", "partner", "owner"}),
            ),
        )
        nodes = root | leaf

        def reached(user, model, **args):
            Model = self.env[model].with_user(user)
            domain = Model._access_predicate_graph_reach(None, args)
            return Model.sudo().search(domain)

        self.assertEqual(
            reached(self.alice, self.Node._name, role="view") & nodes, nodes
        )
        self.assertFalse(reached(self.alice, self.Node._name, role="edit") & nodes)
        self.assertEqual(reached(self.bob, self.Node._name, role="edit") & nodes, leaf)
        self.assertFalse(
            reached(
                self.alice,
                self.Node._name,
                role="view",
                except_groups=["test_access_rights.graph_group_x"],
            )
            & nodes
        )
        grants = reached(self.bob, self.Grant._name, role="edit", at="node_id.")
        self.assertEqual(grants.node_id & nodes, leaf)

    def test_each_alias_reads_the_reach_table_once(self):
        root = self.Node.create({"name": "R"})
        mid = self.Node.create({"name": "m", "parent_id": root.id})
        leaf = self.Node.create({"name": "l", "parent_id": mid.id, "is_boundary": True})
        other = self.Node.create({"name": "o", "parent_id": leaf.id})
        self.Grant.create(
            [
                {"node_id": mid.id, "group_id": self.group_x.id, "role": "view"},
                {
                    "node_id": other.id,
                    "partner_id": self.alice.partner_id.id,
                    "role": "edit",
                },
            ]
        )
        nodes = root | mid | leaf | other
        Node = self.Node.with_user(self.alice)
        reach = Node._access_graph_reach("view")
        walked = reach | Domain("parent_id", "any", reach)

        alone = Node.sudo()._search(reach).statement().code
        self.assertEqual(alone.count(REACH_LOOKUP), 1)
        self.assertEqual(
            Node.sudo()._search(walked).statement().code.count(REACH_LOOKUP), 2
        )
        self.assertEqual(Node.sudo().search(reach) & nodes, mid | other)
        self.assertEqual(Node.sudo().search(walked) & nodes, mid | leaf | other)
        self.assertEqual(
            self.Node.search([("parent_id", "any", Node.sudo()._search(walked))])
            & nodes,
            leaf | other,
            "a subquery of another search",
        )

    def test_the_reach_looks_the_principals_up_by_index(self):
        Node = self.Node.with_user(self.alice)
        statement = Node.sudo()._search(Node._access_graph_reach("view")).statement()
        self.assertIn('"id" IN (SELECT resource_id FROM (', statement.code)
        self.assertIn(REACH_LOOKUP, statement.code)
        self.assertIn(
            f"JOIN {REACH_TABLE} AS reach ON reach.grant_id = grant_row.id",
            statement.code,
        )
        self.assertNotIn("string_to_array(", statement.code)

    def test_opened_groups_read_each_set_of_granted_nodes_once(self):
        companies = (self.company_a | self.company_b).ids
        nodes = self.Node.create(
            [
                {"name": f"g{index}", "company_id": company}
                for index, company in enumerate([False, *companies] * 2)
            ]
        )
        self.Grant.create(
            [
                {
                    "node_id": node.id,
                    "partner_id": self.alice.partner_id.id,
                    "role": "view",
                }
                for node in nodes
            ]
        )
        Node = self.Node.with_user(self.alice).with_context(
            allowed_company_ids=companies
        )
        reach = Node._access_graph_reach("view") & Domain("id", "in", nodes.ids)
        sets = Node.sudo()._search(reach).statement().code.count(REACH_LOOKUP)
        self.assertTrue(sets)

        statements = []
        execute_query = type(self.env).execute_query

        def capture(env, query):
            statements.append(query.code)
            return execute_query(env, query)

        with patch.object(type(self.env), "execute_query", capture):
            result = Node.sudo().web_read_group(
                reach,
                ["company_id"],
                auto_unfold=True,
                unfold_read_specification={"name": {}},
            )
        self.assertEqual(len(result["groups"]), 3)
        [opened] = [code for code in statements if "__gidx" in code]
        self.assertEqual(
            opened.count(REACH_LOOKUP), sets, "one lookup per expression, not per group"
        )
        opened_groups = [group for group in result["groups"] if group["company_id"]]
        self.assertEqual(len(opened_groups), 2)
        for group in result["groups"]:
            if not group["company_id"]:
                self.assertNotIn("__records", group)
                continue
            expected = Node.sudo().search(
                reach & Domain("company_id", "=", group["company_id"][0])
            )
            self.assertEqual(
                {values["id"] for values in group["__records"]}, set(expected.ids)
            )

    def test_a_folder_grant_reaches_its_subtree_live_and_leaves_with_a_move(self):
        root_a = self.Node.create({"name": "A"})
        root_b = self.Node.create({"name": "B"})
        folder = self.Node.create({"name": "F", "parent_id": root_a.id})
        leaf = self.Node.create(
            {"name": "L", "parent_id": folder.id, "is_container": False}
        )
        self.Grant.create(
            {
                "node_id": root_a.id,
                "partner_id": self.carol.partner_id.id,
                "role": "edit",
            }
        )
        as_carol = leaf.with_user(self.carol).sudo()
        self.assertEqual(as_carol.access_role, "edit")
        folder.parent_id = root_b
        leaf.invalidate_recordset(["access_role"])
        self.assertFalse(as_carol.access_role)
        self.assertEqual(leaf.access_scope_path, f"{root_b.id}/{folder.id}/{leaf.id}/")

    def test_a_boundary_stops_what_comes_from_above_not_what_is_granted_on_it(self):
        root = self.Node.create({"name": "R"})
        payroll = self.Node.create(
            {"name": "P", "parent_id": root.id, "is_boundary": True}
        )
        slip = self.Node.create(
            {"name": "S", "parent_id": payroll.id, "is_container": False}
        )
        self.Grant.create(
            [
                {"node_id": root.id, "group_id": self.group_x.id, "role": "view"},
                {
                    "node_id": payroll.id,
                    "partner_id": self.carol.partner_id.id,
                    "role": "view",
                },
            ]
        )
        self.assertEqual(root.with_user(self.alice).sudo().access_role, "view")
        self.assertFalse(slip.with_user(self.alice).sudo().access_role)
        self.assertEqual(slip.with_user(self.carol).sudo().access_role, "view")
        payroll.is_boundary = False
        slip.invalidate_recordset(["access_role"])
        self.assertEqual(slip.with_user(self.alice).sudo().access_role, "view")

    def test_a_grant_on_a_leaf_reaches_that_leaf_only(self):
        folder = self.Node.create({"name": "F"})
        first = self.Node.create(
            {"name": "1", "parent_id": folder.id, "is_container": False}
        )
        second = self.Node.create(
            {"name": "2", "parent_id": folder.id, "is_container": False}
        )
        self.Grant.create(
            {
                "node_id": first.id,
                "partner_id": self.carol.partner_id.id,
                "role": "view",
            }
        )
        found = self.Node.with_user(self.carol).search(
            [("id", "in", (folder | first | second).ids)]
        )
        self.assertEqual(found, first)

    def test_an_expired_grant_grants_nothing(self):
        node = self.Node.create({"name": "E"})
        self.Grant.create(
            {
                "node_id": node.id,
                "partner_id": self.carol.partner_id.id,
                "role": "edit",
                "date_to": fields.Datetime.now() - timedelta(minutes=1),
            }
        )
        self.assertFalse(node.with_user(self.carol).sudo().access_role)

    def test_a_group_held_in_one_company_reaches_that_company_s_records(self):
        root = self.Node.create({"name": "C"})
        in_a = self.Node.create(
            {"name": "a", "parent_id": root.id, "company_id": self.company_a.id}
        )
        in_b = self.Node.create(
            {"name": "b", "parent_id": root.id, "company_id": self.company_b.id}
        )
        self.Grant.create(
            {"node_id": root.id, "group_id": self.group_y.id, "role": "view"}
        )
        both = self.env(
            user=self.bob,
            context={"allowed_company_ids": [self.company_a.id, self.company_b.id]},
        )["test_access_right.graph_node"]
        self.assertEqual(both.browse(in_a.id).access_role, "view")
        self.assertFalse(both.browse(in_b.id).access_role)

    def test_a_group_reaches_only_the_companies_it_is_held_in(self):
        root = self.Node.create({"name": "D"})
        in_b = self.Node.create(
            {"name": "b", "parent_id": root.id, "company_id": self.company_b.id}
        )
        shared = self.Node.create({"name": "none", "parent_id": root.id})
        self.Grant.create(
            {"node_id": root.id, "group_id": self.group_x.id, "role": "view"}
        )
        as_alice = self.Node.with_user(self.alice)
        as_dave = self.Node.with_user(self.dave)
        self.assertEqual(as_alice.browse(in_b.id).access_role, "view")
        self.assertFalse(
            as_dave.browse(in_b.id).access_role, "dave is not in company B"
        )
        self.assertEqual(as_dave.browse(shared.id).access_role, "view")

    def test_a_group_s_grant_limited_to_a_company(self):
        root = self.Node.create({"name": "E"})
        self.Grant.create(
            {
                "node_id": root.id,
                "group_id": self.group_x.id,
                "company_id": self.company_b.id,
                "role": "edit",
            }
        )
        self.assertEqual(root.with_user(self.alice).access_role, "edit")
        self.assertFalse(
            root.with_user(self.dave).access_role,
            "dave holds the group, but not in company B",
        )
        with self.assertRaises(Exception), self.cr.savepoint():
            self.Grant.create(
                {
                    "node_id": root.id,
                    "partner_id": self.carol.partner_id.id,
                    "company_id": self.company_b.id,
                    "role": "view",
                }
            )

    def test_the_owner_holds_the_top_role_below_its_node(self):
        folder = self.Node.create({"name": "O", "owner_id": self.carol.id})
        child = self.Node.create({"name": "c", "parent_id": folder.id})
        self.assertEqual(child.with_user(self.carol).sudo().access_role, "manage")

    def test_grants_are_written_by_whoever_manages_the_node(self):
        node = self.Node.create({"name": "M"})
        self.Grant.create(
            {"node_id": node.id, "partner_id": self.alice.partner_id.id, "role": "edit"}
        )
        with self.assertRaises(AccessError):
            self.Grant.with_user(self.alice).create(
                {
                    "node_id": node.id,
                    "partner_id": self.bob.partner_id.id,
                    "role": "view",
                }
            )
        self.Grant.create(
            {
                "node_id": node.id,
                "partner_id": self.carol.partner_id.id,
                "role": "manage",
            }
        )
        self.Grant.with_user(self.carol).create(
            {"node_id": node.id, "partner_id": self.bob.partner_id.id, "role": "view"}
        )
        self.assertEqual(node.with_user(self.bob).sudo().access_role, "view")

    def test_a_grant_names_exactly_one_principal(self):
        node = self.Node.create({"name": "P"})
        with self.assertRaises(Exception), self.cr.savepoint():
            self.Grant.create({"node_id": node.id, "role": "view"})
        with self.assertRaises(Exception), self.cr.savepoint():
            self.Grant.create(
                {
                    "node_id": node.id,
                    "role": "view",
                    "partner_id": self.bob.partner_id.id,
                    "group_id": self.group_x.id,
                }
            )

    def test_the_public_user_reaches_nothing(self):
        node = self.Node.create({"name": "pub"})
        self.Grant.create(
            {
                "node_id": node.id,
                "group_id": self.env.ref("base.group_public").id,
                "role": "view",
            }
        )
        public = self.env.ref("base.public_user")
        self.assertFalse(node.with_user(public).sudo().access_role)

    def test_the_sources_name_each_grant_and_owner_that_reaches_a_record(self):
        root = self.Node.create({"name": "S", "owner_id": self.alice.id})
        folder = self.Node.create({"name": "f", "parent_id": root.id})
        leaf = self.Node.create(
            {"name": "l", "parent_id": folder.id, "is_container": False}
        )
        grant = self.Grant.create(
            {
                "node_id": folder.id,
                "partner_id": self.carol.partner_id.id,
                "role": "view",
            }
        )
        self.Grant.create(
            {
                "node_id": folder.id,
                "partner_id": self.bob.partner_id.id,
                "role": "edit",
                "date_to": fields.Datetime.now() - timedelta(days=1),
            }
        )
        sources = leaf._access_graph_sources()
        self.assertEqual(
            {(s["node"], s["partner"], s["role"], s["inherited"]) for s in sources},
            {
                (folder, self.carol.partner_id, "view", True),
                (root, self.alice.partner_id, "manage", True),
            },
        )
        self.assertIn(grant, [s["grant"] for s in sources])

    def test_the_mixin_without_a_graph_answers_every_field(self):
        mixin = self.env["mixin.access.graph"]
        description = mixin.fields_get(["access_role", "access_scope_path"])
        self.assertEqual(description["access_role"]["selection"], [])
        self.assertTrue(mixin._search_access_role("in", ["view"]).is_false())


@tagged("post_install", "-at_install")
class TestCausedGrants(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Grant = cls.env["test_access_right.graph_grant"]
        cls.node = cls.env["test_access_right.graph_node"].create({"name": "Caused"})
        cls.user = new_test_user(cls.env, "caused_member", groups="base.group_user")
        cls.partner = cls.user.partner_id

    def share(self, role, date_to=False):
        return self.Grant.create(
            {
                "node_id": self.node.id,
                "partner_id": self.partner.id,
                "role": role,
                "date_to": date_to,
            }
        )

    def sync(self, cause_ref, role=None):
        wanted = [(self.node.id, "partner_id", self.partner.id, role, False)]
        self.Grant._sync_caused_grants(cause_ref, wanted if role else [])

    def expire(self, grant):
        grant.date_to = fields.Datetime.now() - timedelta(minutes=1)

    def held(self):
        return sorted(
            (grant.role, grant.cause, grant.cause_ref)
            for grant in self.Grant.search([("node_id", "=", self.node.id)])
        )

    def effective(self):
        node = self.node.with_user(self.user).sudo()
        node.invalidate_recordset(["access_role"])
        return node.access_role

    def test_an_expiring_share_above_a_module_holds_until_it_expires(self):
        share = self.share("manage", fields.Datetime.now() + timedelta(days=1))
        self.sync("module.a,1", "edit")
        self.assertEqual(self.effective(), "manage")
        self.expire(share)
        self.assertEqual(self.effective(), "edit")
        self.sync("module.a,1")
        self.assertFalse(self.effective())

    def test_a_module_s_release_gives_back_the_share_under_it(self):
        self.share("view")
        self.sync("module.a,1", "edit")
        self.assertEqual(self.effective(), "edit")
        self.sync("module.a,1")
        self.assertEqual(self.held(), [("view", "manual", False)])
        self.assertEqual(self.effective(), "view")

    def test_a_durable_share_above_the_module_stays_the_user_s(self):
        self.share("manage")
        self.sync("module.a,1", "edit")
        self.assertEqual(self.effective(), "manage")
        self.sync("module.a,1")
        self.assertEqual(self.held(), [("manage", "manual", False)])

    def test_each_module_keeps_its_own_claim(self):
        self.sync("module.a,1", "view")
        self.sync("module.b,1", "edit")
        self.sync("module.c,1", "manage")
        self.assertEqual(self.effective(), "manage")
        self.sync("module.a,1", "edit")
        self.sync("module.c,1")
        self.assertEqual(
            self.held(),
            [("edit", "module", "module.a,1"), ("edit", "module", "module.b,1")],
        )
        self.sync("module.b,1")
        self.assertEqual(self.effective(), "edit")
        self.sync("module.a,1")
        self.assertEqual(self.held(), [])
        self.assertFalse(self.effective())

    def test_a_module_resets_the_claim_it_owns(self):
        self.sync("module.a,1", "edit")
        claim = self.Grant.search([("cause_ref", "=", "module.a,1")])
        claim.write({"role": "view", "date_to": fields.Datetime.now()})
        self.sync("module.a,1", "edit")
        self.assertEqual((claim.role, claim.date_to), ("edit", False))

    def test_a_module_asking_twice_keeps_the_higher_role(self):
        wanted = [
            (self.node.id, "partner_id", self.partner.id, role, False)
            for role in ("manage", "view")
        ]
        self.Grant._sync_caused_grants("module.a,1", wanted)
        self.assertEqual(self.held(), [("manage", "module", "module.a,1")])

    def merge_in(self, *grants):
        source = self.env["res.partner"].create({"name": "Merged member"})
        for role, date_to, cause_ref in grants:
            self.Grant.create(
                {
                    "node_id": self.node.id,
                    "partner_id": source.id,
                    "role": role,
                    "date_to": date_to,
                    "cause_ref": cause_ref,
                    "cause": "module" if cause_ref else "manual",
                }
            )
        self.env["wizard.res.partner.merge"]._merge(
            (self.partner | source).ids, self.partner, extra_checks=False
        )
        return source

    def test_a_merge_keeps_the_stronger_share(self):
        self.share("view")
        self.merge_in(("manage", False, False))
        self.assertEqual(self.held(), [("manage", "manual", False)])
        self.assertEqual(self.effective(), "manage")

    def test_a_merge_keeps_the_module_s_higher_claim(self):
        self.sync("module.a,1", "view")
        self.merge_in(("edit", False, "module.a,1"))
        self.assertEqual(self.held(), [("edit", "module", "module.a,1")])

    def test_a_merge_keeps_claims_of_different_causes(self):
        self.share("view")
        self.merge_in(("edit", False, "module.a,1"))
        self.assertEqual(
            self.held(), [("edit", "module", "module.a,1"), ("view", "manual", False)]
        )

    def test_a_one_row_merge_keeps_the_share_that_lasts(self):
        self.share("view")
        with patch.object(type(self.Grant), "_access_grant_by_cause", False):
            self.merge_in(("edit", fields.Datetime.now() + timedelta(days=3), False))
        self.assertEqual(self.held(), [("view", "manual", False)])

    def test_a_merge_keeps_two_shares_that_each_outlast_the_other_somewhere(self):
        share = self.share("edit", fields.Datetime.now() + timedelta(days=3))
        source = self.merge_in(("view", False, False))
        self.assertEqual(
            self.held(),
            [("edit", "manual", False), ("view", "merge", f"res.partner,{source.id}")],
        )
        self.assertEqual(self.effective(), "edit")
        self.expire(share)
        self.assertEqual(self.effective(), "view")
