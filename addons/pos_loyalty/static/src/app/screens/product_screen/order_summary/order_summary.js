/** @odoo-module native */
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import { ask } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { logPosMessage } from "@point_of_sale/app/utils/pretty_console_log";
import { ManageGiftCardPopup } from "@pos_loyalty/app/components/popups/manage_giftcard_popup/manage_giftcard_popup";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { AlertDialog, ConfirmationDialog } from "@web/ui/dialog";
patch(OrderSummary.prototype, {
    setup() {
        super.setup(...arguments);
        this.notification = useService("notification");
    },
    async updateSelectedOrderline({ buffer, key }) {
        const selectedLine = this.currentOrder.getSelectedOrderline();
        if (selectedLine?.gift_code && key !== "Backspace" && key !== "Delete") {
            this.dialog.add(AlertDialog, {
                title: _t("Gift Card"),
                body: _t(
                    "You cannot change the quantity or price of a physical gift card.",
                ),
            });
            return;
        }

        if (key === "-") {
            if (selectedLine && selectedLine._e_wallet_program_id) {
                this.notification.add(
                    _t(
                        "You cannot set negative quantity or price to gift card or ewallet.",
                    ),
                    4000,
                );
                return;
            }
        }
        if (
            selectedLine &&
            selectedLine.is_reward_line &&
            !selectedLine.manual_reward &&
            (key === "Backspace" || key === "Delete")
        ) {
            const reward = selectedLine.reward_id;
            const confirmed = await ask(this.dialog, {
                title: _t("Deactivating reward"),
                body: _t(
                    "Are you sure you want to remove %s from this order?\n You will still be able to claim it through the reward button.",
                    reward.description,
                ),
                cancelLabel: _t("No"),
                confirmLabel: _t("Yes"),
            });
            if (confirmed) {
                buffer = null;
            } else {
                return;
            }
        }
        return super.updateSelectedOrderline({ buffer, key });
    },
    /** @override */
    _setValue(val) {
        const selectedLine = this.currentOrder.getSelectedOrderline();
        if (!selectedLine) {
            return;
        }
        if (selectedLine.is_reward_line && val === "remove") {
            this.currentOrder.uiState.disabledRewards.add(selectedLine.reward_id.id);
            const coupon = selectedLine.coupon_id;
            if (
                coupon &&
                coupon.id > 0 &&
                this.currentOrder._code_activated_coupon_ids.find(
                    (c) => c.code === coupon.code,
                )
            ) {
                coupon.delete();
            }
        }
        if (
            !selectedLine ||
            !selectedLine.is_reward_line ||
            (selectedLine.is_reward_line && ["", "remove"].includes(val))
        ) {
            super._setValue(val);
        }
        if (
            !selectedLine.is_reward_line ||
            (selectedLine.is_reward_line && val === "remove")
        ) {
            this.pos.updateRewards();
        }
    },

    async _showDecreaseQuantityPopup() {
        const result = await super._showDecreaseQuantityPopup();
        if (result) {
            this.pos.updateRewards();
        }
    },

    async _updateGiftCardOrderline(code, points) {
        let selectedLine = this.currentOrder.getSelectedOrderline();
        const product = selectedLine.product_id;

        if (selectedLine.getQuantity() > 1) {
            selectedLine.setQuantity(selectedLine.getQuantity() - 1);
        } else {
            this.currentOrder.removeOrderline(selectedLine);
        }

        const program = this.pos.models["loyalty.program"].find(
            (p) => p.program_type === "gift_card",
        );
        const existingCouponIds = Object.keys(
            this.currentOrder.uiState.couponPointChanges,
        ).filter((key) => {
            const change = this.currentOrder.uiState.couponPointChanges[key];
            return (
                change.points === product.lst_price &&
                change.program_id === program.id &&
                change.product_id === product.id &&
                !change.manual
            );
        });
        if (existingCouponIds.length) {
            const couponId = existingCouponIds.shift();
            delete this.currentOrder.uiState.couponPointChanges[couponId];
        }

        await this.pos.addLineToCurrentOrder(
            { product_id: product, product_tmpl_id: product.product_tmpl_id },
            { price_unit: points },
        );
        selectedLine = this.currentOrder.getSelectedOrderline();
        selectedLine.gift_code = code;
    },

    manageGiftCard(line) {
        this.dialog.add(ManageGiftCardPopup, {
            title: _t("Sell/Manage physical gift card"),
            placeholder: _t("Enter Gift Card Number"),
            line: line,
            getPayload: async (code, points, expirationDate) => {
                points = parseFloat(points);
                if (isNaN(points)) {
                    logPosMessage(
                        "OrderSummary",
                        "updateOnlinePaymentsDataWithServer",
                        `Invalid amount value: ${points}`,
                        false,
                    );
                    return;
                }
                code = code.trim();

                if (this.currentOrder.duplicateCouponChanges(code)) {
                    this.dialog.add(ConfirmationDialog, {
                        title: _t("Validation Error"),
                        body: _t("A coupon/loyalty card must have a unique code."),
                    });
                    return;
                }

                await this._updateGiftCardOrderline(code, points);
                this.currentOrder.processGiftCard(code, points, expirationDate);
            },
        });
    },

    clickLine(ev, orderline) {
        if (
            orderline.isSelected() &&
            orderline.getEWalletGiftCardProgramType() === "gift_card"
        ) {
            return;
        } else {
            super.clickLine(ev, orderline);
        }
    },
});
