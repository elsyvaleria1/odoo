/** @odoo-module native */
import { registry } from "@web/core/registry";

export const knowledgeCommandsService = {
    start() {
        let commandsRecordInfo = null;

        /**
         * @param {Object|null} recordInfo
         * @param {number} [recordInfo.resId]
         * @param {string} [recordInfo.resModel]
         * @param {Array} [recordInfo.breadcrumbs]
         * @param {boolean} [recordInfo.canPostMessages]
         * @param {boolean} [recordInfo.canAttachFiles]
         * @param {boolean} [recordInfo.withHtmlField]
         * @param {Object} [recordInfo.fieldInfo]
         * @param {XMLDocument} [recordInfo.xmlDoc]
         */
        function setCommandsRecordInfo(recordInfo) {
            commandsRecordInfo = recordInfo;
        }

        function getCommandsRecordInfo() {
            return commandsRecordInfo;
        }

        /**
         * @param {Breadcrumbs} breadcrumbs
         * @returns {Array[Object]}
         */
        function getBreadcrumbsIdentifier(breadcrumbs) {
            return breadcrumbs.map((breadcrumb) => ({
                jsId: breadcrumb.jsId,
                name: breadcrumb.name,
            }));
        }

        /** @param {Object} recordInfo */
        function isRecordCompatibleWithMacro(recordInfo) {
            return (
                recordInfo.canAttachFiles ||
                recordInfo.canPostMessages ||
                recordInfo.withHtmlField
            );
        }

        /** @param {Breadcrumbs} breadcrumbs */
        function unregisterCommandsRecordInfo(breadcrumbs) {
            const commandsRecordInfo = getCommandsRecordInfo();
            if (!commandsRecordInfo) {
                return;
            }
            breadcrumbs = getBreadcrumbsIdentifier(breadcrumbs);
            if (
                breadcrumbs.length <= commandsRecordInfo.breadcrumbs.length ||
                breadcrumbs[commandsRecordInfo.breadcrumbs.length - 1].jsId !==
                    commandsRecordInfo.breadcrumbs.at(-1).jsId
            ) {
                setCommandsRecordInfo(null);
            }
        }

        const pendingEmbeddedBlueprints = {};

        /**
         * @param {Object}
         * @param {HTMLElement} embeddedBlueprint
         * @param {string} model
         * @param {string} field
         * @param {integer} resId
         */
        function setPendingEmbeddedBlueprint({
            embeddedBlueprint,
            model,
            field,
            resId,
        }) {
            if (!(model in pendingEmbeddedBlueprints)) {
                pendingEmbeddedBlueprints[model] = {};
            }
            if (!(field in pendingEmbeddedBlueprints[model])) {
                pendingEmbeddedBlueprints[model][field] = {};
            }
            pendingEmbeddedBlueprints[model][field][resId] = embeddedBlueprint;
        }

        function popPendingEmbeddedBlueprint({ model, field, resId }) {
            if (
                model in pendingEmbeddedBlueprints &&
                field in pendingEmbeddedBlueprints[model]
            ) {
                const pendingEmbeddedBlueprint =
                    pendingEmbeddedBlueprints[model][field][resId];
                delete pendingEmbeddedBlueprints[model][field][resId];
                return pendingEmbeddedBlueprint;
            }
        }

        const knowledgeCommandsService = {
            setCommandsRecordInfo,
            getCommandsRecordInfo,
            getBreadcrumbsIdentifier,
            isRecordCompatibleWithMacro,
            unregisterCommandsRecordInfo,
            setPendingEmbeddedBlueprint,
            popPendingEmbeddedBlueprint,
        };
        return knowledgeCommandsService;
    },
};

registry.category("services").add("knowledgeCommandsService", knowledgeCommandsService);
