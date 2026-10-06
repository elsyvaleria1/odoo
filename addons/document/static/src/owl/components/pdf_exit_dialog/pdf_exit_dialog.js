/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";

export class ExitSplitToolsDialog extends Component {
    static components = { Dialog };
    static props = {
        close: t.function(),
        hasSplitPages: t.boolean(),
        onDeleteRemainingPages: t.function(),
        onGatherRemainingPages: t.function(),
    };
    static template = "document.ExitToolsDialog";
    props = useProps(this.constructor.props);

    /**
     * @public
     */
    deleteRemainingPages() {
        this.props.onDeleteRemainingPages();
        this.props.close();
    }
    /**
     * @public
     */
    gatherRemainingPages() {
        this.props.onGatherRemainingPages();
        this.props.close();
    }
}
