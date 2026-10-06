from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools.safe_eval import safe_eval


@tagged("post_install", "-at_install")
class TestDepartmentFilter(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Category = cls.env["approval.category"]
        cls.Department = cls.env["hr.department"]
        cls.Users = cls.env["res.users"]
        cls.Employee = cls.env["hr.employee"]
        cls.Groups = cls.env["res.groups"]

        cls.dept_x = cls.Department.create({"name": "Dept X"})
        cls.dept_y = cls.Department.create({"name": "Dept Y"})

        cls.user_x = cls.Users.create(
            {
                "name": "User X",
                "login": "user_x_dept_filter",
                "email": "user_x@example.com",
            },
        )
        cls.user_y = cls.Users.create(
            {
                "name": "User Y",
                "login": "user_y_dept_filter",
                "email": "user_y@example.com",
            },
        )
        cls.user_orphan = cls.Users.create(
            {
                "name": "User Orphan",
                "login": "user_orphan_dept_filter",
                "email": "user_orphan@example.com",
            },
        )

        cls.Employee.create(
            {
                "name": "User X",
                "user_id": cls.user_x.id,
                "department_id": cls.dept_x.id,
            },
        )
        cls.Employee.create(
            {
                "name": "User Y",
                "user_id": cls.user_y.id,
                "department_id": cls.dept_y.id,
            },
        )

        cls.dashboard_action = cls.env.ref(
            "approval.action_approval_category_dashboard",
        )

    def _eval_dashboard_domain(self, user):
        user_env = self.env(user=user.id)
        domain = safe_eval(self.dashboard_action.domain, {"uid": user.id})
        return user_env["approval.category"].search(domain)

    def test_field_present(self):
        fields = self.Category._fields
        self.assertIn("department_ids", fields)
        self.assertEqual(fields["department_ids"].comodel_name, "hr.department")
        self.assertEqual(fields["department_ids"].type, "many2many")

    def test_no_folder_residue(self):
        fields = self.Category._fields
        self.assertNotIn("parent_id", fields)
        self.assertNotIn("is_folder", fields)
        self.assertNotIn("child_ids", fields)

    def test_department_is_classifier_not_filter(self):
        category = self.Category.create(
            {
                "sequence_code": "SC2001",
                "name": "Tagged with Dept X only",
                "approval_minimum": 1,
                "department_ids": [(6, 0, [self.dept_x.id])],
            },
        )
        self.assertIn(category, self._eval_dashboard_domain(self.user_x))
        self.assertIn(category, self._eval_dashboard_domain(self.user_y))
        self.assertIn(category, self._eval_dashboard_domain(self.user_orphan))

    def test_empty_department_visible_to_all(self):
        category = self.Category.create(
            {
                "sequence_code": "SC2002",
                "name": "Untagged",
                "approval_minimum": 1,
            },
        )
        self.assertIn(category, self._eval_dashboard_domain(self.user_x))
        self.assertIn(category, self._eval_dashboard_domain(self.user_y))
        self.assertIn(category, self._eval_dashboard_domain(self.user_orphan))

    def test_allowed_user_restricts_visibility(self):
        category = self.Category.create(
            {
                "sequence_code": "SC2003",
                "name": "User X only",
                "approval_minimum": 1,
                "allowed_user_ids": [(6, 0, [self.user_x.id])],
            },
        )
        self.assertIn(category, self._eval_dashboard_domain(self.user_x))
        self.assertNotIn(category, self._eval_dashboard_domain(self.user_y))
        self.assertNotIn(category, self._eval_dashboard_domain(self.user_orphan))

    def test_allowed_group_restricts_visibility(self):
        group = self.Groups.create({"name": "Approvals Test Group"})
        self.user_x.write({"group_ids": [(4, group.id)]})
        category = self.Category.create(
            {
                "sequence_code": "SC2004",
                "name": "Group members only",
                "approval_minimum": 1,
                "allowed_group_ids": [(6, 0, [group.id])],
            },
        )
        self.assertIn(category, self._eval_dashboard_domain(self.user_x))
        self.assertNotIn(category, self._eval_dashboard_domain(self.user_y))
        self.assertNotIn(category, self._eval_dashboard_domain(self.user_orphan))

    def _count_as(self, user):
        recordset = self.dept_x.with_user(user)
        recordset.invalidate_recordset(["approval_category_count"])
        return recordset.approval_category_count

    def test_count_honors_access_control(self):
        self.Category.create(
            {
                "sequence_code": "SC2005",
                "name": "Public for Dept X",
                "approval_minimum": 1,
                "department_ids": [(6, 0, [self.dept_x.id])],
            },
        )
        self.Category.create(
            {
                "sequence_code": "SC2006",
                "name": "Restricted to User X",
                "approval_minimum": 1,
                "department_ids": [(6, 0, [self.dept_x.id])],
                "allowed_user_ids": [(6, 0, [self.user_x.id])],
            },
        )
        self.assertEqual(self._count_as(self.user_x), 2)
        self.assertEqual(self._count_as(self.user_y), 1)

    def test_count_no_duplication_on_overlapping_grants(self):
        group = self.Groups.create({"name": "Approvals Overlap Test"})
        self.user_x.write({"group_ids": [(4, group.id)]})
        self.Category.create(
            {
                "sequence_code": "SC2007",
                "name": "Granted via user AND group",
                "approval_minimum": 1,
                "department_ids": [(6, 0, [self.dept_x.id])],
                "allowed_user_ids": [(6, 0, [self.user_x.id])],
                "allowed_group_ids": [(6, 0, [group.id])],
            },
        )
        self.assertEqual(self._count_as(self.user_x), 1)
