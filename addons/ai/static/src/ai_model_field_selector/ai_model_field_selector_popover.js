/** @odoo-module native */
import { onWillStart, proxy, t } from "@odoo/owl";
import { ModelFieldSelectorPopover } from "@web/components/model_field_selector";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

export class AiModelFieldSelectorPopover extends ModelFieldSelectorPopover {
    static template = "ai.AiModelFieldSelectorPopover";
    static props = {
        ...ModelFieldSelectorPopover.props,
        updateBatch: t.function(),
        fieldsPath: t.array().optional(),
        aiFieldPath: t.string().optional(),
        readProperty: ModelFieldSelectorPopover.props.readProperty.optional(true),
    };

    setup() {
        this.allowedQwebExpressionsService = useService("allowed_qweb_expressions");
        this.aiFieldsState = proxy({ selected: [] });

        this.orm = useService("orm");

        onWillStart(async () => {
            if (this.props.fieldsPath) {
                await this._loadFields(this.props.fieldsPath);
            }
        });
        this.isTemplateEditor = null;
        this.allowedQwebExpressions = null;
        return super.setup();
    }

    get fieldNames() {
        const currentPath = [];
        let page = this.state.page.previousPage;
        while (page) {
            currentPath.push(page.selectedName);
            page = page.previousPage;
        }
        const currentPathStr = currentPath.reverse().join(".");

        return super.fieldNames.filter((f) => {
            const path = currentPathStr ? `${currentPathStr}.${f}` : f;
            if (this.props.aiFieldPath && this.props.aiFieldPath === path) {
                return false;
            }
            return true;
        });
    }

    async selectField(field) {
        if (field.type === "properties") {
            return this.followRelation(field);
        }
        this.state.page.selectedName = field.name;
        if (this.isFieldSelected(field)) {
            return;
        }

        this.keepLast.add(Promise.resolve());

        this.aiFieldsState.selected.push([...this.fieldsChain, field]);

        if (!(await user.hasGroup("mail.group_mail_template_editor"))) {
            this.onInsert();
        }
    }

    get fieldsChain() {
        let page = this.state.page.previousPage;
        const fieldsChain = [];
        while (page) {
            fieldsChain.push(page.fieldDefs[page.selectedName]);
            page = page.previousPage;
        }
        return fieldsChain.reverse();
    }

    onInsert() {
        this.props.updateBatch(this.aiFieldsState.selected);
        this.props.close();
    }

    onRemoveField(path) {
        this.aiFieldsState.selected = this.aiFieldsState.selected.filter(
            (f) => f[0] !== path,
        );
    }

    async beforeFilter() {
        if (this.isTemplateEditor === null) {
            const getAllowedQwebExpressions = this.allowedQwebExpressionsService;
            this.isTemplateEditor = await user.hasGroup(
                "mail.group_mail_template_editor",
            );
            this.allowedQwebExpressions = await getAllowedQwebExpressions(
                this.props.resModel,
            );
        }
    }

    async followRelations() {
        await this.beforeFilter();
        return super.followRelations(...arguments);
    }
    async loadPages() {
        await this.beforeFilter();
        return super.loadPages(...arguments);
    }

    filter(fieldDefs, path) {
        fieldDefs = super.filter(fieldDefs, path);
        const filteredKeys = Object.keys(fieldDefs).filter((key) => {
            const fullPath = `object${path ? `.${path}` : ""}.${fieldDefs[key].name}`;
            if (
                !this.isTemplateEditor &&
                !this.allowedQwebExpressions?.includes(fullPath)
            ) {
                return false;
            }
            if (fieldDefs[key].type === "separator") {
                return false;
            }
            return fieldDefs[key].searchable;
        });
        return Object.fromEntries(filteredKeys.map((k) => [k, fieldDefs[k]]));
    }

    /**
     * Resolve field paths into field definition chains and store them as the selection.
     * @param {string[]} fieldsPath - dot-separated field paths
     */
    async _loadFields(fieldsPath) {
        const fieldsInfos = Object.fromEntries(
            await Promise.all(
                fieldsPath.map(async (path) => [
                    path,
                    await this.fieldService.loadPath(this.props.resModel, path, true),
                ]),
            ),
        );

        const selected = [];
        for (const path of fieldsPath) {
            const { names, modelsInfo } = await fieldsInfos[path];
            const fieldsInfo = [];
            for (let i = 0; i < names.length; i++) {
                const f = modelsInfo[i].fieldDefs[names[i]];
                fieldsInfo.push(f);
            }
            selected.push(fieldsInfo);
        }
        this.aiFieldsState.selected = selected;
    }

    isFieldSelected(fieldDef) {
        const fullFieldPath = [...this.fieldsChain, fieldDef]
            .map((f) => f.name)
            .join(".");

        return this.aiFieldsState.selected.some(
            (selectedChain) =>
                selectedChain.map((f) => f.name).join(".") === fullFieldPath,
        );
    }
}
