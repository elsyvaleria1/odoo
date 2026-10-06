/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { useViewConfig } from "@web/core/view_config_hooks";
import { useStudioEditorContext } from "@web_studio/client_action/editor/studio_editor_context";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

export class AddButtonAction extends Component {
    static props = {};
    static template = `web_studio.AddButtonAction`;
    props = useProps(this.constructor.props);
    setup() {
        super.setup();
        this.studioContext = useStudioEditorContext();
        this.viewEditorModel = useCurrentViewEditorModel();
    }

    onClick(ev) {
        let nextButtonCount = 1;
        const findHeader =
            this.viewEditorModel.xmlDoc.firstChild.querySelector(":scope > header");
        if (!findHeader) {
            this.viewEditorModel.pushOperation({
                type: "statusbar",
                view_id: this.viewEditorModel.view.id,
            });
        } else {
            nextButtonCount = findHeader.querySelectorAll(":scope > button").length + 1;
        }
        this.viewEditorModel.doOperation({
            type: "add_header_button",
        });
        this.studioContext.setAutoClick(
            {
                xpath: `/${this.viewEditorModel.viewType}[1]/header[1]/button[${nextButtonCount}]`,
            },
            {},
        );
    }
}

export class SelectionHeaderButtons extends Component {
    static props = { headerButtons: t.array() };
    static template = `web_studio.SelectionHeaderButtons`;
    static components = {
        AddButtonAction,
    };
    props = useProps(this.constructor.props);
    setup() {
        this.debug = useDebugMode();
        this.config = useViewConfig();
        this.viewEditorModel = proxy(useCurrentViewEditorModel());
        this.buttons = this.getButtons();
    }
    makeTooltipButton(button) {
        return JSON.stringify({
            button: {
                string: button.string,
                type: button.clickParams?.type,
                name: button.clickParams?.name,
            },
            debug: true,
        });
    }
    getButtons() {
        if (this.viewEditorModel.showInvisible) {
            return this.props.headerButtons.map((btn) => {
                if (btn.invisible === "True" || btn.invisible === "1") {
                    btn.className += " o_web_studio_show_invisible";
                }
                return btn;
            });
        }
        return this.props.headerButtons.filter(
            (btn) => btn.invisible !== "True" && btn.invisible !== "1",
        );
    }
    getClassName(button) {
        return button.className.includes("btn-primary")
            ? button.className
            : `btn-secondary ${button.className}`;
    }
}
