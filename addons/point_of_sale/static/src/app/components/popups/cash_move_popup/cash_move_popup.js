/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { Input } from "@point_of_sale/app/components/inputs/input/input";
import { CashMoveListPopup } from "@point_of_sale/app/components/popups/cash_move_popup/cash_move_list_popup/cash_move_list_popup";
import { CashMoveReceipt } from "@point_of_sale/app/components/popups/cash_move_popup/cash_move_receipt/cash_move_receipt";
import { NumberPopup } from "@point_of_sale/app/components/popups/number_popup/number_popup";
import { useAsyncLockedMethod } from "@point_of_sale/app/hooks/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { isQueued } from "@point_of_sale/app/services/data_service";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { parseFloat } from "@web/core/parsers";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";
const log = makeLogger("pos.popup.cash_move");

export class CashMovePopup extends Component {
    static template = "point_of_sale.CashMovePopup";
    static components = { Input, Dialog };
    static props = {
        confirmKey: t.any().optional(),
        close: t.any(),
        getPayload: t.any().optional(),
    };
    props = useProps(this.constructor.props);
    setup() {
        useLifecycleLog(log);
        super.setup();
        this.utils = useService("contextual_utils_service");
        this.notification = useService("notification");
        this.pos = usePos();
        this.dialog = useService("dialog");
        this.hardwareProxy = useService("hardware_proxy");
        this.printer = useService("printer");
        this.state = proxy({
            /** @type {'in'|'out'} */
            type: "out",
            amount: "",
            reason: "",
        });
        this.confirm = useAsyncLockedMethod(this.confirm.bind(this));
        this.ui = useService("ui");
    }

    get partnerId() {
        return this.pos.user.partner_id.id;
    }

    async confirm() {
        const amount = parseFloat(this.state.amount);
        const formattedAmount = this.utils.formatCurrency(amount);
        log.pipeline("[session:cash_move] confirm", () => ({
            session: this.pos.session.id,
            type: this.state.type,
            amount,
            reason: this.state.reason.trim(),
            ignored: !amount,
        }));
        if (!amount) {
            this.notification.add(_t("Cash in/out of %s is ignored.", formattedAmount));
            return this.props.close();
        }
        const endMove = log.perf("[session:cash_move] try_cash_in_out");

        const type = this.state.type;
        const label = type === "in" ? _t("Cash In") : _t("Cash Out");
        const extras = { formattedAmount };
        const reason = this.state.reason.trim();

        const result = await this.pos.data.call(
            "pos.session",
            "try_cash_in_out",
            this._prepareTryCashInOutPayload(
                type,
                amount,
                reason,
                this.partnerId,
                extras,
            ),
            {},
            true,
        );
        const queued = isQueued(result);
        endMove({ session: this.pos.session.id, type, amount, queued });
        await this.pos.logEmployeeMessage(
            `${label} - ${_t("Amount")}: ${formattedAmount}`,
            "CASH_DRAWER_ACTION",
        );
        const order = this.pos.models["pos.order"].create({
            session_id: this.pos.session,
            company_id: this.pos.company,
            config_id: this.pos.config,
            user_id: this.pos.user,
            ticket_code: "",
            tracking_number: "",
            sequence_number: 0,
            pos_reference: "",
        });
        log.lifecycle("[session:cash_move] receipt order", () => ({
            order: order.uuid,
            transient: true,
        }));
        try {
            await this.printer.print(CashMoveReceipt, {
                reason,
                label,
                order: order,
                formattedAmount,
                date: new Date().toLocaleString(),
            });
        } finally {
            this.pos.models["pos.order"].delete(order);
        }

        this.props.getPayload?.(true);
        this.props.close();
        const sent =
            type === "in"
                ? _t("Successfully made a cash in of %(amount)s.", {
                      amount: formattedAmount,
                  })
                : _t("Successfully made a cash out of %(amount)s.", {
                      amount: formattedAmount,
                  });
        if (queued) {
            const closeWarning = this.notification.add(
                type === "in"
                    ? _t(
                          "The cash in of %(amount)s has not reached the server yet. It is kept on this device and sent automatically; the register cannot be closed until it is.",
                          { amount: formattedAmount },
                      )
                    : _t(
                          "The cash out of %(amount)s has not reached the server yet. It is kept on this device and sent automatically; the register cannot be closed until it is.",
                          { amount: formattedAmount },
                      ),
                { type: "warning", sticky: true },
            );
            this.pos.data.waitForReplay(result.uuid).then((replayed) => {
                if (replayed) {
                    closeWarning();
                    this.notification.add(sent, { autocloseDelay: 3000 });
                }
            });
            return;
        }
        this.notification.add(sent, { autocloseDelay: 3000 });
    }
    onClickButton(type) {
        this.state.type = type;
        this.inputRef.el.focus();
    }
    format(value) {
        return this.utils.isValidFloat(value)
            ? this.utils.formatCurrency(parseFloat(value))
            : "";
    }
    _prepareTryCashInOutPayload(type, amount, reason, partnerId, extras) {
        return [[this.pos.session.id], type, amount, reason, partnerId, extras];
    }
    isValidCashMove() {
        return (
            this.utils.isValidFloat(this.state.amount) &&
            this.state.reason.trim() !== ""
        );
    }
    async openDetails() {
        const endList = log.perf("[session:cash_move] get_cash_in_out_list");
        const cashMoves = await this.pos.data.call(
            "pos.session",
            "get_cash_in_out_list",
            [this.pos.session.id],
        );
        endList({ session: this.pos.session.id, moves: cashMoves.length });
        this.dialog.add(CashMoveListPopup, {
            cashMoves: cashMoves.map((m) => ({
                ...m,
                date: deserializeDateTime(m.date),
            })),
            partnerId: this.partnerId,
        });
    }
    async openNumpadDialog() {
        if (!this.ui.isTouch) {
            return;
        }

        const result = await makeAwaitable(this.dialog, NumberPopup, {
            title: _t("Amount"),
            startingValue: this.state.amount,
        });

        if (result) {
            this.state.amount = result;
        }
    }
}
