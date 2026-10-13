/** @odoo-module native */
import { patch } from "@web/core/utils/patch";
import { Popover } from "@web/ui/popover";
import { useBackButton } from "@web_mobile/js/core/hooks";

patch(Popover.prototype, {
    setup() {
        super.setup(...arguments);
        useBackButton(
            this.onBackButton.bind(this),
            () => this.props.target.isConnected,
        );
    },

    /** @private */
    onBackButton() {
        this.props.close();
    },
});
