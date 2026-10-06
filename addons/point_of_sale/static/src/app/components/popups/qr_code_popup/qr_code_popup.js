/** @odoo-module native */
import { t } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";
export class QRPopup extends ConfirmationDialog {
    static template = "point_of_sale.QRConfirmationDialog";
    static props = {
        ...ConfirmationDialog.props,
        line: t.object(),
        order: t.object(),
        qrCode: t.string(),
        confirmLabel: ConfirmationDialog.props.confirmLabel.optional(
            _t("Confirm Payment"),
        ),
        cancelLabel: ConfirmationDialog.props.cancelLabel.optional(
            _t("Cancel Payment"),
        ),
        title: ConfirmationDialog.props.title.optional(_t("QR Code Payment")),
    };

    setup() {
        super.setup();
        this.utils = useService("contextual_utils_service");
        this.body = _t("Please scan the QR code with %s", this.props.title);
        this.amount = this.utils.formatCurrency(this.props.line.amount);
    }
}
