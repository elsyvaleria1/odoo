/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";
import { SearchPanel } from "@web/search/search_panel/search_panel";
import { SIZES } from "@web/ui/viewport";

export class LunchSearchPanel extends SearchPanel {
    setup() {
        super.setup();
        this.ui = useService("ui");
        this.state.sidebarExpanded = this.ui.size <= SIZES.LG ? false : true;
    }
}
