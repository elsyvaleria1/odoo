/** @odoo-module native */
import { useMrpMpsContext } from "@mrp_mps/mrp_mps_context";
import { useBus } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { SearchBarMenu } from "@web/search/search_bar_menu/search_bar_menu";
import { useSearchModel } from "@web/search/search_model";

import { GroupMenu } from "./group_menu.js";

export class MrpMpsControlPanel extends ControlPanel {
    setup() {
        super.setup();
        this.mpsContext = useMrpMpsContext();
        this.config = useViewConfig();
        this.searchModel = useSearchModel();
        useBus(this.searchModel, "update", () => {
            this.config.offset = 0;
            this.config.limit = this.mpsContext.defaultPageLimit;
            this.mpsContext.model.load(
                this.searchModel.domain,
                this.config.offset,
                this.config.limit,
            );
        });
    }
}

export class MrpMpsSearchBarMenu extends SearchBarMenu {
    static template = "mrp_mps.SearchBarMenu";
    static components = { ...SearchBarMenu.components, GroupMenu };

    setup() {
        super.setup();
        this.mpsContext = useMrpMpsContext();
    }
}

export class MrpMpsSearchBar extends SearchBar {
    static template = "mrp_mps.SearchBar";
    static components = { ...SearchBar.components, MrpMpsSearchBarMenu };
}
