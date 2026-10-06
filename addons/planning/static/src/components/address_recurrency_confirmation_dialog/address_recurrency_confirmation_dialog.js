/** @odoo-module native */
import { t } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { ConfirmationDialog } from "@web/ui/dialog";

export class AddressRecurrencyConfirmationDialog extends ConfirmationDialog {
    static template = "planning.AddressRecurrencyConfirmationDialog";
    static props = {
        ...ConfirmationDialog.props,
        body: t.string().optional(""),
        onChangeRecurrenceUpdate: t.function(),
        selected: t.string(),
        cancel: ConfirmationDialog.props.cancel.optional(() => () => {}),
        title: ConfirmationDialog.props.title.optional(_t("Delete Recurring Shift")),
    };
}
