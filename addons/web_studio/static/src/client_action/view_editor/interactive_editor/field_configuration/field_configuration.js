/** @odoo-module native */
import { Component, proxy, t, useProps, xml } from "@odoo/owl";
import { DomainSelector } from "@web/components/domain_selector";
import { ModelFieldSelector } from "@web/components/model_field_selector";
import { RecordSelector } from "@web/components/record_selectors";
import { useDebugMode } from "@web/core/debug/debug_context";
import { _t } from "@web/core/translation";
import { useOwnedDialogs, useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog";
import { useDialogConfirmation } from "@web_studio/client_action/utils";
import { SelectionContentDialog } from "@web_studio/client_action/view_editor/interactive_editor/field_configuration/selection_content_dialog";

export class SelectionValuesEditor extends Component {
    static components = {
        SelectionContentDialog,
    };
    static props = {
        configurationModel: t.object(),
        confirm: t.function(),
        cancel: t.function(),
    };
    static template = "web_studio.SelectionValuesEditor";
    static Model = class SelectionValuesModel {
        constructor() {
            this.selection = "[]";
        }
        get isValid() {
            return true;
        }
    };
    props = useProps(this.constructor.props);
    get selection() {
        return JSON.parse(this.props.configurationModel.selection);
    }
    onConfirm(choices) {
        this.props.configurationModel.selection = JSON.stringify(choices);
        this.props.confirm();
    }
}

export class RelationalFieldConfigurator extends Component {
    static template = "web_studio.RelationalFieldConfigurator";
    static components = { RecordSelector };
    static props = {
        configurationModel: t.object(),
        resModel: t.string(),
        fieldType: t.string(),
    };
    static Model = class RelationalFieldModel {
        constructor() {
            this.relationId = false;
        }
        get isValid() {
            return !!this.relationId;
        }
    };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy(this.props.configurationModel);
    }

    get valueSelectorProps() {
        if (this.props.fieldType === "one2many") {
            return {
                resModel: "ir.model.fields",
                domain: [
                    ["relation", "=", this.props.resModel],
                    ["ttype", "=", "many2one"],
                    ["model_id.abstract", "=", false],
                    ["store", "=", true],
                ],
                resId: this.state.relationId,
                update: (resId) => {
                    this.state.relationId = resId;
                },
            };
        }
        return {
            resModel: "ir.model",
            domain: [
                ["transient", "=", false],
                ["abstract", "=", false],
                ["model", "not in", ["knowledge.article"]],
            ],
            resId: this.state.relationId,
            update: (resId) => {
                this.state.relationId = resId;
            },
        };
    }
}

class RelatedChainBuilderModel {
    static services = ["field", "dialog"];

    constructor({ services, props }) {
        this.services = services;
        this.relatedParams = {};
        this.fieldInfo = { resModel: props.resModel, fieldDef: null };
        this.resModel = props.resModel;
    }

    get isValid() {
        return !!this.relatedParams.related;
    }

    getRelatedFieldDescription(resModel, lastField) {
        const fieldType = lastField.type;
        const relatedDescription = {
            readonly: true,
            copy: false,
            string: lastField.string,
            type: fieldType,
            store: false,
        };

        if (["many2one", "many2many", "one2many"].includes(fieldType)) {
            relatedDescription.relation = lastField.relation;
        }
        if (["one2many", "many2many"].includes(fieldType)) {
            relatedDescription.relational_model = resModel;
        }
        if (fieldType === "selection") {
            relatedDescription.selection = lastField.selection;
        }
        return relatedDescription;
    }

    async confirm() {
        const relatedDescription = this.getRelatedFieldDescription(
            this.fieldInfo.resModel,
            this.fieldInfo.fieldDef,
        );
        Object.assign(this.relatedParams, relatedDescription);
        return true;
    }
}

export class RelatedChainBuilder extends Component {
    static template = xml`<ModelFieldSelector resModel="this.props.resModel" path="this.fieldChain" readonly="false" filter.bind="this.filter" update.bind="this.updateChain" />`;
    static components = { ModelFieldSelector };
    static props = { resModel: t.string(), configurationModel: t.object() };
    static Model = RelatedChainBuilderModel;
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy(this.props.configurationModel);
        this.relatedParams.related = "";
    }

    get relatedParams() {
        return this.state.relatedParams;
    }

    get fieldChain() {
        return this.relatedParams.related;
    }

    filter(fieldDef, path) {
        if (fieldDef.type === "properties") {
            return false;
        }
        if (["many2one", "one2many", "many2many"].includes(fieldDef.type)) {
            return fieldDef.searchable;
        }
        return true;
    }

    async updateChain(path, fieldInfo) {
        this.relatedParams.related = path;
        this.state.fieldInfo = fieldInfo;
    }
}

function useConfiguratorModel(Model, props) {
    const services = Object.fromEntries(
        (Model.services || []).map((servName) => {
            let serv;
            if (servName === "dialog") {
                serv = { add: useOwnedDialogs() };
            } else {
                serv = useService(servName);
            }
            return [servName, serv];
        }),
    );

    const model = new Model({ services, props });
    return proxy(model);
}

export class FieldConfigurationDialog extends Component {
    static props = {
        confirm: t.function(),
        cancel: t.function(),
        close: t.function(),
        Component: t.function(),
        componentProps: t.object().optional(),
        fieldType: t.string().optional(),
        isDialog: t.boolean().optional(),
        title: t.string().optional(),
        size: t.string().optional(),
    };
    static template = "web_studio.FieldConfigurationDialog";
    static components = { Dialog };
    props = useProps(this.constructor.props);

    setup() {
        const { confirm, cancel } = useDialogConfirmation({
            confirm: async () => {
                let confirmValues = false;
                if (!this.configurationModel.isValid) {
                    return false;
                }
                if (this.configurationModel.confirm) {
                    const res = await this.configurationModel.confirm();
                    if (res || res === undefined) {
                        confirmValues = this.configurationModel;
                    }
                } else {
                    confirmValues = this.configurationModel;
                }
                return this.props.confirm(confirmValues);
            },
            cancel: () => this.props.cancel(),
        });
        this.confirm = confirm;
        this.cancel = cancel;
        this.configurationModel = useConfiguratorModel(
            this.Component.Model,
            this.props.componentProps,
        );
    }

    get title() {
        if (this.props.title) {
            return this.props.title;
        }
        if (this.props.fieldType) {
            return _t("Field properties: %s", this.props.fieldType);
        }
        return "";
    }

    get Component() {
        return this.props.Component;
    }

    get canConfirm() {
        return this.configurationModel.isValid;
    }
}

export class FilterConfiguration extends Component {
    static components = { DomainSelector };
    static template = "web_studio.FilterConfiguration";
    static props = { resModel: t.string(), configurationModel: t.object() };
    static Model = class FilterConfigurationModel {
        constructor() {
            this.filterLabel = "";
            this.domain = "[]";
        }

        get isValid() {
            return !!this.filterLabel;
        }
    };
    props = useProps(this.constructor.props);

    setup() {
        this.debug = useDebugMode();
        this.state = proxy(this.props.configurationModel);
    }

    get domainSelectorProps() {
        return {
            resModel: this.props.resModel,
            readonly: false,
            domain: this.state.domain,
            update: (domainStr) => {
                this.state.domain = domainStr;
            },
            isDebugMode: !!this.debug,
        };
    }
}
