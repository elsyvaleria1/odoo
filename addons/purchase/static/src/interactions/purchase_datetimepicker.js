/** @odoo-module native */
import { parseISO, serializeDate, toDate, toDateTime } from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Interaction } from "@web/public/interaction";

export class PurchaseDatetimePicker extends Interaction {
    static selector = ".o-purchase-datetimepicker";

    setup() {
        this.notification = this.services.notification;
    }

    start() {
        const initialValue = this.el.dataset.value;
        const picker = this.services.datetime_picker.create({
            target: this.el,
            onChange: (newDate) => this.waitFor(this.updateDate(newDate)),
            pickerProps: {
                type: "date",
                value: this.readCommitmentDay(initialValue),
            },
        });
        picker.enable();
        this.registerCleanup(() => picker.dispose());
    }

    /**
     * @param {string | undefined} value
     * @returns {Temporal.PlainDate | undefined}
     */
    readCommitmentDay(value) {
        const instant = value && parseISO(value, "UTC");
        return instant ? toDate(toDateTime(instant)) : undefined;
    }

    /** @param {Temporal.PlainDate} newDate */
    async updateDate(newDate) {
        const { accessToken, orderId, lineId } = this.el.dataset;
        let result;
        try {
            result = await rpc(`/my/purchase/${orderId}/update`, {
                access_token: accessToken,
                [lineId]: serializeDate(newDate),
            });
        } catch {
            this.notification.add(
                _t("The date could not be saved. Please try again."),
                { type: "danger" },
            );
            return;
        }
        if (!result?.success) {
            this.notification.add(result?.error || _t("The date could not be saved."), {
                type: "danger",
            });
        }
    }
}

registry
    .category("public.interactions")
    .add("purchase.purchase_datetime_picker", PurchaseDatetimePicker);
