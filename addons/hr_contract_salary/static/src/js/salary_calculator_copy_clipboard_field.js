/** @odoo-module native */
import { t } from "@odoo/owl";
import { CopyButton } from "@web/components/copy_button";
import { registry } from "@web/core/registry";
import {
    CopyClipboardButtonField,
    copyClipboardButtonField,
} from "@web/fields/basic/copy_clipboard/copy_clipboard_field";

export class SaveAndCopyButton extends CopyButton {
    static props = { ...CopyButton.props, record: t.object() };
    async onClick() {
        await this.props.record.model.root.save();
        return super.onClick();
    }
}

export class SaveAndCopyToClipboardButtonField extends CopyClipboardButtonField {
    static template = "web.SaveAndCopyToClipboardButtonField";
    static components = { SaveAndCopyButton };
}

const saveAndCopyToClipboardButtonField = {
    ...copyClipboardButtonField,
    component: SaveAndCopyToClipboardButtonField,
};

registry
    .category("fields")
    .add("SaveAndCopyToClipboardButton", saveAndCopyToClipboardButtonField);
