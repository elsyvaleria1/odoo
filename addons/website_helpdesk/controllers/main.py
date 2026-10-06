import re
from typing import Any

from werkzeug.exceptions import NotFound
from werkzeug.utils import redirect

from odoo import Command, http
from odoo.fields import Domain
from odoo.http import request
from odoo.libs.debug_log import DebugLog
from odoo.libs.text import nl2br, nl2br_enclose
from odoo.tools import html2plaintext
from odoo.tools.translate import LazyTranslate

from odoo.addons.website.controllers import form, main
from odoo.addons.website.models.ir_http import sitemap_qs2dom

_debug = DebugLog(__name__)

_lt = LazyTranslate(__name__)


def sitemap_helpdesk(env, rule, qs):
    HelpdeskTeam = env["team.team"]
    slug = env["ir.http"]._slug

    dom = (
        env["website"].get_current_website().website_domain()
        & Domain("use_helpdesk", "=", True)
        & Domain("use_website_helpdesk_form", "=", True)
        & Domain("website_published", "=", True)
    )
    dom += sitemap_qs2dom(qs, "/helpdesk", HelpdeskTeam._rec_name)

    teams = HelpdeskTeam.search(dom)
    for team in teams:
        loc = "/helpdesk/%s" % slug(team)
        if not qs or qs.lower() in loc:
            yield {"loc": loc}

    if not teams:
        return

    if not qs or qs.lower() in "/helpdesk":
        yield {"loc": "/helpdesk"}


class WebsiteHelpdesk(http.Controller):
    def get_helpdesk_team_data(self, team, search=None):
        return {
            "team": team,
            "main_object": team,
        }

    @http.route(
        ["/helpdesk", '/helpdesk/<model("team.team"):team>'],
        type="http",
        auth="public",
        website=True,
        sitemap=sitemap_helpdesk,
        list_as_website_content=_lt("Helpdesk"),
    )
    def website_helpdesk_teams(self, team=None, **kwargs):
        search = kwargs.get("search")
        if team and not team.use_helpdesk:
            _debug.logic("helpdesk_refused", reason="helpdesk_off", team=team.id)
            raise NotFound

        teams_domain = (
            Domain("use_helpdesk", "=", True)
            & Domain("use_website_helpdesk_form", "=", True)
            & Domain("website_id", "=", request.website.id)
        )
        if not request.env.user.has_group("helpdesk.group_helpdesk_manager"):
            if team and not team.is_published:
                _debug.logic(
                    "helpdesk_refused", reason="team_unpublished", team=team.id
                )
                raise NotFound
            teams_domain &= Domain("website_published", "=", True)

        teams = request.env["team.team"].search(teams_domain, order="id asc")
        if not teams:
            _debug.logic("helpdesk_refused", reason="no_visible_team")
            raise NotFound

        if not team:
            if len(teams) != 1:
                return request.render(
                    "website_helpdesk.helpdesk_all_team", {"teams": teams}
                )
            redirect_url = teams.website_url
            if teams.show_knowledge_base and not kwargs.get("contact_form"):
                redirect_url += "/knowledgebase"
            elif kwargs.get("contact_form"):
                redirect_url += "/?contact_form=1"
            return redirect(redirect_url)

        if team.show_knowledge_base and not kwargs.get("contact_form"):
            return redirect(team.website_url + "/knowledgebase")

        result = self.get_helpdesk_team_data(team or teams[0], search=search)
        result["multiple_teams"] = len(teams) > 1
        return request.render("website_helpdesk.team", result)

    def _prepare_knowledge_base_qcontext(self, team) -> dict[str, Any]:
        return {
            "team": team,
            "main_object": team,
        }

    @http.route(
        ['/helpdesk/<model("team.team"):team>/knowledgebase'],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def website_helpdesk_knowledge_base(self, team, **kwargs):
        if not team.use_helpdesk:
            _debug.logic("knowledge_base_refused", reason="helpdesk_off", team=team.id)
            raise NotFound
        if not team.show_knowledge_base:
            return redirect(team.website_url)

        search = kwargs.get("search")
        search_kw = ["type", "date", "tag"]
        if search is not None:
            searches = {
                "search": search,
                **{
                    k: kwargs.get(k)
                    for k in search_kw
                    if request.website.is_view_active(
                        "website_helpdesk.navbar_search_%s" % k
                    )
                },
            }

            types = team._helpcenter_filter_types()
            options = team._get_search_options(searches)
            search_types = [searches["type"]] if searches.get("type") else types.keys()
            results = self._get_search_results(search, search_types, options)

            tags = sorted(set(team._helpcenter_filter_tags(kwargs.get("type"))))
            dates = {
                "7days": request.env._("Last Week"),
                "30days": request.env._("Last Month"),
                "365days": request.env._("Last Year"),
            }
            return request.render(
                "website_helpdesk.search_results",
                {
                    "team": team,
                    "search": search,
                    "search_count": len(results),
                    "searches": searches,
                    "available_types": types,
                    "current_type": types[searches["type"]]
                    if searches.get("type")
                    else False,
                    "available_dates": dates,
                    "current_date": dates[searches["date"]]
                    if searches.get("date")
                    else False,
                    "available_tags": tags,
                    "current_tag": searches["tag"] if searches.get("tag") else False,
                    "results": results,
                },
            )

        return request.render(
            "website_helpdesk.knowledge_base",
            self._prepare_knowledge_base_qcontext(team),
        )

    @http.route(
        ['/helpdesk/<model("team.team"):team>/knowledgebase/autocomplete'],
        type="jsonrpc",
        auth="public",
        website=True,
        sitemap=True,
    )
    def website_helpdesk_autocomplete(self, team, **kwargs):
        if not team.use_helpdesk or not team.show_knowledge_base:
            _debug.logic(
                "helpdesk_autocomplete_refused",
                team=team.id,
                helpdesk=team.use_helpdesk,
                knowledge_base=team.show_knowledge_base,
            )
            raise NotFound

        search = kwargs.get("term")
        if len(search) < 3:
            return {"results": [], "showMore": False}

        searches = {"search": search}
        options = team._get_search_options(searches)

        search_types = team._helpcenter_filter_types().keys()
        results = self._get_search_results(search, search_types, options)

        return {
            "results": [
                {"name": r["record"].name, "icon": r["icon"], "url": r["url"]}
                for r in results[:10]
            ],
            "showMore": len(results) > 10,
        }

    def _get_search_results(self, search, search_types, options):
        search_results = []
        if search:
            for search_type in search_types:
                count, results, _dummy = request.website._search_with_fuzzy(
                    search_type, search, limit=10, order="name", options=options
                )
                if count:
                    for all_results in results:
                        if all_results.get("results", False):
                            search_results += self._format_search_results(
                                search_type, all_results["results"], options
                            )
        return sorted(search_results, key=lambda res: res.get("score", 0), reverse=True)

    def _format_search_results(self, search_type, records, options):
        return []


class WebsiteForm(form.WebsiteForm):
    def _handle_website_form(self, model_name, **kwargs):
        if model_name == "helpdesk.ticket":
            phone = request.params.pop("phone", None) or request.params.pop(
                "partner_phone", None
            )
            if phone:
                request.update_context(website_form_phone_ids=phone)
        email = request.params.get("partner_email")
        if email:
            if request.env.user.email == email:
                partner = request.env.user.partner_id
            else:
                partner = (
                    request.env["res.partner"]
                    .sudo()
                    .search([("email", "=", email)], limit=1)
                )
            if not partner:
                phone = request.env.context.get("website_form_phone_ids")
                partner = (
                    request.env["res.partner"]
                    .sudo()
                    .create(
                        {
                            "email": email,
                            "name": request.params.get("partner_name", False),
                            "phone_ids": [
                                Command.create({"number": phone, "type": "mobile"})
                            ]
                            if phone
                            else False,
                            "lang": request.lang.code,
                        }
                    )
                )
            request.params["partner_id"] = partner.id

        return super()._handle_website_form(model_name, **kwargs)

    def create_attachments(self, model_sudo, id_record, files):
        super().create_attachments(model_sudo, id_record, files)
        model_name = model_sudo.model
        if model_name == "helpdesk.ticket":
            ticket = model_sudo.env[model_name].browse(id_record)
            attachments = (
                request.env["ir.attachment"]
                .sudo()
                .search(
                    [
                        ("res_model", "=", model_name),
                        ("res_id", "=", ticket.id),
                        ("access_token", "=", False),
                    ]
                )
            )
            if not attachments:
                return
            attachments.generate_access_token()
            message = ticket.message_ids.filtered(
                lambda m: m.attachment_ids == attachments
            )
            message.is_internal = False
            message.subtype_id = request.env.ref("mail.mt_comment")

    def create_record(self, request, model_sudo, values, custom, meta=None):
        if model_sudo.model == "helpdesk.ticket":
            phone = request.env.context.get("website_form_phone_ids")
            if phone and not values.get("phone_ids"):
                values["phone_ids"] = [
                    Command.create({"number": phone, "type": "mobile"})
                ]
        res = super().create_record(request, model_sudo, values, custom, meta=meta)
        if model_sudo.model != "helpdesk.ticket":
            return res
        ticket = request.env["helpdesk.ticket"].sudo().browse(res)
        custom_label = nl2br_enclose(request.env._("Other Information"), "h4")
        default_field = model_sudo.website_form_default_field_id
        default_field_data = values.get(default_field.name, "")
        if not custom:
            default_field_content = nl2br_enclose(
                html2plaintext(default_field_data), "p"
            )
        else:
            default_field_content = nl2br_enclose(
                default_field.field_description, "h4"
            ) + nl2br_enclose(html2plaintext(default_field_data), "p")
        custom_content = (
            (default_field_content if default_field_data else "")
            + (custom_label + custom if custom else "")
            + (self._meta_label + meta if meta else "")
        )

        if default_field.name:
            if default_field.ttype == "html":
                custom_content = nl2br(custom_content)
            ticket[default_field.name] = custom_content
            ticket._message_log(
                body=custom_content,
                message_type="comment",
            )
        return res


class Website(main.Website):
    @http.route()
    def get_suggested_link(self, needle, limit=10):
        def _is_helpdesk_team_page(page) -> bool:
            url = page.get("value", "")
            pattern = r"^/helpdesk/([a-zA-Z]+-)+\d+$"
            return bool(re.match(pattern, url))

        res = super().get_suggested_link(needle, limit)
        res["matching_pages"] = [
            page for page in res["matching_pages"] if not _is_helpdesk_team_page(page)
        ]
        return res
