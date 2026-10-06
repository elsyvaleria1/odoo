import random
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.fields import Command, Domain
from odoo.tests import TransactionCase, new_test_user, tagged

ROLES = ("view", "edit", "manage")


def oracle_role(nodes, grants, user, groups, scoped, node_id, now, in_use):
    # the live formula, written independently of the SQL: a live grant held
    # by the user reaches a node from the node itself or any ancestor up to
    # the nearest boundary; an owner there holds the top role; a group counts
    # in the companies in use it is held in (those its membership is limited
    # to, else all the user's), on records of those companies or of none,
    # and a group's grant limited to a company counts only there
    scope = []
    current = node_id
    while current:
        scope.append(current)
        if nodes[current]["boundary"]:
            break
        current = nodes[current]["parent"]
    record_company = nodes[node_id]["company"]
    # a partner's grant and an owner count on a record of a company in use,
    # of none, or of one the user is not in
    personal = (
        not record_company
        or record_company in in_use
        or record_company not in user.company_ids.ids
    )
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

    def build(self, seed, size=60, grants=90):
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
        # companies: the companies in use, else all of each user's
        created, nodes, grants, now = self.build(seed)
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
            # a run of bands is the union of its bands
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
        self.assertEqual(exercised, {0, 1, 2, 3}, "the matrix must reach every band")

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
        # the company switcher: what a group reaches in a company the user
        # deselected is not reached, as an access row's company reach is not
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
        # dave is not in company B: what is shared with him there still is
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
        # "view or above" asks the graph once, not once per role
        def reaches(domain):
            query = self.Node.with_user(self.alice).sudo()._search(domain)
            return query.select().code.count("AS grant_row")

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

    def test_a_search_computes_each_set_of_granted_containers_once(self):
        # a rule that walks to the graph through two aliases -- the node and
        # its parent -- asks for the same granted containers at both; the
        # statement names each set once and both conditions read it, while
        # each alias probes the grants on itself
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
        containers = "AS held JOIN"
        probes = '"id" IN (SELECT grant_row.'

        alone = Node.sudo()._search(reach)
        sets = alone.statement().code.count(containers)
        self.assertGreaterEqual(sets, 1, "a container set at least")
        own = alone.statement().code.count(probes)
        self.assertGreaterEqual(own, 1, "a probe of the node's own grants at least")

        query = Node.sudo()._search(walked)
        self.assertEqual(
            query.statement().code.count(containers),
            sets,
            "the second alias asks for no container set the first did not",
        )
        self.assertEqual(query.statement().code.count(probes), 2 * own)
        # inside another statement the query reads each set where it is used
        self.assertEqual(query.subselect().code.count(containers), 2 * sets)
        self.assertEqual(query.where_clause.code.count(containers), 2 * sets)

        # mid by its group grant, other by the partner's; leaf is a boundary
        # the group's grant stops at, and is reached here through its parent
        self.assertEqual(Node.sudo().search(reach) & nodes, mid | other)
        self.assertEqual(Node.sudo().search(walked) & nodes, mid | leaf | other)
        self.assertEqual(
            self.Node.search([("parent_id", "any", query)]) & nodes,
            leaf | other,
            "a subquery of another search",
        )

        # read without a query to hold them, the condition states them inline
        inline = Node._access_graph_condition("view")(self.Node._table)
        self.assertEqual(inline.code.count(containers), sets)

    def test_a_node_s_own_grants_are_a_semi_join(self):
        # a partner's grants run to thousands of nodes: the node's own grants
        # are a semi-join on the grant table, which PostgreSQL hashes once and
        # probes per row in parallel workers too -- not an array of node ids,
        # which = ANY() scans per row and IN (SELECT unnest()) keeps serial
        Node = self.Node.with_user(self.alice)
        statement = Node.sudo()._search(Node._access_graph_reach("view")).statement()
        self.assertIn('"id" IN (SELECT grant_row.', statement.code)
        self.assertNotIn('"id" = ANY(', statement.code)
        self.assertNotIn("unnest(", statement.code)

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
