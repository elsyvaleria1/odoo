/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { CopyButton } from "@web/components/copy_button";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class CopyButtonJob extends CopyButton {
    static template = "website_hr_recruitment.CopyButtonJob";

    setup() {
        super.setup();
        this.notification = useService("notification");
    }

    showTooltip() {
        this.notification.add(_t("The job link has been copied to the clipboard."), {
            type: "success",
        });
    }
}
export class CopyClipboardCharField extends Component {
    static components = { CopyButtonJob };
    static template = "website_hr_recruitment.CopyJobLinkButton";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    setup() {
        this.copyText = _t("Share Job");
        this.successText = _t("Copied");
    }
}

export const copyClipboardJobLinkButton = {
    component: CopyClipboardCharField,
};

registry
    .category("fields")
    .add("CopyClipboardJobLinkButton", copyClipboardJobLinkButton);
