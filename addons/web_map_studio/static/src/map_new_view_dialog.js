/** @odoo-module native */
import { useDebugMode } from "@web/core/debug/debug_context";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { AlertDialog } from "@web/ui/dialog";
import { NewViewDialog } from "@web_studio/editor";

export class MapNewViewDialog extends NewViewDialog {
    static template = "web_map_studio.MapNewViewDialog";
    static props = { ...NewViewDialog.props };

    setup() {
        super.setup();
        this.debug = useDebugMode();
        this.dialog = useService("dialog");
        this.fieldsChoice = {
            res_partner: null,
        };
    }

    get viewType() {
        return "map";
    }

    computeSpecificFields(fields) {
        this.partnerFields = fields.filter(
            (field) => field.type === "many2one" && field.relation === "res.partner",
        );
        if (!this.partnerFields.length) {
            this.dialog.add(AlertDialog, {
                title: _t("Contact Field Required"),
                body: _t(
                    "Map views are based on the address of a linked Contact. You need to have a Many2one field linked to the res.partner model in order to create a map view.",
                ),
                contentClass: "o_web_studio_preserve_space",
            });
            this.props.close();
        } else {
            this.fieldsChoice.res_partner = this.partnerFields[0].name;
        }
    }
}

delete MapNewViewDialog.props.viewType;
