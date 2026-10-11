from ast import literal_eval
from collections import defaultdict
from itertools import batched
from typing import Literal

from odoo import Command, api, fields, models, modules
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import convert


class MarketingCampaign(models.Model):
    _name = "marketing.campaign"
    _description = "Marketing Campaign"
    _inherits = {"utm.campaign": "utm_campaign_id"}
    _order = "create_date DESC"

    utm_campaign_id = fields.Many2one(
        comodel_name="utm.campaign",
        string="UTM Campaign",
        required=True,
        ondelete="restrict",
    )
    automation_rule_id = fields.Many2one(
        comodel_name="automation.rule",
        string="Workflow",
        index=True,
        copy=False,
        readonly=True,
        ondelete="restrict",
    )
    active = fields.Boolean(default=True)
    state = fields.Selection(
        selection=[("draft", "New"), ("running", "Running"), ("stopped", "Stopped")],
        default="draft",
        copy=False,
        group_expand=True,
    )
    model_id = fields.Many2one(
        comodel_name="ir.model",
        default=lambda self: self.env.ref(
            "base.model_res_partner", raise_if_not_found=False
        ),
        index=True,
        required=True,
        domain="['&', ('is_mail_thread', '=', True), ('model', '!=', 'mail.blacklist')]",
        ondelete="cascade",
    )
    model_name = fields.Char(
        related="model_id.model",
        string="Model Name",
        readonly=True,
    )
    unique_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        compute="_compute_unique_field_id",
        store=True,
        readonly=False,
        domain="[('model_id', '=', model_id), ('ttype', 'in', ['char', 'integer', 'many2one', 'text', 'selection'])]",
        help="""Used to avoid duplicates based on model field.\ne.g.
                For model 'Customers', select email field here if you don't
                want to process records which have the same email address""",
    )
    domain = fields.Char(
        string="Filter",
        compute="_compute_domain",
        store=True,
        readonly=False,
    )
    mailing_filter_id = fields.Many2one(
        comodel_name="mailing.filter",
        string="Favorite Filter",
        compute="_compute_mailing_filter_id",
        store=True,
        readonly=False,
        domain="[('mailing_model_name', '=', model_name)]",
    )
    mailing_filter_domain = fields.Char(
        related="mailing_filter_id.mailing_domain",
        string="Favorite filter domain",
    )
    mailing_filter_count = fields.Integer(
        string="# Favorite Filters",
        compute="_compute_mailing_filter_count",
    )
    marketing_activity_ids = fields.One2many(
        comodel_name="marketing.activity",
        inverse_name="campaign_id",
        string="Activities",
        copy=False,
    )
    mass_mailing_count = fields.Integer(
        string="# Mailings",
        compute="_compute_mass_mailing_count",
    )
    link_tracker_click_count = fields.Integer(
        string="# Clicks",
        compute="_compute_link_tracker_click_count",
    )
    last_sync_date = fields.Datetime(
        string="Last activities synchronization",
        copy=False,
    )
    require_sync = fields.Boolean(
        string="Sync of participants is required",
        compute="_compute_require_sync",
    )
    participant_ids = fields.One2many(
        comodel_name="marketing.participant",
        inverse_name="campaign_id",
        string="Participants",
        copy=False,
    )
    running_participant_count = fields.Integer(
        string="# of active participants",
        compute="_compute_participants",
    )
    completed_participant_count = fields.Integer(
        string="# of completed participants",
        compute="_compute_participants",
    )
    total_participant_count = fields.Integer(
        string="# of active and completed participants",
        compute="_compute_participants",
    )
    test_participant_count = fields.Integer(
        string="# of test participants",
        compute="_compute_participants",
    )

    @api.constrains("model_id", "mailing_filter_id")
    def _check_mailing_filter_model(self) -> None:
        for campaign in self:
            if (
                campaign.mailing_filter_id
                and campaign.model_id != campaign.mailing_filter_id.mailing_model_id
            ):
                raise ValidationError(
                    self.env._(
                        "The saved filter targets different model and is incompatible with this campaign."
                    )
                )

    @api.depends("model_id")
    def _compute_unique_field_id(self) -> None:
        for campaign in self:
            campaign.unique_field_id = False

    @api.depends("model_id", "mailing_filter_id")
    def _compute_domain(self) -> None:
        for campaign in self:
            if campaign.mailing_filter_id:
                campaign.domain = campaign.mailing_filter_id.mailing_domain
            else:
                campaign.domain = repr([])

    @api.depends("marketing_activity_ids.require_sync", "last_sync_date")
    def _compute_require_sync(self) -> None:
        for campaign in self:
            if campaign.last_sync_date and campaign.state == "running":
                activities_changed = campaign.marketing_activity_ids.filtered(
                    lambda activity: activity.require_sync
                )
                campaign.require_sync = bool(activities_changed)
            else:
                campaign.require_sync = False

    @api.depends("model_id", "domain")
    def _compute_mailing_filter_count(self) -> None:
        filter_data = self.env["mailing.filter"]._read_group(
            [("mailing_model_id", "in", self.model_id.ids)],
            ["mailing_model_id"],
            ["__count"],
        )
        mapped_data = {mailing_model.id: count for mailing_model, count in filter_data}
        for campaign in self:
            campaign.mailing_filter_count = mapped_data.get(campaign.model_id.id, 0)

    @api.depends("model_name")
    def _compute_mailing_filter_id(self) -> None:
        for mailing in self:
            mailing.mailing_filter_id = False

    @api.depends("marketing_activity_ids.mass_mailing_id")
    def _compute_mass_mailing_count(self) -> None:
        for campaign in self:
            campaign.mass_mailing_count = len(
                campaign.mapped("marketing_activity_ids.mass_mailing_id").filtered(
                    lambda mailing: mailing.mailing_type == "mail"
                )
            )

    @api.depends("utm_campaign_id")
    def _compute_link_tracker_click_count(self) -> None:
        click_data = (
            self.env["link.tracker.click"]
            .sudo()
            ._read_group(
                [("campaign_id", "in", self.utm_campaign_id.ids)],
                ["campaign_id"],
                ["__count"],
            )
        )
        mapped_data = {utm_campaign.id: count for utm_campaign, count in click_data}
        for campaign in self:
            campaign.link_tracker_click_count = mapped_data.get(
                campaign.utm_campaign_id.id, 0
            )

    @api.depends("participant_ids.state")
    def _compute_participants(self) -> None:
        participants_data = self.env["marketing.participant"]._read_group(
            [("campaign_id", "in", self.ids)],
            ["campaign_id", "state", "is_test"],
            ["__count"],
        )
        mapped_data = defaultdict(dict)
        for campaign, state, is_test, count in participants_data:
            if is_test:
                mapped_data[campaign.id]["is_test"] = (
                    mapped_data[campaign.id].get("is_test", 0) + count
                )
            else:
                mapped_data[campaign.id][state] = count
        for campaign in self:
            campaign_data = mapped_data[campaign.id]
            campaign.running_participant_count = campaign_data.get("running", 0)
            campaign.completed_participant_count = campaign_data.get("completed", 0)
            campaign.total_participant_count = (
                campaign.completed_participant_count
                + campaign.running_participant_count
            )
            campaign.test_participant_count = campaign_data.get("is_test", 0)

    def copy(self, default=None):
        new_compaigns = super().copy(dict(default or {}))

        for old_campaign, new_compaign in zip(self, new_compaigns, strict=False):
            old_to_new = {}

            pending = old_campaign.marketing_activity_ids
            while pending:
                ready = pending.filtered_domain([("parent_id", "not in", pending.ids)])
                for marketing_activity_id in ready:
                    old_to_new[marketing_activity_id] = marketing_activity_id.copy(
                        {
                            "campaign_id": new_compaign.id,
                            "parent_id": old_to_new.get(
                                marketing_activity_id.parent_id,
                                self.env["marketing.activity"],
                            ).id,
                            "require_sync": False,
                        }
                    )
                pending -= ready

        return new_compaigns

    @api.model_create_multi
    def create(self, vals_list):
        default_model = self.default_get(["model_id"]).get("model_id")
        rules = (
            self.env["automation.rule"]
            .sudo()
            .create(
                [
                    {
                        "name": vals.get("name") or self.env._("Marketing Campaign"),
                        "model_id": vals.get("model_id") or default_model,
                        "trigger": "on_hand",
                        "run_mode": "queued",
                        "step_error_policy": "close_branch",
                        "create_runtime_instance": True,
                        "active": vals.get("state") == "running",
                        "is_paused": vals.get("state") != "running",
                    }
                    for vals in vals_list
                ]
            )
        )
        for vals, rule in zip(vals_list, rules, strict=True):
            vals.update({"is_auto_campaign": True, "automation_rule_id": rule.id})
        return super().create(vals_list)

    def _prepare_rule_vals(self):
        self.check_singleton()
        return {
            "name": self.name,
            "model_id": self.model_id.id,
            "trigger": "on_hand",
            "run_mode": "queued",
            "step_error_policy": "close_branch",
            "create_runtime_instance": True,
            "active": self.state == "running",
            "is_paused": self.state != "running",
        }

    def unlink(self):
        rules = self.automation_rule_id.sudo()
        participants = self.with_context(active_test=False).participant_ids
        participants.unlink()
        self.with_context(active_test=False).marketing_activity_ids.unlink()
        res = super().unlink()
        rules.with_context(active_test=False).exists().unlink()
        return res

    @api.onchange("model_id")
    def _onchange_model_id(self) -> dict | None:
        if any(campaign.marketing_activity_ids for campaign in self):
            return {
                "warning": {
                    "title": self.env._("Warning"),
                    "message": self.env._(
                        "Switching Target Model invalidates the existing activities. "
                        "Either update your activity actions to match the new Target Model or delete them."
                    ),
                }
            }

        return None

    def write(self, vals):
        if not vals.get("active", True):
            vals["state"] = "stopped"
        res = super().write(vals)
        if {"name", "model_id", "state", "active"} & set(vals):
            for campaign in self:
                rule = campaign.automation_rule_id.sudo().with_context(
                    active_test=False
                )
                rule_vals = {}
                if rule.name != campaign.name:
                    rule_vals["name"] = campaign.name
                if rule.model_id != campaign.model_id:
                    rule_vals["model_id"] = campaign.model_id.id
                running = campaign.state == "running"
                if rule.active != running:
                    rule_vals["active"] = running
                if rule.is_paused == running:
                    rule_vals["is_paused"] = not running
                if rule_vals:
                    rule.write(rule_vals)
                if running and rule_vals.get("is_paused") is False:
                    self.env["automation.runtime"]._request_dispatch()
            if "model_id" in vals:
                self.marketing_activity_ids._sync_nodes()
        return res

    def action_set_synchronized(self) -> None:
        self.write({"last_sync_date": self.env.cr.now()})
        self.mapped("marketing_activity_ids").write({"require_sync": False})

    def action_update_participants(self) -> None:
        for campaign in self:
            participants = campaign.participant_ids.filtered(
                lambda participant: participant.state != "unlinked"
            )
            participants._launch()
            runtimes = participants.runtime_id.sudo()
            finished = runtimes.filtered(lambda run: run.state == "done")
            finished.state = "in_progress"
            runtimes._sync_to_definition()
            for runtime in finished.filtered(lambda run: run.state == "in_progress"):
                runtime._settle_idle()
        self.action_set_synchronized()

    def action_view_workflow(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "automation.rule",
            "res_id": self.automation_rule_id.id,
            "view_mode": "form",
            "views": [[False, "form"]],
            "target": "current",
        }

    def action_start_campaign(self) -> None:
        if any(not campaign.marketing_activity_ids for campaign in self):
            raise ValidationError(
                self.env._(
                    "You must set up at least one activity to start this campaign."
                )
            )

        self.env["ir.cron"]._trigger_ref(
            "marketing_automation.ir_cron_campaign_sync_participants",
            self.env.cr.now(),
        )
        self.write({"state": "running"})

    def action_stop_campaign(self) -> None:
        self.write({"state": "stopped"})

    def action_view_mailings(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "marketing_automation.mail_mass_mailing_action_marketing_automation"
        )
        action["domain"] = [
            "&",
            ("use_in_marketing_automation", "=", True),
            ("id", "in", self.mapped("marketing_activity_ids.mass_mailing_id").ids),
            ("mailing_type", "=", "mail"),
        ]
        action["context"] = dict(self.env.context)
        action["context"].update(
            {
                "default_mailing_model_id": self.model_id.id,
                "default_campaign_id": self.utm_campaign_id.id,
                "default_use_in_marketing_automation": True,
                "default_mailing_type": "mail",
                "default_state": "done",
                "create": False,
            }
        )
        return action

    def action_view_tracker_statistics(self):
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "marketing_automation.link_tracker_action_marketing_campaign"
        )
        action["domain"] = [("campaign_id", "in", self.utm_campaign_id.ids)]
        return action

    def sync_participants(self):

        def _uniquify_list(seq):
            seen = set()
            return [x for x in seq if x not in seen and not seen.add(x)]

        participants = self.env["marketing.participant"]
        now = self.env.cr.now()
        auto_commit = not modules.module.current_test
        for campaign in self.filtered(lambda c: c.marketing_activity_ids):
            if not campaign.last_sync_date:
                campaign.last_sync_date = now

            user_id = campaign.user_id or self.env.user
            RecordModel = self.env[campaign.model_name].with_context(lang=user_id.lang)

            participants_data = participants.search_read(
                [("campaign_id", "=", campaign.id)], ["res_id"]
            )
            existing_rec_ids = _uniquify_list(
                [live_participant["res_id"] for live_participant in participants_data]
            )

            record_domain = literal_eval(campaign.domain or "[]")
            db_rec_ids = _uniquify_list(RecordModel.search(record_domain).ids)
            to_create = [
                rid for rid in db_rec_ids if rid not in existing_rec_ids
            ]
            to_remove = set(existing_rec_ids) - set(db_rec_ids)
            unique_field = campaign.unique_field_id.sudo()
            if unique_field.name != "id":
                without_duplicates = []
                existing_records = (
                    RecordModel.with_context(prefetch_fields=False)
                    .browse(existing_rec_ids)
                    .exists()
                )
                unique_field_vals = {
                    rec[unique_field.name]
                    for index in range(0, len(existing_records), 1000)
                    for rec in existing_records[index : index + 1000]
                }

                for rec in RecordModel.with_context(prefetch_fields=False).browse(
                    to_create
                ):
                    field_val = rec[unique_field.name]
                    if (
                        not unique_field.relation or field_val
                    ) and field_val not in unique_field_vals:
                        without_duplicates.append(rec.id)
                        unique_field_vals.add(field_val)
                to_create = without_duplicates

            BATCH_SIZE = 100
            for to_create_batch in (
                list(b) for b in batched(to_create, BATCH_SIZE, strict=False)
            ):
                participants += participants.create(
                    [
                        {
                            "campaign_id": campaign.id,
                            "res_id": rec_id,
                        }
                        for rec_id in to_create_batch
                    ]
                )

                if auto_commit:
                    self.env["ir.cron"]._commit_progress(processed=len(to_create_batch))

            if to_remove:
                participants_to_unlink = participants.search(
                    [
                        ("res_id", "in", list(to_remove)),
                        ("campaign_id", "=", campaign.id),
                        ("state", "!=", "unlinked"),
                    ]
                )
                for index in range(0, len(participants_to_unlink), 1000):
                    participants_to_unlink[index : index + 1000].action_set_unlink()
                    if auto_commit and not index % (BATCH_SIZE * 100):
                        self.env["ir.cron"]._commit_progress()

        return participants

    def execute_activities(self) -> None:
        self.env["automation.runtime"].sudo()._dispatch_due_steps(
            rules=self.automation_rule_id.sudo()
        )


    def _prepare_res_partner_category_tag_hot_data(self) -> dict:
        return {
            "xml_id": "marketing_automation.res_partner_category_tag_hot",
            "values": {"name": self.env._("Hot")},
        }

    def _prepare_mailing_list_contact_list_data(self) -> dict:
        return {
            "xml_id": "marketing_automation.mailing_list_contact_list",
            "values": {
                "name": self.env._("Confirmed contacts"),
                "active": True,
                "is_public": True,
            },
        }

    def _prepare_ir_actions_server_partner_tag_data(self) -> dict:
        self._create_records_with_xml_ids(
            {"res.partner.tag": [self._prepare_res_partner_category_tag_hot_data()]}
        )
        hot_id = self.env.ref(
            "marketing_automation.res_partner_category_tag_hot",
            raise_if_not_found=False,
        ).id
        return {
            "xml_id": "marketing_automation.ir_actions_server_partner_tag",
            "values": {
                "name": self.env._("Add Hot Category"),
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "object_write",
                "update_field_id": self.env["ir.model.fields"]._get_ids_by_name(
                    "res.partner"
                )["tag_ids"],
                "update_path": "tag_ids",
                "evaluation_type": "value",
                "resource_ref": f"res.partner.tag,{hot_id}",
                "value": str(hot_id),
            },
        }

    def _prepare_ir_actions_server_partner_todo_data(self) -> dict:
        return {
            "xml_id": "marketing_automation.ir_actions_server_partner_todo",
            "values": {
                "name": self.env._("Next activity: Check Email Address"),
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "next_activity",
                "activity_date_deadline_range": 2,
                "activity_date_deadline_range_type": "day",
                "activity_summary": self.env._("Check Email Address"),
                "activity_type_id": self.env.ref("mail.mail_activity_data_todo").id,
                "activity_user_type": "generic",
                "activity_user_field_name": "user_id",
            },
        }

    def _prepare_ir_actions_server_contact_blacklist_data(self) -> dict:
        return {
            "xml_id": "marketing_automation.ir_actions_server_contact_blacklist",
            "values": {
                "name": self.env._("Blacklist record"),
                "model_id": self.env["ir.model"]._get_id("mailing.contact"),
                "state": "code",
                "code": """
for record in records:
    record.env['mail.blacklist']._add(
    record.email,
    message='Added in blacklist from automated action',
    )
""",
            },
        }

    def _prepare_ir_actions_server_contact_add_list_data(self) -> dict:
        return {
            "xml_id": "marketing_automation.ir_actions_server_contact_add_list",
            "values": {
                "name": self.env._("Add To Confirmed List"),
                "model_id": self.env["ir.model"]._get_id("mailing.contact"),
                "state": "code",
                "code": """
mailing_list = env.ref('marketing_automation.mailing_list_contact_list', raise_if_not_found=False)
if mailing_list:
    records.write({'list_ids': [(4, mailing_list.id)]})
""",
            },
        }

    def _prepare_ir_actions_server_partner_message_data(self) -> dict:
        return {
            "xml_id": "marketing_automation.ir_actions_server_partner_message",
            "values": {
                "name": self.env._("Message for sales person"),
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "state": "code",
                "code": """
for record in records:
    record.message_post(body='%s is interested in becoming partner.' % record.name)
""",
            },
        }

    def _create_records_with_xml_ids(self, create_xmls) -> None:
        for model_name, values in create_xmls.items():
            for record in values:
                module, name = record["xml_id"].split(".")
                if not self.env.ref(f"{module}.{name}", raise_if_not_found=False):
                    created_record = (
                        self.env[model_name].sudo().create(record["values"])
                    )
                    self.env["ir.model.data"].sudo().create(
                        {
                            "name": name,
                            "module": module,
                            "model": model_name,
                            "res_id": created_record.id,
                        }
                    )


    @api.model
    def get_action_marketing_campaign_from_template(
        self, template_str
    ) -> dict | Literal[False] | None:
        if not self.env.su and not self.env.user.has_group(
            "marketing_automation.group_marketing_automation_user"
        ):
            raise AccessError(
                self.env._(
                    "To use this feature you should be an administrator or belong to the marketing automation group."
                )
            )
        campaign_templates_info = self.get_campaign_templates_info()
        template = next(
            (
                template_value
                for group in campaign_templates_info.values()
                for template_key, template_value in group["templates"].items()
                if template_key == template_str
            ),
            False,
        )

        if not template:
            return False
        load_method = template.get("function")
        if not load_method:
            return {
                "type": "ir.actions.act_window",
                "res_model": "marketing.campaign",
                "views": [[False, "form"]],
            }

        if not load_method.startswith("_create_campaign_from_template_") or not hasattr(
            self, load_method
        ):
            return None
        loaded_method = getattr(self, load_method)
        campaign = loaded_method()

        return {
            "name": "marketing_automation_templates_action",
            "type": "ir.actions.act_window",
            "view_mode": "list,form",
            "res_id": campaign.id,
            "res_model": "marketing.campaign",
            "views": [[False, "form"]],
        }

    @api.model
    def get_campaign_templates_info(self):
        return {
            "misc": {
                "label": self.env._("Misc"),
                "templates": {
                    "start_from_scratch": {
                        "title": self.env._("Start from scratch"),
                        "description": self.env._(
                            "Design your own marketing campaign from the ground up."
                        ),
                        "icon": "/marketing_automation/static/img/paintbrush.svg",
                    },
                    "hot_contacts": {
                        "title": self.env._("Tag Hot Contacts"),
                        "description": self.env._(
                            "Send a welcome email to contacts and tag them if they click in it."
                        ),
                        "icon": "/marketing_automation/static/img/tag.svg",
                        "function": "_create_campaign_from_template_hot_contacts",
                    },
                    "commercial_prospection": {
                        "title": self.env._("Commercial prospection"),
                        "description": self.env._(
                            "Send a free catalog and follow-up according to reactions."
                        ),
                        "icon": "/marketing_automation/static/img/search.svg",
                        "function": "_create_campaign_from_template_commercial_prospection",
                    },
                },
            },
            "marketing": {
                "label": self.env._("Marketing"),
                "templates": {
                    "welcome": {
                        "title": self.env._("Welcome Flow"),
                        "description": self.env._(
                            "Send a welcome email to new subscribers, remove the addresses that bounced."
                        ),
                        "icon": "/marketing_automation/static/img/hand_peace.svg",
                        "function": "_create_campaign_from_template_welcome",
                    },
                    "double_opt_in": {
                        "title": self.env._("Double Opt-in"),
                        "description": self.env._(
                            "Send an email to new recipients to confirm their consent."
                        ),
                        "icon": "/marketing_automation/static/img/square-check.svg",
                        "function": "_create_campaign_from_template_double_opt_in",
                    },
                },
            },
        }

    def _create_campaign_from_template_hot_contacts(self):
        convert.convert_file(
            self.sudo().env,
            "marketing_automation",
            "data/templates/mail_template_body_welcome_template.xml",
            idref={},
            mode="init",
        )
        rendered_template = self.env["ir.qweb"]._render(
            self.env.ref("marketing_automation.mail_template_body_welcome_template").id,
            {
                "db_host": self.get_base_url(),
                "company_website": self.env.company.website,
            },
        )
        prerequisites = {
            "mailing.mailing": [
                {
                    "subject": self.env._("Welcome!"),
                    "body_arch": rendered_template,
                    "body_html": rendered_template,
                    "mailing_model_id": self.env["ir.model"]._get_id("res.partner"),
                    "reply_to_mode": "update",
                    "use_in_marketing_automation": True,
                    "mailing_type": "mail",
                }
            ],
        }
        for model_name, values in prerequisites.items():
            records = self.env[model_name].create(values)
            for idx, record in enumerate(records):
                prerequisites[model_name][idx] = record

        self._create_records_with_xml_ids(
            {
                "ir.actions.server": [
                    self._prepare_ir_actions_server_partner_tag_data(),
                    self._prepare_ir_actions_server_partner_todo_data(),
                ]
            }
        )

        campaign = self.env["marketing.campaign"].create(
            {
                "name": self.env._("Tag Hot Contacts"),
                "domain": [
                    "&",
                    "&",
                    ("email", "!=", False),
                    ("is_blacklisted", "=", False),
                    ("user_ids", "=", False),
                ],
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "unique_field_id": self.env["ir.model.fields"]
                ._get("res.partner", "email")
                .id,
            }
        )
        self.env["marketing.activity"].create(
            [
                {
                    "trigger_type": "begin",
                    "activity_type": "email",
                    "interval_type": "hour",
                    "mass_mailing_id": prerequisites["mailing.mailing"][0].id,
                    "interval_number": 2,
                    "name": self.env._("Send Welcome Email"),
                    "campaign_id": campaign.id,
                    "child_ids": [
                        Command.create(
                            {
                                "trigger_type": "mail_click",
                                "activity_type": "action",
                                "interval_type": "hour",
                                "mass_mailing_id": None,
                                "interval_number": 2,
                                "name": self.env._("Add Tag"),
                                "campaign_id": campaign.id,
                                "server_action_id": self.env.ref(
                                    "marketing_automation.ir_actions_server_partner_tag"
                                ).id,
                            }
                        ),
                        Command.create(
                            {
                                "trigger_type": "mail_bounce",
                                "activity_type": "action",
                                "interval_type": "hour",
                                "mass_mailing_id": None,
                                "interval_number": 2,
                                "name": self.env._("Check Bounce Contact"),
                                "campaign_id": campaign.id,
                                "server_action_id": self.env.ref(
                                    "marketing_automation.ir_actions_server_partner_todo"
                                ).id,
                            }
                        ),
                    ],
                }
            ]
        )
        return campaign

    def _create_campaign_from_template_welcome(self):
        convert.convert_file(
            self.sudo().env,
            "marketing_automation",
            "data/templates/mail_template_body_yellow_discount_template.xml",
            idref={},
            mode="init",
        )
        rendered_template = self.env["ir.qweb"]._render(
            self.env.ref(
                "marketing_automation.mail_template_body_yellow_discount_template"
            ).id,
            {
                "db_host": self.get_base_url(),
                "company_website": self.env.company.website,
            },
        )
        prerequisites = {
            "mailing.mailing": [
                {
                    "subject": self.env._("Get 10% OFF"),
                    "body_arch": rendered_template,
                    "body_html": rendered_template,
                    "mailing_model_id": self.env["ir.model"]._get_id("mailing.contact"),
                    "reply_to_mode": "update",
                    "mailing_type": "mail",
                    "use_in_marketing_automation": True,
                }
            ],
        }
        for model_name, values in prerequisites.items():
            records = self.env[model_name].create(values)
            for idx, record in enumerate(records):
                prerequisites[model_name][idx] = record

        create_xmls = {
            "ir.actions.server": [
                self._prepare_ir_actions_server_contact_blacklist_data()
            ],
        }
        self._create_records_with_xml_ids(create_xmls)

        campaign = self.env["marketing.campaign"].create(
            {
                "name": self.env._("Welcome Flow"),
                "domain": ["&", ("email", "!=", False), ("is_blacklisted", "=", False)],
                "model_id": self.env["ir.model"]._get_id("mailing.contact"),
                "unique_field_id": self.env["ir.model.fields"]
                ._get("mailing.contact", "email")
                .id,
            }
        )

        self.env["marketing.activity"].create(
            {
                "trigger_type": "begin",
                "activity_type": "email",
                "interval_type": "hour",
                "mass_mailing_id": prerequisites["mailing.mailing"][0].id,
                "interval_number": 2,
                "name": self.env._("Send 10% Welcome Discount"),
                "campaign_id": campaign.id,
                "child_ids": [
                    Command.create(
                        {
                            "trigger_type": "mail_bounce",
                            "activity_type": "action",
                            "interval_type": "hour",
                            "mass_mailing_id": None,
                            "interval_number": 2,
                            "name": self.env._("Blacklist Bounces"),
                            "parent_id": None,
                            "campaign_id": campaign.id,
                            "server_action_id": self.env.ref(
                                "marketing_automation.ir_actions_server_contact_blacklist"
                            ).id,
                        }
                    )
                ],
            }
        )
        return campaign

    def _create_campaign_from_template_double_opt_in(self):
        convert.convert_file(
            self.sudo().env,
            "marketing_automation",
            "data/templates/mail_template_body_confirmation_template.xml",
            idref={},
            mode="init",
        )
        rendered_template = self.env["ir.qweb"]._render(
            self.env.ref(
                "marketing_automation.mail_template_body_confirmation_template"
            ).id,
            {"db_host": self.get_base_url()},
        )
        prerequisites = {
            "mailing.mailing": [
                {
                    "subject": self.env._("Confirmation"),
                    "body_arch": rendered_template,
                    "body_html": rendered_template,
                    "mailing_model_id": self.env["ir.model"]._get_id("mailing.contact"),
                    "reply_to_mode": "update",
                    "mailing_type": "mail",
                    "use_in_marketing_automation": True,
                }
            ],
        }
        for model_name, values in prerequisites.items():
            records = self.env[model_name].create(values)
            for idx, record in enumerate(records):
                prerequisites[model_name][idx] = record

        create_xmls = {
            "mailing.list": [self._prepare_mailing_list_contact_list_data()],
            "ir.actions.server": [
                self._prepare_ir_actions_server_contact_add_list_data()
            ],
        }
        self._create_records_with_xml_ids(create_xmls)

        campaign = self.env["marketing.campaign"].create(
            {
                "name": self.env._("Double Opt-in"),
                "domain": [
                    "&",
                    "&",
                    ("email", "!=", False),
                    ("is_blacklisted", "=", False),
                    ("list_ids", "ilike", "Newsletter"),
                ],
                "model_id": self.env["ir.model"]._get_id("mailing.contact"),
                "unique_field_id": self.env["ir.model.fields"]
                ._get("mailing.contact", "email")
                .id,
            }
        )
        self.env["marketing.activity"].create(
            {
                "trigger_type": "begin",
                "activity_type": "email",
                "interval_type": "hour",
                "mass_mailing_id": prerequisites["mailing.mailing"][0].id,
                "interval_number": 0,
                "name": self.env._("Confirmation"),
                "campaign_id": campaign.id,
                "child_ids": [
                    Command.create(
                        {
                            "trigger_type": "mail_click",
                            "activity_type": "action",
                            "interval_type": "hour",
                            "mass_mailing_id": None,
                            "interval_number": 0,
                            "name": self.env._("Add to list"),
                            "parent_id": None,
                            "campaign_id": campaign.id,
                            "server_action_id": self.env.ref(
                                "marketing_automation.ir_actions_server_contact_add_list"
                            ).id,
                        }
                    )
                ],
            }
        )
        return campaign

    def _create_campaign_from_template_commercial_prospection(self):
        convert.convert_file(
            self.sudo().env,
            "marketing_automation",
            "data/templates/mail_template_body_join_partnership_template.xml",
            idref={},
            mode="init",
        )
        convert.convert_file(
            self.sudo().env,
            "marketing_automation",
            "data/templates/mail_template_body_free_trial_template.xml",
            idref={},
            mode="init",
        )

        free_trial_rendered = self.env["ir.qweb"]._render(
            self.env.ref(
                "marketing_automation.mail_template_body_free_trial_template"
            ).id,
            {"company_website": self.env.company.website},
        )
        join_partnership_rendered = self.env["ir.qweb"]._render(
            self.env.ref(
                "marketing_automation.mail_template_body_join_partnership_template"
            ).id,
            {"company_website": self.env.company.website},
        )

        prerequisites = {
            "mailing.mailing": [
                {
                    "subject": self.env._("Welcome!"),
                    "body_arch": free_trial_rendered,
                    "body_html": free_trial_rendered,
                    "mailing_model_id": self.env["ir.model"]._get_id("res.partner"),
                    "reply_to_mode": "update",
                    "mailing_type": "mail",
                    "use_in_marketing_automation": True,
                },
                {
                    "subject": self.env._("Join partnership!"),
                    "body_arch": join_partnership_rendered,
                    "body_html": join_partnership_rendered,
                    "mailing_model_id": self.env["ir.model"]._get_id("res.partner"),
                    "reply_to_mode": "update",
                    "mailing_type": "mail",
                    "use_in_marketing_automation": True,
                },
            ],
        }
        for model_name, values in prerequisites.items():
            records = self.env[model_name].create(values)
            for idx, record in enumerate(records):
                prerequisites[model_name][idx] = record
        create_xmls = {
            "ir.actions.server": [
                self._prepare_ir_actions_server_partner_message_data(),
            ],
        }
        self._create_records_with_xml_ids(create_xmls)

        campaign = self.env["marketing.campaign"].create(
            {
                "name": self.env._("Commercial prospection"),
                "model_id": self.env["ir.model"]._get_id("res.partner"),
                "unique_field_id": self.env["ir.model.fields"]
                ._get("res.partner", "email")
                .id,
            }
        )
        self.env["marketing.activity"].create(
            [
                {
                    "trigger_type": "begin",
                    "activity_type": "email",
                    "interval_type": "hour",
                    "mass_mailing_id": prerequisites["mailing.mailing"][0].id,
                    "interval_number": 1,
                    "name": self.env._("Offer free catalog"),
                    "campaign_id": campaign.id,
                },
                {
                    "trigger_type": "begin",
                    "activity_type": "email",
                    "interval_type": "day",
                    "mass_mailing_id": prerequisites["mailing.mailing"][1].id,
                    "interval_number": 7,
                    "name": self.env._("After 7 days"),
                    "campaign_id": campaign.id,
                    "child_ids": [
                        Command.create(
                            {
                                "trigger_type": "mail_reply",
                                "activity_type": "action",
                                "interval_type": "hour",
                                "mass_mailing_id": None,
                                "interval_number": 1,
                                "name": self.env._("Message for sales person"),
                                "parent_id": None,
                                "campaign_id": campaign.id,
                                "server_action_id": self.env.ref(
                                    "marketing_automation.ir_actions_server_partner_message"
                                ).id,
                            }
                        )
                    ],
                },
            ]
        )
        return campaign
