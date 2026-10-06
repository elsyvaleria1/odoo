// @ts-check
/** @odoo-module native */

import { Component, onPatched, proxy, t, useProps } from "@odoo/owl";
import { defineScope } from "@web/core/scope";

const envScope = defineScope("web/components/dropdown/accordion_item");

/**
 * @typedef AccordionParent
 * @property {(isOpen: boolean) => any} [accordionStateChanged]
 */

const ACCORDION = Symbol("Accordion");

/** @param {AccordionParent} parent */
export function provideChildAccordion(parent) {
    envScope.provide({ [ACCORDION]: parent });
}

/** @returns {any} */
function useParentAccordion() {
    return /** @type {any} */ (envScope.use())[ACCORDION];
}
export class AccordionItem extends Component {
    static template = "web.AccordionItem";
    static props = {
        slots: t.object({ default: t.any() }),
        description: t.string(),
        selected: t.boolean().optional(false),
        class: t.string().optional(""),
    };
    props = useProps(this.constructor.props);

    /** @type {{ open: boolean }} */
    state;
    /** @type {AccordionParent | undefined} */
    parentComponent;
    /** @type {boolean} */
    _reportedOpen;

    setup() {
        this.state = proxy({
            open: false,
        });
        this.parentComponent = useParentAccordion();
        this._reportedOpen = this.state.open;
        onPatched(() => this.reportStateChange());
    }

    reportStateChange() {
        if (this.state.open === this._reportedOpen) {
            return;
        }
        this._reportedOpen = this.state.open;
        this.parentComponent?.accordionStateChanged?.(this.state.open);
    }
}
