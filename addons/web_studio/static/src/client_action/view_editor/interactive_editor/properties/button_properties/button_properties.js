/** @odoo-module native */
import {
    Component,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { CheckBox } from "@web/components/checkbox";
import { DomainSelectorDialog } from "@web/components/domain_selector_dialog";
import { SelectMenu } from "@web/components/select_menu";
import { useDebugMode } from "@web/core/debug/debug_context";
import { rpc } from "@web/core/network";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { Many2ManyTagsField } from "@web/fields/relational/many2many_tags";
import { Many2OneField } from "@web/fields/relational/many2one";
import { Record } from "@web/model/record";
import { ClassAttribute } from "@web_studio/client_action/view_editor/interactive_editor/properties/class_attribute/class_attribute";
import { ModifiersProperties } from "@web_studio/client_action/view_editor/interactive_editor/properties/modifiers/modifiers_properties";
import { ViewStructureProperties } from "@web_studio/client_action/view_editor/interactive_editor/properties/view_structure_properties/view_structure_properties";
import { Property } from "@web_studio/client_action/view_editor/property/property";
import { useSnackbarWrapper } from "@web_studio/client_action/view_editor/view_editor_hook";
import { useEditNodeAttributes } from "@web_studio/client_action/view_editor/view_editor_model";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

import { RainbowEffect } from "./rainbow_effect.js";

export class ButtonProperties extends Component {
    static template = "web_studio.ViewEditor.InteractiveEditorProperties.Button";
    static props = { node: t.object(), availableOptions: t.array().optional() };
    static components = {
        CheckBox,
        ClassAttribute,
        Many2OneField,
        Many2ManyTagsField,
        RainbowEffect,
        Record,
        SelectMenu,
        Property,
        ViewStructureProperties,
        ModifiersProperties,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.viewEditorModel = useCurrentViewEditorModel();
        this.debug = useDebugMode();
        this.dialog = useService("dialog");
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = proxy({
            actionsList: [],
            approvalSteps: [],
        });
        this.editNodeAttributes = useEditNodeAttributes();

        this.decoratedOrmCall = useSnackbarWrapper(this.orm.call.bind(this.orm));
        this.decoratedOrmWrite = useSnackbarWrapper(this.orm.write.bind(this.orm));

        this.domainResUsers = [
            ["id", "not in", [1]],
            ["share", "=", false],
        ];
        const m2mFieldsToFetch = {
            display_name: { type: "char" },
        };
        const approvalRecordDefinition = {
            group_id: {
                type: "many2one",
                relation: "res.groups",
                domain: [["share", "=", false]],
            },
            user_ids: {
                type: "many2many",
                relation: "res.users",
                related: { activeFields: m2mFieldsToFetch, fields: m2mFieldsToFetch },
            },
            notify_user_ids: {
                type: "many2many",
                relation: "res.users",
                related: { activeFields: m2mFieldsToFetch, fields: m2mFieldsToFetch },
            },
        };
        this.recordProps = {
            resModel: "approval.category.step",
            fields: approvalRecordDefinition,
            activeFields: approvalRecordDefinition,
        };

        // We don't want to display 'a' in the sidebar.
        this.viewEditorModel.activeNode.humanName = _t("Button");

        onWillStart(async () =>
            Promise.all([this.loadApprovalSteps(), this.loadActions()]),
        );

        onWillUpdateProps((nextProps) => {
            this.loadApprovalSteps(this.getApprovalParams(nextProps.node));
        });
    }

    get availableOptions() {
        if (
            this.viewEditorModel.viewType !== "form" &&
            this.viewEditorModel.activeNode.arch.closest("header")
        ) {
            // Invisible property is not editable for Header buttons in List and Kanban
            return [];
        }
        return this.props.availableOptions;
    }

    get currentActionValue() {
        if (this.state.actionsList?.[this.props.node.attrs.name]) {
            return this.state.actionsList[this.props.node.attrs.name].xml_id;
        }
        return this.props.node.attrs.name;
    }

    get actionsForModel() {
        return Object.values(this.state.actionsList).map((a) => ({
            label: odoo.debug ? `${a.name} (${a.xml_id})` : a.name,
            value: a.xml_id,
        }));
    }

    get types() {
        return [
            { label: _t("Run a Server Action"), value: "action" },
            { label: _t("Call a method"), value: "object" },
        ];
    }

    async loadActions() {
        if (this.props.node.attrs.type !== "action") {
            return;
        }
        this.state.actionsList = await rpc("/web_studio/get_actions_for_model", {
            model: this.viewEditorModel.resModel,
        });
    }

    isValid(fieldName, record) {
        if (["user_ids", "group_id"].includes(fieldName)) {
            const evalContext = record.evalContext;
            return evalContext.user_ids.length || evalContext.group_id;
        }
        return true;
    }

    onChangeAttribute(value, name) {
        return this.editNodeAttributes({ [name]: value });
    }

    async onChangeApprovalRecord(record, changes, id) {
        await this.decoratedOrmWrite("approval.category.step", [id], changes);
        this.loadApprovalSteps();
    }

    get showApprovals() {
        return this.viewEditorModel.viewType === "form";
    }

    get showRainbowMan() {
        const attrs = this.props.node.attrs;
        return attrs.class !== "oe_stat_button" && attrs.type === "object";
    }

    async createApprovalRule() {
        await this.decoratedOrmCall(
            "approval.binding",
            "create_step_for_button",
            this.getApprovalParams(),
        );
        this.loadApprovalSteps();
    }

    getApprovalParams(node = this.props.node) {
        const isMethod = node.attrs.type === "object";
        return [
            this.viewEditorModel.resModel,
            isMethod ? node.attrs.name : false,
            isMethod ? false : node.attrs.name,
        ];
    }

    async onApprovalArchive(id) {
        await this.decoratedOrmWrite("approval.category.step", [id], {
            active: false,
        });
        this.loadApprovalSteps();
    }

    async onApprovalEdit(name, id, value) {
        const field = {
            operation_approval_message: "name",
            operation_different_users: "exclusive",
        }[name];
        if (field === "name" && !value) {
            return this.loadApprovalSteps();
        }
        await this.decoratedOrmWrite("approval.category.step", [id], {
            [field]: value,
        });
        this.loadApprovalSteps();
    }

    onApprovalSelectDomain(id) {
        const step = this.state.approvalSteps.find((s) => s.id === id);
        this.dialog.add(DomainSelectorDialog, {
            resModel: this.viewEditorModel.resModel,
            domain: step?.subject_domain || "[]",
            isDebugMode: !!this.debug,
            onConfirm: async (domain) => {
                await this.decoratedOrmWrite("approval.category.step", [id], {
                    subject_domain: domain,
                });
                this.loadApprovalSteps();
            },
        });
    }

    async onChangeNotificationOrder(ev, id) {
        await this.decoratedOrmWrite("approval.category.step", [id], {
            sequence: parseInt(ev.target.value),
        });
        this.loadApprovalSteps();
    }

    /**
     * The steps gating this button, as approval.binding knows them: an archived step
     * leaves the list, and a button whose steps are all archived answers ungated.
     */
    async loadApprovalSteps([model, method, action] = this.getApprovalParams()) {
        this.viewEditorModel.bus.trigger("approval-update");
        const [approvals] = await this.orm.call(
            "approval.binding",
            "get_button_approvals",
            [[{ model, res_id: false, method, action_id: action, configured: true }]],
        );
        const stepIds = approvals.gated
            ? approvals.steps.map((step) => step.id).filter(Boolean)
            : [];
        this.state.approvalSteps = stepIds.length
            ? await this.orm.searchRead(
                  "approval.category.step",
                  [["id", "in", stepIds]],
                  [
                      "name",
                      "sequence",
                      "exclusive",
                      "subject_domain",
                      "user_ids",
                      "group_id",
                      "notify_user_ids",
                  ],
                  { order: "sequence, id" },
              )
            : [];
    }

    async openKanbanApprovalRules() {
        const [resModel, method, action] = this.getApprovalParams();
        return this.actionService.doActionButton({
            context: {
                studio: true,
            },
            type: "object",
            name: "action_open_button_steps",
            resModel: "approval.binding",
            resIds: [],
            args: JSON.stringify([resModel, method, action]),
            stackPosition: "replaceCurrentAction",
        });
    }
}
