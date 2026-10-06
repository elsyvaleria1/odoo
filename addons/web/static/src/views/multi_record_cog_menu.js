// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { CogMenu } from "@web/search/cog_menu/cog_menu";

export class MultiRecordCogMenu extends CogMenu {
    static props = {
        ...CogMenu.props,
        hasSelectedRecords: t.or([t.boolean(), t.number()]).optional(),
    };

    /**
     * @override
     * @returns {any}
     */
    _registryItems() {
        return this.props.hasSelectedRecords ? [] : super._registryItems();
    }
}
