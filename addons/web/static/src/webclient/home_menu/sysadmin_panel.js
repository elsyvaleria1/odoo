// @ts-check
/** @odoo-module native */

import { Component, markup, t, useProps } from "@odoo/owl";
import { user } from "@web/core/user";
import { session } from "@web/session";
import { bannerRegistry } from "@web/webclient/banners/banner_stack";

/** @returns {string | null} */
function sysadminMessage() {
    const { message, warning_type: audience } = session.sysadmin_message ?? {};
    const reaches = audience === "user" || (audience === "admin" && user.isSystem);
    return message && reaches ? message : null;
}

export class SysAdminPanel extends Component {
    static props = {
        dismiss: t.function().optional(),
    };
    static template = "web.SysAdminPanel";
    props = useProps(this.constructor.props);

    get message() {
        return markup(sysadminMessage() ?? "");
    }
}

bannerRegistry.add(
    "web.sysadmin_message",
    {
        scope: "home",
        Component: SysAdminPanel,
        when: () => Boolean(sysadminMessage()),
    },
    { sequence: 20 },
);
