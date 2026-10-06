// @ts-check
/** @odoo-module native */
import { useDiscussSystray } from "@mail/utils/common/hooks";
import { Component, useProps } from "@odoo/owl";
import { Dropdown, useDropdownState } from "@web/components/dropdown";
import { useAppContext } from "@web/core/app_context";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useCommand } from "@web/ui/commands";

import { activityGroupOpener } from "./activity_group_opener.js";

const log = makeLogger("mail.activity");
export class ActivityMenu extends Component {
    static components = { Dropdown };
    static props = {};
    static template = "mail.ActivityMenu";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.action = useService("action");
        this.appContext = useAppContext();
        this.userId = user.userId;
        this.ui = useService("ui");
        this.dropdown = useDropdownState();
        this.discussSystray = useDiscussSystray(this.dropdown);
        useCommand(_t("Activity"), () => this.store.scheduleActivity(false, false), {
            category: "activity",
            hotkey: "alt+shift+a",
            global: true,
            hotkeyOptions: { bypassEditableProtection: true },
            isAvailable: () =>
                !(
                    /** @type {ParentNode} */ (this.ui.activeElement).querySelector(
                        "[data-hotkey='shift+a'], .o_mail_activity_schedule_wizard",
                    )
                ),
        });
    }

    onBeforeOpen() {
        log.pipeline("onBeforeOpen fetches systray activities");
        this.store.fetchStoreData("systray_get_activities");
    }

    /**
     * @param {import("./activity_group_opener.js").ActivityGroup} group
     * @param {import("./activity_group_opener.js").ActivityFilter} [filter]
     * @param {boolean} [newWindow]
     */
    openActivityGroup(group, filter = "all", newWindow = false) {
        this.dropdown.close();
        return activityGroupOpener.open(this.appContext, group, filter, newWindow);
    }

    /** @param {boolean} [newWindow] */
    openMyActivities(newWindow) {
        log.logic("openMyActivities", () => ({ newWindow }));
        this.dropdown.close();
        this.action.doAction("mail.mail_activity_action_my", {
            newWindow,
            clearBreadcrumbs: true,
        });
    }
}

registry
    .category("systray")
    .add("mail.activity_menu", { Component: ActivityMenu }, { sequence: 20 });
