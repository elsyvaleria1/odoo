/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { DropdownItem } from "@web/components/dropdown";
import { useDebugMode } from "@web/core/debug/debug_context";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { sortBy } from "@web/core/utils/collections/arrays";
import { useOwnedDialogs, useService } from "@web/core/utils/hooks";
import { CharField } from "@web/fields/basic/char/char_field";
import { TextField } from "@web/fields/basic/text/text_field";
import {
    Many2ManyTagsField,
    many2ManyTagsField,
} from "@web/fields/relational/many2many_tags";
import { Record } from "@web/model/record";
import { AlertDialog } from "@web/ui/dialog";
import { standardActionServiceProps } from "@web/webclient/actions";
import { ThumbnailItem } from "@web_studio/client_action/components/thumbnail_item/thumbnail_item";
import { useStudioEditorContext } from "@web_studio/client_action/editor/studio_editor_context";
import {
    useStudioServiceAsReactive,
    viewTypeToString,
} from "@web_studio/studio_service";

function getViewCategories() {
    const categories = {
        general: { title: _t("General views"), viewTypes: [] },
        multiple: { title: _t("Multiple records views"), viewTypes: [] },
        timeline: { title: _t("Timeline views"), viewTypes: [] },
        reporting: { title: _t("Reporting views"), viewTypes: [] },
    };
    for (const [type, editor] of registry.category("studio_editors").getEntries()) {
        categories[editor.group ?? "general"].viewTypes.push(type);
    }
    return categories;
}

const actionFieldsGet = {
    id: { type: "integer" },
    name: { type: "char" },
    help: { type: "text" },
    group_ids: { type: "many2many", relation: "res.groups", string: "Groups" },
};

function getActionActiveFields() {
    const activeFields = {};
    for (const fName of Object.keys(actionFieldsGet)) {
        activeFields[fName] = {};
    }

    const groups_idRelated = Object.fromEntries(
        many2ManyTagsField.relatedFields({ options: {} }).map((f) => [f.name, f]),
    );
    activeFields.group_ids.related = {
        activeFields: groups_idRelated,
        fields: groups_idRelated,
    };

    return activeFields;
}

function getActionValues(action) {
    const values = {};
    for (const fName of Object.keys(actionFieldsGet)) {
        values[fName] = action[fName];
    }
    return values;
}

class ActionEditor extends Component {
    static template = "web_studio.ActionEditor";
    static props = { ...standardActionServiceProps };
    static components = {
        ThumbnailItem,
        DropdownItem,
        Record,
        CharField,
        TextField,
        Many2ManyTagsField,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.studioContext = useStudioEditorContext();
        this.debug = useDebugMode();
        this.studio = useStudioServiceAsReactive();
        this.action = useService("action");
        this.notification = useService("notification");
        this.viewCategories = getViewCategories();
        this.addDialog = useOwnedDialogs();

        this.actionFieldsGet = { ...actionFieldsGet };
    }

    get isActionEditable() {
        return !!this.studio.editedAction.id;
    }

    get actionRecordProps() {
        const values = getActionValues(this.studio.editedAction);
        return {
            fields: this.actionFieldsGet,
            resModel: "ir.actions.act_window",
            resId: values.id,
            mode: "edit",
            values,
            activeFields: getActionActiveFields(),
            hooks: {
                lifecycle: {
                    onRecordChanged: (record, changes) => this.editAction(changes),
                },
            },
        };
    }

    get activeViews() {
        return this.studio.editedAction.views.map(([, name]) => name);
    }

    getOrderedViewTypes(viewTypes) {
        const activeViews = this.activeViews;
        const currentDefaultView = activeViews[0];
        const viewInfos = viewTypes.map((viewType) => ({
            name: viewType,
            title: viewTypeToString(viewType),
            isActive: activeViews.includes(viewType),
            isDefault: currentDefaultView === viewType,
            imgUrl: `/web_studio/static/src/img/view_type/${viewType}.png`,
            canBeDefault: !["form", "search"].includes(viewType),
            canBeDisabled: viewType !== "search",
        }));
        return sortBy(
            viewInfos,
            ({ isDefault, isActive }) => (isDefault ? 2 : isActive ? 1 : 0),
            "desc",
        );
    }

    setDefaultView(viewType) {
        let viewModes = this.studio.editedAction.view_mode.split(",");
        viewModes = viewModes.filter((m) => m !== viewType);
        viewModes.unshift(viewType);
        return this.editAction({ view_mode: viewModes.join(",") });
    }

    disableView(viewType) {
        const viewMode = this.studio.editedAction.view_mode
            .split(",")
            .filter((m) => m !== viewType);

        if (!viewMode.length) {
            this.addDialog(AlertDialog, {
                body: _t(
                    "You cannot deactivate this view as it is the last one active.",
                ),
            });
        } else {
            return this.editAction({ view_mode: viewMode.join(",") });
        }
    }

    restoreDefaultView(viewType) {
        return this.studioContext.editionFlow.restoreDefaultView(null, viewType);
    }

    async addViewType(viewType) {
        const action = this.studio.editedAction;
        const viewMode = action.view_mode.split(",");
        viewMode.push(viewType);
        let viewAdded = await rpc("/web_studio/add_view_type", {
            action_type: action.type,
            action_id: action.id,
            res_model: action.res_model,
            view_type: viewType,
            args: { view_mode: viewMode.join(",") },
            context: user.context,
        });

        if (viewAdded !== true) {
            viewAdded = await new Promise((resolve) => {
                let DialogClass;
                const dialogProps = {
                    confirm: async () => {
                        resolve(true);
                    },
                    cancel: () => resolve(false),
                };
                const editor = registry.category("studio_editors").get(viewType, null);
                if (editor?.newViewDialog) {
                    DialogClass = editor.newViewDialog;
                    dialogProps.viewType = viewType;
                    dialogProps.mandatoryStopDate = Boolean(
                        editor.newViewMandatoryStopDate,
                    );
                } else {
                    this.addDialog(AlertDialog, {
                        body: _t(
                            "Creating this type of view is not currently supported in Studio.",
                        ),
                    });
                    resolve(false);
                }
                this.addDialog(DialogClass, dialogProps);
            });
        }
        if (viewAdded) {
            await this.editAction({ view_mode: viewMode.join(",") });
        }
        return viewAdded;
    }

    editView(viewType) {
        this.studio.setParams({ viewType, editorTab: "views" });
    }

    async onThumbnailClicked(viewType) {
        if (this.activeViews.includes(viewType)) {
            return this.editView(viewType);
        }
        const resModel = this.studio.editedAction.res_model;
        if (viewType === "activity") {
            const modelInfo = await this.studio.IrModelInfo.read(resModel);
            const activityAllowed =
                modelInfo.is_mail_activity || modelInfo.state === "manual";
            if (!activityAllowed) {
                this.notification.add(_t("Activity view unavailable on this model"), {
                    title: false,
                    type: "danger",
                });
                return;
            }
        }
        if (await this.addViewType(viewType)) {
            return this.editView(viewType);
        }
    }

    openFormAction() {
        return this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "ir.actions.act_window",
                res_id: this.studio.editedAction.id,
                views: [[false, "form"]],
                target: "current",
            },
            {
                stackPosition: "replacePreviousAction",
            },
        );
    }

    async editAction(changes) {
        await rpc("/web_studio/edit_action", {
            action_id: this.studio.editedAction.id,
            action_type: "ir.actions.act_window",
            args: changes,
        });
        return this.studio.reload({}, false);
    }
}

registry.category("actions").add("web_studio.action_editor", ActionEditor);
