/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { SpreadsheetShareButton } from "@spreadsheet/components/share_button/share_button";
import { useSpreadsheetEnv } from "@spreadsheet/hooks";
import { registries } from "@spreadsheet/o_spreadsheet/o_spreadsheet";

const { topbarComponentRegistry } = registries;

export class TopbarShareButton extends Component {
    static template = "spreadsheet_edition.TopbarShareButton";
    static components = {
        SpreadsheetShareButton,
    };
    static props = {};
    props = useProps(this.constructor.props);
    env = useSpreadsheetEnv();

    get buttonProps() {
        return {
            onSpreadsheetShared: this.env.onSpreadsheetShared.bind(this),
            model: this.env.model,
        };
    }
}

topbarComponentRegistry.add("share_button", {
    component: TopbarShareButton,
    isVisible: (env) => env.onSpreadsheetShared,
    sequence: 20,
});
