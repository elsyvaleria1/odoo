/** @odoo-module native */
import { t } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useBus } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { ViewButton } from "@web/views/view_button";
import {
    studioIsVisible,
    useStudioRef,
} from "@web_studio/client_action/view_editor/editors/utils";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

/*
 * ViewButton:
 * - Deals with invisible
 * - Click is overriden not to trigger the bound action
 */
export class ViewButtonStudio extends ViewButton {
    static template = "web_studio.ViewButton";
    static props = {
        ...ViewButton.props,
        studioIsVisible: t.boolean().optional(),
        studioXpath: t.string().optional(),
    };

    setup() {
        super.setup();
        this.viewEditorModel = useCurrentViewEditorModel();
        this.config = useViewConfig();
        this.rootRefRef = elementRef();
        useStudioRef(this.rootRefRef);

        useBus(this.viewEditorModel.bus, "approval-update", () => {
            this.approvalGate?.load();
        });
    }
    getClassName() {
        let className = super.getClassName();
        if (!studioIsVisible(this.props)) {
            className += " o_web_studio_show_invisible";
        }
        if (this.props.studioXpath) {
            className += " o-web-studio-editor--element-clickable";
        }
        return className;
    }

    onClick(ev) {
        if (this.props.tag === "a") {
            ev.preventDefault();
        }
        const target = ev.target.classList.contains(
            "o-web-studio-editor--element-clickable",
        )
            ? ev.target
            : ev.target.closest("o-web-studio-editor--element-clickable");
        this.config.onNodeClicked(
            target?.getAttribute("studioxpath") || this.props.studioXpath,
        );
    }

    _isApprovalGated() {
        return true;
    }
}
