/** @odoo-module native */
import { Component, t } from "@odoo/owl";
import { registry, useRegistry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { useForwardRefToParent } from "@web/core/utils/hooks";
import { MainComponentsContainer } from "@web/ui/main_components_container";

export class LocalOverlayContainer extends MainComponentsContainer {
    static template = "html_editor.LocalOverlayContainer";
    static props = {
        localOverlay: t.function().optional(),
        identifier: t.string().optional("overlay_components"),
    };

    setup() {
        const overlayComponents = registry.category(this.props.identifier);
        if (!overlayComponents.validationSchema) {
            overlayComponents.addValidation(
                t.strictObject({
                    Component: t.customValidator(
                        t.any(),
                        (c) => c.prototype instanceof Component,
                    ),
                    props: t.object().optional(),
                }),
            );
        }
        this.Components = useRegistry(overlayComponents);
        this.localOverlayRef = elementRef();
        useForwardRefToParent("localOverlay", this.localOverlayRef);
    }
}
