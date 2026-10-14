from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import common, patch
from odoo.tools import frozendict, mute_logger


class TestCompanyCheck(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create(
            {
                "name": "Company A",
            }
        )
        cls.company_b = cls.env["res.company"].create(
            {
                "name": "Company B",
            }
        )
        cls.company_c = cls.env["res.company"].create(
            {
                "name": "Company C",
            }
        )
        cls.parent_0 = cls.env["test_orm.model_parent"].create(
            {
                "name": "M0",
                "company_id": False,
            }
        )
        cls.parent_a = cls.env["test_orm.model_parent"].create(
            {
                "name": "M1",
                "company_id": cls.company_a.id,
            }
        )
        cls.parent_b = cls.env["test_orm.model_parent"].create(
            {
                "name": "M2",
                "company_id": cls.company_b.id,
            }
        )
        cls.test_user = cls.env["res.users"].create(
            {
                "name": "Test",
                "login": "test",
                "company_id": cls.company_a.id,
                "company_ids": (cls.company_a | cls.company_c).ids,
            }
        )

    def test_check_company_auto(self):
        m1 = self.env["test_orm.model_child"].create({"company_id": self.company_a.id})
        self.assertTrue(m1._check_company_auto)

    def test_company_and_same_company(self):
        self.env["test_orm.model_child"].create(
            {
                "name": "M1",
                "company_id": self.company_a.id,
                "parent_id": self.parent_a.id,
                "parent_ids": [Command.link(self.parent_a.id)],
            }
        )

    def test_company_and_different_company(self):
        with self.assertRaises(UserError):
            self.env["test_orm.model_child"].create(
                {
                    "name": "M1",
                    "company_id": self.company_b.id,
                    "parent_id": self.parent_a.id,
                }
            )
        with self.assertRaises(UserError):
            self.env["test_orm.model_child"].create(
                {
                    "name": "M1",
                    "company_id": self.company_b.id,
                    "parent_ids": [
                        Command.link(self.parent_a.id),
                        Command.link(self.parent_b.id),
                    ],
                }
            )

    def test_company_and_no_company(self):
        self.env["test_orm.model_child"].create(
            {
                "name": "M1",
                "company_id": self.company_a.id,
                "parent_id": self.parent_0.id,
                "parent_ids": [Command.link(self.parent_0.id)],
            }
        )

    def test_no_company_and_no_company(self):
        self.env["test_orm.model_child"].create(
            {
                "name": "M1",
                "company_id": False,
                "parent_id": self.parent_0.id,
                "parent_ids": [Command.link(self.parent_0.id)],
            }
        )

    def test_no_company_and_some_company(self):
        with self.assertRaises(UserError):
            self.env["test_orm.model_child"].create(
                {
                    "name": "M1",
                    "company_id": False,
                    "parent_id": self.parent_a.id,
                }
            )
        with self.assertRaises(UserError):
            self.env["test_orm.model_child"].create(
                {
                    "name": "M1",
                    "company_id": False,
                    "parent_ids": [
                        Command.link(self.parent_0.id),
                        Command.link(self.parent_a.id),
                    ],
                }
            )

    def test_no_company_check(self):
        self.env["test_orm.model_child_nocheck"].create(
            {
                "name": "M1",
                "company_id": self.company_b.id,
                "parent_id": self.parent_a.id,
            }
        )

    def test_company_write(self):
        child = self.env["test_orm.model_child"].create(
            {
                "name": "M1",
                "company_id": self.company_a.id,
                "parent_id": self.parent_a.id,
                "parent_ids": [Command.link(self.parent_a.id)],
            }
        )

        with self.assertRaises(UserError):
            child.company_id = self.company_b.id

        with self.assertRaises(UserError):
            child.parent_id = self.parent_b.id

        with self.assertRaises(UserError):
            child.parent_ids = [Command.link(self.parent_b.id)]

        child.write(
            {
                "parent_id": self.parent_b.id,
                "parent_ids": [
                    Command.unlink(self.parent_a.id),
                    Command.link(self.parent_b.id),
                ],
                "company_id": self.company_b.id,
            }
        )

    def test_unanchored_regular_fields_do_not_disable_company_dependent_checks(self):
        model = self.env["test_orm.company_check_property"].with_company(self.company_a)
        with mute_logger("odoo.models"):
            valid = model.create(
                {
                    "name": "Valid property",
                    "parent_id": self.parent_b.id,
                    "property_parent_id": self.parent_a.id,
                }
            )
            self.assertEqual(valid.property_parent_id, self.parent_a)
            with self.assertRaises(UserError):
                model.create(
                    {
                        "name": "Invalid property",
                        "property_parent_id": self.parent_b.id,
                    }
                )

    def test_property_error_names_the_company_that_was_checked(self):
        model = self.env["test_orm.company_check_property_anchored"].with_company(
            self.company_a
        )
        with self.assertRaises(UserError) as caught:
            model.create(
                {
                    "name": "Company B record in Company A property scope",
                    "company_id": self.company_b.id,
                    "property_parent_id": self.parent_b.id,
                }
            )
        self.assertIn("In company “Company A”", str(caught.exception))

    def test_check_company_write_performance(self):
        child = self.env["test_orm.model_child"].create(
            {
                "name": "M1",
                "company_id": self.company_b.id,
            }
        )
        self.env.invalidate_all()

        ChildModel = self.registry["test_orm.model_child"]
        _check_company = ChildModel._check_company
        with (
            self.assertQueryCount(3),
            patch.object(
                ChildModel,
                "_check_company",
                autospec=True,
                side_effect=_check_company,
            ) as spy,
        ):
            child.parent_id = self.parent_b

        spy.assert_called_once_with(child, ["parent_id", "write_uid", "write_date"])

    def test_field_selection_keeps_regular_and_property_scopes_explicit(self):
        model = self.env["test_orm.company_check_property_anchored"]
        selected = model._get_company_check_field_names(
            ["property_parent_id", "parent_id"]
        )
        self.assertEqual(selected.regular_fields, ["parent_id"])
        self.assertEqual(selected.property_fields, ["property_parent_id"])
        self.assertEqual(model._get_company_check_field_names([]), ([], []))
        self.assertEqual(
            model._get_company_check_field_names(["company_id"]),
            model._get_company_check_field_names(),
        )

    def test_company_groups_preserve_record_order_and_their_company_scopes(self):
        model = self.env["test_orm.company_check_property_anchored"].with_company(
            self.company_a
        )
        records = model.create(
            [
                {
                    "name": "B",
                    "company_id": self.company_b.id,
                    "parent_id": self.parent_b.id,
                    "property_parent_id": self.parent_a.id,
                },
                {
                    "name": "A",
                    "company_id": self.company_a.id,
                    "parent_id": self.parent_a.id,
                    "property_parent_id": self.parent_a.id,
                },
            ]
        )
        groups = records._get_company_check_groups(
            ["parent_id"], ["property_parent_id"]
        )
        self.assertEqual(
            list(groups),
            [
                ("parent_id", tuple(self.company_b.ids)),
                ("property_parent_id", tuple(self.company_a.ids)),
                ("parent_id", tuple(self.company_a.ids)),
            ],
        )
        self.assertEqual(
            [entry[0] for entries in groups.values() for entry in entries], [0, 1, 3, 2]
        )
        self.assertEqual(list(records._get_company_violations(groups)), [])

    def test_company_error_builder_does_not_raise_and_caps_ordered_details_at_five(
        self,
    ):
        records = self.env["test_orm.model_child"].create(
            [
                {"name": f"Candidate {index}", "company_id": self.company_a.id}
                for index in range(6)
            ]
        )
        error = records._prepare_company_inconsistency_error(
            [(record, "parent_id", self.parent_b) for record in records]
        )
        self.assertIsInstance(error, UserError)
        message = str(error)
        for index in range(5):
            self.assertIn(f"Candidate {index}", message)
        self.assertNotIn("Candidate 5", message)
        self.assertEqual(message.count("(parent_id: 'M2')"), 5)
        self.assertEqual(records.mapped("parent_id"), self.env["test_orm.model_parent"])

    def test_two_checked_fields_on_one_comodel_read_its_companies_once(self):
        self.env.invalidate_all()
        with self.capturedQueries() as queries:
            self.env["test_orm.model_child"].create(
                {
                    "name": "M1",
                    "company_id": self.company_b.id,
                    "parent_id": self.parent_0.id,
                    "parent_ids": [Command.set(self.parent_b.ids)],
                }
            )
        parent_reads = [
            query
            for query in queries
            if 'FROM "test_orm_model_parent"' in query and "SELECT" in query
        ]
        self.assertEqual(len(parent_reads), 1, parent_reads)

    def test_company_environment(self):

        user = self.test_user.with_user(self.test_user).with_context(
            allowed_company_ids=[]
        )

        with self.assertRaises(AccessError):
            user.with_context(
                allowed_company_ids=[
                    self.company_a.id,
                    self.company_b.id,
                    self.company_c.id,
                ]
            ).env.companies

        with self.assertRaises(AccessError):
            user.with_context(allowed_company_ids=[self.company_b.id]).env.company

        with self.assertRaises(AccessError):
            user.with_context(
                allowed_company_ids=["company_qsdf", "company564654"]
            ).env.companies

        companies = self.company_a | self.company_b
        self.assertEqual(
            user.sudo().with_context(allowed_company_ids=companies.ids).env.companies,
            companies,
        )

        self.assertEqual(
            user.sudo()
            .with_context(allowed_company_ids=[self.company_b.id, "abc"])
            .env.company,
            self.company_b,
        )
        self.assertEqual(user.env.company, user.company_id)
        self.assertEqual(user.env.companies, user.company_ids)

    def test_with_company(self):

        user = self.test_user.with_user(self.test_user).with_context(
            allowed_company_ids=[]
        )
        self.assertEqual(user.env.companies, user.company_ids)

        self.assertEqual(
            user.with_company(user.env.company).env.company, user.env.company
        )
        self.assertEqual(
            user.with_company(self.company_a).env.company,
            user.with_company(self.company_a.id).env.company,
        )

        for falsy in [False, None, 0, "", self.env["res.company"], []]:
            no_change = user.with_company(falsy)
            self.assertEqual(no_change, user)
            self.assertEqual(no_change.env.context, user.env.context)
            self.assertEqual(no_change.env, user.env)

        comp_a_user = user.with_company(user.company_id)
        comp_a_user2 = user.with_context(allowed_company_ids=user.company_id.ids)

        self.assertEqual(comp_a_user.env, comp_a_user2.env)
        self.assertEqual(comp_a_user.env.context, comp_a_user2.env.context)

        self.assertEqual(comp_a_user.env.company, user.company_id)
        self.assertEqual(comp_a_user.env.companies, user.company_id)

        comp_c_a_user = comp_a_user.with_company(self.company_c)
        self.assertEqual(comp_c_a_user.env.company, self.company_c)
        self.assertEqual(comp_c_a_user.env.companies, self.company_c + self.company_a)
        self.assertEqual(comp_c_a_user.env.companies[0], self.company_c)
        self.assertEqual(comp_c_a_user.env.companies[1], self.company_a)
        self.assertEqual(
            comp_c_a_user.env.context["allowed_company_ids"],
            [self.company_c.id, self.company_a.id],
        )

        comp_a_c_user = comp_c_a_user.with_company(self.company_a)
        self.assertEqual(comp_a_c_user.env.companies[0], self.company_a)
        self.assertEqual(comp_a_c_user.env.companies[1], self.company_c)
        self.assertEqual(
            comp_a_c_user.env.context["allowed_company_ids"],
            [self.company_a.id, self.company_c.id],
        )

        none_user = user.with_context(allowed_company_ids=None)
        self.assertEqual(none_user.env.company, user.company_id)
        self.assertEqual(none_user.env.companies, user.company_ids)

        comp_user = none_user.with_company(user.company_id)
        self.assertEqual(comp_user.env.company, user.company_id)
        self.assertEqual(comp_user.env.companies, user.company_id)

    def test_company_sticky_with_context(self):
        context = frozendict({"nothing_to_see_here": True})
        companies_1 = frozendict({"allowed_company_ids": [1]})
        companies_2 = frozendict({"allowed_company_ids": [2]})

        User = self.env["res.users"].with_context(context)
        self.assertEqual(User.env.context, context)

        User = User.with_context(**companies_1)
        self.assertEqual(User.env.context, dict(context, **companies_1))

        User = User.with_context(**companies_2)
        self.assertEqual(User.env.context, dict(context, **companies_2))

        User = User.with_context(companies_1)
        self.assertEqual(User.env.context, companies_1)

        User = User.with_context(context)
        self.assertEqual(User.env.context, dict(context, **companies_1))
