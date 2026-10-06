import { fields, models } from "@web/../tests/web_test_helpers";

export class CRMLead extends models.ServerModel {
    _name = "crm.lead";

    phone = fields.Char({ string: "Phone" });

    /** @override */
    get_formview_id() {
        return false;
    }
}
