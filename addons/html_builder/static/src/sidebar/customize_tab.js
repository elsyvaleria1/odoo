/** @odoo-module native */
import { useBuilderContext } from "@html_builder/core/builder_context";
import { CustomizeComponent } from "@html_builder/sidebar/customize_component";
import { Component, onPatched, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";

import { useVisibilityObserver } from "../core/utils.js";
import { OptionsContainer } from "./option_container.js";

function containerIds(optionsContainers) {
    return optionsContainers.map((optionsContainer) => optionsContainer.id).join();
}

export class CustomizeTab extends Component {
    static template = "html_builder.CustomizeTab";
    static components = { CustomizeComponent, OptionsContainer };
    static props = {
        currentOptionsContainers: t.array().optional([]),
        snippetModel: t.object(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.builderContext = useBuilderContext();
        this.state = proxy({
            hasContent: true,
        });
        this.customizeComponent = proxy(
            this.builderContext.editor.shared.customizeTab.getCustomizeComponent(),
        );
        this.rootRef = elementRef();
        this.contentRef = elementRef();
        useVisibilityObserver(this.contentRef, (hasContent) => {
            this.state.hasContent = hasContent;
        });
        onWillUpdateProps((nextProps) => {
            if (
                containerIds(nextProps.currentOptionsContainers) !==
                containerIds(this.props.currentOptionsContainers)
            ) {
                // The options of the previous selection stay on screen until
                // every option of the next one has loaded: acting on them
                // would change the element the user just left.
                this.setBlocked(true);
            }
            if (
                !this.state.hasContent &&
                nextProps.currentOptionsContainers.length > 0 &&
                nextProps.currentOptionsContainers !==
                    this.props.currentOptionsContainers
            ) {
                // Force a reconsideration of `content`
                this.state.hasContent = true;
            }
        });
        onPatched(() => this.setBlocked(false));
    }

    setBlocked(isBlocked) {
        this.rootRef.el?.toggleAttribute("inert", isBlocked);
        this.rootRef.el?.classList.toggle("o_is_blocked", isBlocked);
    }

    getCurrentOptionsContainers() {
        const currentOptionsContainers = this.props.currentOptionsContainers;
        if (!currentOptionsContainers.length) {
            return this.builderContext.editor.shared.builderOptions.getPageContainers();
        }
        return currentOptionsContainers;
    }
}
