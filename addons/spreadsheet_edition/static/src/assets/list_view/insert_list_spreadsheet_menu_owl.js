/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { useEventBus } from "@web/core/utils/hooks";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";

export class InsertListSpreadsheetMenu extends Component {
    static props = {};
    static template = "spreadsheet_edition.InsertListSpreadsheetMenu";
    static components = { CogMenuItem };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.bus = useEventBus();
    }

    /**
     * @private
     */
    _onClick() {
        this.bus.trigger("insert-in-spreadsheet");
    }
}
