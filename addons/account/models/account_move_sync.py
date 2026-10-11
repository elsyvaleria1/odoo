from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager

from odoo import api, models
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict
from odoo.tools.misc import clean_context

from odoo.addons.account.tools.dynamic_lines import plan_dynamic_line_sync

_debug = DebugLog(__name__)

TAX_BASE_DISPLAY_TYPES = (
    "product",
    "epd",
    "rounding",
    "non_deductible_product",
    "non_deductible_product_total",
)
NON_DEDUCTIBLE_BASE_DISPLAY_TYPES = (
    "non_deductible_product",
    "non_deductible_product_total",
)
MOVE_TRACKED_FIELDS = ("currency_id", "move_type", "invoice_currency_rate")
TAX_LINE_REBUILDING_MOVE_FIELDS = ("currency_id", "move_type")
TAX_LINE_TRACKED_FIELDS = (
    "amount_currency",
    "balance",
    "analytic_distribution",
    "tax_repartition_line_id",
)
INVOICE_BASE_LINE_TRACKED_FIELDS = (
    "price_unit",
    "quantity",
    "discount",
    "deductible_amount",
)
ENTRY_BASE_LINE_TRACKED_FIELDS = ("amount_currency",)

SKIP = None
FROM_BASE = (False, False)
FROM_TAX = (True, False)
FROM_TAX_REAPPLY_RATE = (True, True)
EMPTY_TAX_SYNC_SNAPSHOT = frozendict(move={}, base_lines={}, tax_lines={})


@contextmanager
def sync_boundary(prepare, commit):
    state = prepare()
    yield  # noqa: RUF075 -- Commit synchronization only after the body succeeds.
    commit(state)


def written_value(record, fname):
    return record._fields[fname].convert_to_write(record[fname], record)


def snapshot_value(record, fname):
    value = record[fname]
    if isinstance(value, models.BaseModel):
        return value._origin._ids
    return written_value(record, fname)


def values_differ(record, values) -> bool:
    return any(written_value(record, fname) != values[fname] for fname in values)


def detach_container(value):
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_cash_rounding_difference(self, total_amount_currency) -> tuple:
        self.check_singleton()
        difference = self.invoice_cash_rounding_id.compute_difference(
            self.currency_id, total_amount_currency
        )
        rate = self.invoice_currency_rate or 1.0
        return self.company_id.currency_id.round(difference / rate), difference

    def _get_cash_rounding_profit_loss_account(self, diff_balance):
        self.check_singleton()
        cash_rounding = self.invoice_cash_rounding_id.with_company(self.company_id)
        if diff_balance > 0.0 and cash_rounding.loss_account_id:
            return cash_rounding.loss_account_id
        return cash_rounding.profit_account_id

    def _get_biggest_tax_line(self):
        self.check_singleton()
        candidates = self.line_ids.filtered(
            lambda line: line.tax_repartition_line_id and line.display_type == "tax"
        )
        return max(
            candidates,
            key=lambda line: abs(line.balance),
            default=self.env["account.move.line"],
        )

    @_debug.perf.timed
    def _prepare_cash_rounding_line_vals(self, diff_balance, diff_amount_currency):
        self.check_singleton()
        vals = {
            "balance": diff_balance,
            "amount_currency": diff_amount_currency,
            "partner_id": self.commercial_partner_id.id,
            "move_id": self.id,
            "currency_id": self.currency_id.id,
            "company_id": self.company_id.id,
            "company_currency_id": self.company_id.currency_id.id,
            "display_type": "rounding",
        }

        biggest_tax_line = (
            self._get_biggest_tax_line()
            if self.invoice_cash_rounding_id.strategy == "biggest_tax"
            else self.env["account.move.line"]
        )
        _debug.logic(
            "cash_rounding_target_chosen",
            move=self,
            biggest_tax_line=bool(biggest_tax_line),
        )
        if biggest_tax_line:
            vals.update(
                {
                    "name": self.env._(
                        "%(tax_name)s (rounding)", tax_name=biggest_tax_line.name
                    ),
                    "account_id": biggest_tax_line.account_id.id,
                    "tax_repartition_line_id": biggest_tax_line.tax_repartition_line_id.id,
                    "tax_tag_ids": [Command.set(biggest_tax_line.tax_tag_ids.ids)],
                    "tax_ids": [Command.set(biggest_tax_line.tax_ids.ids)],
                }
            )
            return vals

        account = self._get_cash_rounding_profit_loss_account(diff_balance)
        _debug.logic("cash_rounding_account_resolved", move=self, found=bool(account))
        if not account:
            return None
        vals.update(
            {
                "name": self.invoice_cash_rounding_id.name,
                "account_id": account.id,
                "tax_ids": [Command.clear()],
            }
        )
        return vals

    @_debug.perf.timed
    def _recompute_cash_rounding_lines(self) -> None:
        self.check_singleton()
        existing_cash_rounding_line = self.line_ids.filtered(
            lambda line: line.display_type == "rounding"
        )[:1]

        if not self.invoice_cash_rounding_id:
            _debug.logic(
                "cash_rounding_unset",
                move=self,
                existing=bool(existing_cash_rounding_line),
            )
            if existing_cash_rounding_line:
                existing_cash_rounding_line.unlink()
            return

        if existing_cash_rounding_line:
            old_strategy = (
                "biggest_tax"
                if existing_cash_rounding_line.tax_line_id
                else "add_invoice_line"
            )
            new_strategy = (
                "biggest_tax"
                if self.invoice_cash_rounding_id.strategy == "biggest_tax"
                and self._get_biggest_tax_line()
                else "add_invoice_line"
            )
            if new_strategy != old_strategy:
                _debug.logic(
                    "cash_rounding_strategy_changed",
                    move=self,
                    old_strategy=old_strategy,
                )
                existing_cash_rounding_line.unlink()
                existing_cash_rounding_line = self.env["account.move.line"]

        others_lines = self.line_ids.filtered(
            lambda line: (
                line.account_id.account_type
                not in ("asset_receivable", "liability_payable")
            )
        )
        others_lines -= existing_cash_rounding_line
        diff_balance, diff_amount_currency = self._get_cash_rounding_difference(
            sum(others_lines.mapped("amount_currency"))
        )

        if self.company_currency_id.is_zero(diff_balance) and self.currency_id.is_zero(
            diff_amount_currency
        ):
            _debug.logic(
                "cash_rounding_zero_difference",
                move=self,
                existing=bool(existing_cash_rounding_line),
            )
            if existing_cash_rounding_line:
                existing_cash_rounding_line.unlink()
            return

        if (
            existing_cash_rounding_line
            and self.company_currency_id.compare_amounts(
                existing_cash_rounding_line.balance, diff_balance
            )
            == 0
            and self.currency_id.compare_amounts(
                existing_cash_rounding_line.amount_currency, diff_amount_currency
            )
            == 0
            and (
                not existing_cash_rounding_line.tax_repartition_line_id
                or existing_cash_rounding_line.tax_repartition_line_id
                == self._get_biggest_tax_line().tax_repartition_line_id
            )
        ):
            _debug.logic("cash_rounding_line_unchanged", move=self)
            return

        vals = self._prepare_cash_rounding_line_vals(diff_balance, diff_amount_currency)
        _debug.pipeline(
            "cash_rounding_line_vals_ready",
            move=self,
            diff_balance=diff_balance,
            diff_amount_currency=diff_amount_currency,
            dropped=vals is None,
            existing=bool(existing_cash_rounding_line),
        )
        if vals is None:
            if existing_cash_rounding_line:
                existing_cash_rounding_line.unlink()
            return
        if existing_cash_rounding_line:
            existing_cash_rounding_line.write(vals)
        else:
            self.env["account.move.line"].create(vals)

    def _get_automatic_balancing_account(self):
        self.check_singleton()
        return (
            self.journal_id.default_account_id
            or self.company_id.account_config_id.account_journal_suspense_account_id
        )

    @_debug.perf.timed
    def _sync_unbalanced_lines(self, container):
        def has_tax(move) -> bool:
            return bool(move.line_ids.tax_ids)

        def prepare():
            return {move: has_tax(move) for move in container["records"]}

        def commit(move_had_tax):
            balancing_line_by_move = {}
            detaxed_moves = self.env["account.move"]
            existing_balancing_lines = self.env["account.move.line"]
            for move in container["records"]:
                if move.state != "draft":
                    continue
                had_tax = move_had_tax.get(move, False)
                if not has_tax(move) and not had_tax:
                    continue
                if had_tax and not has_tax(move):
                    detaxed_moves |= move

                existing_balancing_line = move.line_ids.filtered(
                    lambda line: line.display_type == "balancing"
                )[:1]
                existing_balancing_lines |= existing_balancing_line
                balancing_line_by_move[move] = existing_balancing_line

            if detaxed_moves:
                _debug.logic(
                    "_sync_unbalanced_lines_taxes_removed_dropping_tax",
                    detaxed_moves=detaxed_moves,
                )
                detaxed_moves.line_ids.filtered("tax_line_id").unlink()
                detaxed_moves.line_ids.tax_tag_ids = [Command.set([])]
            if existing_balancing_lines:
                existing_balancing_lines.write({"balance": 0.0, "amount_currency": 0.0})

            if not balancing_line_by_move:
                return
            _debug.pipeline(
                "_sync_unbalanced_lines_balancing",
                balancing_line_by_move_count=len(balancing_line_by_move),
            )
            self._apply_balancing_lines(balancing_line_by_move)

        return sync_boundary(prepare, commit)

    @_debug.perf.timed
    def _apply_balancing_lines(self, balancing_line_by_move) -> None:
        moves = self.env["account.move"].union(*balancing_line_by_move)
        unbalanced_by_move_id = {
            move_id: (debit, credit)
            for move_id, debit, credit in (
                self._get_unbalanced_moves({"records": moves}) or []
            )
        }

        to_unlink = self.env["account.move.line"]
        to_create = []
        for move, existing_balancing_line in balancing_line_by_move.items():
            unbalanced = unbalanced_by_move_id.get(move.id)
            if not unbalanced:
                to_unlink |= existing_balancing_line
                continue
            debit, credit = unbalanced
            balance = credit - debit
            if existing_balancing_line:
                existing_balancing_line.write(
                    {
                        "balance": balance,
                        "amount_currency": existing_balancing_line.currency_id.round(
                            balance * existing_balancing_line.currency_rate
                        ),
                    }
                )
            else:
                to_create.append(
                    {
                        "balance": balance,
                        "name": self.env._("Automatic Balancing Line"),
                        "display_type": "balancing",
                        "move_id": move.id,
                        "account_id": move._get_automatic_balancing_account().id,
                        "currency_id": move.currency_id.id,
                        "tax_ids": False,
                    }
                )

        _debug.pipeline(
            "balancing_lines_planned",
            moves=moves,
            unbalanced=len(unbalanced_by_move_id),
            unlink=len(to_unlink),
            create=len(to_create),
        )
        if to_unlink:
            to_unlink.unlink()
        if to_create:
            self.env["account.move.line"].create(to_create)

    @_debug.perf.timed
    def _sync_rounding_lines(self, container):
        def commit(_state):
            for invoice in container["records"]:
                if invoice.state == "draft":
                    invoice._recompute_cash_rounding_lines()

        return sync_boundary(lambda: None, commit)

    @api.model
    @_debug.perf.timed
    def _sync_dynamic_line_needed_values(self, values_list):
        line_fields = self.env["account.move.line"]._fields
        res = {}
        merged_keys = set()
        for computed_needed in values_list:
            if computed_needed is False:
                continue
            for key, values in computed_needed.items():
                if key not in res:
                    res[key] = {
                        fname: detach_container(value)
                        for fname, value in values.items()
                    }
                    continue
                merged_keys.add(key)
                for fname, value in values.items():
                    if fname not in res[key]:
                        res[key][fname] = detach_container(value)
                    elif line_fields[fname].type == "monetary":
                        res[key][fname] += value

        for key, values in res.items():
            move_id = key.get("move_id")
            if not move_id:
                continue
            record = self.env["account.move"].browse(move_id)
            for fname, current_value in values.items():
                field = line_fields[fname]
                if isinstance(current_value, float):
                    values[fname] = field.convert_to_cache(current_value, record)

        for key in merged_keys:
            values = res[key]
            if not any(
                values[fname]
                for fname in values
                if line_fields[fname].type == "monetary"
            ):
                del res[key]

        _debug.pipeline(
            "needed_values_merged",
            sources=len(values_list),
            merged=len(merged_keys),
            keys=len(res),
        )
        return res

    def _get_tax_base_amls(self):
        self.check_singleton()
        return self.line_ids.filtered(
            lambda line: (
                line.display_type in TAX_BASE_DISPLAY_TYPES
                and not (
                    line.display_type == "rounding" and line.tax_repartition_line_id
                )
            )
        )

    def _get_tax_amls(self, include_cash_rounding=False):
        self.check_singleton()
        return self.line_ids.filtered(
            lambda line: (
                line.tax_repartition_line_id
                and (include_cash_rounding or line.display_type != "rounding")
            )
        )

    def _get_base_line_tracked_fields(self, grouping_key_fields) -> tuple:
        self.check_singleton()
        extra_fields = (
            INVOICE_BASE_LINE_TRACKED_FIELDS
            if self.is_invoice(include_receipts=True)
            else ENTRY_BASE_LINE_TRACKED_FIELDS
        )
        return (*grouping_key_fields, *extra_fields)

    def _get_tax_line_grouping_key_fields(self) -> tuple:
        AccountTax = self.env["account.tax"]
        return tuple(
            AccountTax._prepare_base_line_grouping_key(
                AccountTax._prepare_base_line_for_taxes_computation(None)
            )
        )

    def _get_tax_sync_snapshot(self, grouping_key_fields, base_lines, tax_lines):
        self.check_singleton()
        base_fields = self._get_base_line_tracked_fields(grouping_key_fields)

        def snapshot_lines(lines, fnames):
            return {
                line._origin or line: {
                    fname: snapshot_value(line, fname) for fname in fnames
                }
                for line in lines
            }

        move_values = {
            fname: snapshot_value(self, fname) for fname in MOVE_TRACKED_FIELDS
        }
        if self.is_tax_overridden:
            move_values["tax_overrides"] = {
                override.tax_id.id: override.amount_currency
                for override in self.tax_override_ids
            }
        return {
            "move": move_values,
            "base_lines": snapshot_lines(base_lines, base_fields),
            "tax_lines": snapshot_lines(tax_lines, TAX_LINE_TRACKED_FIELDS),
        }

    @_debug.perf.timed
    def _get_tax_rounding_mode(self, move, before, after):

        def move_field_has_changed(field):
            return before["move"].get(field) != after["move"][field]

        def changed_lines_of(part):
            return [
                line
                for line, values in after[part].items()
                if values != before[part].get(line)
            ]

        tax_before, tax_after = before["tax_lines"], after["tax_lines"]
        base_before, base_after = before["base_lines"], after["base_lines"]

        if any(
            line not in base_after
            for line, values in base_before.items()
            if values["tax_ids"]
        ):
            if changed_lines_of("tax_lines"):
                _debug.logic("tax_rounding_base_removed_tax_edited", move=move)
                return FROM_TAX
            _debug.logic("tax_rounding_base_line_removed", move=move)
            return FROM_BASE

        if changed_lines := changed_lines_of("base_lines"):
            round_from_tax_lines = all(
                not base_after[line]["tax_ids"]
                and not base_before.get(line, {}).get("tax_ids")
                for line in changed_lines
            ) or (
                list(tax_before) != list(tax_after)
                or any(
                    self.env.is_protected(line._fields[fname], line)
                    for line in tax_after
                    for fname in tax_before[line]
                )
            )
            if round_from_tax_lines and any(
                line[field]
                for line in changed_lines
                for field in ("amount_currency", "balance")
            ):
                _debug.logic(
                    "tax_rounding_amounts_edited_skipped",
                    move=move,
                    changed=len(changed_lines),
                )
                return SKIP
            _debug.logic(
                "tax_rounding_base_lines_changed",
                move=move,
                changed=len(changed_lines),
                from_tax=round_from_tax_lines,
            )
            return FROM_TAX if round_from_tax_lines else FROM_BASE

        if move_field_has_changed("invoice_currency_rate"):
            _debug.logic("tax_rounding_rate_changed", move=move)
            return FROM_TAX_REAPPLY_RATE

        return SKIP

    @_debug.perf.timed
    def _get_invoice_tax_sync_mode(self, move, before, after):
        if before == after:
            return SKIP
        tax_before, tax_after = before["tax_lines"], after["tax_lines"]
        edited_tax_lines = (
            []
            if any(
                before["move"].get(fname, after["move"][fname]) != after["move"][fname]
                for fname in TAX_LINE_REBUILDING_MOVE_FIELDS
            )
            else [
                values
                for line, values in tax_after.items()
                if line not in tax_before
                or values["amount_currency"] != tax_before[line]["amount_currency"]
                or self.env.is_protected(line._fields["amount_currency"], line)
            ]
            + [values for line, values in tax_before.items() if line not in tax_after]
        )
        if edited_tax_lines:
            taxes = (
                self.env["account.tax.repartition.line"]
                .browse(
                    {
                        repartition_line_id
                        for values in edited_tax_lines
                        for repartition_line_id in values["tax_repartition_line_id"]
                    }
                )
                .tax_id
            )
            _debug.logic("invoice_tax_lines_edited", move=move, taxes=taxes)
            move._capture_tax_overrides_from_tax_lines(taxes)
        if (
            before["move"] == after["move"]
            and before["base_lines"] == after["base_lines"]
        ):
            _debug.logic("invoice_only_tax_lines_edited", move=move)
            return SKIP
        move._drop_inapplicable_tax_overrides()
        return FROM_BASE

    def _get_draft_tax_overrides(self):
        self.check_singleton()
        if (
            not self.is_tax_overridden
            or self.state != "draft"
            or not self.is_invoice(include_receipts=True)
        ):
            return self.env["account.move.tax.override"]
        return self.tax_override_ids

    def _get_tax_amounts(self, base_lines) -> dict:
        AccountTax = self.env["account.tax"]
        currency = self.currency_id

        def by_tax(base_line, tax_data):
            return (tax_data["tax"], base_line["is_refund"]) if tax_data else None

        amounts = {}
        for key, values in AccountTax._aggregate_base_lines_aggregated_values(
            AccountTax._aggregate_base_lines_tax_details(base_lines, by_tax)
        ).items():
            if not key:
                continue
            tax, is_refund = key
            amounts[tax] = {
                "is_refund": is_refund,
                "base_amount_currency": currency.round(values["base_amount_currency"]),
                "tax_amount_currency": currency.round(values["tax_amount_currency"]),
                "tax_amount": self.company_currency_id.round(values["tax_amount"]),
            }
        return amounts

    def _get_computed_tax_amounts(self) -> dict:
        base_lines, _tax_lines = self._get_rounded_base_and_tax_lines(
            round_from_tax_lines=False, apply_tax_overrides=False
        )
        return self._get_tax_amounts(base_lines)

    @_debug.perf.timed
    def _apply_tax_overrides(self, base_lines) -> None:
        overrides = self._get_draft_tax_overrides()
        if not overrides:
            return
        currency = self.currency_id
        company_currency = self.company_currency_id
        rate = self.invoice_currency_rate or 1.0
        computed = self._get_tax_amounts(base_lines)
        targets = {}
        for override in overrides:
            values = computed.get(override.tax_id)
            if override._get_inapplicable_reason(currency, values):
                continue
            delta = currency.round(
                override.amount_currency - values["tax_amount_currency"]
            )
            if currency.is_zero(delta):
                continue
            delta_balance = (
                delta
                if currency == company_currency
                else company_currency.round(override.amount_currency / rate)
                - company_currency.round(values["tax_amount_currency"] / rate)
            )
            targets[(override.tax_id.id, currency.id, values["is_refund"])] = {
                "tax_amount_currency": override.amount_currency,
                "tax_amount": values["tax_amount"] + delta_balance,
            }
        _debug.logic(
            "tax_overrides_applied",
            move=self,
            overrides=overrides,
            applied=len(targets),
        )
        if targets:
            self.env["account.tax"]._round_tax_details_tax_amounts_to_targets(
                base_lines, self.company_id, targets
            )

    def _get_tax_override_commands(self, target_amounts, computed_amounts, taxes):
        self.check_singleton()
        currency = self.currency_id
        existing = self.tax_override_ids.grouped("tax_id")
        commands = []
        for tax in taxes:
            override = existing.get(tax)
            computed = computed_amounts.get(tax)
            target = target_amounts.get(tax)
            if (
                not computed
                or not target
                or currency.compare_amounts(
                    target["tax_amount_currency"], computed["tax_amount_currency"]
                )
                == 0
            ):
                if override:
                    commands.append(Command.unlink(override.id))
                continue
            values = {
                "currency_id": currency.id,
                "amount_currency": target["tax_amount_currency"],
                "amount_computed_currency": computed["tax_amount_currency"],
                "amount_base_currency": computed["base_amount_currency"],
            }
            if not override:
                commands.append(Command.create({"tax_id": tax.id, **values}))
            elif any(
                override._fields[fname].convert_to_write(override[fname], override)
                != value
                for fname, value in values.items()
            ):
                commands.append(Command.update(override.id, values))
        return commands

    @_debug.perf.timed
    def _capture_tax_overrides_from_tax_lines(self, taxes=None) -> None:
        for move in self:
            if (
                not move.id
                or move.state != "draft"
                or not move.is_invoice(include_receipts=True)
            ):
                continue
            stored_base_lines, _tax_lines = move._get_rounded_base_and_tax_lines(
                include_cash_rounding=False
            )
            stored = move._get_tax_amounts(stored_base_lines)
            computed = move._get_computed_tax_amounts()
            commands = move._get_tax_override_commands(
                stored,
                computed,
                taxes if taxes is not None else stored.keys() | computed.keys(),
            )
            _debug.logic("tax_overrides_captured", move=move, commands=len(commands))
            if commands:
                move.tax_override_ids = commands

    @_debug.perf.timed
    def _update_tax_overrides_from_origin(self, origin) -> None:
        self.check_singleton()
        if (
            self.state != "draft"
            or not self.is_invoice(include_receipts=True)
            or self.currency_id != origin.currency_id
        ):
            return
        origin_base_lines, _tax_lines = origin._get_rounded_base_and_tax_lines(
            include_cash_rounding=False
        )
        target = origin._get_tax_amounts(origin_base_lines)
        computed = self._get_computed_tax_amounts()
        commands = self._get_tax_override_commands(
            target, computed, target.keys() | computed.keys()
        )
        _debug.logic(
            "tax_overrides_carried", move=self, origin=origin, commands=len(commands)
        )
        if commands:
            self.tax_override_ids = commands

    @_debug.perf.timed
    def _update_tax_overrides_from_totals(self, tax_totals) -> None:
        self.check_singleton()
        currency = self.currency_id
        if not currency:
            return
        requested = {
            tax_group["id"]: tax_group["tax_amount_currency"]
            for subtotal in tax_totals["subtotals"]
            for tax_group in subtotal["tax_groups"]
        }
        displayed = {
            tax_group["id"]: tax_group
            for subtotal in self._get_tax_totals_values()["subtotals"]
            for tax_group in subtotal["tax_groups"]
        }
        current_base_lines, _tax_lines = self._get_rounded_base_and_tax_lines(
            include_cash_rounding=False
        )
        current = self._get_tax_amounts(current_base_lines)
        computed = self._get_computed_tax_amounts()
        target_amounts = dict(current)
        taxes = self.env["account.tax"]
        for group_id, amount in requested.items():
            shown = displayed.get(group_id)
            if not shown or not currency.compare_amounts(
                amount, shown["tax_amount_currency"]
            ):
                continue
            group_taxes = [tax for tax in current if tax.tax_group_id.id == group_id]
            if not group_taxes:
                continue
            taxes |= self.env["account.tax"].union(*group_taxes)
            reset_amount = shown.get(
                "computed_tax_amount_currency", shown["tax_amount_currency"]
            )
            _debug.logic(
                "tax_group_amount_requested",
                move=self,
                tax_group=group_id,
                amount=amount,
                reset=not currency.compare_amounts(amount, reset_amount),
            )
            if not currency.compare_amounts(amount, reset_amount):
                for tax in group_taxes:
                    target_amounts[tax] = computed.get(tax)
                continue
            biggest = max(
                group_taxes, key=lambda tax: abs(current[tax]["tax_amount_currency"])
            )
            target_amounts[biggest] = {
                **current[biggest],
                "tax_amount_currency": currency.round(
                    current[biggest]["tax_amount_currency"]
                    + amount
                    - shown["tax_amount_currency"]
                ),
            }
        if commands := self._get_tax_override_commands(target_amounts, computed, taxes):
            self.tax_override_ids = commands

    @_debug.perf.timed
    def _drop_inapplicable_tax_overrides(self) -> list:
        self.check_singleton()
        overrides = self._get_draft_tax_overrides()
        if not overrides:
            return []
        computed = self._get_computed_tax_amounts()
        dropped = []
        for override in overrides:
            reason = override._get_inapplicable_reason(
                self.currency_id, computed.get(override.tax_id)
            )
            if not reason:
                continue
            _debug.logic(
                "tax_override_inapplicable", move=self, override=override, reason=reason
            )
            dropped.append((override.tax_id, override.amount_currency, reason))
            if self.id:
                override.with_context(tax_override_drop_reason=reason).unlink()
            else:
                self.tax_override_ids = [Command.unlink(override.id)]
        return dropped

    @_debug.perf.timed
    def _prepare_non_deductible_tax_line_vals(
        self, move, base_lines_values
    ) -> dict | None:
        non_deductible_lines_values = [
            line_values
            for line_values in base_lines_values
            if line_values["special_type"] == "non_deductible"
            and line_values["tax_ids"]
        ]
        _debug.logic(
            "non_deductible_tax_sources",
            move=move,
            count=len(non_deductible_lines_values),
        )
        if not non_deductible_lines_values:
            return None

        tax_amount = 0.0
        tax_amount_currency = 0.0
        for line_values in non_deductible_lines_values:
            details = line_values["tax_details"]
            tax_amount += -line_values["sign"] * (
                details["total_included"] - details["total_excluded"]
            )
            tax_amount_currency += -line_values["sign"] * (
                details["total_included_currency"] - details["total_excluded_currency"]
            )

        return {
            "move_id": move.id,
            "account_id": (
                move.journal_id.non_deductible_account_id
                or move.journal_id.default_account_id
            ).id,
            "display_type": "non_deductible_tax",
            "name": self.env._("private part (taxes)"),
            "balance": tax_amount,
            "amount_currency": tax_amount_currency,
            "sequence": max(
                move.line_ids.filtered(
                    lambda line: (
                        line.display_type
                        in ("product", *NON_DEDUCTIBLE_BASE_DISPLAY_TYPES)
                    )
                ).mapped("sequence"),
                default=0,
            )
            + 1,
        }

    @_debug.perf.timed
    def _sync_tax_lines(self, container):
        grouping_key_fields = self._get_tax_line_grouping_key_fields()

        def snapshot(move):
            return move._get_tax_sync_snapshot(
                grouping_key_fields, move._get_tax_base_amls(), move._get_tax_amls()
            )

        def prepare():
            return {move: snapshot(move) for move in container["records"]}

        def commit(before):
            to_delete = []
            to_create = []
            grouped_update = defaultdict(set)
            for move in container["records"]:
                if move.state != "draft":
                    continue
                get_mode = (
                    self._get_invoice_tax_sync_mode
                    if move.is_invoice(include_receipts=True)
                    else self._get_tax_rounding_mode
                )
                mode = get_mode(
                    move, before.get(move, EMPTY_TAX_SYNC_SNAPSHOT), snapshot(move)
                )
                if mode is SKIP:
                    _debug.logic("_sync_tax_lines_unchanged_skipped", move=move)
                    continue
                move_delete, move_create, move_update = self._get_tax_line_changes(
                    move, *mode
                )
                _debug.pipeline(
                    "_sync_tax_lines",
                    move=move,
                    mode=mode,
                    delete=len(move_delete),
                    create=len(move_create),
                    update=len(move_update),
                )
                to_delete += move_delete
                to_create += move_create
                for key, line_id in move_update:
                    grouped_update[key].add(line_id)

            for (_currency_id, values), lines in grouped_update.items():
                self.env["account.move.line"].browse(lines).write(dict(values))
            if to_delete:
                self.env["account.move.line"].browse(to_delete).with_context(
                    dynamic_unlink=True
                ).unlink()
            if to_create:
                self.env["account.move.line"].create(to_create)

        return sync_boundary(prepare, commit)

    @_debug.perf.timed
    def _get_tax_line_changes(
        self, move, round_from_tax_lines, reapply_currency_rate
    ) -> tuple:
        AccountTax = self.env["account.tax"]
        to_delete = []
        to_create = []
        to_update = []
        base_lines_values, tax_lines_values = move._get_rounded_base_and_tax_lines(
            round_from_tax_lines=round_from_tax_lines,
            reapply_currency_rate=reapply_currency_rate,
            include_cash_rounding=False,
        )
        AccountTax._add_accounting_data_in_base_lines_tax_details(
            base_lines_values,
            move.company_id,
            include_caba_tags=move.always_tax_exigible,
        )
        tax_results = AccountTax._prepare_tax_lines(
            base_lines_values, move.company_id, tax_lines=tax_lines_values
        )
        _debug.pipeline(
            "tax_lines_prepared",
            move=move,
            from_tax=round_from_tax_lines,
            reapply_rate=reapply_currency_rate,
            base_lines=len(base_lines_values),
            tax_lines=len(tax_lines_values),
            base_updates=len(tax_results["base_lines_to_update"]),
            tax_adds=len(tax_results["tax_lines_to_add"]),
            tax_deletes=len(tax_results["tax_lines_to_delete"]),
            tax_updates=len(tax_results["tax_lines_to_update"]),
        )

        non_deductible_tax_line = move.line_ids.filtered(
            lambda line: line.display_type == "non_deductible_tax"
        )[:1]
        non_deductible_vals = self._prepare_non_deductible_tax_line_vals(
            move, base_lines_values
        )
        _debug.logic(
            "non_deductible_tax_line_action",
            move=move,
            action=(
                "delete"
                if non_deductible_vals is None
                else "update"
                if non_deductible_tax_line
                else "create"
            ),
        )
        if non_deductible_vals is None:
            to_delete.extend(non_deductible_tax_line.ids)
        elif non_deductible_tax_line:
            tax_results["tax_lines_to_update"].append(
                (
                    {"record": non_deductible_tax_line},
                    "unused_grouping_key",
                    {
                        "amount_currency": non_deductible_vals["amount_currency"],
                        "balance": non_deductible_vals["balance"],
                        "account_id": non_deductible_vals["account_id"],
                    },
                )
            )
        else:
            to_create.append(non_deductible_vals)

        def stage_update(line, values):
            if values_differ(line, values):
                to_update.append(((line.currency_id.id, frozendict(values)), line.id))

        for base_line, values in tax_results["base_lines_to_update"]:
            stage_update(base_line["record"], values)

        to_delete.extend(
            tax_line_vals["record"].id
            for tax_line_vals in tax_results["tax_lines_to_delete"]
        )
        to_create.extend(
            {**tax_line_vals, "display_type": "tax", "move_id": move.id}
            for tax_line_vals in tax_results["tax_lines_to_add"]
        )
        for tax_line_vals, _grouping_key, values in tax_results["tax_lines_to_update"]:
            stage_update(tax_line_vals["record"], values)

        return to_delete, to_create, to_update

    def _get_non_deductible_amounts(self, product_lines) -> list:
        self.check_singleton()
        if not self.is_purchase_document(include_receipts=True):
            return []
        sign = self.direction_sign
        rate = self.invoice_currency_rate or 1.0
        amounts = []
        for line in product_lines:
            if line.display_type != "product" or not line._is_partially_deductible():
                continue
            non_deductible_subtotal = self.currency_id.round(
                line.price_subtotal * (1 - line.deductible_amount / 100)
            )
            amounts.append(
                (
                    line,
                    self.currency_id.round(sign * non_deductible_subtotal),
                    self.company_currency_id.round(
                        sign * non_deductible_subtotal / rate
                    ),
                )
            )
        return amounts

    @_debug.perf.timed
    def _prepare_non_deductible_line_vals(self, move):
        product_lines = move.line_ids.filtered(
            lambda line: line.display_type == "product"
        )
        amount_currency_total = 0.0
        balance_total = 0.0
        vals_list = []

        for line, amount_currency, balance in move._get_non_deductible_amounts(
            product_lines
        ):
            amount_currency_total += amount_currency
            balance_total += balance
            vals_list.append(
                {
                    "move_id": move.id,
                    "partner_id": move.commercial_partner_id.id,
                    "account_id": line.account_id.id,
                    "display_type": "non_deductible_product",
                    "name": line.name,
                    "balance": -balance,
                    "amount_currency": -amount_currency,
                    "tax_ids": [
                        Command.set(
                            line.tax_ids.filtered(
                                lambda tax: tax.amount_type != "fixed"
                            ).ids
                        )
                    ],
                    "sequence": line.sequence + 1,
                }
            )

        _debug.pipeline(
            "non_deductible_lines_built",
            move=move,
            products=len(product_lines),
            partial=len(vals_list),
            balance_total=balance_total,
        )
        vals_list.append(
            {
                "move_id": move.id,
                "partner_id": move.commercial_partner_id.id,
                "account_id": (
                    move.journal_id.non_deductible_account_id
                    or move.journal_id.default_account_id
                ).id,
                "display_type": "non_deductible_product_total",
                "name": self.env._("private part"),
                "balance": balance_total,
                "amount_currency": amount_currency_total,
                "tax_ids": [Command.clear()],
                "sequence": max(product_lines.mapped("sequence")) + 1,
            }
        )
        return vals_list

    @_debug.perf.timed
    def _sync_non_deductible_base_lines(self, container):
        def product_line_fingerprint(move):
            return move.journal_id, Counter(
                (
                    line.name,
                    line.price_subtotal,
                    line.tax_ids,
                    line.deductible_amount,
                    line.account_id,
                )
                for line in move.line_ids
                if line.display_type == "product"
            )

        def has_non_deductible_lines(move) -> bool:
            return bool(move._get_non_deductible_amounts(move.line_ids))

        def concerned(move):
            return move.state == "draft" and (
                move.is_purchase_document(include_receipts=True)
                or any(
                    line.display_type in NON_DEDUCTIBLE_BASE_DISPLAY_TYPES
                    for line in move.line_ids
                )
            )

        def prepare():
            return {
                move: product_line_fingerprint(move)
                for move in container["records"]
                if concerned(move)
            }

        def commit(before):
            to_delete = []
            to_create = []
            for move in container["records"]:
                if not concerned(move):
                    continue
                if product_line_fingerprint(move) == before.get(move):
                    continue

                to_delete += move.line_ids.filtered(
                    lambda line: line.display_type in NON_DEDUCTIBLE_BASE_DISPLAY_TYPES
                ).ids
                if has_non_deductible_lines(move):
                    to_create += self._prepare_non_deductible_line_vals(move)

            _debug.pipeline(
                "non_deductible_base_lines_planned",
                moves=container["records"],
                delete=len(to_delete),
                create=len(to_create),
            )
            if to_delete:
                self.env["account.move.line"].browse(to_delete).with_context(
                    dynamic_unlink=True
                ).unlink()
            if to_create:
                self.env["account.move.line"].create(to_create)

        return sync_boundary(prepare, commit)

    @_debug.perf.timed
    def _sync_dynamic_line(
        self,
        existing_key_fname,
        needed_vals_fname,
        needed_dirty_fname,
        line_type,
        container,
    ):
        def existing():
            if line_type == "epd":
                return {
                    line: (
                        line[existing_key_fname] or frozendict({"epd_line_id": line.id})
                    )
                    for line in container["records"].line_ids
                    if line.display_type == "epd"
                    if line[existing_key_fname] or line.id
                }
            return {
                line: line[existing_key_fname]
                for line in container["records"].line_ids
                if line[existing_key_fname]
            }

        def needed():
            return self._sync_dynamic_line_needed_values(
                container["records"].mapped(needed_vals_fname)
            )

        *path, dirty_fname = needed_dirty_fname.split(".")

        def dirty_records():
            eligible_recs = container["records"].mapped(".".join(path))
            if eligible_recs._name == "account.move.line":
                eligible_recs = eligible_recs.filtered(
                    lambda rec: rec.display_type != "cogs"
                )
            return eligible_recs.filtered(dirty_fname)

        def prepare():
            state = (existing(), needed())
            dirty_records()[dirty_fname] = False
            return state

        def commit(state):
            dirty = dirty_records()
            if not dirty:
                _debug.logic(
                    "_sync_dynamic_line_nothing_dirty_skipped", line_type=line_type
                )
                return
            _debug.pipeline(
                "_sync_dynamic_line",
                line_type=line_type,
                dirty=dirty,
                records=container["records"],
            )
            inv_existing_before, needed_before = state
            self._apply_dynamic_line_plan(
                inv_existing_before, existing(), needed_before, needed(), line_type
            )

        return sync_boundary(prepare, commit)

    @_debug.perf.timed
    def _apply_dynamic_line_plan(
        self, existing_before, existing_after, needed_before, needed_after, line_type
    ) -> None:
        AccountMoveLine = self.env["account.move.line"]
        live_ids = set(
            AccountMoveLine.browse(k["id"] for k in needed_before if "id" in k)
            .exists()
            .ids
        )
        needed_before = {
            k: v
            for k, v in needed_before.items()
            if "id" not in k or k["id"] in live_ids
        }

        plan = plan_dynamic_line_sync(
            existing_before,
            existing_after,
            needed_before,
            needed_after,
            values_differ,
        )
        if plan is None:
            _debug.logic(
                "_apply_dynamic_line_plan_no_plan_unchanged", line_type=line_type
            )
            return
        to_delete, to_create, to_write = plan
        _debug.pipeline(
            "_apply_dynamic_line_plan",
            line_type=line_type,
            delete=len(to_delete),
            create=len(to_create),
            write=len(to_write),
        )

        recyclable = defaultdict(list)
        for line in AccountMoveLine.browse([line.id for line in to_delete]).exists():
            recyclable[line.move_id.id].append(line)
        for key in list(to_create):
            candidates = recyclable.get(key.get("move_id"))
            if not candidates:
                continue
            candidates.pop().write(
                {**key, **to_create.pop(key), "display_type": line_type}
            )
        if leftover := [line for lines in recyclable.values() for line in lines]:
            AccountMoveLine.union(*leftover).with_context(dynamic_unlink=True).unlink()
        if to_create:
            AccountMoveLine.with_context(clean_context(self.env.context)).create(
                [
                    {**key, **values, "display_type": line_type}
                    for key, values in to_create.items()
                ]
            )
        for line, values in to_write.items():
            line.write(values)

    @_debug.perf.timed
    def _sync_invoice(self, container):
        def commercial_partner_by_move():
            return {
                move: move.commercial_partner_id
                for move in container["records"].filtered(lambda m: m.is_invoice(True))
            }

        def commit(before):
            after = commercial_partner_by_move()
            line_ids_by_partner = defaultdict(set)
            for move, partner in after.items():
                if move not in before or before[move] != partner:
                    line_ids_by_partner[partner].update(move.line_ids.ids)

            for partner, line_ids in line_ids_by_partner.items():
                _debug.logic(
                    "_sync_invoice_commercial_changed",
                    line_ids_count=len(line_ids),
                    partner=partner,
                )
                self.env["account.move.line"].browse(line_ids).partner_id = partner

        return sync_boundary(commercial_partner_by_move, commit)

    @_debug.perf.timed
    def _get_sync_stack(self, container) -> tuple:
        tax_container, invoice_container, misc_container = ({} for _ in range(3))

        def update_containers():
            tax_container["records"] = container["records"].filtered(
                lambda m: (
                    m.is_invoice(True)
                    or m.line_ids.tax_ids
                    or m.line_ids.tax_repartition_line_id
                )
            )
            invoice_container["records"] = container["records"].filtered(
                lambda m: m.is_invoice(True)
            )
            misc_container["records"] = container["records"].filtered(
                lambda m: m.is_entry() and not m.tax_cash_basis_origin_move_id
            )
            _debug.pipeline(
                "sync_containers_updated",
                moves=container["records"],
                tax=tax_container["records"],
                invoice=invoice_container["records"],
                misc=misc_container["records"],
            )

            return tax_container, invoice_container, misc_container

        stack = [
            self._sync_invoice(invoice_container),
            self._sync_dynamic_line(
                existing_key_fname="epd_key",
                needed_vals_fname="line_ids.epd_needed",
                needed_dirty_fname="line_ids.epd_dirty",
                line_type="epd",
                container=invoice_container,
            ),
            self._sync_non_deductible_base_lines(invoice_container),
            self._sync_tax_lines(tax_container),
            self._sync_dynamic_line(
                existing_key_fname="discount_allocation_key",
                needed_vals_fname="line_ids.discount_allocation_needed",
                needed_dirty_fname="line_ids.discount_allocation_dirty",
                line_type="discount",
                container=invoice_container,
            ),
            self._sync_rounding_lines(invoice_container),
            self._sync_unbalanced_lines(misc_container),
            self._sync_dynamic_line(
                existing_key_fname="term_key",
                needed_vals_fname="needed_terms",
                needed_dirty_fname="needed_terms_dirty",
                line_type="payment_term",
                container=invoice_container,
            ),
        ]

        return stack, update_containers

    @contextmanager
    def _sync_dynamic_lines(self, container):
        with self._disable_recursion("skip_invoice_sync") as disabled:
            if disabled:
                _debug.logic(
                    "_sync_dynamic_lines_skipped_recursion_guard",
                    records=container["records"],
                )
                yield
                return

            _debug.pipeline("_sync_dynamic_lines_enter", records=container["records"])
            stack_list, update_containers = self._get_sync_stack(container)
            update_containers()
            with ExitStack() as stack:
                for contextmgr in reversed(stack_list):
                    stack.enter_context(contextmgr)

                line_container = {"records": container["records"].line_ids}
                with container["records"].line_ids._sync_invoice(line_container):
                    yield  # noqa: RUF075 -- Commit synchronization only after the body succeeds.
                    line_container["records"] = container["records"].line_ids
                update_containers()
