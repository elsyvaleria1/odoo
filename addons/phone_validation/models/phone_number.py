import logging
import re
from collections import defaultdict

from odoo import api, fields, models
from odoo.db.schema import create_index
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, normalize_identifier

from odoo.addons.phone_validation.tools import phone_validation

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

PHONE_NOISE_SQL_PATTERN = r"[\s\\./\(\)\-]"
PHONE_NOISE_PATTERN = re.compile(PHONE_NOISE_SQL_PATTERN)


class PhoneNumber(models.Model):
    _inherit = "phone.number"
    _phone_search_min_length = 3

    valid = fields.Boolean(
        compute="_compute_valid",
        store=True,
    )
    blacklisted = fields.Boolean(
        compute="_compute_blacklisted",
        search="_search_blacklisted",
        compute_sudo=True,
        classification="base.internal",
    )

    def init(self) -> None:
        super().init()
        for fname in ("number", "sanitized"):
            expression = (
                f"regexp_replace(({fname}::text), "
                f"'{PHONE_NOISE_SQL_PATTERN}'::text, ''::text, 'g'::text)"
            )
            create_index(
                self.env.cr,
                indexname=normalize_identifier(f"{self._table}_{fname}_partial_tgm"),
                tablename=self._table,
                expressions=[expression],
                where=f"{fname} IS NOT NULL",
            )
            if self.env.registry.has_trigram:
                create_index(
                    self.env.cr,
                    indexname=normalize_identifier(
                        f"{self._table}_{fname}_partial_gin_idx"
                    ),
                    tablename=self._table,
                    method="gin",
                    expressions=[expression + " gin_trgm_ops"],
                    where=f"{fname} IS NOT NULL",
                )

    @api.model
    def _e164(self, number, country=None):
        return self._e164_in_country(number, country or self.env.company.country_id)

    @api.model
    def _e164_in_country(self, number, country):
        if not number:
            return False
        if not country and not number.lstrip().startswith(("+", "00")):
            return False
        try:
            return phone_validation.phone_format(
                number,
                country.code if country else None,
                country.phone_code if country else None,
                force_format="E164",
                raise_exception=True,
            )
        except UserError:
            return False

    @api.model
    def _normalize_number(self, number, country=None):
        return self._e164(number, country) or super()._normalize_number(number, country)

    @api.model
    def _normalize_number_without_validation(self, number, country=None):
        return super()._normalize_number(number, country)

    @api.model
    def _get_rekeyed_sanitized(self, rows):
        Country = self.env["res.country"]
        keys, local = {}, {}
        for phone_id, number, country_id, sanitized in rows:
            unvalidated = self._normalize_number_without_validation(number)
            if country_id:
                keys[phone_id] = self._normalize_number(
                    number, Country.browse(country_id)
                )
            elif unvalidated.startswith("+"):
                keys[phone_id] = self._e164_in_country(unvalidated, None) or unvalidated
            elif (sanitized or "").startswith("+"):
                keys[phone_id] = sanitized
            else:
                local[phone_id] = (number, sanitized)
        countries = self._get_evidenced_countries(list(local))
        for phone_id, (number, sanitized) in local.items():
            country = countries.get(phone_id)
            keys[phone_id] = (
                self._normalize_number(number, country) if country else sanitized
            )
        return keys

    @api.model
    def _get_rekeyed_sanitized_without_validation(self, rows):
        Country = self.env["res.country"]
        return {
            phone_id: self._normalize_number_without_validation(
                number, Country.browse(country_id)
            )
            for phone_id, number, country_id, _ in rows
        }

    @api.model
    def _get_evidenced_countries(self, phone_ids):
        if not phone_ids:
            return {}
        self.env.flush_all()
        evidence = defaultdict(set)
        for query in self._get_country_evidence_queries(phone_ids):
            self.env.cr.execute(query)
            for phone_id, *country_ids in self.env.cr.fetchall():
                evidence[phone_id].update(filter(None, country_ids))
        companies_country = self._get_companies_country()
        countries, unresolved = {}, defaultdict(list)
        for phone_id in phone_ids:
            found = evidence.get(phone_id) or set(companies_country.ids)
            if len(found) == 1:
                countries[phone_id] = self.env["res.country"].browse(found)
            else:
                unresolved["ambiguous" if found else "unknown"].append(phone_id)
        for reason, ids in unresolved.items():
            _logger.info(
                "%d phone numbers keep their key, their country being %s: %s",
                len(ids),
                reason,
                ids[:20],
            )
        _debug.logic(
            "rekey_countries_evidenced",
            phones=len(phone_ids),
            linked=len(evidence),
            evidenced=len(countries),
        )
        return countries

    @api.model
    def _get_country_evidence_queries(self, phone_ids):
        seen = set()
        for model in self.env.registry.values():
            if model._abstract or model._transient or not model._auto:
                continue
            country = self._get_evidence_column(model, "country_id", "res.country")
            company = self._get_evidence_column(model, "company_id", "res.company")
            if not (country or company):
                continue
            for field in model._fields.values():
                if (
                    field.comodel_name != self._name
                    or not field.store
                    or field.inherited
                    or field.type not in ("many2one", "many2many")
                ):
                    continue
                link = (
                    (field.relation, field.column1, field.column2)
                    if field.type == "many2many"
                    else (model._table, "id", field.name)
                )
                if link in seen:
                    continue
                seen.add(link)
                yield self._get_country_evidence_query(
                    model, link, country, company, phone_ids
                )

    @api.model
    def _get_evidence_column(self, model, fname, comodel_name):
        field = model._fields.get(fname)
        if (
            field
            and field.type == "many2one"
            and field.comodel_name == comodel_name
            and field.store
            and not field.inherited
        ):
            return fname
        return None

    @api.model
    def _get_country_evidence_query(self, model, link, country, company, phone_ids):
        table, record_column, phone_column = link
        return SQL(
            """
            SELECT link.%(phone)s, %(country)s, company_partner.country_id
              FROM %(table)s AS link
              JOIN %(records)s AS rec ON rec.id = link.%(record)s
              LEFT JOIN res_company AS company ON company.id = %(company)s
              LEFT JOIN res_partner AS company_partner
                     ON company_partner.id = company.partner_id
             WHERE link.%(phone)s = ANY(%(phone_ids)s)
            """,
            phone=SQL.identifier(phone_column),
            table=SQL.identifier(table),
            records=SQL.identifier(model._table),
            record=SQL.identifier(record_column),
            country=SQL.identifier("rec", country) if country else SQL("NULL::int"),
            company=SQL.identifier("rec", company) if company else SQL("NULL::int"),
            phone_ids=list(phone_ids),
        )

    @api.model
    def _get_companies_country(self):
        self.env.cr.execute(
            SQL(
                "SELECT DISTINCT partner.country_id FROM res_company AS company"
                " JOIN res_partner AS partner ON partner.id = company.partner_id"
            )
        )
        country_ids = [country_id for (country_id,) in self.env.cr.fetchall()]
        if None in country_ids or len(country_ids) != 1:
            return self.env["res.country"]
        return self.env["res.country"].browse(country_ids)

    @api.model
    def _rekey_local_sanitized(self):
        self._rekey_sanitized(
            where=SQL(
                "country_id IS NULL AND sanitized NOT LIKE %s",
                "+%",
            )
        )

    @api.depends("number", "country_id")
    def _compute_valid(self) -> None:
        for phone in self:
            phone.valid = bool(self._e164(phone.number, phone.country_id))

    @api.depends("sanitized")
    def _compute_blacklisted(self) -> None:
        numbers = [number for number in self.mapped("sanitized") if number]
        blacklist = (
            set(
                self.env["phone.blacklist"]
                .search([("number", "in", numbers)])
                .mapped("number")
            )
            if numbers
            else set()
        )
        for phone in self:
            phone.blacklisted = phone.sanitized in blacklist

    @api.model
    def _search_blacklisted(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        self.env.cr.execute(
            SQL(
                "SELECT pn.id FROM phone_number pn "
                "JOIN phone_blacklist bl ON bl.number = pn.sanitized AND bl.active"
            )
        )
        ids = [row[0] for row in self.env.cr.fetchall()]
        return [("id", operator, ids)]

    @api.onchange("number", "country_id")
    def _onchange_number(self) -> None:
        if self.number:
            country = self.country_id or self.env.company.country_id
            self.number = (
                self._phone_format_number(
                    self.number, country, force_format="INTERNATIONAL"
                )
                or self.number
            )

    @api.model
    def _search_number_terms(self, operator, value) -> list:
        value = value.strip() if isinstance(value, str) else value
        if not value:
            return []
        if self._phone_search_min_length and len(value) < self._phone_search_min_length:
            raise UserError(
                self.env._(
                    "Please enter at least 3 characters when searching a Phone number."
                )
            )
        if value.startswith(("+", "00")):
            term = PHONE_NOISE_PATTERN.sub(
                "", value[1 if value.startswith("+") else 2 :]
            )
            if operator not in ("=", "!="):
                term = f"{term}%"
            return ["00" + term, "+" + term]
        term = PHONE_NOISE_PATTERN.sub("", value)
        if operator not in ("=", "!="):
            term = f"%{term}%"
        return [term]

    @api.model
    def _search_number_ids(self, operator, value) -> list:
        if operator == "in":
            operator, values = "=", value
        else:
            values = [value]
        terms = [
            term
            for value in values
            for term in self._search_number_terms(operator, value)
        ]
        if not terms:
            return []
        sql_operator = {"=like": "LIKE", "=ilike": "ILIKE"}.get(operator, operator)
        clauses = [
            SQL(
                "REGEXP_REPLACE(pn.%s, %s, '', 'g') %s %s",
                SQL.identifier(fname),
                PHONE_NOISE_SQL_PATTERN,
                SQL(sql_operator),
                term,
            )
            for fname in ("number", "sanitized")
            for term in terms
        ]
        self.env.cr.execute(
            SQL(
                "SELECT pn.id FROM phone_number pn WHERE %s",
                SQL(" OR ").join(clauses),
            )
        )
        return [row[0] for row in self.env.cr.fetchall()]

    @api.model
    def _search_phone_domain(self, fnames, operator, value):
        if isinstance(value, str):
            value = value.strip()
        if not fnames:
            raise UserError(self.env._("Missing definition of phone fields."))
        if operator in ("in", "not in"):
            values = [v.strip() if isinstance(v, str) else v for v in value]
            if any(v is True or not v for v in values):
                aggregator = Domain.OR if operator == "in" else Domain.AND
                return aggregator(
                    self._search_phone_domain(
                        fnames, "=" if operator == "in" else "!=", v
                    )
                    for v in values
                )
            ids = self._search_number_ids("in", values)
            if operator == "not in":
                return Domain.AND(Domain(fname, "not in", ids) for fname in fnames)
            return Domain.OR(Domain(fname, "in", ids) for fname in fnames)
        if (value is True or not value) and operator in ("=", "!="):
            if value:
                operator = "=" if operator == "!=" else "!="
            op = Domain.AND if operator == "=" else Domain.OR
            return op(Domain(fname, operator, False) for fname in fnames)
        if not value:
            return Domain.TRUE
        positive = {"!=": "=", "not like": "like", "not ilike": "ilike"}
        if operator in positive:
            ids = self._search_number_ids(positive[operator], value)
            return Domain.AND(Domain(fname, "not in", ids) for fname in fnames)
        ids = self._search_number_ids(operator, value)
        return Domain.OR(Domain(fname, "in", ids) for fname in fnames)
