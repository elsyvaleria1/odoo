/** @odoo-module native */
import { registry } from "@web/core/registry";

export const knowledgeCommandsService = {
    start() {
        let commandsRecordInfo = null;

        /**
         * Register data related to a potential record candidate for Knowledge
         * macros.
         *
         * @param {Object|null} recordInfo if null is given, the
         *        commandsRecordInfo values are reset.
         * @param {number} [recordInfo.resId] id of the target record
         * @param {string} [recordInfo.resModel] model name of the target record
         * @param {Array} [recordInfo.breadcrumbs] array of breadcrumbs objects
         *                {jsId, name} leading to the target record
         * @param {boolean} [recordInfo.canPostMessages] target record
         *                  has a chatter and user can post messages
         * @param {boolean} [recordInfo.canAttachFiles] target record
         *                  has a chatter and user can attach files
         * @param {boolean} [recordInfo.withHtmlField] target record has a
         *                  targeted html field @see FormControllerPatch
         * @param {Object} [recordInfo.fieldInfo] info object for the html field
         *                 {string, name, pageName}
         * @param {XMLDocument} [recordInfo.xmlDoc] xml document (arch of the
         *                      form view of the target record)
         */
        function setCommandsRecordInfo(recordInfo) {
            commandsRecordInfo = recordInfo;
        }

        function getCommandsRecordInfo() {
            return commandsRecordInfo;
        }

        /**
         * Copy some actionService breadcrumbs properties used as an identifier
         * for a recordInfo object.
         *
         * @param {Breadcrumbs} breadcrumbs from the @see actionService
         * @returns {Array[Object]} breadcrumbs identifier containing the jsId
         *                          and name.
         */
        function getBreadcrumbsIdentifier(breadcrumbs) {
            return breadcrumbs.map((breadcrumb) => ({
                jsId: breadcrumb.jsId,
                name: breadcrumb.name,
            }));
        }

        /**
         * Evaluate if a record candidate is usable for at least one macro in
         * Knowledge.
         *
         * @param {Object} recordInfo refer to @see setCommandsRecordInfo
         */
        function isRecordCompatibleWithMacro(recordInfo) {
            return (
                recordInfo.canAttachFiles ||
                recordInfo.canPostMessages ||
                recordInfo.withHtmlField
            );
        }

        /**
         * Compare the provided breadcrumbs identifier with a previously
         * registered recordInfo's and unregister the recordInfo if the
         * registered breadcrumbs are not included at the start of the provided
         * breadcrumbs.
         *
         * @param {Breadcrumbs} breadcrumbs from the @see actionService
         */
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
         * @param {HTMLElement} embeddedBlueprint element to be inserted in a
         *                      html field
         * @param {string} model model name of the target record
         * @param {string} field field name of the target record
         * @param {integer} resId id of the target record
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
