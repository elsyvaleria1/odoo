/** @odoo-module native */
import { elementRef } from "@web/core/utils/element_ref";
import { useViewConfig } from "@web/core/view_config_hooks";
import { Widget } from "@web/views/widgets";
import {
    studioIsVisible,
    useStudioRef,
} from "@web_studio/client_action/view_editor/editors/utils";

export class WidgetStudio extends Widget {
    static template = "web_studio.Widget";
    setup() {
        super.setup();
        this.config = useViewConfig();
        this.rootRefRef = elementRef();
        useStudioRef(this.rootRefRef, this.onClick.bind(this));
    }
    get classNames() {
        const classNames = super.classNames;
        classNames["o_web_studio_show_invisible"] = !studioIsVisible(this.props);
        classNames["o-web-studio-editor--element-clickable"] = !!this.props.studioXpath;
        return classNames;
    }
    get widgetProps() {
        const widgetProps = super.widgetProps;
        delete widgetProps.studioXpath;
        delete widgetProps.hasEmptyPlaceholder;
        delete widgetProps.hasLabel;
        delete widgetProps.studioIsVisible;
        return widgetProps;
    }
    onClick(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        this.config.onNodeClicked(this.props.studioXpath);
    }
}
