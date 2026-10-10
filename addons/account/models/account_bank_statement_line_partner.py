import re
from collections import defaultdict

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_debug = DebugLog(__name__)

_DIGIT_RUN = re.compile(r"\d+")
# One earlier transaction is an anecdote; the label of a transfer between
# strangers repeats that often by chance.
COUNTERPARTY_KEY_MIN_PRECEDENTS = 2
# The bank names the counterparty outright, so one reviewed transaction with that
# name is as strong as the name lookup that runs before it.
PARTNER_NAME_MIN_PRECEDENTS = 1
COUNTERPARTY_KEY_PRECEDENTS_READ = 3
PARTNER_SUGGESTION_SOURCES = [
    (
        "name_precedent_unreviewed",
        "Earlier transactions with this name, not yet reviewed",
    ),
    (
        "counterparty_unreviewed",
        "Earlier transactions with this label, not yet reviewed",
    ),
    (
        "name_precedent_open",
        "Open transactions with this name, partner set by hand",
    ),
    (
        "counterparty_open",
        "Open transactions with this label, partner set by hand",
    ),
]


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    counterparty_key = fields.Char(
        compute="_compute_counterparty_key",
        store=True,
        index="btree_not_null",
        help="What the label says about the other party, in a form that repeats "
        "from one transaction with it to the next: the label with its numbers "
        "blanked, unless the statement format knows a better identifier. A new "
        "transaction takes the partner of the earlier ones carrying the same key.",
    )
    suggested_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Suggested Partner",
        copy=False,
        readonly=True,
        ondelete="set null",
        check_company=True,
        help="A partner the earlier transactions point at without anyone having "
        "confirmed them. It is only shown: matching and reconciliation models "
        "read the partner, never the suggestion.",
    )
    partner_suggestion_source = fields.Selection(
        selection=PARTNER_SUGGESTION_SOURCES,
        string="Suggested From",
        copy=False,
        readonly=True,
    )
    is_partner_manual = fields.Boolean(
        string="Partner Set by Hand",
        copy=False,
        readonly=True,
        help="Someone chose the partner of this transaction after it was "
        "created, rather than the import, a partner lookup or a reconciliation "
        "model giving it. Only such a partner, on a transaction still open, "
        "suggests a partner to the later ones.",
    )

    def write(self, vals):
        if "partner_id" in vals:
            vals = {"is_partner_manual": bool(vals["partner_id"]), **vals}
            if vals["partner_id"]:
                vals |= {
                    "suggested_partner_id": False,
                    "partner_suggestion_source": False,
                }
        return super().write(vals)

    @api.depends("payment_ref")
    def _compute_counterparty_key(self) -> None:
        for st_line in self:
            st_line.counterparty_key = st_line._get_counterparty_key()

    def _get_counterparty_key(self) -> str | None:
        """Return the identifier of the other party this transaction's label carries.

        The numbers of a label are what changes between two payments to one
        party (references, dates, folios), so blanking them leaves what
        repeats. A statement format that names the counterparty outright (an
        account, an agreement, a merchant id) overrides this with that name.
        """
        self.check_singleton()
        label = " ".join((self.payment_ref or "").upper().split())
        return _DIGIT_RUN.sub("#", label) or None

    _PARTNER_MATCH_RANKS = {
        "bank_account": (
            "account_matching_partner_with_company",
            "account_matching_partner_without_company",
        ),
        "partner_name": (
            "full_name_matching_partner_with_company",
            "full_name_matching_partner_without_company",
            "partial_name_matching_partner_with_company",
            "partial_name_matching_partner_without_company",
        ),
    }

    @api.model
    def _first_unambiguous_partner(self, row, ranks):
        for bucket in ranks:
            candidates = row.get(bucket) or []
            if len(candidates) == 1:
                return candidates[0]
        return None

    def _partners_by_bank_account(self) -> dict:
        lines = self.filtered("account_number")
        if not lines:
            return {}
        query = SQL(
            """
            SELECT ARRAY_AGG(DISTINCT partner_bank.partner_id) FILTER (WHERE partner_bank.company_id::TEXT = ANY(STRING_TO_ARRAY(company.parent_path, '/'))) AS account_matching_partner_with_company,
                   ARRAY_AGG(DISTINCT partner_bank.partner_id) FILTER (WHERE partner_bank.company_id IS NULL) AS account_matching_partner_without_company,
                   st_line.id AS st_line_id
              FROM res_partner_bank_account partner_bank
              JOIN account_bank_statement_line st_line ON partner_bank.sanitized_acc_number = NULLIF(REGEXP_REPLACE(st_line.account_number, '\\W+', '', 'g'), '')
              JOIN res_company company ON company.id = st_line.company_id
              JOIN res_partner partner ON partner.id = partner_bank.partner_id
             WHERE st_line.id = ANY(%(st_line_ids)s)
               AND partner.active
          GROUP BY st_line.id
        """,
            st_line_ids=lines.ids,
        )
        ranks = self._PARTNER_MATCH_RANKS["bank_account"]
        return {
            row["st_line_id"]: partner_id
            for row in self.env.execute_query_dict(query)
            if (partner_id := self._first_unambiguous_partner(row, ranks))
        }

    @_debug.perf.timed
    def _partners_by_transaction_name(self) -> dict:
        lines = self.filtered("partner_name")
        _debug.pipeline(
            "partner_name_lookup_started",
            stline=self,
            with_partner_name=len(lines),
        )
        if not lines:
            return {}
        query = SQL(
            r"""
            SELECT ARRAY_AGG(partner.id) FILTER (WHERE partner.complete_name ILIKE st_line.name_pattern ESCAPE '\' AND partner.company_id::TEXT = ANY(STRING_TO_ARRAY(company.parent_path, '/'))) AS full_name_matching_partner_with_company,
                   ARRAY_AGG(partner.id) FILTER (WHERE partner.complete_name ILIKE st_line.name_pattern ESCAPE '\' AND partner.company_id IS NULL) AS full_name_matching_partner_without_company,
                   ARRAY_AGG(partner.id) FILTER (WHERE partner.complete_name ILIKE ('%%' || st_line.name_pattern || '%%') ESCAPE '\' AND partner.company_id::TEXT = ANY(STRING_TO_ARRAY(company.parent_path, '/'))) AS partial_name_matching_partner_with_company,
                   ARRAY_AGG(partner.id) FILTER (WHERE partner.complete_name ILIKE ('%%' || st_line.name_pattern || '%%') ESCAPE '\' AND partner.company_id IS NULL) AS partial_name_matching_partner_without_company,
                   st_line.id AS st_line_id
              FROM res_partner partner
              JOIN (
                        SELECT id,
                               company_id,
                               REPLACE(REPLACE(REPLACE(NULLIF(TRIM(partner_name), ''), '\', '\\'), '%%', '\%%'), '_', '\_') AS name_pattern
                          FROM account_bank_statement_line
                         WHERE id = ANY(%(st_line_ids)s)
                   ) st_line ON partner.complete_name ILIKE ('%%' || st_line.name_pattern || '%%') ESCAPE '\'
              JOIN res_company company ON company.id = st_line.company_id
             WHERE partner.parent_id IS NULL
               AND partner.id != ALL(%(blacklisted_partner_ids)s)
               AND partner.active
          GROUP BY st_line.id
        """,
            st_line_ids=lines.ids,
            blacklisted_partner_ids=self._get_blacklisted_partners().ids,
        )
        ranks = self._PARTNER_MATCH_RANKS["partner_name"]
        return {
            row["st_line_id"]: partner_id
            for row in self.env.execute_query_dict(query)
            if (partner_id := self._first_unambiguous_partner(row, ranks))
        }

    def _get_precedent_condition(self, precedents) -> SQL:
        match precedents:
            case "reviewed":
                return SQL("st_line.is_reconciled IS TRUE AND move.checked IS TRUE")
            case "reconciled":
                return SQL("st_line.is_reconciled IS TRUE")
            case "open":
                # creating a line never marks its partner manual, so neither
                # the asking lines nor the batch imported with them count
                return SQL(
                    "st_line.is_reconciled IS NOT TRUE AND st_line.is_partner_manual IS TRUE"
                )
            case _:
                raise ValueError(precedents)

    def _partners_by_precedents(
        self, key_field, min_precedents, precedents="reviewed"
    ) -> dict:
        lines = self.filtered(key_field)
        _debug.pipeline(
            "precedents_lookup_started",
            stline=self,
            key_field=key_field,
            precedents=precedents,
            with_key=len(lines),
        )
        if not lines:
            return {}
        key = SQL.identifier("st_line", key_field)
        query = SQL(
            """
            WITH precedents AS (
                SELECT st_line.partner_id,
                       st_line.company_id,
                       %(key)s AS key,
                       ROW_NUMBER() OVER (
                           PARTITION BY st_line.company_id, %(key)s
                               ORDER BY st_line.id DESC
                       ) AS row_number
                  FROM account_bank_statement_line st_line
                  JOIN res_partner partner ON partner.id = st_line.partner_id
                  JOIN account_move move ON move.id = st_line.move_id
                 WHERE %(condition)s
                   AND %(key)s = ANY(%(keys)s)
                   AND st_line.company_id = ANY(%(company_ids)s)
                   AND partner.active
            )
            SELECT MIN(partner_id) AS partner_id,
                   company_id,
                   key
              FROM precedents
             WHERE row_number <= %(read)s
          GROUP BY company_id, key
            HAVING COUNT(DISTINCT partner_id) = 1
               AND COUNT(*) >= %(minimum)s
        """,
            key=key,
            condition=self._get_precedent_condition(precedents),
            keys=list(set(lines.mapped(key_field))),
            company_ids=lines.company_id.ids,
            read=COUNTERPARTY_KEY_PRECEDENTS_READ,
            minimum=min_precedents,
        )
        by_key = {
            (row["company_id"], row["key"]): row["partner_id"]
            for row in self.env.execute_query_dict(query)
        }
        _debug.pipeline(
            "precedents_resolved",
            stline=self,
            key_field=key_field,
            precedents=precedents,
            unanimous_keys=len(by_key),
        )
        return {
            line.id: partner_id
            for line in lines
            if (partner_id := by_key.get((line.company_id.id, line[key_field])))
        }

    @_debug.perf.timed
    def _partners_by_earlier_transactions(self) -> dict:
        return self._partners_by_precedents("partner_name", PARTNER_NAME_MIN_PRECEDENTS)

    @_debug.perf.timed
    def _partners_by_counterparty_key(self) -> dict:
        return self._partners_by_precedents(
            "counterparty_key", COUNTERPARTY_KEY_MIN_PRECEDENTS
        )

    @_debug.perf.timed
    def _partners_by_unreviewed_earlier_transactions(self) -> dict:
        return self._partners_by_precedents(
            "partner_name", PARTNER_NAME_MIN_PRECEDENTS, precedents="reconciled"
        )

    @_debug.perf.timed
    def _partners_by_unreviewed_counterparty_key(self) -> dict:
        return self._partners_by_precedents(
            "counterparty_key", COUNTERPARTY_KEY_MIN_PRECEDENTS, precedents="reconciled"
        )

    @_debug.perf.timed
    def _partners_by_open_earlier_transactions(self) -> dict:
        return self._partners_by_precedents(
            "partner_name", PARTNER_NAME_MIN_PRECEDENTS, precedents="open"
        )

    @_debug.perf.timed
    def _partners_by_open_counterparty_key(self) -> dict:
        return self._partners_by_precedents(
            "counterparty_key", COUNTERPARTY_KEY_MIN_PRECEDENTS, precedents="open"
        )

    def _get_partner_lookups(self) -> list:
        """Return the names of the partner lookups, most trusted first.

        Each takes the lines still without a partner and returns the partner
        id it is sure of per line id; a line the earlier ones settled never
        reaches the later ones.
        """
        return [
            "_partners_by_bank_account",
            "_partners_by_transaction_name",
            "_partners_by_earlier_transactions",
            "_partners_by_counterparty_key",
        ]

    def _get_partner_suggestion_lookups(self) -> list:
        """Return the lookups that only suggest a partner, with the source each
        records, most trusted first.

        They run on the lines no lookup of ``_get_partner_lookups`` settled.
        """
        return [
            (
                "_partners_by_unreviewed_earlier_transactions",
                "name_precedent_unreviewed",
            ),
            ("_partners_by_unreviewed_counterparty_key", "counterparty_unreviewed"),
            ("_partners_by_open_earlier_transactions", "name_precedent_open"),
            ("_partners_by_open_counterparty_key", "counterparty_open"),
        ]

    def _set_partner_from_transaction(self) -> None:
        lines = self.filtered(lambda st_line: not st_line.partner_id)
        if not lines:
            return

        self.env.flush_all()

        for lookup in self._get_partner_lookups():
            decided = defaultdict(list)
            for st_line_id, partner_id in getattr(lines, lookup)().items():
                decided[partner_id].append(st_line_id)
            _debug.logic(
                "_set_partner_from_transaction",
                lookup=lookup,
                lines_count=len(lines),
                decided_count=len(decided),
            )
            for partner_id, st_line_ids in decided.items():
                self.browse(st_line_ids).write(
                    {"partner_id": partner_id, "is_partner_manual": False}
                )

            lines = lines.filtered(lambda st_line: not st_line.partner_id)
            if not lines:
                return

        lines._suggest_partner_from_transaction()

    def _suggest_partner_from_transaction(self) -> None:
        suggestions = {}
        pending = self
        for lookup, source in self._get_partner_suggestion_lookups():
            found = getattr(pending, lookup)()
            _debug.logic(
                "_suggest_partner_from_transaction",
                lookup=lookup,
                source=source,
                lines_count=len(pending),
                suggested_count=len(found),
            )
            for st_line_id, partner_id in found.items():
                suggestions[st_line_id] = (partner_id, source)
            pending -= self.browse(list(found))
            if not pending:
                break

        by_suggestion = defaultdict(list)
        for st_line in self:
            current = (
                st_line.suggested_partner_id.id,
                st_line.partner_suggestion_source,
            )
            wanted = suggestions.get(st_line.id, (False, False))
            if current != wanted:
                by_suggestion[wanted].append(st_line.id)
        for (partner_id, source), st_line_ids in by_suggestion.items():
            self.browse(st_line_ids).write(
                {
                    "suggested_partner_id": partner_id,
                    "partner_suggestion_source": source,
                }
            )

    def action_accept_partner_suggestion(self) -> None:
        for partner, st_lines in (
            self.filtered(
                lambda st_line: st_line.suggested_partner_id and not st_line.partner_id
            )
            .grouped("suggested_partner_id")
            .items()
        ):
            _debug.logic(
                "action_accept_partner_suggestion",
                stline=st_lines,
                partner=partner,
            )
            st_lines.set_partner_bank_statement_line(partner.id)

    def _get_blacklisted_partners(self):
        partners = self.env.ref("base.partner_root")
        if ai_agent := self.env.ref("ai.ai_default_agent", raise_if_not_found=False):
            partners += ai_agent.partner_id
        return partners

    def _get_partner_id(self, lines_to_add_partner_ids):
        self.check_singleton()
        if len(lines_to_add_partner_ids) == 1:
            return lines_to_add_partner_ids.pop()
        if len(lines_to_add_partner_ids) == 0:
            return self.partner_id.id
        return None

    def set_partner_bank_statement_line(self, partner_id) -> None:
        all_statement_lines = self
        same_name_domains = [
            Domain("journal_id", "=", journal.id)
            & Domain("partner_name", "in", partner_names)
            for journal, lines in self.grouped("journal_id").items()
            if (partner_names := lines.filtered("partner_name").mapped("partner_name"))
        ]
        if same_name_domains:
            all_statement_lines |= self.search(
                Domain.OR(same_name_domains)
                & Domain("is_reconciled", "=", False)
                & Domain("partner_id", "=", False)
            )

        same_name_lines = all_statement_lines - self
        same_name_lines.move_id._track_set_author(self.env.ref("base.partner_root"))
        for st_lines, is_partner_manual in ((self, True), (same_name_lines, False)):
            st_lines.with_context(force_delete=True, skip_readonly_check=True).write(
                {"partner_id": partner_id, "is_partner_manual": is_partner_manual}
            )
        all_statement_lines._try_auto_reconcile_statement_lines()
