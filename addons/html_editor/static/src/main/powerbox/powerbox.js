/** @odoo-module native */
import { Component, onPatched, t, useListener, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export class Powerbox extends Component {
    static template = "html_editor.Powerbox";
    static props = {
        document: t.customValidator(
            t.any(),
            (doc) => doc.constructor.name === "HTMLDocument",
        ),
        close: t.function(),
        state: t.object(),
        activateCommand: t.function(),
        applyCommand: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        const ref = (this.ref = elementRef());

        onPatched(() => {
            const activeCommand = ref.el.querySelector(".o-we-command.active");
            if (activeCommand) {
                activeCommand.scrollIntoView({ block: "nearest", inline: "nearest" });
            }
        });

        this.mouseSelectionActive = false;
        const onMouseMove = () => (this.mouseSelectionActive = true);
        useListener(this.props.document, "mousemove", onMouseMove);

        useLayoutEffect(
            (ownDoc, propsDoc) => {
                if (ownDoc && propsDoc && ownDoc !== propsDoc) {
                    ownDoc.addEventListener("mousemove", onMouseMove);
                    return () => ownDoc.removeEventListener("mousemove", onMouseMove);
                }
            },
            () => [ref.el?.ownerDocument, this.props.document],
        );
    }

    get commands() {
        return this.props.state.commands;
    }

    get currentIndex() {
        return this.props.state.currentIndex;
    }

    get showCategories() {
        return this.props.state.showCategories;
    }

    onScroll() {
        this.mouseSelectionActive = false;
    }

    onMouseEnter(index) {
        if (this.mouseSelectionActive) {
            this.props.activateCommand(index);
        }
    }
}
