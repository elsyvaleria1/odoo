/** @odoo-module native */
import { Component, onWillStart, proxy, t, useListener, useProps } from "@odoo/owl";
import { DropdownItem } from "@web/components/dropdown";
import { SelectMenu } from "@web/components/select_menu";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { uuid } from "@web/core/utils/format/strings";
import { useAutofocus, useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";
import { SCALE_LABELS } from "@web/views/calendar";

export class ItemCalendarPropsDialog extends Component {
    static template = "knowledge.ItemCalendarPropsDialog";
    static components = {
        DropdownItem,
        Dialog,
        SelectMenu,
    };
    static props = {
        knowledgeArticleId: t.number().optional(),
        close: t.function().optional(),
        colorPropertyId: t.string().optional(),
        dateStartPropertyId: t.string().optional(),
        dateStopPropertyId: t.string().optional(),
        dateType: t.string().optional(),
        isNew: t.boolean().optional(),
        name: t.string().optional(),
        saveItemCalendarProps: t.function(),
        scale: t.string().optional(),
        showWeekEnds: t.boolean().optional(true),
        slotMaxTime: t.string().optional("24:00"),
        slotMinTime: t.string().optional("00:00"),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.autofocusRef = elementRef();
        useAutofocus({ ref: this.autofocusRef });
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({
            name: this.props.name,
            scale: this.props.scale || "week",
            showWeekEnds: this.props.showWeekEnds,
            slotMaxTime: this.props.slotMaxTime,
            slotMinTime: this.props.slotMinTime,
        });
        this.colorChoices = [];
        this.dateChoices = [];
        this.dateTimeChoices = [];
        this.propertyFieldEntries = {};
        this.scalesChoices = Object.entries(SCALE_LABELS).map(([value, label]) => ({
            value,
            label,
        }));

        onWillStart(async () => {
            const propertiesDefinitions = await this.orm.read(
                "knowledge.article",
                [this.props.knowledgeArticleId],
                ["article_properties_definition"],
            );
            this.propertiesDefinitions =
                propertiesDefinitions[0].article_properties_definition;
            for (const definition of this.propertiesDefinitions) {
                this.propertyFieldEntries[definition.name] = {
                    label: definition.string,
                    type: definition.type,
                };
                const choice = {
                    value: definition.name,
                    label: definition.string,
                };
                if (definition.type === "datetime") {
                    this.dateTimeChoices.push(choice);
                } else if (definition.type === "date") {
                    this.dateChoices.push(choice);
                } else if (
                    ["boolean", "many2one", "selection"].includes(definition.type)
                ) {
                    this.colorChoices.push(choice);
                }
            }

            if (this.props.isNew) {
                if (!this.dateTimeChoices.length && !this.dateChoices.length) {
                    this.autoCreateDateProperties = true;
                    this.createProperty(_t("Start Date Time"), "datetime", "dateStart");
                    this.createProperty(_t("End Date Time"), "datetime", "dateStop");
                } else {
                    if (this.dateTimeChoices.length > 1) {
                        this.selectDateStart(this.dateTimeChoices[0].value);
                        this.selectDateStop(this.dateTimeChoices[1].value);
                    } else if (this.dateChoices.length > 1) {
                        this.selectDateStart(this.dateChoices[0].value);
                        this.selectDateStop(this.dateChoices[1].value);
                    } else if (this.dateTimeChoices.length !== 0) {
                        this.selectDateStart(this.dateTimeChoices[0].value);
                    } else {
                        this.selectDateStart(this.dateChoices[0].value);
                    }
                }
            } else {
                for (const propName of [
                    "dateStartPropertyId",
                    "dateStopPropertyId",
                    "colorPropertyId",
                ]) {
                    if (this.propertyFieldEntries[this.props[propName]]) {
                        this.state[propName] = this.props[propName];
                    }
                }
            }
        });

        useListener(window, "keydown", (event) => {
            if (event.key === "Enter") {
                this.save();
            }
        });
    }

    get availableDateStartProperties() {
        return [
            {
                label: _t("Date and Time Properties"),
                choices: this.dateTimeChoices,
            },
            {
                label: _t("Date Properties"),
                choices: this.dateChoices,
            },
        ];
    }

    get availableDateStopProperties() {
        if (this.dateStartProperty?.type === "datetime") {
            return [
                {
                    label: _t("Date and Time Properties"),
                    choices: this.dateTimeChoices.filter(
                        (choice) => choice.value !== this.state.dateStartPropertyId,
                    ),
                },
            ];
        }
        return [
            {
                label: _t("Date Properties"),
                choices: this.dateChoices.filter(
                    (choice) => choice.value !== this.state.dateStartPropertyId,
                ),
            },
        ];
    }

    get colorProperty() {
        return this.propertyFieldEntries[this.state.colorPropertyId];
    }

    get dateStartProperty() {
        return this.propertyFieldEntries[this.state.dateStartPropertyId];
    }

    get dateStopProperty() {
        return this.propertyFieldEntries[this.state.dateStopPropertyId];
    }

    /**
     * @param {string} label:
     * @param {string} type:
     * @param {string} calendarProp:
     */
    createProperty(label, type, calendarProp) {
        const newPropertyId = uuid();
        this.propertyFieldEntries[newPropertyId] = {
            isNew: true,
            label: label,
            type: type,
        };
        const newChoice = {
            value: newPropertyId,
            label,
        };
        if (type === "date") {
            this.dateChoices.push(newChoice);
        } else if (type === "datetime") {
            this.dateTimeChoices.push(newChoice);
        } else {
            this.colorChoices.push(newChoice);
        }
        if (calendarProp === "dateStart") {
            this.selectDateStart(newPropertyId);
        } else if (calendarProp === "dateStop") {
            this.selectDateStop(newPropertyId);
        } else if (calendarProp === "color") {
            this.selectColor(newPropertyId);
        }
    }

    async save() {
        if (!this.state.dateStartPropertyId) {
            this.notification.add(_t("The start date property is required."), {
                type: "danger",
            });
            return;
        }
        if (
            this.dateStartProperty.isNew ||
            this.dateStopProperty?.isNew ||
            this.colorProperty?.isNew
        ) {
            const propertiesDefinitions = [...this.propertiesDefinitions];
            if (this.dateStartProperty.isNew) {
                propertiesDefinitions.push({
                    name: this.state.dateStartPropertyId,
                    string: this.dateStartProperty.label,
                    type: this.dateStartProperty.type,
                });
            }
            if (this.dateStopProperty?.isNew) {
                propertiesDefinitions.push({
                    name: this.state.dateStopPropertyId,
                    string: this.dateStopProperty.label,
                    type: this.dateStopProperty.type,
                });
            }
            if (this.colorProperty?.isNew) {
                propertiesDefinitions.push({
                    name: this.state.colorPropertyId,
                    string: this.colorProperty.label,
                    type: this.colorProperty.type,
                });
            }
            try {
                await this.orm.write(
                    "knowledge.article",
                    [this.props.knowledgeArticleId],
                    { article_properties_definition: propertiesDefinitions },
                );
            } catch (e) {
                this.notification.add(_t("New property could not be created."), {
                    type: "danger",
                });
                console.error(e);
                return;
            }
        }
        this.props.saveItemCalendarProps(this.state.name, {
            dateStartPropertyId: this.state.dateStartPropertyId,
            dateStopPropertyId: this.state.dateStopPropertyId || undefined,
            colorPropertyId: this.state.colorPropertyId || undefined,
            scale: this.state.scale,
            dateType: this.dateStartProperty.type,
            showWeekEnds: this.state.showWeekEnds,
            slotMinTime: this.state.slotMinTime || "00:00",
            slotMaxTime: this.state.slotMaxTime || "24:00",
        });
        this.props.close();
    }

    selectColor(value) {
        this.state.colorPropertyId = value;
    }

    selectDateStop(value) {
        this.state.dateStopPropertyId = value;
    }

    selectScale(value) {
        this.state.scale = value;
    }

    selectDateStart(value) {
        this.state.dateStartPropertyId = value;
        if (
            this.state.dateStopPropertyId &&
            (this.dateStartProperty.type !== this.dateStopProperty.type ||
                this.state.dateStopPropertyId === this.state.dateStartPropertyId)
        ) {
            this.state.dateStopPropertyId = false;
        }
    }
}
