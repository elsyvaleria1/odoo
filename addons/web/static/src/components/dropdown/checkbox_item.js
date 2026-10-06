// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { DropdownItem } from "@web/components/dropdown/dropdown_item";

export class CheckboxItem extends DropdownItem {
    static template = "web.CheckboxItem";
    static props = {
        ...DropdownItem.props,
        checked: t.boolean(),
        role: DropdownItem.props.role.optional("menuitemcheckbox"),
    };
}
