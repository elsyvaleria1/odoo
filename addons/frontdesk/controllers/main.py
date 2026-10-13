from odoo import Command, fields, http
from odoo.fields import Domain
from odoo.http import request
from odoo.tools import consteq
from odoo.tools.image import image_data_uri

HOST_SEARCH_LEAVES = {
    ("display_name", "ilike"): str,
    ("department_id", "="): int,
}


class Frontdesk(http.Controller):
    def _get_additional_info(self, frontdesk, lang, is_mobile=False):
        request.session.logout(keep_db=True)
        return request.render(
            "frontdesk.frontdesk",
            {
                "frontdesk": frontdesk,
                "is_mobile": is_mobile,
                "current_lang": lang,
            },
        )

    def _is_token_valid(self, frontdesk, token) -> bool:
        if consteq(frontdesk.access_token, token):  # noqa: E8537 -- device: a device's or a service's credential, presented by a program
            return True
        else:
            time_difference = fields.Datetime.now() - fields.Datetime.from_string(
                token[-19:]
            )
            return time_difference.total_seconds() <= 3600 and consteq(
                frontdesk._get_tmp_code(), token[:64]
            )

    def _host_domain(self, frontdesk) -> Domain:
        domain = Domain(
            [
                ("company_id", "=", frontdesk.company_id.id),
                "|",
                ("work_email", "!=", False),
                ("phone_ids", "!=", False),
            ]
        )
        if frontdesk.host_ids:
            domain &= Domain("id", "in", frontdesk.host_ids.ids)
        return domain

    def _host_search_domain(self, domain) -> Domain:
        if not isinstance(domain, list):
            raise request.prepare_not_found_error()
        leaves = []
        for item in domain:
            if item == "&":
                continue
            if not (isinstance(item, list) and len(item) == 3):
                raise request.prepare_not_found_error()
            field_name, operator, value = item
            expected = HOST_SEARCH_LEAVES.get((field_name, operator))
            if expected is None or type(value) is not expected:
                raise request.prepare_not_found_error()
            leaves.append(Domain(field_name, operator, value))
        return Domain.AND(leaves)

    @http.route(
        "/kiosk/<int:frontdesk_id>/<string:token>",
        type="http",
        auth="public",
        website=True,
    )
    def launch_frontdesk(self, frontdesk_id, token, lang="en_US"):
        frontdesk = request.env["frontdesk.frontdesk"].sudo().browse(frontdesk_id)
        if not frontdesk.exists() or not self._is_token_valid(frontdesk, token):
            raise request.prepare_not_found_error()
        return self._get_additional_info(frontdesk, lang)

    @http.route(
        "/kiosk/<int:frontdesk_id>/mobile/<string:token>",
        type="http",
        auth="public",
        website=True,
    )
    def launch_frontdesk_mobile(self, frontdesk_id, token, lang="en_US"):
        frontdesk = request.env["frontdesk.frontdesk"].sudo().browse(frontdesk_id)
        if not frontdesk.exists() or not self._is_token_valid(frontdesk, token):
            return request.render("frontdesk.frontdesk_qr_expired")
        return self._get_additional_info(frontdesk, lang, is_mobile=True)

    @http.route(
        "/kiosk/<int:frontdesk_id>/get_tmp_code/<string:token>",
        type="jsonrpc",
        auth="public",
    )
    def get_tmp_code(self, frontdesk_id, token):
        frontdesk = request.env["frontdesk.frontdesk"].sudo().browse(frontdesk_id)
        if not frontdesk.exists() or not self._is_token_valid(frontdesk, token):
            raise request.prepare_not_found_error()
        return (
            frontdesk._get_tmp_code(),
            fields.Datetime.to_string(fields.Datetime.now()),
        )

    @http.route(
        "/frontdesk/<int:frontdesk_id>/<string:token>/get_frontdesk_data",
        type="jsonrpc",
        auth="public",
    )
    def get_frontdesk_data(self, frontdesk_id, token):
        frontdesk = request.env["frontdesk.frontdesk"].sudo().browse(frontdesk_id)
        if not frontdesk.exists() or not self._is_token_valid(frontdesk, token):
            raise request.prepare_not_found_error()
        return frontdesk._get_frontdesk_data()

    @http.route(
        "/frontdesk/<int:frontdesk_id>/<string:token>/get_planned_visitors",
        type="jsonrpc",
        auth="public",
    )
    def get_planned_visitors(self, frontdesk_id, token):
        frontdesk = request.env["frontdesk.frontdesk"].sudo().browse(frontdesk_id)
        if not frontdesk.exists() or not self._is_token_valid(frontdesk, token):
            raise request.prepare_not_found_error()
        return frontdesk._get_planned_visitors()

    @http.route("/frontdesk/<int:frontdesk_id>/background", type="http", auth="public")
    def frontdesk_background_image(self, frontdesk_id):
        frontdesk = request.env["frontdesk.frontdesk"].sudo().browse(frontdesk_id)
        if not frontdesk.image:
            return ""
        return (
            request.env["ir.binary"]
            ._get_stream_image_from_record(frontdesk, "image")
            .prepare_response()
        )

    @http.route(
        "/frontdesk/<int:drink_id>/get_frontdesk_drinks", type="http", auth="public"
    )
    def get_frontdesk_drinks(self, drink_id):
        drink = request.env["frontdesk.drink"].sudo().browse(drink_id)
        return (
            request.env["ir.binary"]
            ._get_stream_image_from_record(drink, "drink_image")
            .prepare_response()
        )

    @http.route(
        "/frontdesk/<int:frontdesk_id>/<string:token>/hosts_infos",
        type="jsonrpc",
        auth="public",
    )
    def hosts_infos(self, frontdesk_id, token, limit, offset, domain):
        frontdesk = request.env["frontdesk.frontdesk"].sudo().browse(frontdesk_id)
        if not frontdesk.exists() or not self._is_token_valid(frontdesk, token):
            raise request.prepare_not_found_error()
        domain = self._host_search_domain(domain) & self._host_domain(frontdesk)
        employees = (
            request.env["hr.employee"]
            .sudo()
            .search_fetch(
                domain,
                ["id", "display_name", "job_id", "avatar_128"],
                limit=limit,
                offset=offset,
                order="name, id",
            )
        )
        employees_data = [
            {
                "id": employee.id,
                "display_name": employee.display_name,
                "job_id": employee.job_id.name,
                "avatar": image_data_uri(employee.avatar_128),
            }
            for employee in employees
        ]
        return {
            "records": employees_data,
            "length": request.env["hr.employee"].sudo().search_count(domain),
        }

    @http.route(
        "/frontdesk/<int:frontdesk_id>/<string:token>/get_departments",
        type="jsonrpc",
        auth="public",
    )
    def get_departments(self, frontdesk_id, token):
        frontdesk = request.env["frontdesk.frontdesk"].sudo().browse(frontdesk_id)
        if not frontdesk.exists() or not self._is_token_valid(frontdesk, token):
            raise request.prepare_not_found_error()
        departments = (
            request.env["hr.department"]
            .sudo()
            .search([("company_id", "=", frontdesk.company_id.id)])
        )
        department_list = []
        host_domain = self._host_domain(frontdesk)
        for department in departments:
            employee_domain = host_domain & Domain("department_id", "=", department.id)
            employee_count = (
                request.env["hr.employee"].sudo().search_count(employee_domain)
            )
            if employee_count:
                department_list.append(
                    {
                        "id": department.id,
                        "name": department.name,
                        "count": employee_count,
                    }
                )
        return department_list

    @http.route(
        "/frontdesk/<int:frontdesk_id>/<string:token>/prepare_visitor_data",
        type="jsonrpc",
        auth="public",
        methods=["POST"],
    )
    def check_in_visitor(self, frontdesk_id, token, visitor_id=None, **kwargs):
        frontdesk = request.env["frontdesk.frontdesk"].sudo().browse(frontdesk_id)
        if not frontdesk.exists() or not self._is_token_valid(frontdesk, token):
            raise request.prepare_not_found_error()
        vals = {"state": "checked_in"}
        if visitor_id:
            visitor_sudo = request.env["frontdesk.visitor"].sudo().browse(visitor_id)
            if not visitor_sudo.exists() or visitor_sudo.station_id != frontdesk:
                raise request.prepare_not_found_error()
            if kwargs.get("drink_ids"):
                drinks = frontdesk.drink_ids.filtered(
                    lambda drink: drink.id in kwargs["drink_ids"]
                )
                visitor_sudo.write(
                    {"drink_ids": [Command.link(drink.id) for drink in drinks]}
                )
                return visitor_sudo._notify_to_people()
            return visitor_sudo.write(vals)
        else:
            hosts = (
                request.env["hr.employee"]
                .sudo()
                .search(
                    self._host_domain(frontdesk)
                    & Domain("id", "in", list(kwargs.get("host_ids") or []))
                )
            )
            vals.update(
                {
                    "station_id": frontdesk.id,
                    "name": kwargs.get("name"),
                    "phone_ids": [
                        Command.set(
                            frontdesk.env["phone.number"]
                            .with_context(
                                default_country_id=frontdesk.company_id.country_id.id
                            )
                            .create({"number": kwargs["phone"], "type": "mobile"})
                            .ids
                        )
                    ]
                    if kwargs.get("phone")
                    else False,
                    "email": kwargs.get("email"),
                    "check_in": fields.Datetime.now(),
                    "company": kwargs.get("company"),
                    "host_ids": [Command.set(hosts.ids)],
                }
            )
            visitor = request.env["frontdesk.visitor"].sudo().create(vals)
            visitor._notify()
            return {"visitor_id": visitor.id}

    @http.route(
        "/frontdesk/visitor/check_out/<int:visitor_id>", type="http", auth="user"
    )
    def frontdesk_visitor_check_out(self, visitor_id):
        visitor = request.env["frontdesk.visitor"].browse(visitor_id)
        if not visitor.exists() or not request.env.user.has_group(
            "frontdesk.frontdesk_group_user"
        ):
            raise request.prepare_not_found_error()
        visitor.sudo().action_check_out()
        return request.render("frontdesk.frontdesk_visitor_check_out")
