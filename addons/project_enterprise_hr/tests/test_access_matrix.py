from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestProjectEnterpriseHrAccessMatrix(AccessMatrixCase):
    personas = {
        "employee_a": Persona(),
        "project_manager_a": Persona("project.group_project_manager"),
        "public": Persona(public=True),
    }
    cells = (
        Cell(
            "project.task",
            "members_task",
            note="a new employee's tasks are read only through "
            "project_enterprise_hr.privilege_book_employee_tasks, which no user holds",
            project_manager_a="rwcd",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        project = cls.env["project.project"].create(
            {"name": "Members only", "privacy_visibility": "followers"}
        )
        return {
            "members_task": cls.env["project.task"].create(
                {"name": "Members only task", "project_id": project.id}
            ),
        }
