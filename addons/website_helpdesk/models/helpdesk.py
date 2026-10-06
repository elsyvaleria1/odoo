from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class TeamTeam(models.Model):
    _name = "team.team"
    _inherit = [
        "team.team",
        "mixin.website.published",
        "mixin.website.seo.metadata",
    ]

    feature_form_url = fields.Char(
        string="URL to Submit Issue",
        export_string_translation=False,
        compute="_compute_form_url",
        readonly=True,
    )
    website_id = fields.Many2one(
        comodel_name="website",
        compute="_compute_website_id",
        store=True,
        readonly=False,
        domain="[('company_id', '=?', company_id)]",
    )
    website_menu_id = fields.Many2one(
        comodel_name="website.menu",
        export_string_translation=False,
    )
    website_form_view_id = fields.Many2one(
        comodel_name="ir.ui.view",
        export_string_translation=False,
    )

    @api.constrains("use_website_helpdesk_form", "website_id", "company_id")
    def _check_website_company(self) -> None:
        if any(
            t.use_website_helpdesk_form
            and t.website_id
            and t.website_id.company_id != t.company_id
            for t in self
        ):
            _debug.logic(
                "helpdesk_website_refused", reason="company_mismatch", teams=self
            )
            raise ValidationError(
                self.env._("The companies of the team and the website should match.")
            )

    @api.depends("company_id")
    def _compute_website_id(self) -> None:
        for team in self:
            team.website_id = team.company_id.website_id

    @api.model
    def _get_fields_knowledge_base(self):
        return []

    @api.depends(
        lambda self: (
            ["use_website_helpdesk_form"] + list(self._get_fields_knowledge_base())
        )
    )
    def _compute_show_knowledge_base(self) -> None:
        kb_fields = self._get_fields_knowledge_base()
        for team in self:
            team.show_knowledge_base = team.use_website_helpdesk_form and any(
                team[field] for field in kb_fields
            )

    def _compute_website_url(self) -> None:
        super()._compute_website_url()
        for team in self.filtered("use_helpdesk"):
            team.website_url = "/helpdesk/%s" % self.env["ir.http"]._slug(team)

    @api.onchange(
        "use_website_helpdesk_form",
        "use_website_helpdesk_forum",
        "use_website_helpdesk_slides",
        "use_website_helpdesk_knowledge",
    )
    def _onchange_use_website_helpdesk(self) -> None:
        if (
            not (
                self.use_website_helpdesk_form
                or self.use_website_helpdesk_forum
                or self.use_website_helpdesk_slides
                or self.use_website_helpdesk_knowledge
            )
            and self.website_published
        ):
            self.is_published = False
        elif self.use_website_helpdesk_form and not self.website_published:
            self.is_published = True

    def write(self, vals):
        if "active" in vals and not vals["active"]:
            vals["is_published"] = False
        res = super().write(vals)
        if vals.get("use_website_helpdesk_form"):
            self._create_missing_submit_form_view()
        if {"use_website_helpdesk_form", "is_published"} & vals.keys():
            self._create_missing_website_menu()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        teams = super().create(vals_list)
        teams.filtered("use_website_helpdesk_form")._create_missing_submit_form_view()
        teams._create_missing_website_menu()
        return teams

    def unlink(self):
        self.website_menu_id.unlink()
        return super().unlink()

    def _create_missing_submit_form_view(self) -> None:
        teams = self.filtered("use_website_helpdesk_form")
        if not teams:
            return

        default_form = self.env.ref("website_helpdesk.ticket_submit_form").sudo().arch
        for team in teams:
            if not team.website_form_view_id:
                xmlid = "website_helpdesk.team_form_" + str(team.id)
                form_template = (
                    self.env["ir.ui.view"]
                    .sudo()
                    .create(
                        {
                            "type": "qweb",
                            "arch": default_form,
                            "name": xmlid,
                            "key": xmlid,
                        }
                    )
                )
                self.env["ir.model.data"].sudo().create(
                    {
                        "module": "website_helpdesk",
                        "name": xmlid.split(".")[1],
                        "model": "ir.ui.view",
                        "res_id": form_template.id,
                        "noupdate": True,
                    }
                )
                team.website_form_view_id = form_template.id

    def _create_missing_website_menu(self) -> None:
        with_website = self.filtered_domain([("use_website_helpdesk_form", "=", True)])
        without_website = self - with_website
        without_website.website_menu_id.unlink()

        team_count_by_website = dict(
            self.env["team.team"]._read_group(
                [("use_website_helpdesk_form", "=", True)],
                ["website_id"],
                ["__count"],
            )
        )
        teams_per_website = with_website.grouped("website_id")
        for website, teams in teams_per_website.items():
            if any(team.website_menu_id for team in teams):
                continue
            team_count = team_count_by_website.get(website.id, 0)
            if team_count <= 1:
                parent_menu = website.menu_id
                if parent_menu:
                    menu = (
                        self.env["website.menu"]
                        .sudo()
                        .create(
                            {
                                "name": self.env._("Help"),
                                "url": "/helpdesk",
                                "parent_id": parent_menu.id,
                                "sequence": 50,
                                "website_id": website.id,
                            }
                        )
                    )
                    teams.website_menu_id = menu.id

    @api.depends("name", "use_website_helpdesk_form", "company_id")
    def _compute_form_url(self) -> None:
        for team in self:
            base_url = team.get_base_url()
            team.feature_form_url = (
                (team.use_website_helpdesk_form and team.name and team.id)
                and (base_url + "/helpdesk/" + self.env["ir.http"]._slug(team))
            ) or False

    def _helpcenter_filter_types(self):
        return {}

    def _helpcenter_filter_tags(self, search_type):
        return []

    def _helpcenter_date_from_search(self, searches):
        if not searches.get("date"):
            return False

        delta = {"7days": 7, "30days": 30, "365days": 365}.get(searches["date"])
        if not delta:
            _debug.logic("helpcenter_date_filter_rejected", value=str(searches["date"]))
            return False

        today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
        return today - timedelta(days=delta)

    def get_knowledge_base_url(self):
        self.check_singleton()
        return self.feature_form_url

    def _get_search_options(self, searches) -> dict:
        return {
            "displayDescription": True,
            "displayDetail": True,
            "displayExtraDetail": True,
            "displayExtraLink": True,
            "displayImage": False,
            "allowFuzzy": True,
            "helpdesk": self.env["ir.http"]._slug(self),
            "max_date": self._helpcenter_date_from_search(searches),
            "tag": searches.get("tag", False),
        }

    def open_website_url(self):
        return self.env["website"].get_client_action(
            self.website_url, website_id=self.website_id.id
        )
