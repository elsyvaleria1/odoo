// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { CheckBox } from "@web/components/checkbox/checkbox";
import { DateTimeInput } from "@web/components/datetime/datetime_input";
import { TagsList } from "@web/components/tags_list/tags_list";
import { useAction } from "@web/core/action_port";
import { getCurrency } from "@web/core/currency";
import { makeLogger } from "@web/core/debug/debug_logger";
import { Domain } from "@web/core/domain";
import { formatInteger, formatMany2one, formatMonetary } from "@web/core/formatters";
import {
    deserializeDate,
    deserializeDateTime,
    formatDate,
    formatDateTime,
    serializeDate,
    serializeDateTime,
} from "@web/core/l10n/dates";
import { parseFloat, parseInteger, parseMonetary } from "@web/core/parsers";
import { _t } from "@web/core/translation";
import { deepCopy } from "@web/core/utils/collections/objects";
import { elementRef } from "@web/core/utils/element_ref";
import { formatFloat } from "@web/core/utils/format/numbers";
import { nbsp } from "@web/core/utils/format/strings";
import { useService } from "@web/core/utils/hooks";
import { imageUrl } from "@web/core/utils/urls";
import { useViewConfig } from "@web/core/view_config_hooks";
import { useFieldFlush } from "@web/fields/hooks/debounced_field_commit";
import { extractData } from "@web/fields/relational/many2one/many2one";
import {
    Many2XAutocomplete,
    useOpenMany2XRecord,
} from "@web/fields/relational/many2x_autocomplete";

import { PropertyTags } from "./property_tags.js";
import { PropertyText } from "./property_text.js";

const log = makeLogger("web.field.property_value");

const NUMBER_PARSERS = {
    integer: parseInteger,
    float: parseFloat,
    monetary: parseMonetary,
};

/**
 * @template {Temporal.PlainDate | Temporal.ZonedDateTime} T
 * @param {any} value
 * @param {(value: string) => T} deserialize
 * @returns {T | false}
 */
function toPropertyDateValue(value, deserialize) {
    if (typeof value !== "string") {
        return value || false;
    }
    try {
        return deserialize(value);
    } catch {
        return false;
    }
}

export class PropertyValue extends Component {
    static template = "web.PropertyValue";
    static components = {
        CheckBox,
        DateTimeInput,
        Many2XAutocomplete,
        TagsList,
        PropertyTags,
        PropertyText,
    };

    static props = {
        id: t.string().optional(),
        type: t.string().optional(),
        comodel: t.string().optional(),
        currencyField: t.string().optional(),
        domain: t.string().optional(),
        string: t.string().optional(),
        value: t.any().optional(),
        context: t.object(),
        readonly: t.boolean().optional(),
        canChangeDefinition: t.boolean().optional(),
        selection: t.array().optional(),
        tags: t.array().optional(),
        onChange: t.function().optional(),
        onTagsChange: t.function().optional(),
        record: t.object().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.config = useViewConfig();
        this.nbsp = nbsp;

        this.orm = useService("orm");
        this.action = useAction();

        if (this.props.record) {
            /** @type {any} */
            this.inputRef = elementRef();
            const flush = (ev) => {
                const el = this.inputRef.el;
                if (!el || el !== document.activeElement) {
                    return;
                }
                const typed = el.value !== this.inputValue;
                log.logic("flush focused input", () => ({
                    type: this.props.type,
                    input: el.value,
                    display: this.inputValue,
                    typed,
                }));
                if (typed) {
                    ev.detail?.proms?.push(this.onValueChange(el.value));
                }
            };
            useFieldFlush(this.props.record.model.bus, flush);
        }

        this.openMany2X = useOpenMany2XRecord(
            /** @type {any} */ ({
                resModel: this.props.comodel,
                activeActions: {
                    create: false,
                    createEdit: false,
                    write: true,
                },
                isToMany: false,
                onRecordSaved: async (record) => {
                    if (!record || record.resId == null) {
                        return;
                    }
                    const records = await this.orm.read(
                        record.resModel,
                        [record.resId],
                        ["display_name"],
                        {
                            context: this.props.context,
                        },
                    );
                    const recordData = extractData(records[0]);
                    await this.onValueChange([recordData]);
                },
                fieldString: this.props.string,
            }),
        );
    }

    get currency() {
        if (!isNaN(this.currencyId)) {
            return getCurrency(this.currencyId) || null;
        }
        return null;
    }

    get currencyId() {
        const currency = this.props.record.data[this.props.currencyField];
        return currency && currency.id;
    }

    /** @returns {any} */
    get propertyValue() {
        const value = this.props.value;

        if (this.props.type === "float") {
            return value;
        } else if (this.props.type === "datetime") {
            return toPropertyDateValue(value, deserializeDateTime);
        } else if (this.props.type === "date") {
            return toPropertyDateValue(value, deserializeDate);
        } else if (this.props.type === "boolean") {
            return !!value;
        } else if (this.props.type === "selection") {
            const options = this.props.selection || [];
            const option = options.find((option) => option[0] === value);
            return option && option.length === 2 && option[0] ? option[0] : "";
        } else if (this.props.type === "many2one") {
            return value?.id ? value : false;
        } else if (this.props.type === "many2many") {
            if (!value || !value.length) {
                return [];
            }

            return value.map((many2manyValue) => {
                const hasAccess = many2manyValue[1] !== null;
                return {
                    id: many2manyValue[0],
                    comodel: this.props.comodel,
                    text: hasAccess ? many2manyValue[1] : _t("No Access"),
                    onClick:
                        hasAccess &&
                        this.clickableRelational &&
                        (async () =>
                            await this._openRecord(
                                this.props.comodel,
                                many2manyValue[0],
                            )),
                    onDelete:
                        !this.props.readonly &&
                        hasAccess &&
                        (() => this.onMany2manyDelete(many2manyValue[0])),
                    colorIndex: 0,
                    img:
                        this.showAvatar && hasAccess
                            ? imageUrl(
                                  this.props.comodel,
                                  many2manyValue[0],
                                  "avatar_128",
                              )
                            : null,
                };
            });
        } else if (this.props.type === "tags") {
            return value || [];
        }

        return value;
    }

    /** @returns {array} */
    get propertyDomain() {
        if (!this.props.domain || !this.props.domain.length) {
            return [];
        }
        let domain = new Domain(this.props.domain);
        if (this.props.type === "many2many" && this.props.value) {
            domain = Domain.and([
                domain,
                [["id", "not in", this.props.value.map((rec) => rec[0])]],
            ]);
        }
        return domain.toList();
    }

    /** @returns {string} */
    get displayValue() {
        const value = this.propertyValue;

        if (this.props.type === "many2one" && value && value.id) {
            return formatMany2one(value);
        } else if (this.props.type === "integer") {
            return formatInteger(value || 0);
        } else if (this.props.type === "float") {
            return formatFloat(value || 0);
        } else if (this.props.type === "monetary") {
            return formatMonetary(value || 0, {
                digits: this.currency?.digits,
                currencyId: this.currencyId,
                noSymbol: !this.props.readonly,
            });
        } else if (!value) {
            return /** @type {any} */ (false);
        } else if (this.props.type === "datetime" && value) {
            return formatDateTime(value);
        } else if (this.props.type === "date" && value) {
            return formatDate(value);
        } else if (this.props.type === "selection") {
            return (
                this.props.selection.find((option) => option[0] === value)?.[1] ?? value
            );
        }
        return value.toString();
    }

    /** @returns {string} */
    get inputValue() {
        return this.displayValue || "";
    }

    /** @returns {boolean} */
    get clickableRelational() {
        return !this.config || this.config.viewType !== "kanban";
    }

    /** @returns {boolean} */
    get showAvatar() {
        return (
            ["many2one", "many2many"].includes(this.props.type) &&
            ["res.users", "res.partner"].includes(this.props.comodel)
        );
    }

    /** @param {any} newValue */
    async onValueChange(newValue) {
        if (this.props.type === "datetime") {
            newValue = newValue && serializeDateTime(newValue);
        } else if (this.props.type === "date") {
            newValue = newValue && serializeDate(newValue);
        } else if (this.props.type in NUMBER_PARSERS) {
            try {
                newValue = NUMBER_PARSERS[this.props.type](newValue) || 0;
            } catch {
                log.logic("invalid number kept the previous value", () => ({
                    type: this.props.type,
                    input: newValue,
                    kept: this.props.value,
                }));
                this.resyncInput();
                return;
            }
        } else if (this.props.type === "many2one") {
            newValue = (Array.isArray(newValue) && newValue[0]) || false;
            if (newValue?.id && newValue.display_name === undefined) {
                const names = await this._readDisplayNames([newValue.id]);
                newValue = {
                    id: newValue.id,
                    display_name: names.get(newValue.id) ?? false,
                };
            }
        } else if (this.props.type === "many2many") {
            const currentValue = this.props.value || [];
            const linkedIds = new Set(currentValue.map((rec) => rec[0]));
            const added = [];
            for (const rec of Array.isArray(newValue) ? newValue : []) {
                if (rec?.id && !linkedIds.has(rec.id)) {
                    linkedIds.add(rec.id);
                    added.push(rec);
                }
            }
            if (!added.length) {
                return;
            }
            const names = await this._readDisplayNames(
                added
                    .filter((rec) => rec.display_name === undefined)
                    .map((rec) => rec.id),
            );
            newValue = [
                ...currentValue,
                ...added.map((rec) => [
                    rec.id,
                    rec.display_name ?? names.get(rec.id) ?? false,
                ]),
            ];
        } else if (this.props.type === "selection") {
            newValue = newValue || false;
        }

        const committed = this.props.onChange(newValue);
        await committed;
        this.resyncInput();
        return committed;
    }

    resyncInput() {
        const el = this.inputRef?.el;
        if (el && el.value !== this.inputValue) {
            el.value = this.inputValue;
        }
    }

    /** @param {Event} event */
    async onMany2oneClick(event) {
        if (this.props.readonly) {
            event.stopPropagation();
            await this._openRecord(this.props.comodel, this.propertyValue.id);
        }
    }

    onExternalLinkClick() {
        return this.openMany2X({
            resId: this.propertyValue.id,
            forceModel: this.props.comodel,
            context: this.props.context,
        });
    }

    /** @param {integer} many2manyId */
    onMany2manyDelete(many2manyId) {
        const currentValue = deepCopy(this.props.value || []);
        const newValue = currentValue.filter((value) => value[0] !== many2manyId);
        this.props.onChange(newValue);
    }

    /** @param {string} name */
    async onQuickCreate(name) {
        const result = await this.orm.call(this.props.comodel, "name_create", [name], {
            context: this.props.context,
        });
        this.onValueChange([{ id: result[0], display_name: result[1] }]);
    }

    /**
     * @param {string} recordModel
     * @param {integer} recordId
     */
    async _openRecord(recordModel, recordId) {
        const action = await this.orm.call(
            recordModel,
            "get_formview_action",
            [[recordId]],
            {
                context: this.props.context,
            },
        );

        this.action.doAction(action);
    }

    /**
     * @param {number[]} recordIds
     * @returns {Promise<Map<number, string>>}
     */
    async _readDisplayNames(recordIds) {
        if (!recordIds.length) {
            return new Map();
        }
        const records = await this.orm.read(
            this.props.comodel,
            recordIds,
            ["display_name"],
            {
                context: this.props.context,
            },
        );
        return new Map(records.map((rec) => [rec.id, rec.display_name]));
    }
}
