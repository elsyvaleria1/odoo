// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { UserMenu } from "@web/webclient/user_menu/user_menu";

export class BurgerUserMenu extends UserMenu {
    static template = "web.BurgerUserMenu";
    static props = { ...UserMenu.props, onMenuClicked: t.function().optional() };
    /**
     * @param {Function} callback
     * @returns {(ev: Event) => void}
     */
    _onItemClicked(callback) {
        return (ev) => {
            callback(ev);
            this.props.onMenuClicked?.(ev);
        };
    }
}
