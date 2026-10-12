from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Command
from odoo.tests.common import TransactionCase


class TestApprovalCategoryManagerField(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

    def test_manager_approval_selection_values(self):
        category = self.env["approval.category"].create(
            {
                "sequence_code": "SC2008",
                "name": "Test Category",
                "company_id": self.company.id,
            },
        )

        self.assertEqual(category.manager_approval, "no")

        category.manager_approval = "optional"
        self.assertEqual(category.manager_approval, "optional")

        category.manager_approval = "required"
        self.assertEqual(category.manager_approval, "required")

    def test_category_without_manager_approval(self):
        category = self.env["approval.category"].create(
            {
                "sequence_code": "SC2009",
                "name": "No Manager Category",
                "company_id": self.company.id,
                "manager_approval": "no",
            },
        )

        self.assertEqual(category.manager_approval, "no")


class TestApprovalRequestManagerApproval(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.test_user = cls.env["res.users"].create(
            {
                "name": "Test Employee User",
                "login": "test_employee@test.com",
                "company_id": cls.company.id,
                "company_ids": [(4, cls.company.id)],
            },
        )

        cls.manager_user = cls.env["res.users"].create(
            {
                "name": "Manager User",
                "login": "manager@test.com",
                "company_id": cls.company.id,
                "company_ids": [(4, cls.company.id)],
            },
        )

        cls.manager_employee = cls.env["hr.employee"].create(
            {
                "name": "Manager Employee",
                "user_id": cls.manager_user.id,
                "company_id": cls.company.id,
            },
        )

        cls.test_employee = cls.env["hr.employee"].create(
            {
                "name": "Test Employee",
                "user_id": cls.test_user.id,
                "parent_id": cls.manager_employee.id,
                "company_id": cls.company.id,
            },
        )

        cls.category_required = cls.env["approval.category"].create(
            {
                "sequence_code": "SC2010",
                "name": "Manager Required Category",
                "company_id": cls.company.id,
                "manager_approval": "required",
                "approval_minimum": 1,
                "step_ids": [
                    Command.create(
                        {
                            "name": "Approvers",
                            "minimum": 1,
                            "counts_added_approvers": True,
                        }
                    )
                ],
            },
        )

        cls.category_optional = cls.env["approval.category"].create(
            {
                "sequence_code": "SC2011",
                "name": "Manager Optional Category",
                "company_id": cls.company.id,
                "manager_approval": "optional",
                "approval_minimum": 1,
                "step_ids": [
                    Command.create(
                        {
                            "name": "Approvers",
                            "minimum": 1,
                            "counts_added_approvers": True,
                        }
                    )
                ],
            },
        )

    def test_manager_approval_related_field(self):
        request = self.env["approval.request"].create(
            {
                "name": "Test Request",
                "category_id": self.category_required.id,
                "request_owner_id": self.test_user.id,
                "company_id": self.company.id,
            },
        )

        self.assertEqual(request.manager_approval, "required")

    def test_the_requester_manager_is_asked(self):
        request = self.env["approval.request"].create(
            {
                "name": "Test Request with Manager",
                "category_id": self.category_required.id,
                "request_owner_id": self.test_user.id,
                "company_id": self.company.id,
            },
        )
        request.action_confirm()

        self.assertIn(self.manager_user, request.approver_ids.user_id)

    def test_a_group_step_never_pools_the_manager(self):
        group_member = self.env["res.users"].create(
            {
                "name": "Exclusive Group Member",
                "login": "excl_group_member@test.com",
                "company_id": self.company.id,
                "company_ids": [(4, self.company.id)],
            },
        )
        group = self.env["res.groups"].create(
            {
                "name": "HR Exclusive Approval Group",
                "user_ids": [(6, 0, [group_member.id])],
            },
        )
        category = self.env["approval.category"].create(
            {
                "sequence_code": "SC2012",
                "name": "Exclusive + Manager Category",
                "company_id": self.company.id,
                "manager_approval": "optional",
                "approval_minimum": 1,
                "step_ids": [
                    Command.create(
                        {"name": "Group", "minimum": 1, "group_id": group.id}
                    )
                ],
            },
        )
        request = self.env["approval.request"].create(
            {
                "name": "Exclusive Manager Request",
                "category_id": category.id,
                "request_owner_id": self.test_user.id,
                "company_id": self.company.id,
            },
        )

        approver_user_ids = request.approver_ids.mapped("user_id").ids
        self.assertNotIn(self.manager_user.id, approver_user_ids)
        self.assertIn(group_member.id, approver_user_ids)

    def test_a_required_manager_has_a_step_only_they_meet(self):
        request = self.env["approval.request"].create(
            {
                "name": "Test Request Required",
                "category_id": self.category_required.id,
                "request_owner_id": self.test_user.id,
                "company_id": self.company.id,
            },
        )
        request.action_confirm()

        manager_row = request.approver_ids.filtered(
            lambda row: row.user_id == self.manager_user
        )
        own_steps = manager_row.step_ids.filtered(
            lambda step: (
                request.approver_ids.filtered(lambda row: step in row.step_ids)
                == manager_row
            )
        )
        self.assertTrue(own_steps)

    def test_an_optional_manager_is_an_optional_approver(self):
        request = self.env["approval.request"].create(
            {
                "name": "Test Request Optional",
                "category_id": self.category_optional.id,
                "request_owner_id": self.test_user.id,
                "company_id": self.company.id,
            },
        )
        request.action_confirm()

        manager_row = request.approver_ids.filtered(
            lambda row: row.user_id == self.manager_user
        )
        self.assertTrue(manager_row)
        self.assertFalse(manager_row.required)

    def test_check_manager_approval_constraints_no_employee(self):
        no_employee_user = self.env["res.users"].create(
            {
                "name": "No Employee User",
                "login": "no_employee@test.com",
                "company_id": self.company.id,
                "company_ids": [(4, self.company.id)],
            },
        )

        request = self.env["approval.request"].create(
            {
                "name": "Request Without Employee",
                "category_id": self.category_required.id,
                "request_owner_id": no_employee_user.id,
                "company_id": self.company.id,
            },
        )

        with self.assertRaises(UserError) as context:
            request._check_manager_approval_constraints()

        self.assertIn("employee profile", str(context.exception))

    def test_check_manager_approval_constraints_no_manager(self):
        no_manager_user = self.env["res.users"].create(
            {
                "name": "No Manager User",
                "login": "no_manager@test.com",
                "company_id": self.company.id,
                "company_ids": [(4, self.company.id)],
            },
        )

        self.env["hr.employee"].create(
            {
                "name": "Employee Without Manager",
                "user_id": no_manager_user.id,
                "parent_id": False,
                "company_id": self.company.id,
            },
        )

        request = self.env["approval.request"].create(
            {
                "name": "Request Without Manager",
                "category_id": self.category_required.id,
                "request_owner_id": no_manager_user.id,
                "company_id": self.company.id,
            },
        )

        with self.assertRaises(UserError) as context:
            request._check_manager_approval_constraints()

        self.assertIn("no manager is assigned", str(context.exception))

    def test_check_manager_approval_constraints_manager_no_user(self):
        manager_no_user = self.env["hr.employee"].create(
            {
                "name": "Manager Without User",
                "user_id": False,
                "company_id": self.company.id,
            },
        )

        employee_user = self.env["res.users"].create(
            {
                "name": "Employee With Invalid Manager",
                "login": "invalid_manager@test.com",
                "company_id": self.company.id,
                "company_ids": [(4, self.company.id)],
            },
        )

        self.env["hr.employee"].create(
            {
                "name": "Employee",
                "user_id": employee_user.id,
                "parent_id": manager_no_user.id,
                "company_id": self.company.id,
            },
        )

        request = self.env["approval.request"].create(
            {
                "name": "Request with Invalid Manager",
                "category_id": self.category_required.id,
                "request_owner_id": employee_user.id,
                "company_id": self.company.id,
            },
        )

        with self.assertRaises(UserError) as context:
            request._check_manager_approval_constraints()

        self.assertIn("does not have an active user account", str(context.exception))

    def test_action_confirm_calls_manager_validation(self):
        request = self.env["approval.request"].create(
            {
                "name": "Confirm Test Request",
                "category_id": self.category_required.id,
                "request_owner_id": self.test_user.id,
                "company_id": self.company.id,
            },
        )

        try:
            request.action_confirm()
        except UserError as e:
            self.assertNotIn("employee profile", str(e))
            self.assertNotIn("no manager is assigned", str(e))

    def test_the_requester_manager_is_the_owner_employee_manager(self):
        request = self.env["approval.request"].create(
            {
                "name": "Sequence Test Request",
                "category_id": self.category_required.id,
                "request_owner_id": self.test_user.id,
                "company_id": self.company.id,
            },
        )

        self.assertEqual(request.requester_manager_user_id, self.manager_user)

    def test_escalation_manager_walks_up_archived_chain(self):
        grand_user = self.env["res.users"].create(
            {
                "name": "Grand Manager User",
                "login": "grand_manager@test.com",
                "company_id": self.company.id,
                "company_ids": [(4, self.company.id)],
            },
        )
        grand_employee = self.env["hr.employee"].create(
            {
                "name": "Grand Manager Employee",
                "user_id": grand_user.id,
                "company_id": self.company.id,
            },
        )
        self.manager_employee.parent_id = grand_employee
        self.manager_user.action_archive()

        request = self.env["approval.request"].create(
            {
                "category_id": self.category_optional.id,
                "request_owner_id": self.test_user.id,
                "company_id": self.company.id,
            },
        )
        approver_row = (
            self.env["approval.approver"]
            .sudo()
            .create(
                {
                    "request_id": request.id,
                    "user_id": self.test_user.id,
                },
            )
        )

        self.assertEqual(
            request._get_escalation_manager(approver_row),
            grand_user,
            "the chain walk must skip the archived manager and land on "
            "the grandmanager",
        )


class TestOptionalManagerMissingApprovers(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.no_manager_user = cls.env["res.users"].create(
            {
                "name": "User Without Manager",
                "login": "no_manager_user@test.com",
                "company_id": cls.company.id,
                "company_ids": [(4, cls.company.id)],
            },
        )

        cls.category = cls.env["approval.category"].create(
            {
                "sequence_code": "SC2013",
                "name": "Optional Manager Category",
                "company_id": cls.company.id,
                "manager_approval": "optional",
                "approval_minimum": 2,
            },
        )

    def test_optional_manager_missing_insufficient_approvers(self):
        request = self.env["approval.request"].create(
            {
                "name": "Insufficient Approvers Request",
                "category_id": self.category.id,
                "request_owner_id": self.no_manager_user.id,
                "company_id": self.company.id,
            },
        )

        with self.assertRaises(UserError) as context:
            request.action_confirm()

        error_message = str(context.exception)
        self.assertTrue(
            "optional approver" in error_message or "minimum" in error_message.lower(),
        )


class _Probe(Exception):
    pass


class TestManagerRoutingConvertedToSteps(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        approver_group = cls.env.ref("approval.group_approval_approver")
        cls.people = {}
        for key in ("owner", "manager", "a"):
            cls.people[key] = cls.env["res.users"].create(
                {
                    "name": f"Manager routing {key}",
                    "login": f"manager_routing_{key}@test.com",
                    "company_id": cls.company.id,
                    "company_ids": [(4, cls.company.id)],
                    "group_ids": [(4, approver_group.id)],
                }
            )
        manager_employee = cls.env["hr.employee"].create(
            {
                "name": "Routing Manager",
                "user_id": cls.people["manager"].id,
                "company_id": cls.company.id,
            }
        )
        cls.env["hr.employee"].create(
            {
                "name": "Routing Owner",
                "user_id": cls.people["owner"].id,
                "parent_id": manager_employee.id,
                "company_id": cls.company.id,
            }
        )

    def _category(self, manager_approval, minimum, in_order=False, sequence=10):
        return self.env["approval.category"].create(
            {
                "name": f"Manager routing {manager_approval}",
                "company_id": self.company.id,
                "manager_approval": manager_approval,
                "approval_minimum": minimum,
                "step_ids": [
                    Command.create(
                        {
                            "name": "Approvers",
                            "minimum": minimum,
                            "counts_added_approvers": True,
                            "in_order": in_order,
                            "member_ids": [
                                Command.create(
                                    {
                                        "user_id": self.people["a"].id,
                                        "sequence": sequence,
                                    }
                                )
                            ],
                        }
                    )
                ],
            }
        )

    def _decidable(self, request):
        keys = set()
        for key, user in self.people.items():
            try:
                with self.env.cr.savepoint():
                    request.with_user(user).action_approve()
                    raise _Probe
            except _Probe:
                keys.add(key)
            except AccessError, UserError, ValidationError:
                pass
            self.env.invalidate_all()
        return keys

    def _run(self, category, script):
        request = self.env["approval.request"].create(
            {
                "category_id": category.id,
                "request_owner_id": self.people["owner"].id,
                "company_id": self.company.id,
            }
        )
        request.action_confirm()
        for index, (approver, state, decidable) in enumerate(script):
            if approver:
                request.with_user(self.people[approver]).action_approve()
                request.invalidate_recordset()
            with self.subTest(step=index, approver=approver):
                self.assertEqual(request.state, state)
                self.assertEqual(self._decidable(request), decidable)

    SCRIPT = [
        (None, "pending", {"manager", "a"}),
        ("a", "pending", {"manager"}),
        ("manager", "approved", set()),
    ]

    def test_required_manager(self):
        self._run(self._category("required", 1), self.SCRIPT)

    def test_optional_manager_counted_toward_the_minimum(self):
        self._run(self._category("optional", 2), self.SCRIPT)

    SEQUENTIAL_SCRIPT = [
        (None, "pending", {"manager"}),
        ("manager", "pending", {"a"}),
        ("a", "approved", set()),
    ]

    def test_a_required_manager_goes_first_in_a_sequence(self):
        category = self._category("required", 2, in_order=True)
        self.assertTrue(category.step_ids.filtered("in_order"))
        self._run(category, self.SEQUENTIAL_SCRIPT)

    def test_an_optional_manager_first_in_a_sequence_can_complete_it(self):
        self._run(
            self._category("optional", 1, in_order=True),
            [(None, "pending", {"manager"}), ("manager", "approved", set())],
        )

    def test_a_required_manager_in_a_sequence_is_waited_for(self):
        self._run(
            self._category("required", 1, in_order=True, sequence=5),
            [
                (None, "pending", {"a"}),
                ("a", "pending", {"manager"}),
                ("manager", "approved", set()),
            ],
        )

    def test_the_manager_set_later_joins_the_pool(self):
        category = self._category("no", 2)
        category.manager_approval = "optional"
        self._run(category, self.SCRIPT)

    def test_the_manager_required_later_gets_a_step(self):
        category = self._category("no", 1)
        category.manager_approval = "required"
        self._run(category, self.SCRIPT)

    def test_the_manager_dropped_is_no_longer_asked(self):
        category = self._category("required", 1)
        category.manager_approval = "no"
        self._run(category, [(None, "pending", {"a"}), ("a", "approved", set())])
