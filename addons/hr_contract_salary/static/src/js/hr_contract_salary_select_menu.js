/** @odoo-module native */
import { SelectMenu } from "@web/components/select_menu";

export class HrContractSalarySelectMenu extends SelectMenu {
    static template = "hrContractSalary.SelectMenu";

    onStateChanged(open) {
        super.onStateChanged(open);
        if (open && this.inputRef.el) {
            this.inputRef.el.focus();
        }
    }

    getItemClass(choice) {
        if (this.isOptionSelected(choice)) {
            return "o_select_menu_item fw-bolder bg-primary text-white";
        } else {
            return "o_select_menu_item";
        }
    }
}
