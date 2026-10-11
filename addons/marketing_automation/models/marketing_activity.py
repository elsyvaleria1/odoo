import logging
from ast import literal_eval
from collections import defaultdict
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain
from odoo.libs.json import dumps as json_dumps
from odoo.tools import format_date
from odoo.tools.date_utils import time_unit_selection
from odoo.tools.misc import clean_context

_logger = logging.getLogger(__name__)

NODE_FIELDS = {
    "name",
    "campaign_id",
    "trigger_type",
    "parent_id",
    "interval_number",
    "interval_type",
    "validity_duration",
    "validity_duration_number",
    "validity_duration_type",
}


class MarketingActivity(models.Model):
    _name = "marketing.activity"
    _description = "Marketing Activity"
    _inherit = ["mixin.utm.source"]
    _order = "interval_standardized, id ASC"

    activity_type = fields.Selection(
        selection=[("email", "Email"), ("action", "Server Action")],
        default="email",
        required=True,
    )
    mass_mailing_id = fields.Many2one(
        comodel_name="mailing.mailing",
        string="Marketing Template",
        compute="_compute_mass_mailing_id",
        store=True,
        index="btree_not_null",
        readonly=False,
    )
    mass_mailing_id_mailing_type = fields.Selection(
        selection=[("mail", "Email")],
        string="Mailing Type",
        compute="_compute_mass_mailing_id_mailing_type",
        store=True,
        readonly=True,
    )
    server_action_id = fields.Many2one(
        comodel_name="ir.actions.server",
        compute="_compute_server_action_id",
        store=True,
        readonly=False,
    )
    campaign_id = fields.Many2one(
        comodel_name="marketing.campaign",
        index=True,
        required=True,
        ondelete="cascade",
    )
    node_id = fields.Many2one(
        comodel_name="ir.actions.server",
        string="Workflow Step",
        index="btree_not_null",
        copy=False,
        readonly=True,
        ondelete="restrict",
    )
    utm_campaign_id = fields.Many2one(
        comodel_name="utm.campaign",
        related="campaign_id.utm_campaign_id",
        string="UTM Campaign",
        readonly=True,
    )
    interval_number = fields.Integer(
        string="Send after",
        default=0,
    )
    interval_type = fields.Selection(
        selection=time_unit_selection("hour", "day", "week", "month"),
        string="Delay Type",
        default="hour",
        required=True,
    )
    interval_standardized = fields.Integer(
        string="Send after (in hours)",
        compute="_compute_interval_standardized",
        store=True,
        readonly=True,
    )
    validity_duration = fields.Boolean(
        help="Check this to make sure your actions are not executed after a specific amount of time after the scheduled date. (e.g. Time-limited offer, Upcoming event, …)"
    )
    validity_duration_number = fields.Integer(
        string="Valid during",
        default=0,
    )
    validity_duration_type = fields.Selection(
        selection=time_unit_selection("hour", "day", "week", "month"),
        default="hour",
        required=True,
    )
    domain = fields.Char(
        string="Applied Filter",
        compute="_compute_inherited_domain",
        recursive=True,
        store=True,
        readonly=True,
        help="Activity will only be performed if record satisfies this domain, obtained from the combination of the activity filter and its inherited filter",
    )
    activity_domain = fields.Char(
        string="Activity Filter",
        default="[]",
        help="Domain that applies to this activity and its child activities",
    )
    model_id = fields.Many2one(
        comodel_name="ir.model",
        related="campaign_id.model_id",
        string="Model",
        readonly=True,
    )
    model_name = fields.Char(
        related="model_id.model",
        string="Model Name",
        readonly=True,
    )
    parent_id = fields.Many2one(
        comodel_name="marketing.activity",
        string="Activity",
        compute="_compute_parent_id",
        store=True,
        index=True,
        readonly=False,
        ondelete="cascade",
    )
    allowed_parent_ids = fields.Many2many(
        comodel_name="marketing.activity",
        string="Allowed parents",
        compute="_compute_allowed_parent_ids",
        help="All activities which can be the parent of this one",
    )
    child_ids = fields.One2many(
        comodel_name="marketing.activity",
        inverse_name="parent_id",
        string="Child Activities",
    )
    trigger_type = fields.Selection(
        selection=[
            ("begin", "beginning of workflow"),
            ("activity", "another activity"),
            ("mail_open", "Mail: opened"),
            ("mail_not_open", "Mail: not opened"),
            ("mail_reply", "Mail: replied"),
            ("mail_not_reply", "Mail: not replied"),
            ("mail_click", "Mail: clicked"),
            ("mail_not_click", "Mail: not clicked"),
            ("mail_bounce", "Mail: bounced"),
        ],
        default="begin",
        required=True,
    )
    trigger_category = fields.Selection(
        selection=[("email", "Mail")],
        compute="_compute_trigger_category",
    )
    require_sync = fields.Boolean(
        string="Require trace sync",
        copy=False,
    )
    trace_ids = fields.One2many(
        comodel_name="marketing.trace",
        inverse_name="activity_id",
        string="Traces",
        copy=False,
    )
    processed = fields.Integer(compute="_compute_statistics")
    rejected = fields.Integer(compute="_compute_statistics")
    total_sent = fields.Integer(compute="_compute_statistics")
    total_click = fields.Integer(compute="_compute_statistics")
    total_open = fields.Integer(compute="_compute_statistics")
    total_reply = fields.Integer(compute="_compute_statistics")
    total_bounce = fields.Integer(compute="_compute_statistics")
    statistics_graph_data = fields.Char(compute="_compute_statistics_graph_data")
    activity_summary = fields.Html(compute="_compute_activity_summary")

    @api.constrains("trigger_type", "parent_id")
    def _check_consistency_in_activities(self) -> None:
        for activity in self:
            if (
                activity.parent_id or activity.allowed_parent_ids
            ) and activity.parent_id not in activity.allowed_parent_ids:
                trigger_string = dict(
                    activity._fields["trigger_type"]._description_selection(self.env)
                )[activity.trigger_type]
                raise ValidationError(
                    self.env._(
                        'You are trying to set the activity "%(parent_activity)s" as "%(parent_type)s" while its child "%(activity)s" has the trigger type "%(trigger_type)s"\nPlease modify one of those activities before saving.',
                        parent_activity=activity.parent_id.name,
                        parent_type=activity.parent_id.activity_type,
                        activity=activity.name,
                        trigger_type=trigger_string,
                    )
                )

    @api.depends("activity_type")
    def _compute_mass_mailing_id_mailing_type(self) -> None:
        for activity in self:
            if activity.activity_type == "email":
                activity.mass_mailing_id_mailing_type = "mail"
            elif activity.activity_type == "action":
                activity.mass_mailing_id_mailing_type = False

    @api.depends("mass_mailing_id_mailing_type")
    def _compute_mass_mailing_id(self) -> None:
        for activity in self:
            if (
                activity.mass_mailing_id_mailing_type
                != activity.mass_mailing_id.mailing_type
            ):
                activity.mass_mailing_id = False

    @api.depends("activity_type")
    def _compute_server_action_id(self) -> None:
        for activity in self:
            if activity.activity_type != "action":
                activity.server_action_id = False

    @api.depends("activity_domain", "campaign_id.domain", "parent_id.domain")
    def _compute_inherited_domain(self) -> None:
        for activity in self:
            domain = Domain.AND(
                [
                    literal_eval(activity.activity_domain or "[]"),
                    literal_eval(activity.campaign_id.domain or "[]"),
                ]
            )
            ancestor = activity.parent_id
            while ancestor:
                domain &= Domain(literal_eval(ancestor.activity_domain or "[]"))
                ancestor = ancestor.parent_id
            activity.domain = domain

    @api.depends("interval_type", "interval_number")
    def _compute_interval_standardized(self) -> None:
        factors = {"hour": 1, "day": 24, "week": 168, "month": 720}
        for activity in self:
            activity.interval_standardized = (
                (activity.interval_number * factors[activity.interval_type])
                if activity.interval_type
                else 0
            )

    @api.depends("trigger_type")
    def _compute_parent_id(self) -> None:
        for activity in self:
            if not activity.parent_id or (
                activity.parent_id and activity.trigger_type == "begin"
            ):
                activity.parent_id = False

    @api.depends("trigger_type", "campaign_id.marketing_activity_ids")
    def _compute_allowed_parent_ids(self) -> None:
        for activity in self:
            if activity.trigger_type == "activity":
                activity.allowed_parent_ids = activity._get_sibling_activities()
            elif activity.trigger_category:
                activity.allowed_parent_ids = activity._get_sibling_activities(
                    activity.trigger_category
                )
            else:
                activity.allowed_parent_ids = False

    def _get_sibling_activities(self, activity_type=None):
        self.check_singleton()
        siblings = self.campaign_id.marketing_activity_ids.filtered(
            lambda activity: activity.ids != self.ids
        )
        if activity_type:
            return siblings.filtered(
                lambda activity: activity.activity_type == activity_type
            )
        return siblings

    @api.depends("trigger_type")
    def _compute_trigger_category(self) -> None:
        for activity in self:
            if activity.trigger_type in [
                "mail_open",
                "mail_not_open",
                "mail_reply",
                "mail_not_reply",
                "mail_click",
                "mail_not_click",
                "mail_bounce",
            ]:
                activity.trigger_category = "email"
            else:
                activity.trigger_category = False

    @api.depends("activity_type", "trace_ids")
    def _compute_statistics(self) -> None:
        self.update(
            {
                "total_bounce": 0,
                "total_reply": 0,
                "total_sent": 0,
                "rejected": 0,
                "total_click": 0,
                "processed": 0,
                "total_open": 0,
            }
        )
        if self.ids:
            activity_data = {activity._origin.id: {} for activity in self}
            for stat in self._get_full_statistics():
                activity_data[stat.pop("activity_id")].update(stat)
            for activity in self:
                activity.update(activity_data[activity._origin.id])

    @api.depends("activity_type", "trace_ids")
    def _compute_statistics_graph_data(self) -> None:
        if not self.ids:
            date_range = [date.today() - timedelta(days=d) for d in range(15)]
            date_range.reverse()
            default_values = [
                {"x": format_date(self.env, date_item, date_format="dd MMM"), "y": 0}
                for date_item in date_range
            ]
            self.statistics_graph_data = json_dumps(
                [
                    {
                        "points": default_values,
                        "label": self.env._("Success"),
                        "color": "#28A745",
                    },
                    {
                        "points": default_values,
                        "label": self.env._("Rejected"),
                        "color": "#D23f3A",
                    },
                ]
            )
        else:
            activity_data = {activity._origin.id: {} for activity in self}
            for act_id, graph_data in self._get_graph_statistics().items():
                activity_data[act_id]["statistics_graph_data"] = json_dumps(graph_data)
            for activity in self:
                activity.update(activity_data[activity._origin.id])

    def _get_activity_summary_dependencies(self):
        return [
            "activity_type",
            "mass_mailing_id",
            "server_action_id",
            "interval_number",
            "interval_type",
            "trigger_type",
            "parent_id",
            "validity_duration",
            "validity_duration_number",
            "validity_duration_type",
        ]

    @api.depends(lambda self: self._get_activity_summary_dependencies())
    def _compute_activity_summary(self) -> None:
        for activity in self:
            if not activity.interval_type or not activity.validity_duration_type:
                activity.activity_summary = ""
                continue
            activity.activity_summary = self.env["ir.qweb"]._render(
                "marketing_automation.marketing_activity_summary_template",
                {
                    "activity": activity,
                    "parent_activity_name": activity.parent_id.name,
                    "activity_type_label": dict(
                        activity._fields["activity_type"]._description_selection(
                            self.env
                        )
                    )[activity.activity_type],
                    "interval_type_label": dict(
                        activity._fields["interval_type"]._description_selection(
                            self.env
                        )
                    )[activity.interval_type],
                    "validity_duration_type_label": dict(
                        activity._fields[
                            "validity_duration_type"
                        ]._description_selection(self.env)
                    )[activity.validity_duration_type],
                },
            )

    @api.constrains("parent_id")
    def _check_parent_id(self) -> None:
        if self._has_cycle():
            raise ValidationError(
                self.env._("Error! You can't create recursive hierarchy of Activity.")
            )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            campaign_id = values.get("campaign_id")
            if not campaign_id:
                campaign_id = self.default_get(["campaign_id"])["campaign_id"]
            values["require_sync"] = (
                self.env["marketing.campaign"].browse(campaign_id).state == "running"
            )
        activities = super().create(vals_list)
        activities._sync_nodes()
        for activity in activities.filtered("parent_id"):
            activity.campaign_id.participant_ids.filtered(
                lambda participant: participant.state != "unlinked"
            ).runtime_id.sudo()._add_steps(activity.node_id.sudo())
        return activities

    def copy_data(self, default=None):
        default = dict(default or {})
        if self.mass_mailing_id:
            default["mass_mailing_id"] = self.mass_mailing_id.copy().id
        return super().copy_data(default=default)

    def write(self, vals):
        if any(activity.campaign_id.state == "running" for activity in self) and any(
            field in vals for field in ("interval_number", "interval_type")
        ):
            vals["require_sync"] = True
        if "campaign_id" in vals:
            nodes = self._with_descendants().node_id.sudo()
            (nodes.edge_in_ids | nodes.edge_out_ids).unlink()
        res = super().write(vals)
        if set(vals) & NODE_FIELDS:
            self._with_descendants()._sync_nodes()
        return res

    def unlink(self):
        activities = self._with_descendants()
        nodes = activities.node_id.sudo()
        self.env["automation.runtime.line"].sudo().search(
            [("action_id", "in", nodes.ids)]
        ).unlink()
        res = super().unlink()
        nodes.exists().unlink()
        return res

    def _with_descendants(self):
        activities = self
        while descendants := activities.child_ids - activities:
            activities |= descendants
        return activities


    def _sync_nodes(self) -> None:
        Node = self.env["ir.actions.server"].sudo()
        for activity in self:
            vals = activity._prepare_node_vals()
            if activity.node_id:
                activity.node_id.sudo().write(vals)
            else:
                activity.node_id = Node.create(vals)
        self._sync_edges()

    def _prepare_node_vals(self) -> dict:
        self.check_singleton()
        campaign = self.campaign_id
        return {
            "name": self.name,
            "model_id": campaign.model_id.id,
            "automation_rule_id": campaign.automation_rule_id.id,
            "usage": "automation",
            "start_delay": self.interval_number if self.trigger_type == "begin" else 0,
            "start_delay_unit": self.interval_type,
            "validity_delay": (
                self.validity_duration_number if self.validity_duration else 0
            ),
            "validity_unit": self.validity_duration_type,
            "state": "code",
            "code": "",
        }

    def _get_workflow_subject(self):
        self.check_singleton()
        return (self.mass_mailing_id or self.server_action_id).display_name or ""

    def _sync_edges(self) -> None:
        Edge = self.env["workflow.edge"].sudo()
        for activity in self:
            incoming = activity.node_id.sudo().edge_in_ids
            vals = activity._prepare_edge_vals()
            if not vals:
                incoming.unlink()
                continue
            kept = incoming.filtered_domain(
                [("source_node_id", "=", vals["source_node_id"])]
            )
            (incoming - kept).unlink()
            if kept:
                kept.write(
                    {
                        key: value
                        for key, value in vals.items()
                        if key not in ("source_node_id", "target_node_id")
                    }
                )
            else:
                Edge.create(vals)

    def _prepare_edge_vals(self):
        self.check_singleton()
        if self.trigger_type == "begin" or not self.parent_id.node_id:
            return None
        vals = {
            "source_node_id": self.parent_id.node_id.id,
            "target_node_id": self.node_id.id,
            "condition": "always",
            "event_code": False,
            "delay": self.interval_number,
            "delay_unit": self.interval_type,
        }
        if self.trigger_type == "activity":
            return vals
        if "_not_" in self.trigger_type:
            vals.update(
                condition="no_event",
                event_code=self.trigger_type.replace("_not_", "_"),
            )
        else:
            vals.update(condition="event", event_code=self.trigger_type)
        return vals

    def _get_full_statistics(self):
        self.env["marketing.trace"].flush_model(
            ["activity_id", "participant_id", "state"]
        )
        self.env["mailing.trace"].flush_model(
            [
                "marketing_trace_id",
                "links_click_datetime",
                "sent_datetime",
                "trace_status",
            ]
        )
        self.env["marketing.participant"].flush_model(["is_test"])
        self.env.cr.execute(
            """
            SELECT
                trace.activity_id,
                COUNT(stat.sent_datetime) AS total_sent,
                COUNT(stat.links_click_datetime) AS total_click,
                COUNT(stat.trace_status) FILTER (WHERE stat.trace_status = 'reply') AS total_reply,
                COUNT(stat.trace_status) FILTER (WHERE stat.trace_status in ('open', 'reply')) AS total_open,
                COUNT(stat.trace_status) FILTER (WHERE stat.trace_status = 'bounce') AS total_bounce,
                COUNT(trace.state) FILTER (WHERE trace.state = 'processed') AS processed,
                COUNT(trace.state) FILTER (WHERE trace.state = 'rejected') AS rejected
            FROM
                marketing_trace AS trace
            LEFT JOIN
                mailing_trace AS stat
                ON (stat.marketing_trace_id = trace.id)
            JOIN
                marketing_participant AS part
                ON (trace.participant_id = part.id)
            WHERE
                (part.is_test = false or part.is_test IS NULL) AND
                trace.activity_id = ANY(%s)
            GROUP BY
                trace.activity_id;
        """,
            (list(self.ids),),
        )
        return self.env.cr.dictfetchall()

    def _get_graph_statistics(self):
        past_date = (self.env.cr.now() + timedelta(days=-14)).strftime(
            "%Y-%m-%d 00:00:00"
        )
        stat_map = {}
        base = date.today() + timedelta(days=-14)
        date_range = [base + timedelta(days=d) for d in range(15)]

        self.env["marketing.trace"].flush_model(
            ["activity_id", "participant_id", "schedule_date", "state"]
        )
        self.env["marketing.participant"].flush_model(["is_test"])
        self.env.cr.execute(
            """
            SELECT
                activity.id AS activity_id,
                trace.schedule_date::date AS dt,
                count(*) AS total,
                trace.state
            FROM
                marketing_trace AS trace
            JOIN
                marketing_activity AS activity
                ON (activity.id = trace.activity_id)
            JOIN
                marketing_participant AS participant
                ON (participant.id = trace.participant_id)
            WHERE
                activity.id = ANY(%s) AND
                trace.schedule_date >= %s AND
                (participant.is_test = false or participant.is_test IS NULL)
            GROUP BY activity.id , dt, trace.state
            ORDER BY dt;
        """,
            (list(self.ids), past_date),
        )

        for stat in self.env.cr.dictfetchall():
            stat_map[(stat["activity_id"], stat["dt"], stat["state"])] = stat["total"]
        graph_data = {}
        for activity in self:
            success = []
            rejected = []
            for i in date_range:
                x = format_date(self.env, i, date_format="dd MMM")
                success.append(
                    {
                        "x": x,
                        "y": stat_map.get((activity._origin.id, i, "processed"), 0),
                    }
                )
                rejected.append(
                    {"x": x, "y": stat_map.get((activity._origin.id, i, "rejected"), 0)}
                )
            graph_data[activity._origin.id] = [
                {"points": success, "label": self.env._("Success"), "color": "#28A745"},
                {
                    "points": rejected,
                    "label": self.env._("Rejected"),
                    "color": "#D23f3A",
                },
            ]
        return graph_data


    def execute(self, domain=None):
        rules = self.campaign_id.automation_rule_id.sudo()
        self.env["automation.runtime"].sudo()._dispatch_due_steps(rules=rules)

    def execute_on_traces(self, traces) -> None:
        self.check_singleton()
        traces.action_execute()

    def _execute_lines(self, lines) -> bool:
        self.check_singleton()
        lines = lines.sudo().filtered(lambda line: line.state == "ready")
        expired = lines.filtered(lambda line: line._is_expired())
        for line in expired:
            line._skip(
                reason="expired",
                message=self.env._("Not sent: the activity's validity had passed."),
            )
        lines -= expired
        traces = lines.marketing_trace_ids
        if not traces:
            return True

        rec_domain = literal_eval(self.domain or self.campaign_id.domain or "[]")
        user = self.campaign_id.user_id or self.env.user
        rec_valid_ids = set(
            self.env[self.model_name]
            .with_context(lang=user.lang)
            .search(Domain.AND([rec_domain, [("id", "in", traces.mapped("res_id"))]]))
            .ids
        )
        traces_rejected = traces.filtered(
            lambda trace: trace.res_id not in rec_valid_ids
        )
        traces_rejected._settle_line(
            "rejected",
            message=self.env._(
                "Rejected by activity filter or record deleted / archived"
            ),
            advance=False,
        )
        traces_allowed = traces - traces_rejected
        if traces_allowed:
            self._get_activity_executors()[self.activity_type](traces_allowed)
        return True

    def _get_activity_executors(self):
        return {"action": self._execute_action, "email": self._execute_email}

    def _execute_action(self, traces) -> bool:
        if not self.server_action_id:
            return False
        succeeded = self.env["marketing.trace"]
        failed = defaultdict(lambda: self.env["marketing.trace"])
        for trace in traces:
            action = self.server_action_id.with_context(
                active_model=self.model_name,
                active_ids=[trace.res_id],
                active_id=trace.res_id,
            )
            try:
                with self.env.cr.savepoint():
                    action.run()
            except PG_RETRY_EXCEPTIONS:
                raise
            except Exception as e:
                _logger.warning(
                    "Marketing Automation: activity <%s> encountered server action issue %s",
                    self.id,
                    e,
                    exc_info=True,
                )
                failed[self.env._("Exception in server action: %s", e)] |= trace
            else:
                succeeded |= trace
        succeeded._settle_line("processed", advance=False)
        for message, failed_traces in failed.items():
            failed_traces._settle_line("error", message=message, advance=False)
        return True

    def _execute_email(self, traces) -> bool:
        if not self.env.is_superuser() and not self.env.user.has_group(
            "marketing_automation.group_marketing_automation_user"
        ):
            raise AccessError(
                self.env._(
                    "To use this feature you should be an administrator or belong to the marketing automation group."
                )
            )

        res_ids = list(dict.fromkeys(traces.mapped("res_id")))
        ctx = dict(
            clean_context(self.env.context),
            default_marketing_activity_id=self.ids[0],
            marketing_trace_ids=traces.ids,
            active_ids=res_ids,
        )
        mailing = self.mass_mailing_id.sudo().with_context(ctx)

        try:
            mailing.action_send_mail(res_ids)
        except Exception as e:
            _logger.warning(
                "Marketing Automation: activity <%s> encountered mass mailing issue %s",
                self.id,
                e,
                exc_info=True,
            )
            traces._settle_line(
                "error",
                message=self.env._("Exception in mass mailing: %s", e),
                advance=False,
            )
            return True

        failed_stats = (
            self.env["mailing.trace"]
            .sudo()
            .search(
                [
                    ("marketing_trace_id", "in", traces.ids),
                    ("trace_status", "in", ["error", "bounce", "cancel"]),
                ]
            )
        )
        error_doc_ids = {
            stat.res_id
            for stat in failed_stats
            if stat.trace_status in ("error", "bounce")
        }
        cancel_doc_ids = {
            stat.res_id for stat in failed_stats if stat.trace_status == "cancel"
        }
        canceled = traces.filtered(lambda trace: trace.res_id in cancel_doc_ids)
        failed = traces.filtered(lambda trace: trace.res_id in error_doc_ids)
        canceled._settle_line(
            "canceled", message=self.env._("Email cancelled"), advance=False
        )
        failed._settle_line("error", message=self.env._("Email failed"), advance=False)
        (traces - canceled - failed)._settle_line("processed", advance=False)
        return True

    def action_view_sent(self):
        return self._action_view_documents_filtered("sent")

    def action_view_replied(self):
        return self._action_view_documents_filtered("reply")

    def action_view_clicked(self):
        return self._action_view_documents_filtered("click")

    def action_view_opened(self):
        return self._action_view_documents_filtered("open")

    def _action_view_documents_filtered(self, view_filter):
        if not self.mass_mailing_id:
            return False
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "marketing_automation.marketing_participants_action_mail"
        )

        if view_filter == "reply":
            found_traces = self.trace_ids.filtered(
                lambda trace: trace.mailing_trace_status == view_filter
            )
        elif view_filter == "open":
            found_traces = self.trace_ids.filtered(
                lambda trace: trace.mailing_trace_status in ("open", "reply")
            )
        elif view_filter == "sent":
            found_traces = self.trace_ids.filtered("mailing_trace_ids.sent_datetime")
        elif view_filter == "click":
            found_traces = self.trace_ids.filtered(
                "mailing_trace_ids.links_click_datetime"
            )
        else:
            found_traces = self.env["marketing.trace"]

        participants = found_traces.participant_id
        action.update(
            {
                "display_name": self.env._(
                    "Participants of %(activity)s (%(filter)s)",
                    activity=self.name,
                    filter=view_filter,
                ),
                "domain": [("id", "in", participants.ids)],
                "context": dict(self.env.context, create=False),
            }
        )
        return action
