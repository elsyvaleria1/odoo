/** @odoo-module native */
import { proxy, t } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { useBus, useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";

export class MrpEmployeeDialog extends ConfirmationDialog {
    static template = "mrp_workorder.MrpEmployeeDialog";
    static props = {
        ...ConfirmationDialog.props,
        employees: t.object(),
        setConnectedEmployees: t.function(),
    };

    setup() {
        super.setup();
        this.imageBaseURL = `${browser.location.origin}/web/image?model=hr.employee&field=avatar_128&id=`;
        this.selected = proxy({
            ids: this.props.employees.connected.map((item) => item.id),
        });
        this.orm = useService("orm");
        this.barcode = useService("barcode");
        useBus(this.barcode.bus, "barcode_scanned", (event) =>
            this._onBarcodeScanned(event.detail.barcode),
        );
    }

    toggleEmployee(id) {
        if (this.selected.ids.includes(id)) {
            this.selected.ids.splice(this.selected.ids.indexOf(id), 1);
        } else {
            this.selected.ids.push(id);
        }
    }

    async confirm() {
        await this.props.setConnectedEmployees(this.selected.ids);
        return this.props.close();
    }

    async _onBarcodeScanned(barcode) {
        const employee = await this.orm.call("mrp.workcenter", "get_employee_barcode", [
            barcode,
        ]);
        if (employee) {
            this.toggleEmployee(employee);
        }
    }
}
