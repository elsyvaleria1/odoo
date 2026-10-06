// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { ConfirmationDialog } from "@web/ui/dialog/confirmation_dialog";

export class SettingsConfirmationDialog
    extends /** @type {any} */ (ConfirmationDialog)
{
    static template = "web.SettingsConfirmationDialog";
    static props = {
        .../** @type {any} */ (ConfirmationDialog).props,
        stayHere: t.function().optional(),
        title: ConfirmationDialog.props.title.optional(_t("Unsaved changes")),
    };

    _stayHere() {
        if (this.props.stayHere) {
            this.props.stayHere();
        }
        this.props.close();
    }
}
