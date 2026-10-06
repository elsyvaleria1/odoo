// @ts-check
/** @odoo-module native */
import { Dropdown } from "@web/components/dropdown";

/** A dropdown inside the messaging menu: closing it must not close the menu around it. */
export class IsolatedDropdown extends Dropdown {
    get hasParent() {
        return false;
    }
}
