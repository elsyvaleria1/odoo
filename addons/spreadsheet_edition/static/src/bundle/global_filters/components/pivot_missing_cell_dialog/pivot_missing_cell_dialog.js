/** @odoo-module native */
import { components } from "@odoo/o-spreadsheet";
import { Component, t, useProps } from "@odoo/owl";
import { provideSpreadsheetEnv } from "@spreadsheet/hooks";
import { Dialog } from "@web/ui/dialog";

const { PivotHTMLRenderer } = components;

export class PivotMissingCellDialog extends Component {
    static template = "spreadsheet_edition.PivotMissingCellDialog";
    static components = { Dialog, PivotHTMLRenderer };
    static props = {
        close: t.function(),
        pivotId: t.string(),
        model: t.object(),
        onCellClicked: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        provideSpreadsheetEnv({
            model: this.props.model,
        });
    }
}
