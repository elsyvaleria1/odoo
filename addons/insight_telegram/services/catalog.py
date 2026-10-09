from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import pytz
from babel.dates import format_date

from odoo import fields

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
        """The records of `model` whose name contains `value`, noted in the
        answer when the name is ambiguous."""
        domain = list(extra or [])
        terms = [(name, "ilike", value) for name in fields_]
        domain += ["|"] * (len(terms) - 1) + terms
        found = self.env[model].search(domain, limit=MAX_MATCHES)
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
    group_path = groups.get(ask.group)
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


GROUPS = ("company", "warehouse", "salesperson", "partner", "product", "month")
FILTERS = ("company", "warehouse", "partner", "product", "salesperson")

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


def answer(env, query, params, *, tz, today) -> str:
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
    return "\n".join(lines + ask.notes)
