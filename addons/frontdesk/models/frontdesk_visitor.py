from datetime import UTC, timedelta

from markupsafe import Markup

from odoo import SUPERUSER_ID, api, fields, models
from odoo.libs.web import urljoin as url_join
from odoo.tools import frozendict


class FrontdeskVisitor(models.Model):
    _name = "frontdesk.visitor"
    _description = "Frontdesk Visitors"
    _inherit = ["mixin.mail.thread"]
    _order = "check_in"
    _access_anchors = frozendict(
        {
            "company": "station_id.company_id",
            "owner": "station_id.responsible_ids",
        }
    )

    active = fields.Boolean(default=True)
    name = fields.Char(required=True)
    phone_ids = fields.Many2many(
        comodel_name="phone.number",
        relation="frontdesk_visitor_phone_number_rel",
        column1="visitor_id",
        column2="phone_number_id",
        copy=False,
    )
    email = fields.Char()
    company = fields.Char(string="Visitor Company")
    message = fields.Html()
    host_ids = fields.Many2many(
        comodel_name="hr.employee",
        string="Host Name",
        domain="[('company_id', '=', company_id), '|', ('work_email', '!=', False), ('phone_ids', '!=', False)]",
    )
    drink_ids = fields.Many2many(
        comodel_name="frontdesk.drink",
        string="Drinks",
    )
    check_in = fields.Datetime()
    check_out = fields.Datetime()
    duration = fields.Float(
        compute="_compute_duration",
        default=1.0,
        store=True,
    )
    state = fields.Selection(
        selection=[
            ("planned", "Planned"),
            ("checked_in", "Checked-In"),
            ("checked_out", "Checked-Out"),
            ("canceled", "Cancelled"),
        ],
        string="Status",
        default="planned",
        tracking=True,
    )
    station_id = fields.Many2one(
        comodel_name="frontdesk.frontdesk",
        index=True,
        required=True,
    )
    visitor_properties = fields.Properties(
        definition="station_id.visitor_properties_definition",
        string="Properties",
        copy=True,
    )
    served = fields.Boolean(string="Drink Served")
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        res._check_and_notify_visitor()
        return res

    def write(self, vals):
        if vals.get("state") == "checked_in":
            vals["check_in"] = fields.Datetime.now()
            self._notify()
            if self.drink_ids:
                self._notify_to_people()
        elif vals.get("state") == "checked_out":
            vals["check_out"] = fields.Datetime.now()
            vals["served"] = True
        return super().write(vals)

    @api.depends("check_in", "check_out")
    def _compute_duration(self):
        for visitor in self:
            if visitor.check_in and visitor.check_out:
                visitor.duration = (
                    visitor.check_out - visitor.check_in
                ).total_seconds() / 3600

    def action_check_in(self) -> None:
        self.check_singleton()
        self.state = "checked_in"

    def action_canceled(self) -> None:
        self.check_singleton()
        self.state = "canceled"

    def action_planned(self) -> None:
        self.check_singleton()
        self.state = "planned"

    def action_check_out(self) -> None:
        self.check_singleton()
        self.state = "checked_out"

    def action_served(self) -> None:
        self.check_singleton()
        self.served = True

    def _notify(self):
        for visitor in self:
            msg = ""
            visitor_name = visitor.name
            visitor_name += (
                f" ({visitor._phone_get_number().number})" if visitor.phone_ids else ""
            )
            visitor_name += f" ({visitor.company})" if visitor.company else ""
            if visitor.station_id.responsible_ids:
                if visitor.host_ids:
                    host_info = ", ".join([f"{host.name}" for host in visitor.host_ids])
                    msg = self.env._(
                        "%(station)s Check-In: %(visitor)s to meet %(host)s",
                        station=visitor.station_id.name,
                        visitor=visitor_name,
                        host=host_info,
                    )
                else:
                    msg = self.env._(
                        "%(station)s Check-In: %(visitor)s",
                        station=visitor.station_id.name,
                        visitor=visitor_name,
                    )
                visitor._notify_by_discuss(visitor.station_id.responsible_ids, msg)
            if visitor.station_id.host_selection and visitor.host_ids:
                if visitor.station_id.notify_discuss:
                    msg = self.env._("%s just checked-in.", visitor_name)
                    for host in visitor.host_ids:
                        if host.user_id:
                            visitor._notify_by_discuss([host], msg, True)
                        elif not visitor.station_id.notify_email and host.work_email:
                            visitor._notify_by_email()
                        elif not visitor.station_id.notify_sms and host.phone_ids:
                            visitor._notify_by_sms()
                if visitor.station_id.notify_email:
                    visitor._notify_by_email()
                if visitor.station_id.notify_sms:
                    visitor._notify_by_sms()

    def _notify_to_people(self) -> None:
        for visitor in self:
            if visitor.drink_ids.notify_user_ids:
                action = visitor.env.ref("frontdesk.action_frontdesk_visitor").id
                name = f"{self.name} ({self.company})" if self.company else self.name
                msg = self.env._(
                    "%(name)s just checked-in. Requested Drink: %(drink)s.",
                    name=Markup('<a href="%s">%s</a>')
                    % (
                        url_join(
                            self.env["frontdesk.visitor"].get_base_url(),
                            f"/odoo/action-{action}/{visitor.id}",
                        ),
                        name,
                    ),
                    drink=", ".join(drink.name for drink in visitor.drink_ids),
                )
                visitor._notify_by_discuss(visitor.drink_ids.notify_user_ids, msg)

    def _notify_by_discuss(self, recipients, msg, is_host=False) -> None:
        for recipient in recipients:
            if is_host and (not recipient.user_id or not recipient.user_id.partner_id):
                continue
            odoobot_id = self.env.ref("base.partner_root").id
            partners_to = [recipient.partner_id.id]
            channel = (
                self.env["discuss.channel"]
                .with_user(SUPERUSER_ID)
                ._get_or_create_chat(partners_to)
            )
            channel.message_post(
                body=msg,
                author_id=odoobot_id,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )

    def _notify_by_email(self) -> None:
        for host in self.host_ids:
            if host.work_email:
                odoobot = self.env.ref("base.partner_root")
                values = {"host_name": host.name, "object": self}
                body = self.env["ir.qweb"]._render(
                    "frontdesk.frontdesk_mail_template",
                    values,
                    lang=host.partner_id.lang,
                )
                self.message_post(
                    email_from=odoobot.email_formatted,
                    author_id=self.env.user.partner_id.id,
                    body=body,
                    subject=self.env._(
                        "Your Visitor %(name)s Requested To Meet You", name=self.name
                    ),
                    partner_ids=host.partner_id.ids,
                    message_type="email",
                    subtype_xmlid="mail.mt_comment",
                    email_layout_xmlid="mail.mail_notification_light",
                    force_send=True,
                )

    def _notify_by_sms(self) -> None:
        self.check_singleton()
        self._message_sms_with_template(
            template=self.station_id.sms_template_id,
            partner_ids=self.host_ids.filtered("phone_ids").partner_id.ids,
        )

    def _get_host_name(self) -> str:
        return ", ".join(self.host_ids.mapped("name"))

    def _check_resources_leave(self, resources, check_in) -> list:
        if not resources or not check_in:
            return []
        start = check_in.replace(tzinfo=UTC)
        stop = start + timedelta(minutes=1)
        calendar = self.env.company.resource_calendar_id
        leaves = calendar._leave_intervals_batch(start, stop, resources=resources)
        return [resource.id for resource in resources if leaves[resource.id]._items]

    def _check_and_notify_visitor(self) -> None:
        resources = [host.resource_id for host in self.host_ids]
        odoobot = self.env.ref("base.partner_root")
        author = self.station_id.company_id.partner_id
        for visitor in self:
            resources_on_leave = self._check_resources_leave(
                resources, visitor.check_in
            )
            hosts_on_leave = visitor.host_ids.filtered_domain(
                [("resource_id", "in", resources_on_leave)]
            )
            if hosts_on_leave:
                body = Markup(
                    """<div>
                        <p>%(greeting)s</p>
                        <p>%(message)s</p>
                        <ul>
                            %(host_details)s
                        </ul>
                        <p>%(footer_contact)s</p>
                        <p>%(footer)s</p>
                    </div>"""
                ) % {
                    "greeting": self.env._(
                        "Dear %(visitor_name)s,", visitor_name=visitor.name
                    ),
                    "message": self.env._(
                        "We regret to inform you that the following %(host_status)s currently unavailable:",
                        host_status=self.env._("host is")
                        if len(hosts_on_leave) == 1
                        else self.env._("hosts are"),
                    ),
                    "host_details": Markup().join(
                        Markup(
                            "<li><strong>%(host_name)s</strong>%(manager_info)s</li>"
                        )
                        % {
                            "host_name": host.name,
                            "manager_info": self.env._(
                                " - Manager: %(manager_name)s",
                                manager_name=host.parent_id.name,
                            )
                            if host.parent_id
                            else "",
                        }
                        for host in hosts_on_leave
                    ),
                    "footer_contact": self.env._(
                        "You can contact the host's manager or frontdesk responsible for further assistance."
                    ),
                    "footer": self.env._("Thanks for your understanding."),
                }
                if visitor.email and visitor.station_id.ask_email in [
                    "required",
                    "optional",
                ]:
                    visitor.message_post(
                        body=body,
                        subject=self.env._("Your host isn't available"),
                        author_id=author.id,
                        message_type="comment",
                        subtype_xmlid="mail.mt_comment",
                    )
                if visitor.phone_ids and visitor.station_id.ask_phone in [
                    "required",
                    "optional",
                ]:
                    visitor._message_sms(
                        author_id=odoobot.id,
                        body=body,
                        sms_numbers=[visitor._phone_get_number().number],
                    )
