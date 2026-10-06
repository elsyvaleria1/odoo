/** @odoo-module native */
import { t } from "@odoo/owl";
import { AlertDialog } from "@web/ui/dialog";

export class TemplateAlertDialog extends AlertDialog {
    static props = { ...AlertDialog.props, body: t.string().optional() };
    static template = "sign.TemplateAlertDialog";
}
