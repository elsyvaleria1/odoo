import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import pytz
from babel.dates import format_date

from odoo import fields
from odoo.fields import Domain
from odoo.tools import SQL, remove_accents

TOP = 10
MAX_TOP = 30
MAX_MATCHES = 20


@dataclass(frozen=True)
class Query:
    """A business question the bot answers exactly: what it reads, and the
    words the classifier is given to recognise it."""

    key: str
    description: str
    run: object
    group_by: tuple = ()
    filters: tuple = ()
    periodic: bool = True
    requires: str = ""


@dataclass
class Ask:
    """One interpreted question, run against a read-only environment."""

    env: object
    tz: str
    today: date
    params: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    # what a report learns that the chat needs next, e.g. whose statement
    extras: dict = field(default_factory=dict)

    # -- parameters ------------------------------------------------------------

    @property
    def group(self):
        return self.params.get("group_by")

    @property
    def top(self) -> int:
        try:
            top = int(self.params.get("top") or TOP)
        except TypeError, ValueError:
            top = TOP
        return max(1, min(top, MAX_TOP))

    def period(self):
        """The asked period as inclusive dates, the current month by default."""
        start = _parse_date(self.params.get("date_from"))
        end = _parse_date(self.params.get("date_to"))
        if not start and not end:
            start, end = self.today.replace(day=1), self.today
        start = start or end.replace(day=1)
        end = end or self.today
        if end < start:
            start, end = end, start
        return start, end

    def datetime_range(self, field_name):
        """A domain bounding a datetime field by the period, in the owner's
        timezone: the database keeps UTC."""
        start, end = self.period()
        zone = pytz.timezone(self.tz)
        begin = zone.localize(datetime.combine(start, time.min)).astimezone(pytz.UTC)
        stop = zone.localize(
            datetime.combine(end + timedelta(days=1), time.min)
        ).astimezone(pytz.UTC)
        return [
            (field_name, ">=", fields.Datetime.to_string(begin.replace(tzinfo=None))),
            (field_name, "<", fields.Datetime.to_string(stop.replace(tzinfo=None))),
        ]

    def date_range(self, field_name):
        start, end = self.period()
        return [(field_name, ">=", start), (field_name, "<=", end)]

    def period_label(self) -> str:
        start, end = self.period()
        return f"{self.format_day(start)} – {self.format_day(end)}"

    def format_day(self, value) -> str:
        return format_date(value, "d MMM yyyy", locale=self.locale)

    def format_month(self, value) -> str:
        return format_date(value, "MMMM yyyy", locale=self.locale)

    @property
    def locale(self) -> str:
        return self.env.lang or "es_MX"

    def matches(self, model, value, fields_=("name",), extra=None):
        """The records of `model` whose name matches `value`, noted in the
        answer when the name is ambiguous."""
        found = find(self.env, model, value, fields_, extra)
        if not found:
            raise NotFound(self.env._("I could not find «%(value)s».", value=value))
        if len(found) > 1:
            names = ", ".join(found[:5].mapped("display_name"))
            more = "…" if len(found) > 5 else ""
            self.notes.append(
                self.env._(
                    "«%(value)s» matched: %(names)s%(more)s",
                    value=value,
                    names=names,
                    more=more,
                )
            )
        return found

    def filter_domain(self, mapping):
        """The domain of the filters the question names, by the field each
        filter reads on this query's model."""
        domain = []
        for name, (path, model, fields_, extra) in mapping.items():
            value = (self.params.get(name) or "").strip()
            if value:
                ids = self.matches(model, value, fields_, extra).ids
                operator = "child_of" if model == "res.partner" else "in"
                domain.append((path, operator, ids))
        return domain


_WORD = re.compile(r"\w{2,}")


def find(env, model, value, fields_=("name",), extra=None, limit=MAX_MATCHES):
    """The records of `model` a person means by `value`, as said or dictated.

    The whole phrase first; else every word of it, in any order and with
    anything between them ("Victor Juárez" is "Victor Hugo Juarez
    Hernandez"); else the same ignoring accents. Contacts that trade the most
    come first.
    """
    Model = env[model]
    base = list(extra or [])
    order = (
        "customer_rank desc, supplier_rank desc, id"
        if "customer_rank" in Model._fields
        else None
    )
    phrase = Domain.OR(Domain(name, "ilike", value) for name in fields_)
    found = Model.search(Domain(base) & phrase, limit=limit, order=order)
    if found:
        return found
    words = _WORD.findall(value or "")
    if not words:
        return found
    by_word = Domain.AND(
        Domain.OR(
            Domain(name, "ilike", variant)
            for name in fields_
            for variant in {word, remove_accents(word)}
        )
        for word in words
    )
    found = Model.search(Domain(base) & by_word, limit=limit, order=order)
    if found or model != "res.partner":
        return found
    # contacts keep their accents in plain text: unaccent both sides, where
    # the database has the extension
    env.cr.execute("SELECT 1 FROM pg_extension WHERE extname = 'unaccent'")
    if not env.cr.fetchone():
        return found
    clauses = SQL(" AND ").join(
        SQL("unaccent(name) ILIKE unaccent(%s)", f"%{word}%") for word in words
    )
    try:
        with env.cr.savepoint():
            env.cr.execute(
                SQL(
                    "SELECT id FROM res_partner WHERE active AND %s LIMIT %s",
                    clauses,
                    limit,
                )
            )
            ids = [row[0] for row in env.cr.fetchall()]
    except Exception:
        # a database without the unaccent extension: nothing more to try
        return found
    return Model.search(
        Domain(base) & Domain("id", "in", ids), limit=limit, order=order
    )


class NotFound(Exception):
    """A filter named something that does not exist: the message is the
    answer."""


# -- formatting -----------------------------------------------------------------


def money(amount, currency) -> str:
    return f"${amount:,.2f} {currency.name}"


def quantity(amount) -> str:
    return f"{amount:,.2f}".rstrip("0").rstrip(".")


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _label(ask, value):
    if isinstance(value, date):
        return ask.format_month(value)
    if hasattr(value, "display_name"):
        return value.display_name or ask.env._("(none)")
    return str(value) if value not in (None, False) else ask.env._("(none)")


def money_report(ask, title, model, domain, amount, currency_path, groups):
    """Total an amount by currency, and by the asked grouping."""
    group_path = None if ask.params.get("summary_only") else groups.get(ask.group)
    by = [currency_path] + ([group_path] if group_path else [])
    rows = ask.env[model]._read_group(domain, by, [f"{amount}:sum", "__count"])
    lines = [f"**{title}**", ask.period_label()] if title else []
    if not rows:
        lines.append(ask.env._("No records in that period."))
        return lines
    per_currency = defaultdict(list)
    for row in rows:
        per_currency[row[0]].append(row)
    for currency, currency_rows in per_currency.items():
        total = sum(row[-2] for row in currency_rows)
        count = sum(row[-1] for row in currency_rows)
        lines.append(
            ask.env._(
                "Total: **%(amount)s** (%(count)s documents)",
                amount=money(total, currency),
                count=count,
            )
        )
        if group_path:
            lines += _ranked(
                ask,
                [(_label(ask, row[1]), row[2], row[3]) for row in currency_rows],
                lambda value, currency=currency: money(value, currency),
                by_date=ask.group == "month",
            )
    return lines


def _ranked(ask, items, show, by_date=False):
    """`• label: value (count)` lines, largest first -- or in order for a
    time series -- cut to the asked top."""
    if not by_date:
        items = sorted(items, key=lambda item: item[1], reverse=True)
    shown = items if by_date else items[: ask.top]
    lines = [f"• {label}: {show(value)} ({count})" for label, value, count in shown]
    if len(items) > len(shown):
        lines.append(ask.env._("… and %(count)s more", count=len(items) - len(shown)))
    return lines


# -- the queries ------------------------------------------------------------------


def run_sales(ask):
    filters = ask.filter_domain(
        {
            "company": ("company_id", "res.company", ("name",), None),
            "warehouse": ("warehouse_id", "stock.warehouse", ("name", "code"), None),
            "partner": ("partner_id", "res.partner", ("name",), None),
            "salesperson": ("user_id", "res.users", ("name",), None),
        }
    )
    title = ask.env._("Confirmed sales orders, before taxes (counter sales excluded)")
    if ask.group == "product" or ask.params.get("product"):
        domain = [("order_id.state", "=", "done")] + [
            (f"order_id.{path}", operator, value) for path, operator, value in filters
        ]
        domain += ask.datetime_range("order_id.date_order")
        domain += ask.filter_domain(
            {
                "product": (
                    "product_id",
                    "product.product",
                    ("name", "default_code"),
                    None,
                )
            }
        )
        return money_report(
            ask,
            title,
            "sale.order.line",
            domain,
            "price_subtotal",
            "order_id.currency_id",
            {"product": "product_id", None: None},
        )
    domain = [("state", "=", "done")] + filters + ask.datetime_range("date_order")
    return money_report(
        ask,
        title,
        "sale.order",
        domain,
        "amount_untaxed",
        "currency_id",
        {
            "company": "company_id",
            "warehouse": "warehouse_id",
            "salesperson": "user_id",
            "partner": "partner_id",
            "month": "date_order:month",
        },
    )


def run_pos_sales(ask):
    filters = ask.filter_domain(
        {
            "company": ("company_id", "res.company", ("name",), None),
            "warehouse": (
                "config_id.warehouse_id",
                "stock.warehouse",
                ("name", "code"),
                None,
            ),
            "partner": ("partner_id", "res.partner", ("name",), None),
            "salesperson": ("user_id", "res.users", ("name",), None),
        }
    )
    title = ask.env._("Counter (point of sale) sales, taxes included")
    states = ("paid", "done")
    if ask.group == "product" or ask.params.get("product"):
        domain = [("order_id.state", "in", states)] + [
            (f"order_id.{path}", operator, value) for path, operator, value in filters
        ]
        domain += ask.datetime_range("order_id.date_order")
        domain += ask.filter_domain(
            {
                "product": (
                    "product_id",
                    "product.product",
                    ("name", "default_code"),
                    None,
                )
            }
        )
        return money_report(
            ask,
            title,
            "pos.order.line",
            domain,
            "price_subtotal_incl",
            "order_id.company_id.currency_id",
            {"product": "product_id", None: None},
        )
    domain = [("state", "in", states)] + filters + ask.datetime_range("date_order")
    return money_report(
        ask,
        title,
        "pos.order",
        domain,
        "amount_total",
        "company_id.currency_id",
        {
            "company": "company_id",
            "warehouse": "config_id.warehouse_id",
            "salesperson": "user_id",
            "partner": "partner_id",
            "month": "date_order:month",
        },
    )


def run_invoicing(ask):
    domain = [
        ("move_type", "in", ("out_invoice", "out_refund")),
        ("state", "=", "posted"),
    ]
    domain += ask.filter_domain(
        {
            "company": ("company_id", "res.company", ("name",), None),
            "partner": ("partner_id", "res.partner", ("name",), None),
            "salesperson": ("invoice_user_id", "res.users", ("name",), None),
        }
    )
    domain += ask.date_range("invoice_date")
    return money_report(
        ask,
        ask.env._("Customer invoicing, before taxes, net of credit notes"),
        "account.move",
        domain,
        "amount_untaxed_signed",
        "company_id.currency_id",
        {
            "company": "company_id",
            "partner": "partner_id",
            "salesperson": "invoice_user_id",
            "month": "invoice_date:month",
        },
    )


def _balance_report(ask, title, move_types, sign):
    domain = [
        ("move_type", "in", move_types),
        ("state", "=", "posted"),
        ("amount_residual_signed", "!=", 0),
    ]
    domain += ask.filter_domain(
        {
            "company": ("company_id", "res.company", ("name",), None),
            "partner": ("partner_id", "res.partner", ("name",), None),
        }
    )
    overdue = [("invoice_date_due", "<", ask.today)]
    if ask.params.get("overdue_only"):
        domain += overdue
    group_path = {"company": "company_id"}.get(ask.group, "partner_id")
    Move = ask.env["account.move"]
    lines = [f"**{title}**", ask.env._("As of %(day)s", day=ask.format_day(ask.today))]
    totals = Move._read_group(
        domain, ["company_id.currency_id"], ["amount_residual_signed:sum", "__count"]
    )
    if not totals:
        lines.append(ask.env._("Nothing pending."))
        return lines
    late = dict(
        Move._read_group(
            domain + overdue, ["company_id.currency_id"], ["amount_residual_signed:sum"]
        )
    )
    ranked = defaultdict(list)
    for currency, key, amount, count in Move._read_group(
        domain,
        ["company_id.currency_id", group_path],
        ["amount_residual_signed:sum", "__count"],
    ):
        ranked[currency].append((key, amount, count))
    for currency, amount, count in totals:
        lines.append(
            ask.env._(
                "Pending: **%(amount)s** (%(count)s documents)",
                amount=money(sign * amount, currency),
                count=count,
            )
        )
        lines.append(
            ask.env._(
                "Overdue: **%(amount)s**",
                amount=money(sign * late.get(currency, 0.0), currency),
            )
        )
        if ask.params.get("summary_only"):
            continue
        lines += _ranked(
            ask,
            [
                (_label(ask, key), sign * amount, count)
                for key, amount, count in ranked.get(currency, ())
            ],
            lambda value, currency=currency: money(value, currency),
        )
    return lines


def run_receivables(ask):
    return _balance_report(
        ask,
        ask.env._("Accounts receivable from customers"),
        ("out_invoice", "out_refund"),
        1,
    )


def run_payables(ask):
    return _balance_report(
        ask,
        ask.env._("Accounts payable to suppliers"),
        ("in_invoice", "in_refund"),
        -1,
    )


def run_purchases(ask):
    filters = ask.filter_domain(
        {
            "company": ("company_id", "res.company", ("name",), None),
            "warehouse": (
                "picking_type_id.warehouse_id",
                "stock.warehouse",
                ("name", "code"),
                None,
            ),
            "partner": ("partner_id", "res.partner", ("name",), None),
            "salesperson": ("user_id", "res.users", ("name",), None),
        }
    )
    title = ask.env._("Confirmed purchase orders, before taxes")
    if ask.group == "product" or ask.params.get("product"):
        domain = [("order_id.state", "=", "done")] + [
            (f"order_id.{path}", operator, value) for path, operator, value in filters
        ]
        domain += ask.datetime_range("order_id.date_order")
        domain += ask.filter_domain(
            {
                "product": (
                    "product_id",
                    "product.product",
                    ("name", "default_code"),
                    None,
                )
            }
        )
        return money_report(
            ask,
            title,
            "purchase.order.line",
            domain,
            "price_subtotal",
            "order_id.currency_id",
            {"product": "product_id", None: None},
        )
    domain = [("state", "=", "done")] + filters + ask.datetime_range("date_order")
    return money_report(
        ask,
        title,
        "purchase.order",
        domain,
        "amount_untaxed",
        "currency_id",
        {
            "company": "company_id",
            "warehouse": "picking_type_id.warehouse_id",
            "salesperson": "user_id",
            "partner": "partner_id",
            "month": "date_order:month",
        },
    )


def run_stock(ask):
    domain = [("location_id.usage", "=", "internal")]
    domain += ask.filter_domain(
        {
            "company": ("company_id", "res.company", ("name",), None),
            "warehouse": (
                "location_id.warehouse_id",
                "stock.warehouse",
                ("name", "code"),
                None,
            ),
            "product": (
                "product_id",
                "product.product",
                ("name", "default_code"),
                None,
            ),
        }
    )
    group_path = (
        "location_id.warehouse_id"
        if ask.group == "warehouse" or ask.params.get("product")
        else "product_id"
    )
    Quant = ask.env["stock.quant"]
    rows = Quant._read_group(
        domain,
        ["product_id", group_path] if group_path != "product_id" else ["product_id"],
        ["quantity:sum", "reserved_quantity:sum"],
    )
    lines = [
        "**" + ask.env._("Stock on hand") + "**",
        ask.env._("As of %(day)s", day=ask.format_day(ask.today)),
    ]
    if not rows:
        lines.append(ask.env._("No stock found."))
        return lines
    # quantities of different products are in different units: they are
    # listed per product, never added up
    items = []
    for row in rows:
        product = row[0]
        place = f" · {_label(ask, row[1])}" if group_path != "product_id" else ""
        on_hand, reserved = row[-2], row[-1]
        unit = product.uom_id.name or ""
        items.append(
            (
                f"{product.display_name}{place}",
                on_hand,
                ask.env._("%(free)s free", free=quantity(on_hand - reserved)),
                unit,
            )
        )
    items.sort(key=lambda item: item[1], reverse=True)
    lines += [
        f"• {label}: **{quantity(on_hand)} {unit}** ({free})"
        for label, on_hand, free, unit in items[: ask.top]
    ]
    if len(items) > ask.top:
        lines.append(ask.env._("… and %(count)s more", count=len(items) - ask.top))
    return lines


def run_cash(ask):
    company_domain = ask.filter_domain(
        {"company": ("company_id", "res.company", ("name",), None)}
    )
    journals = ask.env["account.journal"].search(
        [("type", "in", ("bank", "cash")), ("default_account_id", "!=", False)]
        + company_domain
    )
    lines = [
        "**" + ask.env._("Bank and cash balances") + "**",
        ask.env._("As of %(day)s", day=ask.format_day(ask.today)),
    ]
    if not journals:
        lines.append(ask.env._("No bank or cash journal found."))
        return lines
    rows = ask.env["account.move.line"]._read_group(
        [
            ("account_id", "in", journals.default_account_id.ids),
            ("parent_state", "=", "posted"),
        ],
        ["account_id"],
        ["balance:sum", "amount_currency:sum"],
    )
    balances = {account: (balance, foreign) for account, balance, foreign in rows}
    totals = defaultdict(float)
    for journal in journals.sorted(lambda j: (j.company_id.id, j.name)):
        balance, foreign = balances.get(journal.default_account_id, (0.0, 0.0))
        currency = journal.currency_id or journal.company_id.currency_id
        amount = foreign if journal.currency_id else balance
        totals[currency] += amount
        if not ask.params.get("summary_only"):
            lines.append(f"• {journal.name}: {money(amount, currency)}")
    lines += [
        ask.env._(
            "Total %(currency)s: **%(amount)s**",
            currency=currency.name,
            amount=money(amount, currency),
        )
        for currency, amount in totals.items()
    ]
    return lines


def run_deliveries(ask):
    domain = [
        ("picking_type_id.code", "=", "outgoing"),
        ("state", "not in", ("draft", "done", "cancel")),
    ]
    domain += ask.filter_domain(
        {
            "company": ("company_id", "res.company", ("name",), None),
            "warehouse": (
                "picking_type_id.warehouse_id",
                "stock.warehouse",
                ("name", "code"),
                None,
            ),
            "partner": ("partner_id", "res.partner", ("name",), None),
        }
    )
    now = fields.Datetime.now()
    late_domain = domain + [("date_planned", "<", now)]
    if ask.params.get("overdue_only"):
        domain = late_domain
    Picking = ask.env["stock.picking"]
    pending = Picking.search_count(domain)
    late = Picking.search_count(late_domain)
    lines = [
        "**" + ask.env._("Pending customer deliveries") + "**",
        ask.env._(
            "Pending: **%(count)s**, of which late: **%(late)s**",
            count=pending,
            late=late,
        ),
    ]
    group_path = {"partner": "partner_id"}.get(
        ask.group, "picking_type_id.warehouse_id"
    )
    rows = Picking._read_group(domain, [group_path], ["__count"])
    late_rows = dict(Picking._read_group(late_domain, [group_path], ["__count"]))
    lines += _ranked(
        ask,
        [(_label(ask, key), count, late_rows.get(key, 0)) for key, count in rows],
        lambda value: ask.env._("%(count)s pending", count=value),
    )
    if rows:
        lines.append(ask.env._("(the number in brackets is the late ones)"))
    return lines


def run_production(ask):
    domain = [("production_id", "!=", False), ("state", "=", "done")]
    domain += ask.filter_domain(
        {
            "company": ("company_id", "res.company", ("name",), None),
            "product": (
                "product_id",
                "product.product",
                ("name", "default_code"),
                None,
            ),
            "warehouse": (
                "picking_type_id.warehouse_id",
                "stock.warehouse",
                ("name", "code"),
                None,
            ),
        }
    )
    domain += ask.datetime_range("date")
    rows = ask.env["stock.move"]._read_group(
        domain, ["product_id"], ["quantity:sum", "production_id:count_distinct"]
    )
    lines = ["**" + ask.env._("Finished production") + "**", ask.period_label()]
    if not rows:
        lines.append(ask.env._("Nothing was produced in that period."))
        return lines
    rows = sorted(rows, key=lambda row: row[1], reverse=True)
    lines.append(
        ask.env._(
            "%(products)s products, %(orders)s manufacturing orders",
            products=len(rows),
            orders=sum(row[2] for row in rows),
        )
    )
    lines += [
        f"• {product.display_name}: **{quantity(qty)} {product.uom_id.name or ''}**"
        f" ({orders})"
        for product, qty, orders in rows[: ask.top]
    ]
    if len(rows) > ask.top:
        lines.append(ask.env._("… and %(count)s more", count=len(rows) - ask.top))
    return lines


def run_headcount(ask):
    domain = ask.filter_domain(
        {"company": ("company_id", "res.company", ("name",), None)}
    )
    employees = ask.env["hr.employee"].search(domain)
    lines = [
        "**" + ask.env._("Active employees") + "**",
        ask.env._("Total: **%(count)s**", count=len(employees)),
    ]
    key = (
        (lambda employee: employee.company_id.display_name)
        if ask.group == "company"
        else (
            lambda employee: employee.department_id.display_name or ask.env._("(none)")
        )
    )
    counts = defaultdict(int)
    for employee in employees:
        counts[key(employee)] += 1
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    lines += [f"• {label}: {count}" for label, count in ranked]
    return lines


def run_salaries(ask):
    domain = ask.filter_domain(
        {
            "company": ("company_id", "res.company", ("name",), None),
            "employee": ("id", "hr.employee", ("name",), None),
        }
    )
    employees = ask.env["hr.employee"].search(domain).filtered("current_version_id")
    lines = [
        "**" + ask.env._("Salaries by current contract") + "**",
        ask.env._("As of %(day)s", day=ask.format_day(ask.today)),
    ]
    if not employees:
        lines.append(ask.env._("No employee with a contract found."))
        return lines
    totals = defaultdict(float)
    for employee in employees:
        totals[employee.company_id.currency_id] += employee.current_version_id.wage
    for currency, amount in totals.items():
        lines.append(
            ask.env._(
                "Total: **%(amount)s** (%(count)s employees)",
                amount=money(amount, currency),
                count=len(
                    employees.filtered(
                        lambda e, c=currency: e.company_id.currency_id == c
                    )
                ),
            )
        )
    if ask.params.get("employee"):
        lines += [
            f"• {employee.name}"
            + (
                f" ({employee.current_version_id.job_id.name})"
                if employee.current_version_id.job_id
                else ""
            )
            + f": **{money(employee.current_version_id.wage, employee.company_id.currency_id)}**"
            for employee in employees.sorted(lambda e: -e.current_version_id.wage)[
                : ask.top
            ]
        ]
        return lines
    key = (
        (lambda employee: employee.company_id.display_name)
        if ask.group == "company"
        else (
            lambda employee: (
                employee.current_version_id.department_id.display_name
                or ask.env._("(none)")
            )
        )
    )
    groups = defaultdict(lambda: [0.0, 0])
    for employee in employees:
        entry = groups[(key(employee), employee.company_id.currency_id)]
        entry[0] += employee.current_version_id.wage
        entry[1] += 1
    ranked = sorted(groups.items(), key=lambda item: item[1][0], reverse=True)
    lines += [
        f"• {label}: {money(amount, currency)} ({count})"
        for (label, currency), (amount, count) in ranked[: ask.top]
    ]
    if len(ranked) > ask.top:
        lines.append(ask.env._("… and %(count)s more", count=len(ranked) - ask.top))
    return lines


def run_payments(ask):
    """Payments received from customers or made to suppliers in a period:
    who paid, and how much."""
    domain = [("state", "in", ("in_process", "paid"))]
    domain += ask.filter_domain(
        {
            "company": ("company_id", "res.company", ("name",), None),
            "partner": ("partner_id", "res.partner", ("name", "vat"), None),
        }
    )
    if not (ask.params.get("date_from") or ask.params.get("date_to")):
        ask.params["date_from"] = ask.params["date_to"] = ask.today.isoformat()
    domain += ask.date_range("date")
    title = ask.env._("Payments received and made")
    group_path = (
        None
        if ask.params.get("summary_only")
        else (
            {"company": "company_id", "month": "date:month"}.get(
                ask.group, "partner_id"
            )
        )
    )
    Payment = ask.env["account.payment"]
    lines = ["**" + title + "**", ask.period_label()]
    rows = Payment._read_group(
        domain,
        ["payment_type", "company_id.currency_id"]
        + ([group_path] if group_path else []),
        ["amount_company_currency_signed:sum", "__count"],
    )
    if not rows:
        lines.append(ask.env._("No payments in that period."))
        return lines
    labels = {
        "inbound": ask.env._("Received from customers"),
        "outbound": ask.env._("Paid to suppliers"),
    }
    by_side = defaultdict(list)
    for row in rows:
        by_side[(row[0], row[1])].append(row)
    for (payment_type, currency), side_rows in sorted(
        by_side.items(), key=lambda item: item[0][0]
    ):
        total = sum(abs(row[-2]) for row in side_rows)
        count = sum(row[-1] for row in side_rows)
        lines.append(
            ask.env._(
                "%(label)s: **%(amount)s** (%(count)s payments)",
                label=labels.get(payment_type, payment_type),
                amount=money(total, currency),
                count=count,
            )
        )
        if group_path:
            lines += _ranked(
                ask,
                [(_label(ask, row[2]), abs(row[3]), row[4]) for row in side_rows],
                lambda value, currency=currency: money(value, currency),
                by_date=ask.group == "month",
            )
    return lines


CREDIT_DOCUMENTS = 25


def run_credit(ask):
    """A customer's credit file across every company: profile, credit lines,
    the guarantees, promissory notes and guarantor documents on file, what
    the grade still requires, and any guarantee release."""
    name = (ask.params.get("partner") or "").strip()
    if not name:
        return [
            ask.env._(
                "Tell me whose credit or guarantees you want: the customer's name."
            )
        ]
    partners = ask.matches("res.partner", name, ("name", "vat"))
    partner = partners[:1].commercial_partner_id
    lines = [
        "**"
        + ask.env._("Credit and guarantees of %(name)s", name=partner.display_name)
        + "**",
        ask.env._("As of %(day)s", day=ask.format_day(ask.today)),
    ]
    env = ask.env
    if "credit.profile" in env:
        states = dict(
            env["credit.profile"]._fields["state"]._description_selection(env)
        )
        for profile in env["credit.profile"].search([("partner_id", "=", partner.id)]):
            currency = profile.currency_id
            lines.append(
                ask.env._(
                    "• %(company)s: %(state)s, grade %(grade)s, guarantee amount %(collateral)s, open %(open)s, overdue %(overdue)s",
                    company=profile.company_id.display_name,
                    state=states.get(profile.state, profile.state or "-"),
                    grade=profile.grade_id.display_name or "-",
                    collateral=money(profile.collateral_amount, currency),
                    open=money(profile.exposure_open, currency),
                    overdue=money(profile.exposure_overdue, currency),
                )
            )
            issues = profile._render_document_issues(profile._get_document_issues())
            if issues:
                lines.append(ask.env._("  What the grade still requires:"))
                lines += [f"  {issue}" for issue in issues]
    if "credit.facility" in env:
        for facility in env["credit.facility"].search(
            [("partner_id", "=", partner.id), ("state", "=", "active")]
        ):
            lines.append(
                ask.env._(
                    "• Credit line %(name)s in %(company)s: %(amount)s until %(end)s",
                    name=facility.name or "-",
                    company=facility.company_id.display_name,
                    amount=money(facility.amount, facility.currency_id),
                    end=ask.format_day(facility.date_end) if facility.date_end else "-",
                )
            )
    documents = env["document.document"].search(
        [("partner_id", "child_of", partner.id), ("type", "!=", "folder")],
        order="document_type_id, id desc",
    )
    if not documents:
        lines.append(ask.env._("No documents on file."))
        return lines
    lines.append(ask.env._("Documents on file:"))
    for document in documents[:CREDIT_DOCUMENTS]:
        kind = document.document_type_id
        tags = []
        if "is_guarantor" in document._fields and document.is_guarantor:
            tags.append(ask.env._("guarantor's"))
        if "has_collateral" in kind._fields and kind.has_collateral:
            tags.append(
                ask.env._(
                    "guarantee of %(amount)s",
                    amount=f"{document.collateral_amount:,.2f}",
                )
                if document.collateral_amount
                else ask.env._("guarantee without amount captured")
            )
        if "amount" in document._fields and document.amount:
            tags.append(
                ask.env._("amount %(amount)s", amount=f"{document.amount:,.2f}")
            )
        if document.date_expiration:
            tags.append(
                ask.env._(
                    "expires %(day)s", day=ask.format_day(document.date_expiration)
                )
            )
        if document.expiration_state == "expired":
            tags.append(ask.env._("EXPIRED"))
        label = kind.display_name or ask.env._("(no type)")
        extra = f" ({', '.join(tags)})" if tags else ""
        lines.append(f"• {label}: {document.name}{extra}")
    if len(documents) > CREDIT_DOCUMENTS:
        lines.append(
            ask.env._("… and %(count)s more", count=len(documents) - CREDIT_DOCUMENTS)
        )
    released = documents.filtered(
        lambda document: (
            "liberaci" in (document.document_type_id.display_name or "").lower()
            or "release" in (document.document_type_id.display_name or "").lower()
        )
    )
    if released:
        lines.append(
            ask.env._(
                "Note: there is a guarantee release document on file (%(names)s): the guarantee may have been returned.",
                names=", ".join(released.mapped("name")),
            )
        )
    return lines


STATEMENT_DAYS = 90
STATEMENT_DOCUMENTS = 15


def run_statement(ask):
    """A customer's or supplier's account statement over every company: the
    balance and what is overdue first; the breakdown by age when asked."""
    env = ask.env
    if ask.params.get("partner_id"):
        partners = env["res.partner"].browse(int(ask.params["partner_id"])).exists()
    else:
        name = (ask.params.get("partner") or "").strip()
        if not name:
            return [
                env._(
                    "Tell me whose account statement you want: the customer's or "
                    "supplier's name."
                )
            ]
        partners = ask.matches("res.partner", name, ("name", "vat"))
    partner = partners[:1].commercial_partner_id
    ask.extras["statement_partner_id"] = partner.id
    company_domain = ask.filter_domain(
        {"company": ("company_id", "res.company", ("name",), None)}
    )
    if ask.params.get("date_from") or ask.params.get("date_to"):
        start, end = ask.period()
    else:
        start, end = ask.today - timedelta(days=STATEMENT_DAYS), ask.today
    Move = env["account.move"]
    base = [
        ("partner_id", "child_of", partner.id),
        ("state", "=", "posted"),
        ("move_type", "in", ("out_invoice", "out_refund", "in_invoice", "in_refund")),
    ] + company_domain
    open_moves = Move.search(
        base + [("amount_residual_signed", "!=", 0)],
        order="invoice_date_due asc, id asc",
    )
    lines = [
        "📄 **" + env._("Account statement") + "**",
        f"**{partner.display_name}** · "
        + env._("as of %(day)s", day=ask.format_day(ask.today)),
        "",
    ]
    sides = (
        (("out_invoice", "out_refund"), 1, "💰", env._("Receivable")),
        (("in_invoice", "in_refund"), -1, "💸", env._("Payable")),
    )
    for move_types, sign, icon, label in sides:
        moves = open_moves.filtered(lambda m, t=move_types: m.move_type in t)
        by_company = defaultdict(lambda: env["account.move"])
        for move in moves:
            by_company[move.company_id] |= move
        for company, company_moves in by_company.items():
            currency = company.currency_id
            pending = sum(sign * m.amount_residual_signed for m in company_moves)
            late = company_moves.filtered(
                lambda m: m.invoice_date_due and m.invoice_date_due < ask.today
            )
            overdue = sum(sign * m.amount_residual_signed for m in late)
            share = f" ({overdue / pending:.0%})" if pending else ""
            lines += [
                f"{icon} {label} · {company.display_name}: **{money(pending, currency)}**",
                "⚠️ " + env._("Overdue") + f": **{money(overdue, currency)}**{share}",
                "📑 " + env._("%(count)s open documents", count=len(company_moves)),
                "",
            ]
            if ask.params.get("detail"):
                lines += _aging(ask, company_moves, sign, currency)
    if not open_moves:
        lines += ["✅ " + env._("Nothing pending."), ""]
    lines.append(
        "🗓 "
        + env._(
            "From %(start)s to %(end)s:",
            start=ask.format_day(start),
            end=ask.format_day(end),
        )
    )
    labels = {
        "out_invoice": env._("invoiced"),
        "out_refund": env._("credit notes issued"),
        "in_invoice": env._("bills received"),
        "in_refund": env._("credit notes received"),
    }
    invoiced = Move._read_group(
        base + [("invoice_date", ">=", start), ("invoice_date", "<=", end)],
        ["company_id", "move_type"],
        ["amount_total_signed:sum", "__count"],
    )
    for company, move_type, amount, count in invoiced:
        lines.append(
            f"• {labels[move_type].capitalize()}: "
            f"{money(abs(amount), company.currency_id)} ({count})"
        )
    payments = env["account.payment"]._read_group(
        [
            ("partner_id", "child_of", partner.id),
            ("state", "in", ("in_process", "paid")),
            ("date", ">=", start),
            ("date", "<=", end),
        ]
        + company_domain,
        ["company_id", "payment_type"],
        ["amount_company_currency_signed:sum", "__count"],
    )
    for company, payment_type, amount, count in payments:
        label = (
            env._("payments received")
            if payment_type == "inbound"
            else env._("payments made")
        )
        lines.append(
            f"• {label.capitalize()}: {money(abs(amount), company.currency_id)} ({count})"
        )
    if not invoiced and not payments:
        lines.append("• " + env._("No movements in that period."))
    if open_moves and not ask.params.get("detail"):
        lines += [
            "",
            env._("Want the breakdown or the PDF? Use the buttons below, or just ask."),
        ]
    return lines


AGING_BUCKETS = (
    (91, "🔴"),
    (61, "🟠"),
    (31, "🟡"),
    (1, "🔵"),
    (None, "🟢"),
)
BUCKET_DOCUMENTS = 10


def _aging(ask, moves, sign, currency) -> list:
    """The open documents grouped by how late they are, oldest first."""
    env = ask.env
    names = {
        91: env._("More than 90 days late"),
        61: env._("61 to 90 days late"),
        31: env._("31 to 60 days late"),
        1: env._("1 to 30 days late"),
        None: env._("Not due yet"),
    }
    groups = defaultdict(list)
    for move in moves:
        due = move.invoice_date_due
        late = (ask.today - due).days if due else 0
        bucket = next(
            (low for low, _icon in AGING_BUCKETS if low is not None and late >= low),
            None,
        )
        groups[bucket].append((move, late))
    lines = []
    for low, icon in AGING_BUCKETS:
        items = groups.get(low)
        if not items:
            continue
        total = sum(sign * move.amount_residual_signed for move, _late in items)
        lines.append(
            f"{icon} **{names[low]}**: {money(total, currency)} ({len(items)})"
        )
        for move, late in items[:BUCKET_DOCUMENTS]:
            when = (
                f"{late} d"
                if late > 0
                else env._("due %(day)s", day=ask.format_day(move.invoice_date_due))
                if move.invoice_date_due
                else "-"
            )
            lines.append(
                f"   • {move.name} · {money(sign * move.amount_residual_signed, currency)} · {when}"
            )
        if len(items) > BUCKET_DOCUMENTS:
            lines.append(
                "   "
                + env._("… and %(count)s more", count=len(items) - BUCKET_DOCUMENTS)
            )
        lines.append("")
    return lines


LOCATIONS = 10
# a reading older than this is said to be old: the unit may be off or out
# of coverage, and where it was is not where it is
STALE_READING = timedelta(hours=2)


def _tracked_devices(env):
    """``{device: employee}``: the GPS units with a position, and who they
    track -- the driver of the vehicle they are in, or the employee they
    are bound to."""
    devices = env["device.device"].search(
        [("is_gps_device", "=", True), ("log_gps_last_id", "!=", False)]
    )
    owners = {}
    if "asset_operator_id" in devices._fields:
        for device in devices:
            owners[device] = device.asset_operator_id
    if "hr.employee" in env:
        employees = env["hr.employee"].search(
            [("resource_id.gps_device_id", "in", devices.ids)]
        )
        for employee in employees:
            owners[employee.resource_id.gps_device_id] = employee
    return {device: owners.get(device) or env["hr.employee"] for device in devices}


def _whose(ask, tracked, value):
    """The units `value` names: by the person they track, as said or
    dictated, else by the unit or its plate."""
    people = ask.env["hr.employee"].browse(
        sorted({employee.id for employee in tracked.values() if employee})
    )
    found = find(ask.env, "hr.employee", value, ("name",), [("id", "in", people.ids)])
    if not found:
        # a dictated surname is often misheard ("Carreira" for "Ferreyra"):
        # any word that names one of the tracked people
        words = [word for word in _WORD.findall(value) if len(word) >= 3]
        found = people.filtered(
            lambda employee: any(
                remove_accents(word).lower()
                in remove_accents(employee.name or "").lower()
                for word in words
            )
        )
        if found:
            ask.notes.append(
                ask.env._(
                    "I found no one called exactly «%(value)s» with a GPS; I took "
                    "%(names)s.",
                    value=value,
                    names=", ".join(found.mapped("name")),
                )
            )
    if found:
        return [device for device, owner in tracked.items() if owner & found]
    text = remove_accents(value).lower()
    return [
        device
        for device in tracked
        if text
        in remove_accents(
            f"{device.display_name} {getattr(device, 'asset_license_plate', '') or ''}"
        ).lower()
    ]


def _place_text(device, live):
    """Where a unit is, in words: the customer's land it is on, and the
    address of its last position -- looked up now when `live`, else only
    the one cached for that very position."""
    parts = []
    partner = getattr(device, "current_client_partner_id", None)
    if partner:
        parts.append(
            device.env._(
                "at %(partner)s's land (%(distance)s m)",
                partner=partner.display_name,
                distance=device.current_client_distance_m,
            )
        )
    latitude, longitude = device.log_gps_last_latitude, device.log_gps_last_longitude
    address = False
    if hasattr(device, "current_address"):
        key = f"{latitude:.4f},{longitude:.4f}"
        if device.current_address and device.current_address_key == key:
            address = device.current_address
        elif live:
            try:
                address = device._reverse_geocode(latitude, longitude)
            except Exception:
                address = False
    if address:
        parts.append(address)
    return " · ".join(parts)


def run_location(ask):
    tracked = _tracked_devices(ask.env)
    value = (ask.params.get("employee") or "").strip()
    devices = _whose(ask, tracked, value) if value else list(tracked)
    if value and not devices:
        raise NotFound(ask.env._("I found no GPS unit for «%(value)s».", value=value))
    devices = sorted(
        devices, key=lambda device: device.log_gps_last_id.timestamp, reverse=True
    )
    zone = pytz.timezone(ask.tz)
    now = fields.Datetime.now()
    lines = ["📍 **" + ask.env._("Where they are") + "**"]
    for device in devices[: LOCATIONS if not value else 5]:
        reading = device.log_gps_last_id
        owner = tracked[device]
        plate = getattr(device, "asset_license_plate", "") or ""
        title = owner.name or device.display_name
        lines.append("")
        lines.append(f"**{title}**" + (f" · {plate}" if plate else ""))
        local = pytz.UTC.localize(reading.timestamp).astimezone(zone)
        age = now - reading.timestamp
        seen = ask.env._(
            "Last signal: %(day)s %(time)s",
            day=ask.format_day(local.date()),
            time=local.strftime("%H:%M"),
        )
        if age > STALE_READING:
            seen += " ⚠️ " + ask.env._("(old: it may be off or without signal)")
        lines.append(seen)
        if (reading.speed or 0) > 3:
            lines.append(
                "🚗 "
                + ask.env._("Moving at %(speed)s km/h", speed=round(reading.speed or 0))
            )
        else:
            lines.append(
                "🅿️ "
                + (
                    ask.env._("Stopped, engine on")
                    if reading.ignition
                    else ask.env._("Stopped")
                )
            )
        place = _place_text(device, live=bool(value))
        if place:
            lines.append("🏠 " + place)
        latitude = device.log_gps_last_latitude
        longitude = device.log_gps_last_longitude
        lines.append(f"🗺 https://www.google.com/maps?q={latitude:.6f},{longitude:.6f}")
    if not value and len(devices) > LOCATIONS:
        lines.append("")
        lines.append(
            ask.env._(
                "%(count)s more units: ask for a person.",
                count=len(devices) - LOCATIONS,
            )
        )
    return lines


GROUPS = ("company", "warehouse", "salesperson", "partner", "product", "month")
FILTERS = ("company", "warehouse", "partner", "product", "salesperson", "employee")

QUERIES = {
    query.key: query
    for query in (
        Query(
            "sales",
            "Sales orders confirmed in a period: how much was sold, by branch "
            "(warehouse), salesperson, customer, product or month. Not counter "
            "sales.",
            run_sales,
            GROUPS,
            FILTERS,
            requires="sale.order",
        ),
        Query(
            "pos_sales",
            "Counter / point-of-sale / store (mostrador) sales in a period.",
            run_pos_sales,
            GROUPS,
            FILTERS,
            requires="pos.order",
        ),
        Query(
            "invoicing",
            "Customer invoicing (facturación) in a period, net of credit notes.",
            run_invoicing,
            ("company", "partner", "salesperson", "month"),
            ("company", "partner", "salesperson"),
            requires="account.move",
        ),
        Query(
            "receivables",
            "What customers owe us now (cartera, cuentas por cobrar), overdue "
            "amounts, by customer or company.",
            run_receivables,
            ("company", "partner"),
            ("company", "partner"),
            periodic=False,
            requires="account.move",
        ),
        Query(
            "payables",
            "What we owe suppliers now (cuentas por pagar), overdue amounts, by "
            "supplier or company.",
            run_payables,
            ("company", "partner"),
            ("company", "partner"),
            periodic=False,
            requires="account.move",
        ),
        Query(
            "purchases",
            "Purchase orders confirmed in a period, by supplier, product, "
            "branch, buyer or month.",
            run_purchases,
            GROUPS,
            FILTERS,
            requires="purchase.order",
        ),
        Query(
            "stock",
            "Stock on hand now (existencias, inventario disponible) of products, "
            "by product or branch (warehouse).",
            run_stock,
            ("warehouse", "product"),
            ("company", "warehouse", "product"),
            periodic=False,
            requires="stock.quant",
        ),
        Query(
            "cash",
            "Current balances of bank accounts and cash (bancos, caja, saldo).",
            run_cash,
            (),
            ("company",),
            periodic=False,
            requires="account.move",
        ),
        Query(
            "deliveries",
            "Customer deliveries still pending or late (entregas, pedidos por "
            "surtir), by branch or customer.",
            run_deliveries,
            ("warehouse", "partner"),
            ("company", "warehouse", "partner"),
            periodic=False,
            requires="stock.picking",
        ),
        Query(
            "production",
            "Finished production (manufacturing, formulaciones) in a period, by "
            "product.",
            run_production,
            ("product",),
            ("company", "product", "warehouse"),
            requires="mrp.production",
        ),
        Query(
            "payments",
            "Payments (cobros, pagos) received from customers or made to "
            "suppliers in a period: who paid today, which customers paid or "
            "settled their debt, collections by customer, company or month. "
            "Today when no period is said.",
            run_payments,
            ("company", "partner", "month"),
            ("company", "partner"),
            requires="account.payment",
        ),
        Query(
            "credit",
            "A customer's credit file and guarantees (garantías, colateral, "
            "pagarés, avales, línea de crédito, documentos de crédito): credit "
            "status and grade per company, credit lines, the guarantee, "
            "promissory-note and guarantor documents on file, what is missing, "
            "and guarantee releases. Needs the partner.",
            run_credit,
            (),
            ("partner",),
            periodic=False,
            requires="document.document",
        ),
        Query(
            "statement",
            "The account statement (estado de cuenta) of one customer or "
            "supplier across every company: open and overdue invoices and "
            "bills, what was invoiced and paid in a period. Needs the partner.",
            run_statement,
            (),
            ("company", "partner"),
            requires="account.move",
        ),
        Query(
            "salaries",
            "What employees earn (sueldos, salarios, nómina, cuánto gana alguien) "
            "by their current contract: one employee by name, or totals by "
            "department or company.",
            run_salaries,
            ("company",),
            ("company", "employee"),
            periodic=False,
            requires="hr.version",
        ),
        Query(
            "location",
            "Where a person, vehicle or GPS unit is right now (ubicación, dónde "
            "está, GPS, rastreo): by the employee who drives it or carries it, "
            "or every tracked unit. A map link and the place it is at.",
            run_location,
            (),
            ("employee",),
            periodic=False,
            requires="device.device",
        ),
        Query(
            "headcount",
            "How many active employees there are (plantilla, personal), by "
            "department or company.",
            run_headcount,
            ("company",),
            ("company",),
            periodic=False,
            requires="hr.employee",
        ),
    )
}


def available_queries(env) -> dict:
    """The queries whose models are installed."""
    return {
        key: query
        for key, query in QUERIES.items()
        if not query.requires or query.requires in env
    }


def answer(env, query, params, *, tz, today, extras=None) -> str:
    """The answer to `query` with the classifier's `params`, read from `env`.

    :param env: a read-only environment
    :param Query query: the catalogued question
    :param dict params: the parameters the classifier extracted
    :param str tz: the owner's timezone
    :param date today: the owner's current date
    :return: the answer text, Markdown-light
    :rtype: str
    """
    ask = Ask(env, tz, today, dict(params or {}))
    if ask.group and ask.group not in query.group_by:
        ask.params["group_by"] = None
    try:
        lines = query.run(ask)
    except NotFound as error:
        return str(error)
    if extras is not None:
        extras.update(ask.extras)
    return "\n".join(lines + ask.notes)
