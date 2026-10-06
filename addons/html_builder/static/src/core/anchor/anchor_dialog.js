/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { Dialog } from "@web/ui/dialog";

export class AnchorDialog extends Component {
    static template = "html_builder.AnchorDialog";
    static components = { Dialog };
    static props = {
        currentAnchorName: t.string(),
        renameAnchor: t.function(),
        deleteAnchor: t.function(),
        formatAnchor: t.function(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.title = _t("Link Anchor");
        this.inputRef = elementRef();
        this.state = proxy({ isValid: true });
    }

    async onConfirmClick() {
        const newAnchorName = this.props.formatAnchor(this.inputRef.el.value);
        if (newAnchorName === this.props.currentAnchorName) {
            this.props.close();
        }

        this.state.isValid = await this.props.renameAnchor(newAnchorName);
        if (this.state.isValid) {
            this.props.close();
        }
    }

    onRemoveClick() {
        this.props.deleteAnchor();
        this.props.close();
    }
}
