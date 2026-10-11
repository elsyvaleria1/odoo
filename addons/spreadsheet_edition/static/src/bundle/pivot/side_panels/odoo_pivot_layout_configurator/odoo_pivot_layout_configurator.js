/** @odoo-module native */
import { components } from "@odoo/o-spreadsheet";
import { t } from "@odoo/owl";
import {
    getRelationalFieldDefinition,
    ODOO_AGGREGATORS,
} from "@spreadsheet/pivot/pivot_helpers";
import {
    ModelFieldSelector,
    ModelFieldSelectorPopover,
} from "@web/components/model_field_selector";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/ui/popover";
const { PivotLayoutConfigurator } = components;

export class PivotModelFieldSelectorPopover extends ModelFieldSelectorPopover {
    static template = "spreadsheet_edition.PivotModelFieldSelectorPopover";

    canFollowRelationFor(fieldDef) {
        if (fieldDef.type === "many2many" || !(fieldDef.store || fieldDef.groupable)) {
            return false;
        }
        return super.canFollowRelationFor(fieldDef);
    }

    duplicateTooltip(alreadyPresent) {
        return alreadyPresent ? _t("Pivot contains duplicate groupbys") : undefined;
    }

    filter(fieldDefs, path) {
        const RELATIONAL_FIELDS = new Set(["many2one", "one2many"]);
        const DATE_FIELDS = new Set(["date", "datetime"]);
        const result = {};
        for (const key in fieldDefs) {
            const field = fieldDefs[key];
            if (!field.groupable) {
                continue;
            }
            const isFieldAlreadyPresent = this.props.filter(field, path);
            if (RELATIONAL_FIELDS.has(field.type)) {
                result[key] = { ...field, isFieldAlreadyPresent };
            } else if (!isFieldAlreadyPresent || DATE_FIELDS.has(field.type)) {
                result[key] = field;
            }
        }
        return result;
    }
}

export class PivotModelFieldSelector extends ModelFieldSelector {
    static template = "spreadsheet_edition.PivotModelFieldSelector";
    static components = {
        Popover: PivotModelFieldSelectorPopover,
    };

    setup() {
        super.setup();
        this.popover = usePopover(this.constructor.components.Popover, {
            class: "o_popover_field_selector o_spreadsheet_pivot_field_selector",
            onClose: async () => {
                if (this.newPath !== null) {
                    const fieldInfo = await this.fieldService.loadFieldInfo(
                        this.props.resModel,
                        this.newPath,
                    );
                    this.props.update(this.newPath, fieldInfo);
                }
            },
        });
    }
}

export class OdooPivotLayoutConfigurator extends PivotLayoutConfigurator {
    static template = "spreadsheet_edition.OdooPivotLayoutConfigurator";
    static components = {
        ...PivotLayoutConfigurator.components,
        PivotModelFieldSelector,
    };
    static props = { ...PivotLayoutConfigurator.props, addDraftField: t.function() };

    setup() {
        super.setup(...arguments);
        this.fieldService = useService("field");
        this.AGGREGATORS = ODOO_AGGREGATORS;
    }

    async addColumnDimension(fieldName) {
        const definition = await getRelationalFieldDefinition(
            this.props.definition.model,
            fieldName,
            this.fieldService,
        );
        this.props.addDraftField(fieldName, definition);
        super.addColumnDimension(fieldName);
    }

    async addRowDimension(fieldName) {
        const definition = await getRelationalFieldDefinition(
            this.props.definition.model,
            fieldName,
            this.fieldService,
        );
        this.props.addDraftField(fieldName, definition);
        super.addRowDimension(fieldName);
    }

    get allDimensions() {
        return this.props.definition.rows.concat(this.props.definition.columns);
    }

    isFieldAlreadyPresent(field, path) {
        const fullField = path ? `${path}.${field.name}` : field.name;
        return this.allDimensions.some((f) => f.fieldName === fullField);
    }
}
