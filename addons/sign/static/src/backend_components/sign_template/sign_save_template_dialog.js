/** @odoo-module native */
import { Component, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";

export class SignSaveTemplateDialog extends Component {
    static template = "sign.SignSaveTemplateDialog";
    static components = {};
    static props = {
        isShown: t.boolean(),
        documentUsedTimesCounter: t.number(),
        onTemplateSaveClick: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({
            isShown: this.props.isShown,
        });

        onWillUpdateProps((nextProps) => {
            this.props = nextProps;
            this.state.isShown = this.props.documentUsedTimesCounter > 2;
        });
    }
}
