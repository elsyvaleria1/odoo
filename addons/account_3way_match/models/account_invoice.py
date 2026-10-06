from odoo import api, fields, models
from odoo.libs.numbers import float_compare

from odoo.addons.account.tools.display_types import NON_ACCOUNTABLE_DISPLAY_TYPES

# Shared by release_to_pay and release_to_pay_manual on the bill, and by
# can_be_paid on its lines.
_release_to_pay_status_list = [("yes", "Yes"), ("no", "No"), ("exception", "Exception")]

# One help text, exported once. The two bill-level fields explain the same three
# values, so keeping two near-identical blocks meant translating the same
# paragraph twice in every language and letting them drift the first time one of
# them was edited.
#
# The last sentence describes the gesture the user can actually make. It used to
# read "you can force it by ticking the 'Force Status' checkbox", which is
# impossible: the checkbox is invisible until it is already true, and it is set
# for the user by _onchange_release_to_pay_manual.
_release_to_pay_help = (
    "  * Yes: you should pay the bill, you have received the products\n"
    "  * No, you should not pay the bill, you have not received the products\n"
    "  * Exception, there is a difference between received and billed quantities\n"
    "Changing this status forces it, and 'Force Status' is ticked to say so. "
    "Clear that box to go back to the automatic verdict."
)


class AccountMove(models.Model):
    _inherit = "account.move"

    release_to_pay = fields.Selection(
        selection=_release_to_pay_status_list,
        string="Release to Pay",
        compute="_compute_release_to_pay",
        # release_to_pay reads release_to_pay_manual, which is computed back
        # from release_to_pay: the two fields are a declared cycle and the ORM
        # requires it to be named. It converges because the branches are
        # mutually exclusive -- a forced bill takes the manual value and leaves
        # it alone, an unforced one derives both from its lines.
        recursive=True,
        store=True,
        copy=False,
        help="This field can take the following values :\n" + _release_to_pay_help,
    )
    release_to_pay_manual = fields.Selection(
        selection=_release_to_pay_status_list,
        string="Should Be Paid",
        compute="_compute_release_to_pay_manual",
        recursive=True,
        store=True,
        copy=False,
        readonly=False,
        help=_release_to_pay_help,
    )
    force_release_to_pay = fields.Boolean(
        string="Force Status",
        copy=False,
        help="Indicates whether the 'Should Be Paid' status is defined automatically or manually.",
    )

    @api.model
    def _release_to_pay_move_types(self):
        """The move types this module has an opinion about.

        One definition, read by _compute_release_to_pay, by _compute_can_be_paid on
        the lines and by the journal dashboard. The three used to disagree:
        the compute ran for every invoice, customer ones included; the form
        view showed the result only on ('in_invoice', 'in_refund'); and the
        dashboard's draft query dropped purchase receipts entirely. A purchase
        receipt therefore carried a computed, invisible, undashboarded verdict
        on whether it could be paid.

        The module is "Vendor Bill: Release to Pay", so the honest set is the
        purchase documents, receipts included. views/account_invoice_view.xml
        repeats it as a literal because a view's `invisible` cannot call a
        model method; keep the two in step.
        """
        return self.get_purchase_types(include_receipts=True)

    @api.model
    def _release_to_pay_refund_types(self) -> list:
        """The refund documents among _release_to_pay_move_types().

        A credit note is not a document one pays; it offsets one. Three places
        need to know which of the judged move types are refunds -- the quantity
        source, where a refund subtracts; the line's own contribution to that
        quantity, which is negative for a refund; and the dashboard gate, which
        exempts them. They must not each keep their own list, or widening the
        judged set will leave some of them behind.
        """
        return [
            move_type
            for move_type in self._release_to_pay_move_types()
            if move_type in ("in_refund", "out_refund")
        ]

    @api.depends(
        "invoice_line_ids.can_be_paid",
        "force_release_to_pay",
        "release_to_pay_manual",
        "payment_state",
    )
    def _compute_release_to_pay(self) -> None:
        """Compute the bill-level release-to-pay verdict from its lines, the
        manual override and the payment state.
        """
        release_to_pay_types = self._release_to_pay_move_types()
        for invoice in self:
            if invoice.move_type not in release_to_pay_types:
                # Not a document this module judges. Leaving it unset says so;
                # it used to land on 'exception', which is a verdict, and one
                # that happened to fall inside the dashboard's gate.
                invoice.release_to_pay = False
            elif invoice.payment_state == "paid":
                # no need to pay, if it's already paid
                invoice.release_to_pay = "no"
            elif invoice.force_release_to_pay:
                # release_to_pay_manual is user-editable, so a forced bill can
                # be left without one. Storing that NULL would match none of
                # 'yes', 'no' or 'exception': the bill would fall out of the
                # dashboard gate and out of all three search filters at once --
                # neither payable, nor blocked, nor flagged, just unmonitored.
                # Fall back to the status that asks for a human.
                invoice.release_to_pay = invoice.release_to_pay_manual or "exception"
            else:
                result = None
                for invoice_line in invoice.invoice_line_ids.filtered(
                    lambda l: l.display_type not in NON_ACCOUNTABLE_DISPLAY_TYPES
                ):
                    line_status = invoice_line.can_be_paid
                    if line_status == "exception":
                        # one line in exception puts the whole bill in exception
                        result = "exception"
                        break
                    # the bill takes the status its lines agree on; lines that
                    # disagree put it in exception
                    if not result:
                        result = line_status
                    elif line_status != result:
                        result = "exception"
                        break

                # 'result' stays None when the bill carries no billable line
                invoice.release_to_pay = result or "no"

    @api.depends("release_to_pay", "force_release_to_pay")
    def _compute_release_to_pay_manual(self) -> None:
        for invoice in self:
            if invoice.force_release_to_pay:
                # The override belongs to the user, so the compute keeps it.
                # Saying so by assigning the field to itself is not a no-op:
                # falling off the end of the method leaves a stored field
                # cached as False and writes NULL over the very value this
                # branch exists to preserve.
                invoice.release_to_pay_manual = invoice.release_to_pay_manual
            else:
                invoice.release_to_pay_manual = invoice.release_to_pay

    @api.onchange("release_to_pay_manual")
    def _onchange_release_to_pay_manual(self) -> None:
        if self.release_to_pay and self.release_to_pay_manual != self.release_to_pay:
            self.force_release_to_pay = True


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    can_be_paid = fields.Selection(
        selection=_release_to_pay_status_list,
        # Not "Release to Pay": that is the bill-level verdict's label, and two
        # messages differing only in the case of one word read as the same field
        # in the UI while denoting different things.
        string="Line Release to Pay",
        compute="_compute_can_be_paid",
        store=True,
        copy=False,
    )

    @api.depends(
        "purchase_line_ids",
        "purchase_line_ids.qty_transferred",
        "purchase_line_ids.product_qty",
        "purchase_line_ids.invoice_line_ids.quantity",
        "purchase_line_ids.invoice_line_ids.product_uom_id",
        "purchase_line_ids.invoice_line_ids.parent_state",
        "purchase_line_ids.invoice_line_ids.move_id.move_type",
        "purchase_line_ids.invoice_line_ids.move_id.payment_state",
        # The order side of the comparison, and it has to be declared as
        # carefully as the bill side: the price check below reads the order
        # line's own price, discount, currency and unit, and the policy switch
        # reads its product. Without these, raising the price on the purchase
        # order after the bill exists left the stored verdict at 'yes' and the
        # bill stayed payable at the old price -- which is the bypass the price
        # check was added to close. The window is real: the form makes
        # price_unit readonly once a bill claims the line, but that is the
        # form's rule only, and a write that does not go through it still
        # reaches the price while the bill is a draft awaiting release.
        "purchase_line_ids.price_unit",
        "purchase_line_ids.discount",
        "purchase_line_ids.currency_id",
        "purchase_line_ids.product_uom_id",
        "purchase_line_ids.product_id",
        "purchase_line_ids.product_id.bill_policy",
        "price_unit",
        "discount",
        "product_uom_id",
        "currency_id",
        "move_id.move_type",
        "move_id.invoice_date",
    )
    def _compute_can_be_paid(self) -> None:
        """Compute each invoice line's release-to-pay status.

        The status is decided by the billing policy of the product on the
        linked purchase order line, but two rules come first and are easy to
        miss when reading the branches below:

        * a line linked to no purchase order at all is 'exception' -- there is
          nothing to match it against;
        * a line whose price no longer agrees with the order it came from is
          'exception', whatever the quantities say.
        """
        precision = self.env["decimal.precision"].get_precision("Product Unit")
        # The unit price carries its own precision, and it is not the
        # currency's. price_unit is stored at 'Product Price' digits, which a
        # company is free to raise above the two decimals its currency rounds
        # to -- and companies that bill fractions of a cent per unit do. See
        # the comparison below for what that costs.
        price_precision = self.env["decimal.precision"].get_precision("Product Price")
        release_to_pay_types = self.env["account.move"]._release_to_pay_move_types()
        refund_types = self.env["account.move"]._release_to_pay_refund_types()
        for invoice_line in self:
            if invoice_line.move_id.move_type not in release_to_pay_types:
                # can_be_paid is stored on account_move_line, the largest table
                # in the database. Every customer-invoice line, tax line and
                # journal-entry line used to hold 'exception' there -- a verdict
                # on a question nobody asked about them.
                invoice_line.can_be_paid = False
                continue

            po_lines = invoice_line.purchase_line_ids
            if po_lines:
                # Every quantity and price below is expressed in `uom`, the
                # unit of the first order line, so that a bill written in a
                # different unit from its order still compares like with like.
                uom = po_lines[0].product_uom_id
                if not self._release_to_pay_uoms_comparable(
                    invoice_line, po_lines, uom
                ):
                    invoice_line.can_be_paid = "exception"
                    continue

                invoiced_qty = self._billed_qty_for_order_lines(po_lines, uom)
                received_qty = sum(
                    line.product_uom_id._get_quantity_in_unit(line.qty_transferred, uom)
                    for line in po_lines
                )
                ordered_qty = sum(
                    line.product_uom_id._get_quantity_in_unit(line.product_qty, uom)
                    for line in po_lines
                )
                # What this line itself contributed to `invoiced_qty`. A refund
                # subtracts there, so its own contribution is negative and the
                # branches below have to add it back rather than subtract it
                # again -- netting a credit note's quantity off twice produced a
                # verdict with no arithmetic behind it.
                own_qty = invoice_line.product_uom_id._get_quantity_in_unit(
                    invoice_line.quantity, uom
                )
                if invoice_line.move_id.move_type in refund_types:
                    own_qty = -own_qty

                # A price that no longer matches the order is an exception. Both
                # sides are reduced to the same thing first -- net of discount,
                # per unit of `uom`, in the order's currency -- because a bill
                # written in another unit, or carrying its discount in the
                # discount field rather than in the unit price, is not a price
                # change and must not be flagged as one.
                invoice_currency = invoice_line.currency_id
                rate_date = (
                    invoice_line.move_id.invoice_date
                    or fields.Date.context_today(invoice_line)
                )
                invoice_price = invoice_line.product_uom_id._get_price_in_unit(
                    invoice_line.price_unit
                    * (1.0 - (invoice_line.discount or 0.0) / 100.0),
                    uom,
                )
                has_price_exception = False

                for po_line in po_lines:
                    order_currency = po_line.currency_id
                    order_price = po_line.product_uom_id._get_price_in_unit(
                        po_line.price_unit * (1.0 - (po_line.discount or 0.0) / 100.0),
                        uom,
                    )
                    invoice_converted_price = invoice_currency._convert(
                        invoice_price,
                        order_currency,
                        invoice_line.company_id,
                        rate_date,
                        round=False,
                    )
                    # float_compare at the price precision, not
                    # currency.compare_amounts. These are unit prices, not
                    # amounts: rounding them to the currency's two decimals
                    # before comparing hid every drift smaller than a cent per
                    # unit. Measured, with 'Product Price' at 4 digits: an
                    # order at 100.1234 billed at 100.1249 compared equal and
                    # the line read 'yes' -- a price change the whole check
                    # exists to catch, multiplied by every unit on the bill.
                    # `round=False` above is what makes the finer comparison
                    # mean anything; rounding the converted price to the
                    # currency first would put the noise back.
                    if (
                        float_compare(
                            order_price,
                            invoice_converted_price,
                            precision_digits=price_precision,
                        )
                        != 0
                    ):
                        has_price_exception = True
                        break

                if has_price_exception:
                    invoice_line.can_be_paid = "exception"
                    continue

                # Quantities of different products cannot be added together and
                # their billing policies can disagree, so a mixed link is not
                # something this control can judge. Say so rather than summing
                # apples with oranges and answering from the first line.
                #
                # The second half checks the line being judged against the
                # order, which the first half never did: it only made the order
                # lines agree among themselves. A bill line carrying one product
                # linked to an order line for another read its verdict off
                # quantities and a price belonging to a different article --
                # measured 'yes' on a bill for a product that was never ordered.
                # Lines with no product at all are left alone: they were judged
                # before and nothing here makes them less judgeable.
                if len(po_lines.product_id) > 1 or (
                    invoice_line.product_id
                    and invoice_line.product_id != po_lines.product_id
                ):
                    invoice_line.can_be_paid = "exception"
                    continue

                # Read the policy off the first purchase line. Lines carrying
                # different products were rejected above, so they agree.
                if po_lines[0].product_id.bill_policy == "ordered":
                    invoice_line.can_be_paid = self._release_to_pay_for_ordered(
                        own_qty, invoiced_qty, ordered_qty, precision
                    )
                else:
                    invoice_line.can_be_paid = self._release_to_pay_for_transferred(
                        invoiced_qty, received_qty, ordered_qty, precision
                    )

            else:
                invoice_line.can_be_paid = "exception"

    @staticmethod
    def _release_to_pay_uoms_comparable(invoice_line, po_lines, uom) -> bool:
        """Can every quantity and price this verdict needs be stated in `uom`?

        Answering it up front, and answering 'exception' when it cannot, is
        not politeness towards the conversion helpers.
        uom.uom._get_price_in_unit and _get_quantity_in_unit are strict: handed two units with no common
        reference unit they raise UserError, and can_be_paid is a *stored*
        compute, so the ORM replays it over every row when the column is
        created or a dependency changes. One row whose bill line carries a
        unit unrelated to its order line therefore aborts the whole flush --
        an unrelated write, or `-u account_3way_match` on a database with any
        legacy row like it, dies on a traceback that names neither. That is
        the exact failure the fork describes above
        uom.uom._get_quantity_reconcile, and core's own qty_invoiced --
        the quantity this method reproduces -- degrades there instead of
        raising (purchase/models/purchase_order_line.py, in _get_invoiced_qty).

        Degrading is not enough here, though: an unconverted quantity is a
        wrong number, and this compute decides whether money may leave. A
        unit that cannot be expressed in `uom` makes every comparison below
        meaningless, so the honest verdict is the one the module already gives
        when it cannot judge a line.

        The units checked are every one the branches below convert: the bill
        line's own, each order line's, and each bill line counted against
        those order lines by _billed_qty_for_order_lines.
        """
        units = (
            invoice_line.product_uom_id
            | po_lines.product_uom_id
            | po_lines.invoice_line_ids.product_uom_id
        )
        return all(unit._has_common_reference(uom) for unit in units)

    @staticmethod
    def _billed_qty_for_order_lines(po_lines, uom):
        """Quantity billed against `po_lines`, expressed in `uom`.

        Deliberately not `po_lines._prepare_qty_invoiced()`: that helper keys
        its result per order line and each value counts every bill line
        reachable from that line, so summing the values multiplies a bill line
        by the number of order lines it is linked to. `purchase_line_ids` is a
        Many2many, so that is the ordinary case, not a corner one. Its two
        rules are reproduced here over the distinct bill lines instead: a
        cancelled move does not count unless it is invoicing legacy, and a
        refund subtracts.

        Also not `qty_invoiced`: that deliberately counts posted bills only,
        and a release-to-pay control exists precisely to judge a bill that is
        not posted yet. Two draft bills of 6 and 5 against an order of 10 have
        to read as over-billed while both are still drafts.

        The documents counted here are the ones the module judges, and not
        `po_lines._get_invoice_move_types()`, which is core's notion of an
        order's billing chain and stops at ('in_invoice', 'in_refund'). The
        two disagreed about purchase receipts: the module judged a receipt but
        counted nothing for it, so a receipt could bill any quantity at all
        against an order and still read 'yes'. A document this module is
        willing to release for payment is a document that has to count against
        what was ordered.
        """
        AccountMove = po_lines.env["account.move"]
        judged_types = AccountMove._release_to_pay_move_types()
        refund_types = AccountMove._release_to_pay_refund_types()
        billed = 0.0
        for line in po_lines.invoice_line_ids:
            move = line.move_id
            if move.move_type not in judged_types:
                continue
            if move.state == "cancel" and move.payment_state != "invoicing_legacy":
                continue
            qty = line.product_uom_id._get_quantity_in_unit(line.quantity, uom)
            if move.move_type in refund_types:
                billed -= qty
            else:
                billed += qty
        return billed

    @staticmethod
    def _release_to_pay_for_ordered(
        own_qty, invoiced_qty, ordered_qty, precision
    ) -> str:
        """Release-to-pay status of a line billed on ordered quantity.

        All three quantities are expressed in the purchase order line's unit.
        """
        if (
            float_compare(
                invoiced_qty - own_qty, ordered_qty, precision_digits=precision
            )
            >= 0
        ):
            # other invoicing already covers the ordered quantity: nothing left to pay
            return "no"
        if float_compare(invoiced_qty, ordered_qty, precision_digits=precision) <= 0:
            # total invoiced stays within the ordered quantity: payable
            return "yes"
        # billed beyond the ordered quantity
        return "exception"

    @staticmethod
    def _release_to_pay_for_transferred(
        invoiced_qty, received_qty, ordered_qty, precision
    ) -> str:
        """Release-to-pay status of a line billed on received quantity.

        All three quantities are expressed in the purchase order line's unit.
        """
        if float_compare(invoiced_qty, received_qty, precision_digits=precision) <= 0:
            # received at least what was invoiced: payable
            return "yes"
        if (
            # float_compare, not `== 0`: received_qty is a sum of converted
            # quantities, and summing them is not exact -- 0.1 + 0.2 - 0.3 over
            # three order lines measures 2.8e-17, which is zero at every
            # precision this module works in and is not zero to `==`. That
            # difference alone turned a 'no' into an 'exception'.
            float_compare(received_qty, 0.0, precision_digits=precision) == 0
            and float_compare(invoiced_qty, ordered_qty, precision_digits=precision)
            <= 0
        ):
            # nothing received yet; the ordered-qty guard sends an over-billed line to exception instead of 'no'
            return "no"
        # invoiced more than received (over-billed)
        return "exception"
