/** @odoo-module native */
import { WebChatter } from "@mail/chatter/web/web_chatter";
import { Component, t, useProps } from "@odoo/owl";
import { useViewConfig } from "@web/core/view_config_hooks";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

export class ChatterContainer extends WebChatter {
    static template = "web_studio.ChatterContainer";
    static props = { ...WebChatter.props, studioXpath: t.any().optional() };

    setup() {
        super.setup();
        this.config = useViewConfig();
    }

    onClick(ev) {
        this.config.onNodeClicked(this.props.studioXpath);
    }
}

export class ChatterContainerHook extends Component {
    static template = "web_studio.ChatterContainerHook";
    static components = { Chatter: WebChatter };
    static props = { chatterData: t.object(), threadModel: t.string() };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.viewEditorModel = useCurrentViewEditorModel();
    }

    onClick() {
        this.viewEditorModel.doOperation({
            type: "chatter",
            model: this.viewEditorModel.resModel,
            ...this.props.chatterData,
        });
    }
}
