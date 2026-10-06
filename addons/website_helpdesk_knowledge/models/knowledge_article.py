from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class KnowledgeArticle(models.Model):
    _inherit = "knowledge.article"

    @api.model
    def _search_get_detail(self, website, order, options):
        res = super()._search_get_detail(website, order, options)
        team = self.env["team.team"]
        if options.get("helpdesk"):
            team = team.browse(self.env["ir.http"]._unslug(options["helpdesk"])[1])

        if not team:
            return res
        team_article = team.sudo().website_article_id
        if team_article:
            res["base_domain"] = [
                Domain.AND(
                    [
                        [
                            "|",
                            ("id", "=", team_article.id),
                            ("root_article_id", "=", team_article.id),
                        ],
                        res["base_domain"][0],
                    ]
                )
            ]
        return res

    def write(self, vals):
        check_if_used_in_helpdesk_team = (
            not vals.get("website_published", True)
            or not vals.get("is_published", True)
            or not vals.get("active", True)
            or vals.get("parent_id", False)
        )
        if check_if_used_in_helpdesk_team and self.env["team.team"].sudo().search_count(
            [("website_article_id", "in", self.ids)], limit=1
        ):
            _debug.logic(
                "article_change_refused", reason="used_by_helpdesk_team", articles=self
            )
            raise ValidationError(
                self.env._(
                    "You cannot delete, unpublish or set a parent on an article that is used by a helpdesk team."
                )
            )
        return super().write(vals)
