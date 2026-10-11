// @ts-check
/** @odoo-module native */
import { Dropdown } from "@web/components/dropdown";

export class IsolatedDropdown extends Dropdown {
    get hasParent() {
        return false;
    }
}
