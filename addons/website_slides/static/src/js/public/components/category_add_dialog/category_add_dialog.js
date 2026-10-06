/** @odoo-module native */
import { t } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";

export class CategoryAddDialog extends ConfirmationDialog {
    static template = "website_slides.CategoryAddDialog";
    static props = { ...ConfirmationDialog.props, channelId: t.string() };

    setup() {
        super.setup();
        this.autofocusRef = elementRef();
        this.inputRef = useAutofocus({ ref: this.autofocusRef });
        this.csrf_token = odoo.csrf_token;
        this.lastInputValue;
    }

    confirm() {
        this.execButton(() => {
            if (this.inputRef.el.value === this.lastInputValue) {
                return;
            }
            this.lastInputValue = this.inputRef.el.value;
            return this.props.confirm({
                formEl: this.modalRef.el.querySelector("form"),
            });
        });
    }
}
