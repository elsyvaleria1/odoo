from odoo.tests.common import BaseCase, TransactionCase
from odoo.tools import SQL, Query


class QueryTestCase(BaseCase):
    def test_basic_query(self):
        query = Query(None, "product_product")
        query.add_table("product_template")
        query.add_where(SQL("product_product.template_id = product_template.id"))
        alias = query.join(
            "product_template", "categ_id", "product_category", "id", "categ_id"
        )
        self.assertEqual(alias, "product_template__categ_id")
        alias = query.left_join(
            "product_product", "user_id", "res_user", "id", "user_id"
        )
        self.assertEqual(alias, "product_product__user_id")

        self.assertEqual(
            query.from_clause.code,
            '"product_product" CROSS JOIN "product_template" JOIN "product_category" AS "product_template__categ_id" ON ("product_template"."categ_id" = "product_template__categ_id"."id") LEFT JOIN "res_user" AS "product_product__user_id" ON ("product_product"."user_id" = "product_product__user_id"."id")',
        )
        self.assertEqual(
            query.where_clause.code,
            "product_product.template_id = product_template.id",
        )

    def test_query_chained_explicit_joins(self):
        query = Query(None, "product_product")
        query.add_table("product_template")
        query.add_where(SQL("product_product.template_id = product_template.id"))
        alias = query.join(
            "product_template", "categ_id", "product_category", "id", "categ_id"
        )
        self.assertEqual(alias, "product_template__categ_id")
        alias = query.left_join(
            "product_template__categ_id", "user_id", "res_user", "id", "user_id"
        )
        self.assertEqual(alias, "product_template__categ_id__user_id")

        self.assertEqual(
            query.from_clause.code,
            '"product_product" CROSS JOIN "product_template" JOIN "product_category" AS "product_template__categ_id" ON ("product_template"."categ_id" = "product_template__categ_id"."id") LEFT JOIN "res_user" AS "product_template__categ_id__user_id" ON ("product_template__categ_id"."user_id" = "product_template__categ_id__user_id"."id")',
        )
        self.assertEqual(
            query.where_clause.code,
            "product_product.template_id = product_template.id",
        )

    def test_mixed_query_chained_explicit_implicit_joins(self):
        query = Query(None, "product_product")
        query.add_table("product_template")
        query.add_where(SQL("product_product.template_id = product_template.id"))
        alias = query.join(
            "product_template", "categ_id", "product_category", "id", "categ_id"
        )
        self.assertEqual(alias, "product_template__categ_id")
        alias = query.left_join(
            "product_template__categ_id", "user_id", "res_user", "id", "user_id"
        )
        self.assertEqual(alias, "product_template__categ_id__user_id")
        query.add_table("account_account")
        query.add_where(SQL("product_category.expense_account_id = account_account.id"))

        self.assertEqual(
            query.from_clause.code,
            '"product_product" CROSS JOIN "product_template" CROSS JOIN "account_account" JOIN "product_category" AS "product_template__categ_id" ON ("product_template"."categ_id" = "product_template__categ_id"."id") LEFT JOIN "res_user" AS "product_template__categ_id__user_id" ON ("product_template__categ_id"."user_id" = "product_template__categ_id__user_id"."id")',
        )
        self.assertEqual(
            query.where_clause.code,
            "product_product.template_id = product_template.id AND product_category.expense_account_id = account_account.id",
        )

    def test_raise_missing_lhs(self):
        query = Query(None, "product_product")
        with self.assertRaises(AssertionError):
            query.join(
                "product_template",
                "categ_id",
                "product_category",
                "id",
                "categ_id",
            )

    def test_long_aliases(self):
        query = Query(None, "product_product")
        tmp = query.join(
            "product_product",
            "product_tmpl_id",
            "product_template",
            "id",
            "product_tmpl_id",
        )
        self.assertEqual(tmp, "product_product__product_tmpl_id")
        tmp_cat = query.join(
            tmp,
            "product_category_id",
            "product_category",
            "id",
            "product_category_id",
        )
        self.assertEqual(
            tmp_cat, "product_product__product_tmpl_id__product_category_id"
        )
        tmp_cat_cmp = query.join(
            tmp_cat, "company_id", "res_company", "id", "company_id"
        )
        self.assertEqual(
            tmp_cat_cmp,
            "product_product__product_tmpl_id__product_category_id__9f0ddff7",
        )
        tmp_cat_stm = query.join(
            tmp_cat, "salesteam_id", "res_company", "id", "salesteam_id"
        )
        self.assertEqual(
            tmp_cat_stm,
            "product_product__product_tmpl_id__product_category_id__953a466f",
        )
        tmp_cat_cmp_par = query.join(
            tmp_cat_cmp, "partner_id", "res_partner", "id", "partner_id"
        )
        self.assertEqual(
            tmp_cat_cmp_par,
            "product_product__product_tmpl_id__product_category_id__56d55687",
        )
        tmp_cat_stm_par = query.join(
            tmp_cat_stm, "partner_id", "res_partner", "id", "partner_id"
        )
        self.assertEqual(
            tmp_cat_stm_par,
            "product_product__product_tmpl_id__product_category_id__00363fdd",
        )

    def test_table_expression(self):
        query = Query(None, "foo")
        from_clause = query.from_clause.code
        self.assertEqual(from_clause, '"foo"')

        query = Query(None, "bar", SQL("(SELECT id FROM foo)"))
        from_clause = query.from_clause.code
        self.assertEqual(from_clause, '(SELECT id FROM foo) AS "bar"')

        query = Query(None, "foo")
        query.add_table("bar", SQL("(SELECT id FROM foo)"))
        from_clause = query.from_clause.code
        self.assertEqual(from_clause, '"foo" CROSS JOIN (SELECT id FROM foo) AS "bar"')

        query = Query(None, "foo")
        query.join("foo", "bar_id", SQL("(SELECT id FROM foo)"), "id", "bar")
        from_clause = query.from_clause.code
        self.assertEqual(
            from_clause,
            '"foo" JOIN (SELECT id FROM foo) AS "foo__bar" ON ("foo"."bar_id" = "foo__bar"."id")',
        )

    def test_empty_set_result_ids(self):
        query = Query(None, "foo")
        query.set_result_ids([])
        self.assertEqual(query.get_result_ids(), ())
        self.assertTrue(query.is_empty())
        self.assertIn("SELECT", query.subselect().code, "subselect must contain SELECT")

        query.add_where(SQL("x > 0"))
        self.assertTrue(query.is_empty(), "adding where clauses keeps the result empty")

    def test_set_result_ids(self):
        query = Query(None, "foo")
        query.set_result_ids([1, 2, 3])
        self.assertEqual(query.get_result_ids(), (1, 2, 3))
        self.assertFalse(query.is_empty())

        query.add_where(SQL("x > 0"))
        self.assertIsNone(query._ids, "adding where clause resets the ids")

    def test_once_states_an_expression_one_time(self):
        query = Query(None, "foo")
        granted = SQL(
            "ARRAY(SELECT n FROM g WHERE r = ANY(%s) AND t LIKE 'a%%')", ["a"]
        )
        owned = SQL("ARRAY(SELECT id FROM foo AS node WHERE owner_id = %s)", 7)
        first = query.once(granted)
        self.assertEqual(first.code, '(SELECT v FROM "foo__$once0")')
        self.assertEqual(query.once(owned).code, '(SELECT v FROM "foo__$once1")')
        again = query.once(
            SQL("ARRAY(SELECT n FROM g WHERE r = ANY(%s) AND t LIKE 'a%%')", ["a"])
        )
        self.assertEqual(again, first, "an expression asked for twice is stated once")
        query.add_join(
            "LEFT JOIN",
            "foo__up",
            "foo",
            SQL(
                '"foo"."up" = "foo__up"."id" AND "foo__up"."id" = ANY(%s::int4[])',
                query.once(owned),
            ),
        )
        query.add_where(
            SQL(
                "foo.name LIKE %s AND (foo.id = ANY(%s::int4[]) "
                "OR foo.up = ANY(%s::int4[])) AND foo.x = %s",
                "50%",
                first,
                again,
                3,
            )
        )

        # run on its own, the statement opens with each expression and its
        # conditions read it from there
        statement = query.statement()
        self.assertEqual(
            statement.code,
            'WITH "foo__$once0" AS MATERIALIZED (SELECT ARRAY(SELECT n FROM g '
            "WHERE r = ANY(%s) AND t LIKE 'a%%') AS v), "
            '"foo__$once1" AS MATERIALIZED (SELECT ARRAY(SELECT id FROM foo AS node '
            "WHERE owner_id = %s) AS v) "
            'SELECT "foo"."id" FROM "foo" LEFT JOIN "foo" AS "foo__up" ON '
            '("foo"."up" = "foo__up"."id" AND "foo__up"."id" = '
            'ANY((SELECT v FROM "foo__$once1")::int4[])) '
            "WHERE foo.name LIKE %s AND "
            '(foo.id = ANY((SELECT v FROM "foo__$once0")::int4[]) '
            'OR foo.up = ANY((SELECT v FROM "foo__$once0")::int4[])) AND foo.x = %s',
        )
        self.assertEqual(statement.params, (["a"], 7, "50%", 3))

        # what goes into another statement has no WITH to read: there each
        # expression is back where it is used, with its parameters
        inline = "ARRAY(SELECT n FROM g WHERE r = ANY(%s) AND t LIKE 'a%%')"
        from_clause = (
            '"foo" LEFT JOIN "foo" AS "foo__up" ON ("foo"."up" = "foo__up"."id" '
            'AND "foo__up"."id" = ANY(ARRAY(SELECT id FROM foo AS node '
            "WHERE owner_id = %s)::int4[]))"
        )
        where_clause = (
            f"foo.name LIKE %s AND (foo.id = ANY({inline}::int4[]) "
            f"OR foo.up = ANY({inline}::int4[])) AND foo.x = %s"
        )
        self.assertEqual(query.from_clause.code, from_clause)
        self.assertEqual(query.from_clause.params, (7,))
        self.assertEqual(query.where_clause.code, where_clause)
        self.assertEqual(query.where_clause.params, ("50%", ["a"], ["a"], 3))
        select = f'SELECT "foo"."id" FROM {from_clause} WHERE {where_clause}'
        self.assertEqual(query.select().code, select)
        self.assertEqual(query.select().params, (7, "50%", ["a"], ["a"], 3))
        self.assertEqual(query.subselect().code, f"({select})")

    def test_once_is_part_of_the_query_s_state(self):
        query = Query(None, "foo")
        self.assertEqual(query.statement().code, 'SELECT "foo"."id" FROM "foo"')
        self.assertEqual(query.statement("foo.a"), query.select("foo.a"))

        query.set_result_ids([1, 2], ordered=False)
        query.once(SQL("ARRAY(SELECT 1)"))
        self.assertIsNone(
            query._ids, "a query that reads something more is not its ids"
        )

        other = query.copy()
        other.once(SQL("ARRAY(SELECT 2)"))
        self.assertEqual(len(query._once), 1, "a copy shares none of it")

        with self.assertRaises(ValueError):
            other.set_result_ids([3])


class TestQuery(TransactionCase):
    def test_auto(self):
        model = self.env["res.partner.tag"]
        model.create([{"name": "Test Category 1"}, {"name": "Test Category 2"}])
        query = model._search([])
        self.assertIsInstance(query, Query)

        ids = list(query)
        self.assertGreater(len(ids), 1)

    def test_records_as_query(self):
        records = self.env["res.partner.tag"]
        query = records._as_query()
        self.assertEqual(list(query), records.ids)
        self.cr.execute(query.select())
        self.assertEqual([row[0] for row in self.cr.fetchall()], records.ids)

        records = self.env["res.partner.tag"].search([])
        query = records._as_query()
        self.assertEqual(list(query), records.ids)
        self.cr.execute(query.select())
        self.assertEqual([row[0] for row in self.cr.fetchall()], records.ids)

        records = records.browse(reversed(records.ids))
        query = records._as_query()
        self.assertEqual(list(query), records.ids)
        self.cr.execute(query.select())
        self.assertEqual([row[0] for row in self.cr.fetchall()], records.ids)

    def test_a_query_pinned_to_more_ids_than_bind_parameters_subselects(self):
        partner = self.env["res.partner"].create({"name": "Pinned among many"})
        pinned = [partner.id, *range(10**9, 10**9 + 70_000)]
        for ordered in (False, True):
            with self.subTest(ordered=ordered):
                query = self.env["res.partner"].browse(pinned)._as_query(ordered)
                self.assertEqual(
                    self.env["res.partner"].search([("id", "in", query)]), partner
                )
                self.assertEqual(len(query.subselect().params), 1)

    def test_many2many_groups_count_against_a_query_pinned_to_its_ids(self):
        groups = self.env["res.groups"].create(
            [{"name": f"Pinned group {index}"} for index in range(3)]
        )
        user = self.env["res.users"].create(
            {"name": "Pinned groups", "login": "pinned_groups", "group_ids": groups.ids}
        )
        groups = user.group_ids
        for pinned in (groups.ids, [*groups.ids, *range(10**9, 10**9 + 200)]):
            with self.subTest(pinned=len(pinned)):
                query = self.env["res.groups"].browse(pinned)._as_query()
                counts = self.env.backend.count_m2m_groups(
                    user, "res_groups_users_rel", "uid", "gid", query
                )
                self.assertEqual(counts, {user.id: len(groups)})

    def test_extra_tables_and_joins_produce_executable_sql(self):
        query = Query(self.env, "res_partner")
        query.add_table("res_users")
        query.left_join("res_partner", "company_id", "res_company", "id", "company")
        query.add_where(SQL('"res_users"."partner_id" = "res_partner"."id"'))
        query.limit = 1
        self.env.execute_query(query.select())

    def test_search_count_honours_a_zero_limit(self):
        model = self.env["res.partner.tag"]
        model.create([{"name": f"CMZ Test {i}"} for i in range(3)])
        self.assertEqual(model.search_count([("name", "like", "CMZ Test")], limit=0), 0)

    def test_a_widening_limit_drops_the_memoised_empty_result(self):
        model = self.env["res.partner.tag"]
        model.create([{"name": f"CMW Test {i}"} for i in range(3)])
        domain = [("name", "like", "CMW Test")]

        query = model._search(domain)
        query.limit = 0
        self.assertEqual(query.get_result_ids(), ())
        query.limit = 10
        self.assertEqual(len(query.get_result_ids()), 3)
        self.assertFalse(query.is_empty())

        query = model._search(domain)
        query.offset = 99
        self.assertEqual(query.get_result_ids(), ())
        query.offset = 0
        self.assertEqual(len(query.get_result_ids()), 3)
        self.assertTrue(bool(query))
