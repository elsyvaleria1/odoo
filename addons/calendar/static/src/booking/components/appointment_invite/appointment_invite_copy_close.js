/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets";

export class AppointmentInviteCopyClose extends Component {
    static props = { ...standardWidgetProps };
    static template = "calendar.booking.AppointmentInviteCopyClose";
    props = useProps(this.constructor.props);
    setup() {
        this.dialogContext = useDialogContext();
        this.notification = useService("notification");
        this.action = useService("action");
    }
    /**
     * Save the invitation and copy the url in the clipboard
     * @param ev
     */
    async onSaveAndCopy() {
        if (this.props.readonly) {
            return;
        }

        if (!this.props.record.data.identical_config_id) {
            const recordSaved = await this.props.record.save();
            if (!recordSaved) {
                return;
            }
        }

        const bookUrl = this.props.record.data.book_url;
        setTimeout(async () => {
            await browser.navigator.clipboard.writeText(bookUrl);
            this.notification.add(_t("Link copied to clipboard!"), { type: "success" });
            this.dialogContext.dialogData.close();
            if (
                this.action.currentController?.props?.resModel === "appointment.invite"
            ) {
                this.action.loadState();
            }
        });
    }
}

export const appointmentInviteCopyClose = {
    component: AppointmentInviteCopyClose,
    fieldDependencies: [{ name: "disable_save_button", type: "boolean" }],
};
registry
    .category("view_widgets")
    .add("appointment_invite_copy_close", appointmentInviteCopyClose);
