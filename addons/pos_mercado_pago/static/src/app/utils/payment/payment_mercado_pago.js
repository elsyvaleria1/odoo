/** @odoo-module native */
import { register_payment_method } from "@point_of_sale/app/services/pos_store";
import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { _t } from "@web/core/translation";
import { AlertDialog } from "@web/ui/dialog";

const POLLING_INTERVAL_MS = 5000;
const SETTLED_STATES = ["FINISHED", "PROCESSED"];
const FAILED_STATES = ["CANCELED", "ERROR", "ABANDONED"];
const AWAITING_STATUSES = ["waitingCard", "waitingCancel"];

export class PaymentMercadoPago extends PaymentInterface {
    setup() {
        super.setup(...arguments);
        this.paymentLineResolvers = {};
        this.pollingIntervals = {};
        this.pendingChecks = {};
        for (const line of this.pos.models["pos.payment"].getAll()) {
            if (line.payment_method_id?.id === this.payment_method_id.id) {
                this.resumePayment(line);
            }
        }
    }

    _callMercadoPago(method, argument) {
        return this.env.services.orm.silent.call("pos.payment.method", method, [
            [this.payment_method_id.id],
            argument,
        ]);
    }

    createPaymentIntent(line) {
        const order = line.pos_order_id;
        // "external_reference" is sent back with the webhook notification
        return this._callMercadoPago("mp_payment_intent_create", {
            amount: this.pos.currency.toMinorUnits(line.amount),
            additional_info: {
                external_reference: `${this.pos.config.current_session_id.id}_${this.payment_method_id.id}_${order.uuid}`,
                print_on_terminal: true,
            },
        });
    }

    getPaymentIntent(paymentIntentId) {
        return this._callMercadoPago("mp_payment_intent_get", paymentIntentId);
    }

    cancelPaymentIntent(paymentIntentId) {
        return this._callMercadoPago("mp_payment_intent_cancel", paymentIntentId);
    }

    getPaymentOfIntent(paymentIntentId) {
        return this._callMercadoPago("mp_get_payment_status", paymentIntentId);
    }

    async sendPaymentRequest(uuid) {
        await super.sendPaymentRequest(...arguments);
        const line = this.pos.getOrder().getPaymentlineByUuid(uuid);
        try {
            // During payment creation, user can't cancel the payment intent
            line.setPaymentStatus("waitingCapture");
            const paymentIntent = await this.createPaymentIntent(line);
            if (!paymentIntent?.id) {
                this._showMsg(paymentIntent?.message, "error");
                return false;
            }
            line.uiState = { ...line.uiState, mercadoPagoIntentId: paymentIntent.id };
            line.setPaymentStatus("waitingCard");
            return await this.waitForPaymentConfirmation(line);
        } catch (error) {
            this._showMsg(error, "System error");
            return false;
        }
    }

    async sendPaymentCancel(order, uuid) {
        await super.sendPaymentCancel(order, uuid);
        const line = order.getPaymentlineByUuid(uuid);
        const paymentIntentId = line?.uiState?.mercadoPagoIntentId;
        if (!paymentIntentId || !this._isAwaiting(line, paymentIntentId)) {
            return true;
        }
        const cancelingStatus = await this.cancelPaymentIntent(paymentIntentId);
        if (!("error" in cancelingStatus)) {
            this._settle(line, false);
            return true;
        }
        // The intent may have finished on the terminal meanwhile: its result
        // decides, never the failed cancel.
        await this.checkPaymentIntent(line);
        if (!this._isAwaiting(line, paymentIntentId)) {
            return true;
        }
        this._showMsg(_t("Payment has to be canceled on terminal"), "info");
        return false;
    }

    waitForPaymentConfirmation(line) {
        const { promise, resolve } = Promise.withResolvers();
        this.paymentLineResolvers[line.uuid] = resolve;
        this._startPolling(line);
        return promise;
    }

    resumePayment(line) {
        if (
            this.paymentLineResolvers[line.uuid] ||
            !this._isAwaiting(line, line.uiState?.mercadoPagoIntentId)
        ) {
            return;
        }
        this.waitForPaymentConfirmation(line).then((isPaymentSuccessful) =>
            line.handlePaymentResponse(isPaymentSuccessful),
        );
        return this.checkPaymentIntent(line);
    }

    handleMercadoPagoWebhook(line) {
        return this.checkPaymentIntent(line);
    }

    checkPaymentIntent(line) {
        this.pendingChecks[line.uuid] ??= this._checkPaymentIntent(line).finally(
            () => delete this.pendingChecks[line.uuid],
        );
        return this.pendingChecks[line.uuid];
    }

    async _checkPaymentIntent(line) {
        const paymentIntentId = line.uiState?.mercadoPagoIntentId;
        if (!this._isAwaiting(line, paymentIntentId)) {
            return;
        }
        let paymentIntent;
        let payment;
        try {
            paymentIntent = await this.getPaymentIntent(paymentIntentId);
            if (SETTLED_STATES.includes(paymentIntent?.state)) {
                payment = await this.getPaymentOfIntent(paymentIntentId);
            }
        } catch {
            return;
        }
        if (
            paymentIntent?.id !== paymentIntentId ||
            !this._isAwaiting(line, paymentIntentId)
        ) {
            return;
        }
        if (FAILED_STATES.includes(paymentIntent.state)) {
            this._showMsg(_t("Payment has been canceled"), "info");
            this._settle(line, false);
        } else if (payment) {
            const isApproved = payment.status === "approved";
            if (!isApproved) {
                this._showMsg(_t("Payment has been rejected"), "info");
            }
            this._settle(line, isApproved);
        }
    }

    _isAwaiting(line, paymentIntentId) {
        return Boolean(
            paymentIntentId &&
            line.uiState?.mercadoPagoIntentId === paymentIntentId &&
            AWAITING_STATUSES.includes(line.getPaymentStatus()),
        );
    }

    _startPolling(line) {
        this._stopPolling(line);
        const paymentIntentId = line.uiState.mercadoPagoIntentId;
        this.pollingIntervals[line.uuid] = setInterval(() => {
            if (this._isAwaiting(line, paymentIntentId)) {
                this.checkPaymentIntent(line);
            } else {
                this._stopPolling(line);
            }
        }, POLLING_INTERVAL_MS);
    }

    _stopPolling(line) {
        clearInterval(this.pollingIntervals[line.uuid]);
        delete this.pollingIntervals[line.uuid];
    }

    _settle(line, isPaymentSuccessful) {
        this._stopPolling(line);
        line.handlePaymentResponse(isPaymentSuccessful);
        const resolver = this.paymentLineResolvers[line.uuid];
        delete this.paymentLineResolvers[line.uuid];
        resolver?.(isPaymentSuccessful);
    }

    // private methods
    _showMsg(msg, title) {
        this.env.services.dialog.add(AlertDialog, {
            title: "Mercado Pago " + title,
            body: msg,
        });
    }
}

register_payment_method("mercado_pago", PaymentMercadoPago);
