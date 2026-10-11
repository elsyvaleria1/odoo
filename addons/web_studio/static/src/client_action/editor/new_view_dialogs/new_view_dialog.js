/** @odoo-module native */
import { onWillStart, t } from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";

export class NewViewDialog extends ConfirmationDialog {
    static template = "web_studio.NewViewDialog";
    static GROUPABLE_TYPES = [
        "many2one",
        "char",
        "boolean",
        "selection",
        "date",
        "datetime",
    ];
    static MEASURABLE_TYPES = ["integer", "float"];
    static props = {
        ...ConfirmationDialog.props,
        viewType: t.string(),
        mandatoryStopDate: t.boolean().optional(),
    };

    setup() {
        super.setup();
        this.debug = useDebugMode();
        this.orm = useService("orm");
        this.studio = useService("studio");
        this.mandatoryStopDate = Boolean(this.props.mandatoryStopDate);

        this.title = _t("Generate %s View", this.viewType);

        this.fieldsChoice = {
            date_start: null,
            date_stop: null,
        };

        onWillStart(async () => {
            const fieldsGet = await this.orm.call(
                this.studio.editedAction.res_model,
                "fields_get",
            );
            const fields = Object.entries(fieldsGet).map(([fName, field]) => {
                field.name = fName;
                return field;
            });
            fields.sort((first, second) => {
                if (first.string === second.string) {
                    return 0;
                }
                if (first.string < second.string) {
                    return -1;
                }
                if (first.string > second.string) {
                    return 1;
                }
            });
            this.computeSpecificFields(fields);
        });
    }

    get viewType() {
        return this.props.viewType;
    }

    computeSpecificFields(fields) {
        this.dateFields = [];
        this.rowFields = [];
        this.measureFields = [];
        fields.forEach((field) => {
            if (field.store) {
                if (field.type === "date" || field.type === "datetime") {
                    this.dateFields.push(field);
                }
                if (this.constructor.GROUPABLE_TYPES.includes(field.type)) {
                    this.rowFields.push(field);
                }
                if (this.constructor.MEASURABLE_TYPES.includes(field.type)) {
                    if (field.name !== "id" && field.name !== "sequence") {
                        this.measureFields.push(field);
                    }
                }
            }
        });
        if (this.dateFields.length) {
            this.fieldsChoice.date_start = this.dateFields[0].name;
            this.fieldsChoice.date_stop = this.dateFields[0].name;
        }
    }

    async confirm() {
        await rpc("/web_studio/create_default_view", {
            model: this.studio.editedAction.res_model,
            view_type: this.viewType,
            attrs: this.fieldsChoice,
        });
        super.confirm();
    }
}
delete NewViewDialog.props.body;
