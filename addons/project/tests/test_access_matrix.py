from odoo import Command
from odoo.tests import tagged

from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestProjectAccessMatrix(AccessMatrixCase):
    personas = {
        "user_a": Persona("project.group_project_user"),
        "follower_a": Persona("project.group_project_user"),
        "member_a": Persona("project.group_project_user"),
        "manager_a": Persona("project.group_project_manager"),
        "employee_a": Persona(),
        "assignee_a": Persona(),
        "user_b": Persona("project.group_project_user", company="b"),
        "portal_c": Persona(portal="customer_c"),
        "manager_ab": Persona("project.group_project_manager", companies=("a", "b")),
    }
    cells = (
        Cell(
            "project.project",
            "project_employees",
            user_a="r",
            follower_a="r",
            member_a="r",
            manager_a="rwcd",
            employee_a="r",
            assignee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "project.project",
            "project_followers",
            member_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.project",
            "project_portal",
            user_a="r",
            follower_a="r",
            member_a="r",
            manager_a="rwcd",
            employee_a="r",
            assignee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "project.project",
            "project_b",
            user_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "project.task",
            "task_employees",
            user_a="rwcd",
            follower_a="rwcd",
            member_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            assignee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "project.task",
            "task_followers",
            follower_a="rwcd",
            member_a="rwcd",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.task",
            "task_assigned",
            follower_a="rwcd",
            member_a="rwcd",
            manager_a="rwcd",
            assignee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "project.task",
            "task_portal",
            user_a="rwcd",
            follower_a="rwcd",
            member_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            assignee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "project.task",
            "task_b",
            user_b="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.task",
            "task_private",
            user_a="rwcd",
        ),
        Cell(
            "project.baseline",
            "baseline",
            member_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.baseline.line",
            "baseline_line",
            member_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.benefit",
            "benefit",
            member_a="rwc",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.collaborator",
            "collaborator",
            user_a="r",
            follower_a="r",
            member_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.gate",
            "gate",
            member_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.gate.criterion",
            "gate_criterion",
            member_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.history",
            "history",
            member_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.milestone",
            "milestone",
            member_a="rwcd",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.phase",
            "phase",
            user_a="r",
            follower_a="r",
            member_a="r",
            manager_a="rwcd",
            employee_a="r",
            assignee_a="r",
            manager_ab="rwcd",
        ),
        Cell(
            "project.retrospective",
            "retrospective",
            member_a="rwc",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.retrospective.action",
            "retrospective_action",
            member_a="rwc",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.risk",
            "risk",
            member_a="rwc",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.sprint",
            "sprint",
            member_a="rwc",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.tags",
            "tag",
            user_a="rwc",
            follower_a="rwc",
            member_a="rwc",
            manager_a="rwcd",
            employee_a="rwc",
            assignee_a="rwc",
            user_b="rwc",
            portal_c="r",
            manager_ab="rwcd",
        ),
        Cell(
            "project.task.dependency",
            "dependency",
            member_a="rwcd",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "loss.reason",
            "lost_reason",
            user_a="r",
            follower_a="r",
            member_a="r",
            manager_a="rwcd",
            employee_a="r",
            assignee_a="r",
            portal_c="r",
            manager_ab="rwcd",
        ),
        Cell(
            "project.task.recurrence",
            "recurrence",
            user_a="rwcd",
            follower_a="rwcd",
            member_a="rwcd",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.triage",
            "triage",
            user_a="rwcd",
        ),
        Cell(
            "project.task.triage",
            "task_triage",
            user_a="rwcd",
        ),
        Cell(
            "project.update",
            "update",
            member_a="rwcd",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "project.workflow.step",
            "workflow_step",
            user_a="rwcd",
            follower_a="rwcd",
            member_a="rwcd",
            manager_a="rwcd",
            employee_a="r",
            assignee_a="r",
            user_b="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "report.project.task.user",
            "task_report",
            follower_a="r",
            member_a="r",
            manager_a="r",
            manager_ab="r",
        ),
        Cell(
            "project.resource.report",
            "resource_report",
            member_a="r",
            manager_a="r",
            manager_ab="r",
        ),
        Cell(
            "account.analytic.account",
            "analytic",
            installed={"account": {"employee_a": "r", "assignee_a": "r"}},
            user_a="r",
            follower_a="r",
            member_a="r",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "account.analytic.line",
            "analytic_line",
            note="hr_timesheet gives a line outside every project to analytic accounting",
            installed={"hr_timesheet": {"manager_a": "-rwcd", "manager_ab": "-rwcd"}},
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "account.analytic.line",
            "timesheet_line",
            needs="hr_timesheet",
            manager_a="rwcd",
            manager_ab="rwcd",
        ),
        Cell(
            "mail.activity.plan",
            "activity_plan",
            user_a="r",
            follower_a="r",
            member_a="r",
            manager_a="rwcd",
            employee_a="r",
            assignee_a="r",
            user_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "mail.activity.plan.template",
            "activity_plan_template",
            user_a="r",
            follower_a="r",
            member_a="r",
            manager_a="rwcd",
            employee_a="r",
            assignee_a="r",
            user_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "mail.activity.type",
            "activity_type",
            user_a="r",
            follower_a="r",
            member_a="r",
            manager_a="rwcd",
            employee_a="r",
            assignee_a="r",
            user_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "resource.role",
            "role",
            user_a="r",
            follower_a="r",
            member_a="r",
            manager_a="rwcd",
            employee_a="r",
            assignee_a="r",
            user_b="r",
            manager_ab="rwcd",
        ),
        Cell(
            "resource.schedule.exception",
            "schedule_exception",
            user_a="r",
            follower_a="r",
            member_a="r",
            manager_a="r",
            employee_a="r",
            assignee_a="r",
            manager_ab="r",
        ),
        Cell(
            "res.users.grant",
            "feature_grant",
            employee_a="r",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        env = cls.env
        a, b = cls.companies["a"], cls.companies["b"]
        users = cls.users
        customer_c = cls.partners["customer_c"]

        def project(name, company, privacy, **values):
            return env["project.project"].create(
                {
                    "name": name,
                    "company_id": company.id,
                    "privacy_visibility": privacy,
                    **values,
                }
            )

        project_employees = project("matrix employees", a, "employees")
        project_followers = project(
            "matrix followers",
            a,
            "followers",
            member_user_ids=[Command.set(users["member_a"].ids)],
        )
        project_followers.message_subscribe(
            partner_ids=users["follower_a"].partner_id.ids
        )
        project_portal = project("matrix portal", a, "portal", partner_id=customer_c.id)
        project_b = project("matrix b", b, "employees")

        def task(name, project_record, **values):
            return env["project.task"].create(
                {"name": name, "project_id": project_record.id, **values}
            )

        task_employees = task("matrix task", project_employees)
        task_followers = task("matrix hidden task", project_followers)
        task_assigned = task(
            "matrix assigned task",
            project_followers,
            user_ids=[Command.set(users["assignee_a"].ids)],
        )
        task_portal = task("matrix portal task", project_portal)
        task_b = task("matrix task b", project_b)
        task_private = task(
            "matrix private task",
            env["project.project"],
            user_ids=[Command.set(users["user_a"].ids)],
        )
        baseline = env["project.baseline"].create(
            {"name": "matrix baseline", "project_id": project_followers.id}
        )
        gate = env["project.gate"].create(
            {"name": "matrix gate", "project_id": project_followers.id}
        )
        retrospective = env["project.retrospective"].create(
            {
                "name": "matrix retro",
                "project_id": project_followers.id,
                "date": "2026-09-01",
            }
        )
        plan = env["account.analytic.plan"].create({"name": "matrix plan"})
        analytic = env["account.analytic.account"].create(
            {"name": "matrix analytic", "plan_id": plan.id, "company_id": a.id}
        )
        activity_plan = env["mail.activity.plan"].create(
            {"name": "matrix project plan", "res_model": "project.task"}
        )
        activity_type = env["mail.activity.type"].create(
            {"name": "matrix type", "res_model": "project.task"}
        )
        resource = env["resource.resource"].create(
            {"name": "matrix resource", "user_id": users["follower_a"].id}
        )
        env["resource.reservation"].create(
            {
                "name": "matrix reservation",
                "resource_id": resource.id,
                "res_model": "project.task",
                "res_id": task_followers.id,
                "date_start": "2026-09-01 08:00:00",
                "date_end": "2026-09-01 12:00:00",
                "allocated_hours": 4,
            }
        )
        env.flush_all()
        report = env["report.project.task.user"].sudo()
        resource_report = env["project.resource.report"].sudo()
        return {
            "project_employees": project_employees,
            "project_followers": project_followers,
            "project_portal": project_portal,
            "project_b": project_b,
            "task_employees": task_employees,
            "task_followers": task_followers,
            "task_assigned": task_assigned,
            "task_portal": task_portal,
            "task_b": task_b,
            "task_private": task_private,
            "baseline": baseline,
            "baseline_line": env["project.baseline.line"].create(
                {"baseline_id": baseline.id, "task_name": "matrix snapshot"}
            ),
            "benefit": env["project.benefit"].create(
                {"name": "matrix benefit", "project_id": project_followers.id}
            ),
            "collaborator": env["project.collaborator"].create(
                {"project_id": project_portal.id, "partner_id": customer_c.id}
            ),
            "gate": gate,
            "gate_criterion": env["project.gate.criterion"].create(
                {"name": "matrix criterion", "gate_id": gate.id}
            ),
            "history": env["project.history"].create(
                {
                    "name": "matrix history",
                    "project_id": project_followers.id,
                    "date_completed": "2026-09-01",
                }
            ),
            "milestone": env["project.milestone"].create(
                {"name": "matrix milestone", "project_id": project_followers.id}
            ),
            "phase": env["project.phase"].create(
                {"name": "matrix phase", "company_id": a.id}
            ),
            "retrospective": retrospective,
            "retrospective_action": env["project.retrospective.action"].create(
                {
                    "name": "matrix action",
                    "retrospective_id": retrospective.id,
                    "owner_id": users["user_a"].id,
                }
            ),
            "risk": env["project.risk"].create(
                {"name": "matrix risk", "project_id": project_followers.id}
            ),
            "sprint": env["project.sprint"].create(
                {
                    "name": "matrix sprint",
                    "project_id": project_followers.id,
                    "date_start": "2026-09-01",
                    "date_end": "2026-09-14",
                }
            ),
            "tag": env["project.tags"].create({"name": "matrix tag"}),
            "dependency": env["project.task.dependency"].create(
                {"task_id": task_followers.id, "depends_on_id": task_assigned.id}
            ),
            "lost_reason": env["loss.reason"].create(
                {"name": "matrix lost task", "scope": "task", "company_id": a.id}
            ),
            "recurrence": env["project.task.recurrence"].create(
                {"task_ids": [Command.set(task_employees.ids)]}
            ),
            "triage": env["project.triage"]
            .with_user(users["user_a"])
            .create({"name": "matrix triage"})
            .sudo(),
            "task_triage": env["project.task.triage"].create(
                {"task_id": task_employees.id, "user_id": users["user_a"].id}
            ),
            "update": env["project.update"].create(
                {
                    "name": "matrix update",
                    "project_id": project_followers.id,
                    "user_id": users["manager_a"].id,
                    "status": "on_track",
                }
            ),
            "workflow_step": env["project.workflow.step"].create(
                {"name": "matrix step"}
            ),
            "task_report": report.search([("task_id", "=", task_followers.id)]),
            "resource_report": resource_report.search(
                [("project_id", "=", project_followers.id)], limit=1
            ),
            "analytic": analytic,
            "analytic_line": env["account.analytic.line"].create(
                {"name": "matrix", "account_id": analytic.id, "company_id": a.id}
            ),
            "timesheet_line": env["account.analytic.line"].create(
                {
                    "name": "matrix timesheet",
                    "project_id": project_followers.id,
                    "employee_id": env["hr.employee"]
                    .create({"name": "matrix timesheet employee", "company_id": a.id})
                    .id,
                }
            )
            if "project_id" in env["account.analytic.line"]._fields
            else None,
            "activity_plan": activity_plan,
            "activity_plan_template": env["mail.activity.plan.template"].create(
                {
                    "plan_id": activity_plan.id,
                    "activity_type_id": activity_type.id,
                    "summary": "matrix",
                }
            ),
            "activity_type": activity_type,
            "role": env["resource.role"].create({"name": "matrix role"}),
            "schedule_exception": env["resource.schedule.exception"].create(
                {
                    "name": "matrix exception",
                    "company_id": a.id,
                    "time_type_id": env.ref("base.time_type_leave").id,
                    "date_from": "2026-09-01 08:00:00",
                    "date_to": "2026-09-01 12:00:00",
                }
            ),
            "feature_grant": env["res.users.grant"].create(
                {
                    "user_id": users["employee_a"].id,
                    "group_id": env.ref("project.group_project_stages").id,
                }
            ),
        }
