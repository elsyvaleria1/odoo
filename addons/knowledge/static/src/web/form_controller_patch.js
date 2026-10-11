/** @odoo-module native */
import {
    provideKnowledgeContext,
    useKnowledgeContext,
} from "@knowledge/js/knowledge_context";
import { CallbackRecorder } from "@web/core/action_hook";
import { evaluateBooleanExpr } from "@web/core/py_js/py";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form";

const KNOWLEDGE_RECORDED_FIELD_NAMES = [
    "note",
    "memo",
    "description",
    "comment",
    "narration",
    "additional_note",
    "internal_notes",
    "notes",
];

const KNOWLEDGE_EXCLUDED_MODELS = new Set(["knowledge.article", "res.config.settings"]);

const FormControllerPatch = {
    setup() {
        super.setup(...arguments);
        this.command = useService("command");
        if (!this.dialogContext.inDialog) {
            this.knowledgeCommandsService = useService("knowledgeCommandsService");
            provideKnowledgeContext({
                __knowledgeUpdateCommandsRecordInfo__: new CallbackRecorder(),
            });
            useLayoutEffect(
                () => this._evaluateRecordCandidate(),
                () => [this.model.root.resId],
            );
        }
        this.knowledgeContext = useKnowledgeContext();
    },
    _evaluateRecordCandidate() {
        if (
            KNOWLEDGE_EXCLUDED_MODELS.has(this.props.resModel) ||
            !this.config.breadcrumbs ||
            !this.config.breadcrumbs.length
        ) {
            return;
        }

        const record = this.model.root;
        const fields = this.props.fields;
        const xmlDoc = this.props.archInfo.xmlDoc;
        const commandsRecordInfo = {
            resId: this.model.root.resId,
            resModel: this.props.resModel,
            breadcrumbs: this.knowledgeCommandsService.getBreadcrumbsIdentifier(
                this.config.breadcrumbs || [],
            ),
            canPostMessages: false,
            canAttachFiles: false,
            withHtmlField: false,
            fieldInfo: {},
            xmlDoc: this.props.archInfo.xmlDoc,
        };

        if (this.props.archInfo.xmlDoc.querySelector("chatter")) {
            for (const callback of this.knowledgeContext
                .__knowledgeUpdateCommandsRecordInfo__.callbacks) {
                callback(commandsRecordInfo);
            }
        }

        if (this.props.mode === "readonly" || !this.canEdit) {
            return;
        }

        const defaultFieldNamesSet = new Set(KNOWLEDGE_RECORDED_FIELD_NAMES);
        const fieldNames = KNOWLEDGE_RECORDED_FIELD_NAMES.filter(
            (name) =>
                name in record.activeFields &&
                fields[name].type === "html" &&
                !fields[name].readonly,
        ).concat(
            Object.getOwnPropertyNames(record.activeFields).filter(
                (name) =>
                    !defaultFieldNamesSet.has(name) &&
                    fields[name].type === "html" &&
                    !fields[name].readonly,
            ),
        );

        loopFieldNames: for (const fieldName of fieldNames) {
            if (
                evaluateBooleanExpr(
                    record.activeFields[fieldName].readonly,
                    record.evalContextWithVirtualIds,
                ) ||
                evaluateBooleanExpr(
                    record.activeFields[fieldName].invisible,
                    record.evalContextWithVirtualIds,
                )
            ) {
                continue loopFieldNames;
            }
            const xmlFields = Array.from(
                xmlDoc.querySelectorAll(
                    `field[name="${fieldName}"]:is([widget="html"], :not([widget])`,
                ),
            );
            const xmlFieldsCandidates = xmlFields.filter(
                (xmlField) =>
                    !xmlField.parentElement.closest("field") &&
                    !evaluateBooleanExpr(
                        xmlField.getAttribute("readonly"),
                        record.evalContextWithVirtualIds,
                    ) &&
                    !evaluateBooleanExpr(
                        xmlField.getAttribute("invisible"),
                        record.evalContextWithVirtualIds,
                    ),
            );
            loopXmlFieldsCandidates: for (const xmlField of xmlFieldsCandidates) {
                const xmlFieldParent = xmlField.parentElement;
                let xmlInvisibleParent = xmlFieldParent.closest("[invisible]");
                while (xmlInvisibleParent) {
                    const invisibleParentModifier =
                        xmlInvisibleParent.getAttribute("invisible");
                    if (
                        evaluateBooleanExpr(
                            invisibleParentModifier,
                            record.evalContextWithVirtualIds,
                        )
                    ) {
                        continue loopXmlFieldsCandidates;
                    }
                    xmlInvisibleParent =
                        xmlInvisibleParent.parentElement &&
                        xmlInvisibleParent.parentElement.closest("[invisible]");
                }
                const page = xmlField.closest("page");
                const pageName = page ? page.getAttribute("name") : undefined;
                if (!page || pageName) {
                    commandsRecordInfo.fieldInfo = {
                        name: fieldName,
                        string: fields[fieldName].string,
                        pageName: pageName,
                    };
                    break loopFieldNames;
                }
            }
        }
        if (commandsRecordInfo.fieldInfo.name) {
            commandsRecordInfo.withHtmlField = true;
        }
        if (
            this.knowledgeCommandsService.isRecordCompatibleWithMacro(
                commandsRecordInfo,
            )
        ) {
            this.knowledgeCommandsService.setCommandsRecordInfo(commandsRecordInfo);
        }
    },
    async onClickSearchKnowledgeArticle() {
        if ((await this.model.root.isDirty()) || this.model.root.isNew) {
            const saved = await this.model.root.save();
            if (!saved) {
                return;
            }
        }
        this.command.openMainPalette({ searchValue: "?" });
    },
};

patch(FormController.prototype, FormControllerPatch);
