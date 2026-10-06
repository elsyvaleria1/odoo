/** @odoo-module native */
import { MessagingMenuInDropdown } from "@mail/core/web/messaging_menu_in_dropdown";
import { patch } from "@web/core/utils/patch";
import { useBackButton } from "@web_mobile/js/core/hooks";

patch(MessagingMenuInDropdown.prototype, {
    setup() {
        super.setup();
        useBackButton(
            () => this.dropdown.close(),
            () => this.dropdown.isOpen,
        );
    },
});
