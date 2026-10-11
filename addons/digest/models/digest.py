import logging
from datetime import UTC, datetime
from itertools import batched
from typing import NamedTuple
from urllib.parse import urlencode

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import api, fields, models, tools
from odoo.exceptions import AccessError
from odoo.fields import Command, Domain
from odoo.http import request
from odoo.libs.datetime import timezone
from odoo.libs.numbers import float_round
from odoo.libs.web import urljoin as url_join
from odoo.tools import SQL

from odoo.addons.integration.tools.admission import Resolution

_logger = logging.getLogger(__name__)

UNSUBSCRIBE_SCOPE = tools.register_signed_scope(
    "digest-unsubscribe",
    purpose="unsubscribe a user from a digest from its mail",
    lifetime="undated: carried by every digest mail the user receives",
)

KPI_AGGREGATE_MEMO = "digest.kpi_aggregates"

KPI_PREFIXES = ("kpi_", "x_kpi_", "x_studio_kpi_")


class Periodicity(NamedTuple):
    """Everything a periodicity decides, in one place.

    Three separate ``if periodicity ==`` chains used to live in this file --
    one picking the next mailing date, one picking how long a recipient may be
    away before the digest slows down, one picking what it slows down *to*.
    They agreed by hand: the weekly chain spelled its idle window ``days=7``
    while its run delta was ``weeks=1``, and the run chain had no ``quarterly``
    branch at all, only a bare ``else``. A table makes a disagreement between
    the three a visible edit rather than a silent one.

    The ``periodicity`` selection is built from this table
    (``PERIODICITY_SELECTION``) rather than written beside it, so the two cannot
    disagree at all; ``test_periodicity_table_is_the_selection`` holds the
    remaining invariants -- that every fallback is itself a key, and that
    ``quarterly`` is the floor.
    """

    run: relativedelta
    idle: relativedelta
    slower: str
    label: str


PERIODICITIES = {
    "daily": Periodicity(
        relativedelta(days=1), relativedelta(days=2), "weekly", "Daily"
    ),
    "weekly": Periodicity(
        relativedelta(weeks=1), relativedelta(weeks=1), "monthly", "Weekly"
    ),
    "monthly": Periodicity(
        relativedelta(months=1), relativedelta(months=1), "quarterly", "Monthly"
    ),
    "quarterly": Periodicity(
        relativedelta(months=3), relativedelta(months=3), "quarterly", "Quarterly"
    ),
}

PERIODICITY_SELECTION = [(key, p.label) for key, p in PERIODICITIES.items()]


class DigestDigest(models.Model):
    """Periodic KPI email digest sent to a set of recipients."""

    _name = "digest.digest"
    _description = "Digest"
    _order = "name, id"

    name = fields.Char(
        translate=True,
        required=True,
    )
    user_ids = fields.Many2many(
        comodel_name="res.users",
        string="Recipients",
        domain="[('share', '=', False)]",
    )
    periodicity = fields.Selection(
        selection=PERIODICITY_SELECTION,
        default="daily",
        required=True,
    )
    next_run_date = fields.Date(
        string="Next Mailing Date",
        compute="_compute_next_run_date",
        store=True,
        readonly=False,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id",
        string="Currency",
        readonly=False,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company.id,
    )
    is_subscribed = fields.Boolean(
        string="Is user subscribed",
        compute="_compute_is_subscribed",
    )
    state = fields.Selection(
        selection=[("activated", "Activated"), ("deactivated", "Deactivated")],
        string="Status",
        default="activated",
        readonly=True,
    )
    kpi_res_users_connected = fields.Boolean(string="Connected Users")
    kpi_res_users_connected_value = fields.Integer(
        compute="_compute_kpi_res_users_connected_value"
    )
    kpi_mail_message_total = fields.Boolean(string="Messages Sent")
    kpi_mail_message_total_value = fields.Integer(
        compute="_compute_kpi_mail_message_total_value"
    )

    @api.depends("user_ids")
    @api.depends_context("uid")
    def _compute_is_subscribed(self) -> None:
        user = self.env.user
        for digest in self:
            digest.is_subscribed = user in digest.user_ids

    def _get_kpi_compute_parameters(self) -> tuple:
        companies = self.company_id
        if any(not digest.company_id for digest in self):
            companies |= self.env.company

        return (
            fields.Datetime.to_string(self.env.context.get("start_datetime")),
            fields.Datetime.to_string(self.env.context.get("end_datetime")),
            companies,
        )

    def _compute_kpi_res_users_connected_value(self) -> None:
        self._update_company_based_kpi(
            "res.users",
            "kpi_res_users_connected_value",
            date_field="login_date",
        )

    def _compute_kpi_mail_message_total_value(self) -> None:
        start, end, __ = self._get_kpi_compute_parameters()
        self.kpi_mail_message_total_value = self.env["mail.message"].search_count(
            [
                ("create_date", ">=", start),
                ("create_date", "<", end),
                ("subtype_id", "=", self.env.ref("mail.mt_comment").id),
                ("message_type", "in", ("comment", "email", "email_outgoing")),
            ]
        )

    @api.depends("periodicity")
    def _compute_next_run_date(self) -> None:
        for digest in self:
            digest.next_run_date = digest._get_next_run_date(digest.periodicity)

    @api.model_create_multi
    def create(self, vals_list):
        default_periodicity = None
        seeded = []
        for vals in vals_list:
            periodicity = vals.get("periodicity")
            if not periodicity:
                if default_periodicity is None:
                    default_periodicity = self.default_get(["periodicity"])[
                        "periodicity"
                    ]
                periodicity = default_periodicity
            if vals.get("next_run_date") or periodicity not in PERIODICITIES:
                seeded.append(vals)
                continue
            seeded.append(
                {**vals, "next_run_date": self._get_next_run_date(periodicity)}
            )
        return super().create(seeded)


    def action_subscribe(self) -> None:
        if self.env.user._is_internal() and self.env.user not in self.user_ids:
            self._action_subscribe_users(self.env.user)

    def _action_subscribe_users(self, users) -> None:
        self.sudo().user_ids |= users

    def action_unsubscribe(self) -> None:
        if self.env.user._is_internal() and self.env.user in self.user_ids:
            self._action_unsubscribe_users(self.env.user)

    def _action_unsubscribe_users(self, users) -> None:
        self.sudo().user_ids -= users

    def action_activate(self):
        self.state = "activated"

    def action_deactivate(self) -> None:
        self.state = "deactivated"

    def action_set_periodicity(self, periodicity) -> None:
        self.periodicity = periodicity

    def action_send(self):
        return self._action_send(update_periodicity=True)

    def action_send_manual(self):
        return self._action_send(update_periodicity=False)

    def _action_send(self, update_periodicity=True) -> None:
        to_slowdown = (
            self._get_digests_to_slowdown() if update_periodicity else self.browse()
        )

        for digest in self:
            for user in digest.user_ids:
                try:
                    digest.with_context(
                        digest_slowdown=digest in to_slowdown,
                        lang=user.lang,
                        tz=user.tz,
                    )._action_send_to_user(user, tips_count=1)
                except Exception:
                    _logger.exception(
                        "Failed to send digest %r to %s", digest.name, user.login
                    )
                    continue
            if digest in to_slowdown:
                digest.periodicity = digest._get_next_periodicity()[0]
            digest.next_run_date = digest._get_next_run_date()

    def _action_send_to_user(self, user, tips_count=1, consume_tips=True):
        unsubscribe_token = self._get_unsubscribe_token(user.id)

        rendered_body = self.env["mixin.mail.render"]._render_template(
            "digest.digest_mail_main",
            "digest.digest",
            self.ids,
            engine="qweb_view",
            add_context={
                "title": self.name,
                "top_button_label": self.env._("Connect"),
                "top_button_url": self.get_base_url(),
                "company": user.company_id,
                "user": user,
                "unsubscribe_token": unsubscribe_token,
                "tips_count": tips_count,
                "formatted_date": tools.format_date(
                    self.env,
                    fields.Date.context_today(self),
                    date_format="MMMM dd, yyyy",
                ),
                "display_mobile_banner": True,
                "kpi_data": self._get_kpi_data(user.company_id, user),
                "tips": self._acquire_tips(
                    user.company_id, user, tips_count=tips_count, consumed=consume_tips
                ),
                "preferences": self._get_preferences(user.company_id, user),
            },
            options={
                "preserve_comments": True,
                "post_process": True,
            },
        )[self.id]
        full_mail = self.env["mixin.mail.render"]._render_encapsulate(
            "digest.digest_mail_layout",
            rendered_body,
            add_context={
                "company": user.company_id,
                "user": user,
            },
        )
        unsub_params = urlencode(
            {
                "token": unsubscribe_token,
                "user_id": user.id,
            }
        )
        unsub_url = url_join(
            self.get_base_url(),
            f"/digest/{self.id}/unsubscribe_oneclick?{unsub_params}",
        )
        mail_values = {
            "auto_delete": True,
            "author_id": self.env.user.partner_id.id,
            "body_html": full_mail,
            "email_from": (
                self.company_id.partner_id.email_formatted
                or self.env.user.email_formatted
                or self.env.ref("base.user_root").email_formatted
            ),
            "email_to": user.email_formatted,
            "headers": {
                "List-Unsubscribe": f"<{unsub_url}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                "X-Auto-Response-Suppress": "OOF",
            },
            "state": "outgoing",
            "subject": f"{user.company_id.name}: {self.name}",
        }
        self.env["mail.mail"].sudo().create(mail_values)
        return True

    @api.model
    def _cron_send_digest_email(self) -> None:
        digests = self.search(
            [("next_run_date", "<=", fields.Date.today()), ("state", "=", "activated")]
        )
        commit_progress = self.env["ir.cron"]._commit_progress
        commit_progress(0, remaining=len(digests))
        for batch_ids in batched(digests.ids, 10, strict=False):
            self.browse(batch_ids).action_send()
            if not commit_progress(processed=len(batch_ids)):
                break

    @api.model
    def _receiver_for_unsubscribe(self, digest_id=None, **path_args):
        digest = self.sudo().browse(digest_id).exists()
        if not digest:
            return digest
        params = request.get_http_params()
        token, user_id = params.get("token"), params.get("user_id")

        def is_request_authorized(headers, body) -> bool:
            if token and user_id:
                try:
                    return digest._is_unsubscribe_token(int(user_id), token)
                except TypeError, ValueError:
                    return False
            if not token and not user_id and request.session.uid:
                user = self.env["res.users"].sudo().browse(request.session.uid)
                return bool(user.exists()) and not user.share
            return False

        return Resolution(
            digest,
            {"token": token, "user_id": user_id},
            (
                digest,
                self.env._("%(digest)s unsubscribes", digest=digest.name),
                "unsubscribe",
            ),
            is_request_authorized,
        )

    def _get_unsubscribe_token(self, user_id):
        return tools.hmac(self.env(su=True), UNSUBSCRIBE_SCOPE, (self.id, user_id))

    def _is_unsubscribe_token(self, user_id, token) -> bool:
        self.check_singleton()
        return tools.is_hmac_valid(
            self.env, UNSUBSCRIBE_SCOPE, (self.id, user_id), token
        )


    def _get_kpi_data(self, company, user) -> list:
        self.check_singleton()
        kpi_names = self._get_fields_kpi()
        kpi_actions = self._get_kpi_actions(company, user)
        timeframes = self._get_timeframes(company)
        all_windows = tuple(
            (fields.Datetime.to_string(start), fields.Datetime.to_string(end))
            for __, pair in timeframes
            for start, end in pair
        )
        memo = {}
        self.env.cr.cache[KPI_AGGREGATE_MEMO] = memo
        ir_model_fields = self.env["ir.model.fields"]
        kpis = {
            name: {
                "kpi_name": name,
                "kpi_fullname": ir_model_fields._get(
                    self._name, name
                ).field_description,
                "kpi_action": kpi_actions.get(name),
                "kpi_col1": {},
                "kpi_col2": {},
                "kpi_col3": {},
            }
            for name in kpi_names
        }
        denied = set()

        digest = self.with_context(digest_windows=all_windows)
        try:
            kpis = digest._update_kpi_columns(
                kpis, kpi_names, timeframes, company, user, denied
            )
        finally:
            self.env.cr.cache.pop(KPI_AGGREGATE_MEMO, None)

        return [kpi for name, kpi in kpis.items() if name not in denied]

    def _update_kpi_columns(self, kpis, kpi_names, timeframes, company, user, denied):
        for col_index, (tf_name, (current, previous)) in enumerate(timeframes, start=1):
            for name in kpi_names:
                if name in denied:
                    continue
                value_field = f"{name}_value"
                try:
                    value = self._get_kpi_value(value_field, current, company, user)
                    previous_value = self._get_kpi_value(
                        value_field, previous, company, user
                    )
                except AccessError:
                    denied.add(name)
                    continue

                margin = self._get_margin_value(value, previous_value)
                field_type = self._fields[value_field].type
                if field_type == "monetary":
                    value = self._format_currency_amount(
                        tools.misc.format_decimalized_amount(value),
                        company.currency_id,
                    )
                elif field_type == "float":
                    value = "%.2f" % value

                kpis[name][f"kpi_col{col_index}"].update(
                    {
                        "value": value,
                        "margin": margin,
                        "col_subtitle": tf_name,
                    }
                )

        return kpis

    def _get_kpi_value(self, value_field, window, company, user):
        digest = (
            self.with_context(
                start_datetime=window[0],
                end_datetime=window[1],
            )
            .with_user(user)
            .with_company(company)
        )
        try:
            return digest[value_field]
        finally:
            digest.invalidate_recordset([value_field], flush=False)

    def _get_unloaded_tip_ids(self):
        loaded = self.env.registry.loaded_modules
        if not loaded:
            return []
        return (
            self.env["ir.model.data"]
            .sudo()
            .search_fetch(
                [("model", "=", "digest.tip"), ("module", "not in", list(loaded))],
                ["res_id"],
            )
            .mapped("res_id")
        )

    def _acquire_tips(
        self, company, user, tips_count: int = 1, consumed: bool = True
    ) -> list[str]:
        tips = self.env["digest.tip"].search(
            [
                ("user_ids", "not in", user.id),
                ("id", "not in", self._get_unloaded_tip_ids()),
                "|",
                ("group_id", "in", user.all_group_ids.ids),
                ("group_id", "=", False),
            ],
            limit=tips_count,
        )
        tip_descriptions = [
            tools.html_sanitize(
                self.env["mixin.mail.render"]
                .sudo()
                ._render_template(
                    tip.tip_description,
                    "digest.tip",
                    tip.ids,
                    engine="qweb",
                    options={"post_process": True},
                )[tip.id]
            )
            for tip in tips
        ]
        if consumed:
            tips.sudo().user_ids = [Command.link(user.id)]
        return tip_descriptions

    def _get_kpi_actions(self, company, user):
        return {}

    def _get_preferences(self, company, user):
        preferences = []
        if self.env.context.get("digest_slowdown"):
            __, new_perioridicy_str = self._get_next_periodicity()
            preferences.append(
                self.env._(
                    "We have noticed you did not connect these last few days. We have automatically switched your preference to %(new_perioridicy_str)s Digests.",
                    new_perioridicy_str=new_perioridicy_str,
                )
            )
        elif self.periodicity == "daily" and user.has_group("base.group_erp_manager"):
            preferences.append(
                Markup(
                    '<p>%s<br /><a href="%s" target="_blank" style="color:#017e84; font-weight: bold;">%s</a></p>'
                )
                % (
                    self.env._("Prefer a broader overview?"),
                    f"/digest/{self.id:d}/set_periodicity?periodicity=weekly",
                    self.env._("Switch to weekly Digests"),
                )
            )
        if user.has_group("base.group_erp_manager"):
            preferences.append(
                Markup(
                    '<p>%s<br /><a href="%s" target="_blank" style="color:#017e84; font-weight: bold;">%s</a></p>'
                )
                % (
                    self.env._("Want to customize this email?"),
                    f"/odoo/{self._name}/{self.id:d}",
                    self.env._("Choose the metrics you care about"),
                )
            )

        return preferences

    def _get_next_run_date(self, periodicity=None):
        if periodicity is None:
            self.check_singleton()
            periodicity = self.periodicity
        return fields.Date.today() + PERIODICITIES[periodicity].run

    def _get_timeframes(self, company):
        start_datetime = datetime.now(UTC)
        tz_name = company.partner_id.tz
        if tz_name:
            start_datetime = start_datetime.astimezone(timezone(tz_name))

        def window(start_delta, end_delta=None):
            start = start_datetime + start_delta
            end = start_datetime + end_delta if end_delta else start_datetime
            return (
                start.astimezone(UTC).replace(tzinfo=None),
                end.astimezone(UTC).replace(tzinfo=None),
            )

        return [
            (
                self.env._("Last 24 hours"),
                (
                    window(relativedelta(days=-1)),
                    window(relativedelta(days=-2), relativedelta(days=-1)),
                ),
            ),
            (
                self.env._("Last 7 Days"),
                (
                    window(relativedelta(weeks=-1)),
                    window(relativedelta(weeks=-2), relativedelta(weeks=-1)),
                ),
            ),
            (
                self.env._("Last 30 Days"),
                (
                    window(relativedelta(months=-1)),
                    window(relativedelta(months=-2), relativedelta(months=-1)),
                ),
            ),
        ]


    def _update_company_based_kpi(
        self,
        model,
        digest_kpi_field,
        date_field="create_date",
        additional_domain=None,
        sum_field=None,
    ) -> None:
        start, end, companies = self._get_kpi_compute_parameters()
        extra_domain = Domain(additional_domain) if additional_domain else Domain.TRUE

        values_per_company = self._read_kpi_over_windows(
            digest_kpi_field,
            model,
            date_field,
            extra_domain,
            sum_field,
            companies,
        )
        if values_per_company is None:
            base_domain = (
                Domain(
                    [
                        ("company_id", "in", companies.ids),
                        (date_field, ">=", start),
                        (date_field, "<", end),
                    ]
                )
                & extra_domain
            )
            values = self.env[model]._read_group(
                domain=base_domain,
                groupby=["company_id"],
                aggregates=[f"{sum_field}:sum"] if sum_field else ["__count"],
            )
            values_per_company = {company.id: agg for company, agg in values}
        else:
            values_per_company = {
                company_id: per_window[(start, end)]
                for company_id, per_window in values_per_company.items()
            }

        for digest in self:
            company = digest.company_id or self.env.company
            digest[digest_kpi_field] = values_per_company.get(company.id, 0)

    def _read_kpi_over_windows(
        self, digest_kpi_field, model, date_field, extra_domain, sum_field, companies
    ):
        windows = self.env.context.get("digest_windows")
        memo = self.env.cr.cache.get(KPI_AGGREGATE_MEMO)
        if not windows or memo is None:
            return None

        Model = self.env[model]
        needed = [date_field, "company_id", *filter(None, [sum_field])]
        if not all(Model._fields[name].store for name in needed):
            return None

        key = (
            digest_kpi_field,
            model,
            date_field,
            sum_field,
            windows,
            tuple(companies.ids),
            self.env.uid,
            self.env.su,
        )
        if key in memo:
            return memo[key]

        lo = min(start for start, __ in windows)
        hi = max(end for __, end in windows)
        query = Model._search(
            Domain(
                [
                    ("company_id", "in", companies.ids),
                    (date_field, ">=", lo),
                    (date_field, "<", hi),
                ]
            )
            & extra_domain
        )

        date_sql = Model._field_to_sql(Model._table, date_field, query)
        company_sql = Model._field_to_sql(Model._table, "company_id", query)
        if sum_field:
            value_sql = Model._field_to_sql(Model._table, sum_field, query)
            aggregate = lambda window: SQL(
                "COALESCE(SUM(%s) FILTER (WHERE %s >= %s AND %s < %s), 0)",
                value_sql,
                date_sql,
                window[0],
                date_sql,
                window[1],
            )
        else:
            aggregate = lambda window: SQL(
                "COUNT(*) FILTER (WHERE %s >= %s AND %s < %s)",
                date_sql,
                window[0],
                date_sql,
                window[1],
            )

        sql = SQL(
            "%s GROUP BY %s",
            query.select(company_sql, *(aggregate(w) for w in windows)),
            company_sql,
        )
        result = {
            row[0]: dict(zip(windows, row[1:], strict=True))
            for row in self.env.execute_query(sql)
        }
        memo[key] = result
        return result

    @api.model
    def _get_kpi_boolean_names(self) -> list:
        return [
            field_name
            for field_name, field in self._fields.items()
            if field.type == "boolean" and field_name.startswith(KPI_PREFIXES)
        ]

    def _get_fields_kpi(self) -> list:
        return [name for name in self._get_kpi_boolean_names() if self[name]]

    def _get_margin_value(self, value, previous_value=0.0):
        if value == previous_value or not previous_value:
            return 0.0
        return float_round(
            (value - previous_value) / previous_value * 100, precision_digits=2
        )

    def _get_digests_to_slowdown(self):
        now = fields.Datetime.now()
        recipients = self.user_ids
        last_log_per_user = (
            dict(
                self.env["res.users.log"]
                .sudo()
                ._read_group(
                    [("create_uid", "in", recipients.ids)],
                    groupby=["create_uid"],
                    aggregates=["create_date:max"],
                )
            )
            if recipients
            else {}
        )

        to_slowdown = self.browse()
        for digest in self:
            limit_dt = now - PERIODICITIES[digest.periodicity].idle
            if not any(
                (last_log := last_log_per_user.get(user)) and last_log >= limit_dt
                for user in digest.user_ids
            ):
                to_slowdown += digest
        return to_slowdown

    def _get_next_periodicity(self) -> tuple:
        slower = PERIODICITIES[self.periodicity].slower
        selection_labels = dict(
            self._fields["periodicity"]._description_selection(self.env)
        )
        return slower, selection_labels[slower].lower()

    def _format_currency_amount(self, amount, currency_id) -> str:
        symbol = currency_id.symbol or ""
        if currency_id.position == "before":
            return f"{symbol}{amount}"
        return f"{amount}{symbol}"
