/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class CopyButtonReferral extends Component {
    static template = "hr_referral.CopyButtonReferral";
    static props = { ...standardFieldProps };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    async onClick() {
        const referral_link = await this.orm.call("hr.job", "create_referral_url", [
            this.props.record.data.id,
            "direct",
        ]);
        try {
            await browser.navigator.clipboard.writeText(referral_link);
            this.notification.add(
                _t("Referral link: %s has been copied to clipboard", referral_link),
                { type: "success" },
            );
        } catch (error) {
            this.notification.add(
                _t(
                    "Error while copying the Referral link: %s to clipboard",
                    referral_link,
                ),
                { type: "danger", sticky: true },
            );
            browser.console.warn(error);
        }
    }
}

export const copyClipboardReferralButton = {
    component: CopyButtonReferral,
};

registry
    .category("fields")
    .add("CopyClipboardReferralButton", copyClipboardReferralButton);
