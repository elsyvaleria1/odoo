from ast import literal_eval
from datetime import UTC

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.libs.intervals import Intervals
from odoo.tools import get_lang
from odoo.tools.date_utils import get_intervals_hours

from odoo.addons.timer.utils.timer_utils import round_time_spent


class ProjectTask(models.Model):
    _name = "project.task"
    _inherit = "project.task"

    @api.model
    def default_get(self, fields):
        context = dict(self.env.context)
        is_fsm_mode = self.env.context.get("fsm_mode")
        fsm_project = False
        if (
            is_fsm_mode
            and "project_id" in fields
            and not self.env.context.get("default_parent_id")
        ):
            company_id = (
                self.env.context.get("default_company_id") or self.env.company.id
            )
            fsm_project = self.env["project.project"].search(
                [("is_fsm", "=", True), ("company_id", "=", company_id)],
                order="sequence, name, id",
                limit=1,
            )
            if fsm_project:
                context["default_project_id"] = self.env.context.get(
                    "default_project_id", fsm_project.id
                )
        result = super(ProjectTask, self.with_context(context)).default_get(fields)
        if fsm_project:
            result.update(
                {
                    "company_id": company_id,
                    "step_id": self.get_step_id(fsm_project.id, [("fold", "=", False)]),
                }
            )
        return result

    is_fsm = fields.Boolean(related="project_id.is_fsm")
    fsm_done = fields.Boolean(
        string="Task Done",
        compute="_compute_fsm_done",
        store=True,
        copy=False,
        readonly=False,
    )
    display_enabled_conditions_count = fields.Integer(
        export_string_translation=False,
        compute="_compute_display_conditions_count",
    )
    display_satisfied_conditions_count = fields.Integer(
        export_string_translation=False,
        compute="_compute_display_conditions_count",
    )
    display_mark_as_done_primary = fields.Boolean(
        export_string_translation=False,
        compute="_compute_mark_as_done_buttons",
    )
    display_mark_as_done_secondary = fields.Boolean(
        export_string_translation=False,
        compute="_compute_mark_as_done_buttons",
    )
    partner_city = fields.Char(
        related="partner_id.city",
        readonly=False,
    )
    partner_zip = fields.Char(
        related="partner_id.zip",
        string="ZIP",
    )
    partner_street = fields.Char(related="partner_id.street")
    partner_street2 = fields.Char(related="partner_id.street2")
    partner_country_id = fields.Many2one(
        comodel_name="res.country",
        related="partner_id.country_id",
    )
    partner_state_id = fields.Many2one(
        comodel_name="res.country.state",
        related="partner_id.state_id",
        string="Customer State",
    )
    is_task_phone_update = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_task_phone_update",
    )

    display_sign_report_primary = fields.Boolean(
        export_string_translation=False,
        compute="_compute_display_sign_report_buttons",
    )
    display_sign_report_secondary = fields.Boolean(
        export_string_translation=False,
        compute="_compute_display_sign_report_buttons",
    )
    display_send_report_primary = fields.Boolean(
        export_string_translation=False,
        compute="_compute_display_send_report_buttons",
    )
    display_send_report_secondary = fields.Boolean(
        export_string_translation=False,
        compute="_compute_display_send_report_buttons",
    )
    fsm_is_sent = fields.Boolean(
        export_string_translation=False,
        copy=False,
        readonly=True,
    )
    show_customer_preview = fields.Boolean(
        export_string_translation=False,
        compute="_compute_show_customer_preview",
    )
    worksheet_signature = fields.Binary(
        string="Signature",
        attachment=True,
        copy=False,
    )
    worksheet_signed_by = fields.Char(
        string="Signed By",
        copy=False,
    )
    allow_geolocation = fields.Boolean(related="project_id.allow_geolocation")

    @api.depends("date_start", "date_end", "user_ids")
    def _compute_planning_overlap(self):
        fsm_tasks = self.filtered("is_fsm")
        overlap_mapping = super()._compute_planning_overlap()
        for row in self._get_planning_overlap_rows([("is_fsm", "=", True)]):
            task_id = row["id"]
            if task_id not in overlap_mapping:
                overlap_mapping[task_id] = {row["user_id"]: {}}
            if row["user_id"] not in overlap_mapping[task_id]:
                overlap_mapping[task_id][row["user_id"]] = {}
            overlap_data = overlap_mapping[task_id][row["user_id"]]
            overlap_data["partner_name"] = row["partner_name"]
            existing_task_ids = overlap_data.get("overlapping_tasks_ids", [])
            overlap_data["overlapping_tasks_ids"] = list(
                set(existing_task_ids) | set(row["task_ids"])
            )
            existing_min_date = overlap_data.get("min_date_start", row["min"])
            overlap_data["min_date_start"] = min(existing_min_date, row["min"])
            existing_max_date = overlap_data.get("max_date_end", row["max"])
            overlap_data["max_date_end"] = max(existing_max_date, row["max"])
        if not overlap_mapping:
            fsm_tasks.planning_overlap = False
            return
        for task in fsm_tasks:
            overlap_messages = []
            for task_mapping in overlap_mapping.get(task.id, {}).values():
                message = self.env._(
                    "%(partner)s has %(number)s tasks at the same time.",
                    partner=task_mapping["partner_name"],
                    number=len(task_mapping["overlapping_tasks_ids"]),
                )
                overlap_messages.append(message)
            task.planning_overlap = " ".join(overlap_messages) or False

    @property
    def TASK_PORTAL_READABLE_FIELDS(self):
        return super().TASK_PORTAL_READABLE_FIELDS | {
            "is_fsm",
            "date_start",
            "fsm_done",
            "phone_ids",
            "partner_city",
        }

    @api.depends(
        "fsm_done",
        "is_fsm",
        "timer_start",
        "display_enabled_conditions_count",
        "display_satisfied_conditions_count",
    )
    def _compute_mark_as_done_buttons(self) -> None:
        for task in self:
            primary, secondary = True, True
            if task.fsm_done or not task.is_fsm or task.sudo().timer_start:
                primary, secondary = False, False
            elif (
                task.display_enabled_conditions_count
                == task.display_satisfied_conditions_count
            ):
                secondary = False
            else:
                primary = False
            task.update(
                {
                    "display_mark_as_done_primary": primary,
                    "display_mark_as_done_secondary": secondary,
                }
            )

    @api.depends("phone_ids", "partner_id.phone_ids")
    def _compute_is_task_phone_update(self) -> None:
        for task in self:
            task.is_task_phone_update = task.phone_ids != task.partner_id.phone_ids

    @api.depends("project_id.allow_timesheets", "total_hours_spent")
    def _compute_display_conditions_count(self) -> None:
        for task in self:
            enabled = 1 if task.project_id.allow_timesheets else 0
            satisfied = 1 if enabled and task.total_hours_spent else 0
            task.update(
                {
                    "display_enabled_conditions_count": enabled,
                    "display_satisfied_conditions_count": satisfied,
                }
            )

    @api.depends("fsm_done")
    def _compute_display_timesheet_timer(self) -> None:
        fsm_done_tasks = self.filtered("fsm_done")
        fsm_done_tasks.display_timesheet_timer = False
        super(ProjectTask, self - fsm_done_tasks)._compute_display_timesheet_timer()

    @api.onchange("date_end", "date_start")
    def _onchange_planned_dates(self):
        if not self.is_fsm:
            return super()._onchange_planned_dates()
        return None

    def write(self, vals):
        self_fsm = self.filtered("is_fsm")
        basic_projects = self - self_fsm
        if basic_projects:
            res = super(ProjectTask, basic_projects).write(vals.copy())
            if not self_fsm:
                return res

        is_start_date_set = bool(vals.get("date_start", False))
        is_end_date_set = bool(vals.get("date_end", False))
        both_dates_changed = "date_start" in vals and "date_end" in vals
        self_fsm = self_fsm.with_context(fsm_mode=True)

        if self_fsm and (
            (both_dates_changed and is_start_date_set != is_end_date_set)
            or (
                not both_dates_changed
                and (
                    (
                        "date_start" in vals
                        and not all(bool(t.date_end) == is_start_date_set for t in self)
                    )
                    or (
                        "date_end" in vals
                        and not all(bool(t.date_start) == is_end_date_set for t in self)
                    )
                )
            )
        ):
            vals.update({"date_end": False, "date_start": False})

        return super(ProjectTask, self_fsm).write(vals)

    @api.model
    def _group_expand_project_ids(self, projects, domain):
        res = super()._group_expand_project_ids(projects, domain)
        if self.env.context.get("fsm_mode"):
            search_on_comodel = self._search_on_comodel(
                domain, "project_id", "project.project", [("is_fsm", "=", True)]
            )
            res &= search_on_comodel
        return res

    def _group_expand_user_ids_domain(self, domain_expand):
        if self.env.context.get("fsm_mode"):
            new_domain_expand = Domain.OR(
                [
                    [
                        ("is_closed", "=", False),
                        ("date_start", "=", False),
                        ("date_end", "=", False),
                    ],
                    domain_expand,
                ]
            )
            return new_domain_expand & Domain("is_fsm", "=", True)
        else:
            return super()._group_expand_user_ids_domain(domain_expand)

    def _compute_fsm_done(self) -> None:
        closed_tasks = self.filtered(lambda t: t.is_closed)
        closed_tasks.fsm_done = True

    def action_timer_start(self):
        if not self.user_timer_id.timer_start and self.display_timesheet_timer:
            super().action_timer_start()
            if not self.is_fsm:
                return

            if self.allow_geolocation and (
                geolocation := self.env.context.get("geolocation")
            ):
                success = geolocation.get("success")
                latitude = 0
                longitude = 0
                localisation_start = False

                if success:
                    latitude = geolocation["latitude"]
                    longitude = geolocation["longitude"]
                    localisation_start = self.env["geocoder"]._get_localisation(
                        latitude=latitude, longitude=longitude
                    )

                    geolocation_message = self.env._(
                        "GPS Coordinates: %(localisation_start)s (%(latitude)s, %(longitude)s)",
                        localisation_start=localisation_start,
                        latitude=latitude,
                        longitude=longitude,
                    )
                else:
                    geolocation_message = geolocation.get(
                        "message", self.env._("Location error")
                    )
            else:
                geolocation_message = False

            time = fields.Datetime.context_timestamp(self, self.timer_start)
            body = self.env._(
                "Timer started at: %(date)s %(time)s",
                date=time.strftime(get_lang(self.env).date_format),
                time=time.strftime(get_lang(self.env).time_format),
            )
            if geolocation_message:
                body += Markup("<br/>") + geolocation_message
                if latitude and latitude:
                    body += Markup(
                        " <a href='https://maps.google.com?q={latitude},{longitude}' target='_blank'>{label}</a>"
                    ).format(
                        latitude=latitude,
                        longitude=longitude,
                        label=self.env._("View on Map"),
                    )
            self.message_post(body=body)

    def action_view_timesheets(self):
        kanban_view = self.env.ref("hr_timesheet.view_kanban_account_analytic_line")
        form_view = self.env.ref("industry_fsm.timesheet_view_form")
        list_view = self.env.ref("industry_fsm.timesheet_view_tree_user_inherit")
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Time"),
            "res_model": "account.analytic.line",
            "view_mode": "list,form,kanban",
            "views": [
                (list_view.id, "list"),
                (kanban_view.id, "kanban"),
                (form_view.id, "form"),
            ],
            "domain": [("task_id", "=", self.id), ("project_id", "!=", False)],
            "context": {
                "fsm_mode": True,
                "default_project_id": self.project_id.id,
                "default_task_id": self.id,
            },
        }

    def _get_action_fsm_task_mobile_view(self):
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "industry_fsm.project_task_action_fsm"
        )
        mobile_form_view = self.env.ref(
            "industry_fsm.project_task_view_mobile_form", raise_if_not_found=False
        )
        if mobile_form_view:
            action["views"] = [(mobile_form_view.id, "form")]
        context = action.get("context", {})
        context = context.replace("uid", str(self.env.uid))
        context = dict(
            self.env["ir.actions.actions"]._eval_action_context(context),
            active_test=True,
        )
        fsm_project_count = self.env["project.project"].search_count(
            [("is_fsm", "=", True)], limit=2
        )
        context.update(
            industry_fsm_one_project=fsm_project_count == 1,
            industry_fsm_hide_user_ids=bool(self.user_ids)
            and self.env.user not in self.user_ids,
        )
        action["context"] = context
        action["view_mode"] = "form"
        action["res_id"] = self.id
        return action

    def action_fsm_validate(self, stop_running_timers=False):
        Timer = self.env["timer.timer"]
        running_timers = Timer.search(
            [
                ("parent_res_model", "=", "project.task"),
                ("parent_res_id", "in", self.ids),
            ]
        )
        if running_timers:
            if stop_running_timers:
                self._stop_all_timers_and_update_timesheets(running_timers)
            else:
                wizard = self.env["wizard.project.task.validate.running.timer"].create(
                    {
                        "line_ids": [
                            Command.create({"task_id": task.id}) for task in self
                        ],
                    }
                )
                return {
                    "name": self.env._("Do you want to stop the running timers?"),
                    "type": "ir.actions.act_window",
                    "view_mode": "form",
                    "view_id": self.env.ref(
                        "industry_fsm.view_task_stop_timer_wizard_form"
                    ).id,
                    "target": "new",
                    "res_model": "wizard.project.task.validate.running.timer",
                    "res_id": wizard.id,
                }

        self.write({"fsm_done": True, "state": "done"})

        return True

    @api.model
    def _stop_all_timers_and_update_timesheets(self, running_timers):
        ConfigParameter = self.env["ir.config_parameter"].sudo()
        Timesheet = self.env["account.analytic.line"]

        if not running_timers:
            return Timesheet
        if any(
            timer.res_model != "account.analytic.line"
            or (timer.parent_res_model and timer.parent_res_model != "project.task")
            for timer in running_timers
        ):
            raise UserError(
                self.env._(
                    "All running timers should be linked to a timesheet and a task."
                )
            )

        result = Timesheet
        minimum_duration = int(
            ConfigParameter.get_param("timesheet_grid.timesheet_min_duration", 0)
        )
        rounding = int(
            ConfigParameter.get_param("timesheet_grid.timesheet_rounding", 0)
        )
        if running_timers:
            timesheets = (
                self.env["account.analytic.line"]
                .sudo()
                .search([("id", "in", running_timers.mapped("res_id"))])
            )
            timesheets_dict = {timesheet.id: timesheet for timesheet in timesheets}
            for timer in running_timers:
                timesheet = timesheets_dict[timer.res_id]
                minutes_spent = timer._get_minutes_spent()
                timesheet.write(
                    {
                        "unit_amount": round_time_spent(
                            minutes_spent, minimum_duration, rounding
                        )
                        / 60
                    }
                )
                result += timesheet
            running_timers.sudo().unlink()

        return result

    def action_fsm_navigate(self):
        if not self.partner_id.city or not self.partner_id.country_id:
            return {
                "name": self.env._("Customer"),
                "type": "ir.actions.act_window",
                "res_model": "res.partner",
                "res_id": self.partner_id.id,
                "view_mode": "form",
                "view_id": self.env.ref(
                    "industry_fsm.view_partner_address_form_industry_fsm"
                ).id,
                "target": "new",
            }
        return self.partner_id.action_partner_navigate()

    def web_read(self, specification: dict[str, dict]) -> list[dict]:
        if (
            len(self) == 1
            and "partner_id" in specification
            and "show_address_if_fsm" in specification["partner_id"].get("context", {})
        ):
            specification["partner_id"]["context"]["show_address"] = self.is_fsm
        return super().web_read(specification)

    def _server_action_project_task_fsm(
        self,
        xml_id_multiple_fsm_projects,
        xml_id_one_fsm_project,
        default_user_ids=False,
    ):
        project_ids = self.env["project.project"].search(
            [("is_fsm", "=", True)], limit=2
        )
        if len(project_ids) <= 1:
            action_id = xml_id_one_fsm_project
            project_id = project_ids.id
        else:
            action_id = xml_id_multiple_fsm_projects
            project_id = False
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(action_id)
        context = self.env["ir.actions.actions"]._eval_action_context(
            action.get("context", "{}")
        )
        allow_timesheets = any(project.allow_timesheets for project in project_ids)
        if project_id:
            context["default_project_id"] = project_id
        return {
            **action,
            "context": {
                **context,
                "default_user_ids": default_user_ids,
                "allow_timesheets": allow_timesheets,
            },
            "domain": Domain.AND(
                [
                    literal_eval(action.get("domain", [])),
                    [("has_template_ancestor", "=", False)],
                ]
            ),
        }


    def _compute_display_send_report_buttons(self) -> None:
        self.display_send_report_primary = False
        self.display_send_report_secondary = False

    def _compute_display_sign_report_buttons(self) -> None:
        self.display_sign_report_primary = False
        self.display_sign_report_secondary = False

    def _compute_show_customer_preview(self) -> None:
        for task in self:
            task.show_customer_preview = task.fsm_is_sent or task.worksheet_signature

    def _has_to_be_signed(self) -> bool:
        self.check_singleton()
        return bool(self._is_fsm_report_available() and not self.worksheet_signature)

    def _is_fsm_report_available(self) -> bool:
        self.check_singleton()
        return bool(self.timesheet_ids)

    def _get_send_report_action(self) -> dict:
        template_id = self.env.ref("industry_fsm.mail_template_data_task_report").id
        self.message_subscribe(partner_ids=self.partner_id.ids)
        return {
            "name": self.env._("Send Field Service Report"),
            "type": "ir.actions.act_window",
            "res_model": "wizard.mail.message.send",
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_composition_mode": "mass_mail"
                if len(self.ids) > 1
                else "comment",
                "default_model": "project.task",
                "default_res_ids": self.ids,
                "default_template_id": template_id,
                "fsm_mark_as_sent": True,
            },
        }

    def action_send_report(self):
        tasks_with_report = self.filtered(lambda task: task._is_fsm_report_available())
        if not tasks_with_report:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "message": self.env._("There are no reports to send."),
                    "sticky": False,
                    "type": "danger",
                },
            }
        action = tasks_with_report._get_send_report_action()
        if (
            not self.env.context.get("discard_logo_check")
            and self.env.is_admin()
            and not self.env.company.report_config_id.external_report_layout_id
        ):
            layout_action = self.env[
                "ir.actions.report"
            ]._prepare_layout_configurator_action(action)
            action.pop("close_on_report_download", None)
            return layout_action
        return action

    def action_preview_worksheet(self) -> dict:
        self.check_singleton()
        source = "fsm" if self.env.context.get("fsm_mode", False) else "project"
        return {
            "type": "ir.actions.act_url",
            "target": "self",
            "url": self.get_portal_url(query_string=f"&source={source}"),
        }

    def _message_post_after_hook(self, message, msg_vals):
        if self.env.context.get("fsm_mark_as_sent") and not self.fsm_is_sent:
            self.fsm_is_sent = True
        return super()._message_post_after_hook(message, msg_vals)


    def _get_domain_projects_to_make_billable(self, additional_domain=None):
        return Domain.AND(
            [
                super()._get_domain_projects_to_make_billable(additional_domain),
                [("is_fsm", "=", False)],
            ]
        )

    def _planned_hours_per_user_for_scale(self, users, start, stop):
        fsm_tasks = self.filtered("is_fsm")
        planned_hours_mapped = super(
            ProjectTask, self - fsm_tasks
        )._planned_hours_per_user_for_scale(users, start, stop)
        if not fsm_tasks:
            return planned_hours_mapped
        users_work_intervals, _dummy = users.sudo()._get_valid_work_intervals(
            start, stop
        )
        for task in fsm_tasks:
            max_start = max(start, task.date_start.replace(tzinfo=UTC))
            min_end = min(stop, task.date_end.replace(tzinfo=UTC))
            interval = Intervals(
                [(max_start, min_end, self.env["resource.calendar.attendance"])]
            )
            duration = (
                (task.date_end - task.date_start).total_seconds() / 3600.0
                if task.date_start and task.date_end
                else 0.0
            )
            nb_hours_per_user = (
                (get_intervals_hours(interval) / (len(task.user_ids) or 1))
                if duration < 24
                else 0.0
            )
            for user in task.user_ids:
                if duration < 24:
                    planned_hours_mapped[user.id] += nb_hours_per_user
                else:
                    work_intervals = interval & users_work_intervals[user.id]
                    planned_hours_mapped[user.id] += get_intervals_hours(work_intervals)
        return planned_hours_mapped

    def action_view_overlapping_tasks(self):
        action = super().action_view_overlapping_tasks()
        if self.is_fsm:
            action["context"]["fsm_mode"] = True
            action["domain"] = Domain.AND(
                [
                    action["domain"],
                    [("is_fsm", "=", True)],
                ]
            )
        return action

    def _prepare_domains_for_all_deadlines(self, date_start, date_end):
        domain = super()._prepare_domains_for_all_deadlines(date_start, date_end)
        if self.env.context.get("fsm_mode"):
            domain["project"] = Domain.AND([domain["project"], [("is_fsm", "=", True)]])
            domain["milestone"] = Domain.AND(
                [domain["milestone"], [("project_id.is_fsm", "=", True)]]
            )
        return domain

    def _get_report_base_filename(self):
        self.check_singleton()
        return "Field Service Report %s - %s" % (self.name, self.partner_id.name)
