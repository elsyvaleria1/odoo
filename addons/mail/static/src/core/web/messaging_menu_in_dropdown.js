// @ts-check
/** @odoo-module native */
import { MessagingMenu } from "@mail/core/public_web/messaging_menu/messaging_menu";
import { useDiscussSystray } from "@mail/utils/common/hooks";
import { Component, onWillDestroy, useProps } from "@odoo/owl";
import { Dropdown, useDropdownState } from "@web/components/dropdown";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const log = makeLogger("mail.messaging_menu");

export class MessagingMenuInDropdown extends Component {
    static components = { Dropdown, MessagingMenu };
    static props = {};
    static template = "mail.MessagingMenuInDropdown";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.ui = useService("ui");
        this.pwa = useService("pwa");
        this.notification = useService("mail.notification.permission");
        this.dropdown = useDropdownState();
        this.store.messagingMenuDropdown = this.dropdown;
        onWillDestroy(() => (this.store.messagingMenuDropdown = undefined));
        this.discussSystray = useDiscussSystray(this.dropdown);
        this.closeDropdown = () => this.dropdown.close();
    }

    beforeOpen() {
        const state = this.store.messagingMenuSystrayState;
        log.logic("beforeOpen", () => ({ tab: state.activeTab?.id }));
        state.searchTerm = "";
    }

    get counter() {
        let value =
            this.store.globalCounter +
            this.store.failures.reduce((acc, f) => acc + f.notifications.length, 0);
        if (this.pwa.canPromptToInstall) {
            value++;
        }
        if (
            this.notification.permission === "prompt" &&
            !this.store.isNotificationPermissionDismissed
        ) {
            value++;
        }
        return value;
    }
}

registry
    .category("systray")
    .add(
        "mail.messaging_menu",
        { Component: MessagingMenuInDropdown },
        { sequence: 25 },
    );
