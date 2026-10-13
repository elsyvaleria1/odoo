from odoo import api, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_debug = DebugLog(__name__)

_OWNED_MOVE_FIELDS = frozenset({"date", "partner_id", "journal_id", "currency_id"})


class AccountMove(models.Model):
    _inherit = "account.move"

    def _as_entry_owner_check(self):
        return self.with_privilege(
            "account.privilege_check_entry_owner",
            reason="an entry is held to the payment that generated it",
        )

    def _get_entry_owner(self):
        self.check_singleton()
        return (
            self._as_entry_owner_check().payment_ids.filtered(
                lambda payment: not payment.counterpart_review_required
            )[:1]
            or self.statement_line_id
        )

    def _check_owned_move_write(self, vals) -> None:
        if (
            self.env.context.get("entry_owner_sync")
            or "state" in vals
            or _OWNED_MOVE_FIELDS.isdisjoint(vals)
        ):
            return
        for move in self:
            if not (owner := move._get_entry_owner()):
                continue
            changed = [
                fname
                for fname in _OWNED_MOVE_FIELDS & vals.keys()
                if self._field_will_change(move, vals, fname)
            ]
            if not changed:
                continue
            _debug.logic("owned_move_write_refused", move=move, fields=changed)
            raise UserError(
                self.env._(
                    "%(owner)s generated %(move)s, so its %(fields)s can only change "
                    "through it: %(hint)s",
                    owner=owner.display_name,
                    hint=owner._get_entry_correction_hint(),
                    move=move.display_name,
                    fields=", ".join(
                        self._fields[fname].get_description(self.env)["string"]
                        for fname in sorted(changed)
                    ),
                )
            )

    def _check_entry_shape(self) -> None:
        for move in self.filtered("statement_line_id"):
            journal = move.statement_line_id.journal_id
            liquidity = move.line_ids.filtered(
                lambda line: line.payment_role == "liquidity"
            )
            if len(liquidity) != 1 or (move.line_ids - liquidity).filtered(
                lambda line, account=liquidity.account_id: line.account_id == account
            ):
                _debug.logic("statement_entry_liquidity_refused", move=move)
                raise UserError(
                    self.env._(
                        "The journal entry %s reached an invalid state regarding its related statement line.\n"
                        "To be consistent, the journal entry must always have exactly one journal item involving the "
                        "bank/cash account.",
                        move.display_name,
                    )
                )
            suspense = move.line_ids.filtered(
                lambda line, account=journal.suspense_account_id: (
                    line.account_id == account
                )
            )
            if len(suspense) > 1:
                _debug.logic("statement_entry_suspense_refused", move=move)
                raise UserError(
                    self.env._(
                        "%(move)s reached an invalid state regarding its related statement line.\n"
                        "To be consistent, the journal entry must always have exactly one suspense line.",
                        move=move.display_name,
                    )
                )

    @api.model
    def _move_payment_records_to_entries(self, pairs) -> None:
        if not pairs:
            return
        cr = self.env.cr
        mapping = SQL(
            "(VALUES %s) AS pm(payment_id, move_id)",
            SQL(", ").join(
                SQL("(%s, %s)", payment_id, move_id) for payment_id, move_id in pairs
            ),
        )
        payment_model_id = self.env["ir.model"]._get_id("account.payment")
        move_model_id = self.env["ir.model"]._get_id("account.move")
        cr.execute(
            SQL(
                """
                DELETE FROM mail_followers fol
                 USING %(mapping)s
                 WHERE fol.res_model = 'account.payment'
                   AND fol.res_id = pm.payment_id
                   AND EXISTS (
                        SELECT 1 FROM mail_followers other
                         WHERE other.res_model = 'account.move'
                           AND other.res_id = pm.move_id
                           AND other.partner_id = fol.partner_id
                   )
                """,
                mapping=mapping,
            )
        )
        for ir_field in self.env["ir.model.fields"].search(
            [("ttype", "=", "many2one_reference"), ("store", "=", True)]
        ):
            if ir_field.model not in self.env:
                continue
            model = self.env[ir_field.model]
            field = model._fields.get(ir_field.name)
            if model._abstract or not model._auto or not field or not field.store:
                continue
            model_field = model._fields.get(field.model_field)
            if not model_field or not model_field.store:
                continue
            assignments = [SQL("%s = pm.move_id", SQL.identifier(field.name))]
            if model_field.type == "many2one":
                match = SQL(
                    "rec.%s = %s", SQL.identifier(model_field.name), payment_model_id
                )
                assignments.append(
                    SQL("%s = %s", SQL.identifier(model_field.name), move_model_id)
                )
            else:
                match = SQL(
                    "rec.%s = 'account.payment'", SQL.identifier(model_field.name)
                )
                assignments.append(
                    SQL("%s = 'account.move'", SQL.identifier(model_field.name))
                )
                if (
                    "res_model_id" in model._fields
                    and model._fields["res_model_id"].store
                ):
                    assignments.append(SQL("res_model_id = %s", move_model_id))
            cr.execute(
                SQL(
                    """
                    UPDATE %(table)s rec
                       SET %(assignments)s
                      FROM %(mapping)s
                     WHERE %(match)s AND rec.%(column)s = pm.payment_id
                    """,
                    table=SQL.identifier(model._table),
                    assignments=SQL(", ").join(assignments),
                    mapping=mapping,
                    match=match,
                    column=SQL.identifier(field.name),
                )
            )
        for ir_field in self.env["ir.model.fields"].search(
            [("ttype", "=", "reference"), ("store", "=", True)]
        ):
            if ir_field.model not in self.env:
                continue
            model = self.env[ir_field.model]
            if model._abstract or not model._auto or ir_field.name not in model._fields:
                continue
            cr.execute(
                SQL(
                    """
                    UPDATE %(table)s rec
                       SET %(column)s = 'account.move,' || pm.move_id
                      FROM %(mapping)s
                     WHERE rec.%(column)s = 'account.payment,' || pm.payment_id
                    """,
                    table=SQL.identifier(model._table),
                    column=SQL.identifier(ir_field.name),
                    mapping=mapping,
                )
            )
        cr.execute(
            SQL(
                """
                UPDATE account_move_line line
                   SET payment_role = NULL
                  FROM %(mapping)s
                 WHERE line.move_id = pm.move_id
                """,
                mapping=mapping,
            )
        )
        cr.execute(
            SQL(
                "DELETE FROM account_payment WHERE id = ANY(%s)",
                [payment_id for payment_id, _move_id in pairs],
            )
        )
