/** @odoo-module native */
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { MenuDialog } from "@website/components/dialog/edit_menu";

patch(MenuDialog.prototype, {
    /**
     * @override
     */
    setup() {
        super.setup();
        this.notification = useService("notification");
        this.originalUrl = this.props.url;
    },
    /**
     * @override
     */
    onClickOk() {
        const hasUrlChanged = this.state.url !== this.originalUrl;
        if (hasUrlChanged && this.state.url) {
            const isHelpdeskUrl = this.state.url === "/helpdesk";
            const isHelpdeskTeamPattern =
                isHelpdeskUrl || /^\/helpdesk\/([a-zA-Z]+-)+\d+$/.test(this.state.url);
            if (isHelpdeskUrl || isHelpdeskTeamPattern) {
                this.state.invalidUrl = true;
                this.notification.add(
                    isHelpdeskUrl
                        ? _t(
                              "This URL is reserved for the helpdesk teams with 'website form' feature enabled.",
                          )
                        : _t(
                              "The %s URL is reserved for the helpdesk team with the same name. \
                        To use it, please enable the 'website form' feature on that team instead.",
                              this.state.url,
                          ),
                    { type: "danger" },
                );
                return;
            }
        }
        super.onClickOk();
    },
});
