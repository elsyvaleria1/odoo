/** @odoo-module native */
import { provideChildBuilderContext } from "@html_builder/core/builder_context";
import { DependencyManager } from "@html_builder/core/dependency_manager";
import { BaseOptionComponent } from "@html_builder/core/utils";
import { toolbarButtonProps } from "@html_editor/main/toolbar/toolbar";
import { Component, onMounted, onWillDestroy, proxy, t, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { usePositionBus } from "@web/core/position/position_hook";
import { elementRef } from "@web/core/utils/element_ref";
import { provideServices } from "@web/core/utils/hooks";
import { usePopover } from "@web/ui/popover";

import { AnimateOption } from "./animate_option.js";

const log = makeLogger("website.builder.option.animate_text");

class AnimateTextPopover extends BaseOptionComponent {
    static template = "website_builder.AnimateTextPopover";
    static props = {
        animateOptionProps: t.object(AnimateOption.props),
        onReset: t.function(),
        close: t.function().optional(),
    };
    static components = { AnimateOption };

    setup() {
        super.setup();
        this.positionBus = usePositionBus();
        useLifecycleLog(log);
        this.contentRef = elementRef();
        this.resizeObserver = new ResizeObserver(() => {
            this.positionBus?.trigger("update");
        });
        onMounted(() => {
            log.lifecycle("AnimateTextPopover resize observer attached");
            this.resizeObserver.observe(this.contentRef.el);
        });
        onWillDestroy(() => {
            log.lifecycle("AnimateTextPopover resize observer disconnected");
            this.resizeObserver.disconnect();
        });
    }
}

export class AnimateText extends Component {
    static template = "website_builder.AnimateText";
    static props = {
        ...toolbarButtonProps,
        config: t.object({ editor: t.object(), editorBus: t.object() }),
        animateOptionProps: t.object(AnimateOption.props),
        getAnimatedTextOrCreateDefault: t.function(),
        isActive: t.function(),
        isDisabled: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        useLifecycleLog(log);
        this.state = proxy({});
        this.updateState();

        this.root = elementRef();
        provideChildBuilderContext({
            dependencyManager: new DependencyManager(),
            getEditingElement: () => this.activeElement,
            getEditingElements: () => (this.activeElement ? [this.activeElement] : []),
            weContext: {},
            editor: this.props.config.editor,
            editorBus: this.props.config.editorBus,
        });
        provideServices(this.props.config.editor.services);
        this.popover = usePopover(AnimateTextPopover, {
            pluginManager: this.__owl__.pluginManager,
            onClose: () => {
                log.lifecycle("AnimateText popover closed", () => ({
                    editorDestroyed: this.props.config.editor.isDestroyed,
                }));
                if (!this.props.config.editor.isDestroyed) {
                    this.updateState();
                }
            },
        });
    }

    onClick() {
        if (this.popover.isOpen) {
            log.logic("AnimateText click ignored: popover already open");
            return;
        }
        const { element, onReset } = this.props.getAnimatedTextOrCreateDefault();
        if (!element) {
            log.logic("AnimateText click ignored: no animated text element");
            return;
        }
        this.activeElement = element;

        this.updateState();
        log.lifecycle("AnimateText open popover", () => ({
            tag: element.tagName,
            className: element.className,
        }));
        this.popover.open(this.root.el, {
            animateOptionProps: this.props.animateOptionProps,
            onReset: () => {
                onReset(this.activeElement);
                this.popover.close();
            },
        });
    }

    updateState() {
        this.state.isActive = this.props.isActive();
        this.state.isDisabled = this.props.isDisabled();
    }
}
