/** @odoo-module native */
import { resolveRecipientPartners } from "@mail/core/common/full_composer_hook";
import { browser } from "@web/core/browser/browser";
import {
    formatDate,
    formatDateTime,
    isDateOrDateTimeValue,
    isDateTimeValue,
    parseISO,
} from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

export const aiChatLauncherService = {
    dependencies: ["mail.store", "orm", "action"],
    start(env, services) {
        const actionService = services["action"];
        const mailStore = services["mail.store"];

        async function openFullComposer(msgType, resModel, resId, content) {
            let allRecipients = [];
            const thread = await mailStore.Thread.getOrFetch({
                model: resModel,
                id: resId,
            });
            if (msgType === "message") {
                allRecipients = await resolveRecipientPartners(
                    mailStore,
                    thread,
                    thread.allRecipients,
                );
            }
            actionService.doAction(
                {
                    name: msgType === "message" ? _t("Send Message") : _t("Log Note"),
                    res_model: "wizard.mail.message.send",
                    target: "new",
                    type: "ir.actions.act_window",
                    view_id: false,
                    view_mode: "form",
                    views: [[false, "form"]],
                    context: {
                        clicked_on_full_composer: true,
                        default_body: content,
                        default_model: resModel,
                        default_partner_ids: allRecipients.map(
                            (recipient) => recipient.partner_id,
                        ),
                        default_res_ids: [resId],
                        default_subtype_xmlid:
                            msgType === "message" ? "mail.mt_comment" : "mail.mt_note",
                    },
                },
                { onClose: () => thread?.fetchNewMessages() },
            );
        }

        return {
            async launchAIChat({
                callerComponentName,
                recordModel,
                recordId,
                channelTitle,
                aiSpecialActions,
                aiChatSourceId,
                originalRecordData = null,
                originalRecordFields = null,
                textSelection = null,
            }) {
                let frontEndRecordInfo;
                if (
                    [
                        "html_field_record",
                        "html_field_text_select",
                        "chatter_ai_button",
                    ].includes(callerComponentName)
                ) {
                    frontEndRecordInfo = this.recordDataToContextJSON(
                        originalRecordData,
                        originalRecordFields,
                    );
                }
                services["mail.store"].aiInsertButtonTarget = aiChatSourceId;

                const { ai_channel_id, data, prompts, model_has_thread } =
                    await services.orm.call(
                        "discuss.channel",
                        "create_ai_draft_channel",
                        [
                            callerComponentName,
                            channelTitle,
                            recordModel,
                            recordId,
                            frontEndRecordInfo,
                            textSelection,
                        ],
                    );

                services["mail.store"].insert(data);
                const thread = await services["mail.store"].Thread.getOrFetch({
                    model: "discuss.channel",
                    id: Number(ai_channel_id),
                });
                browser.localStorage.setItem(
                    "ai.thread.prompt_buttons.".concat(thread.id),
                    JSON.stringify(prompts),
                );

                if (callerComponentName === "chatter_ai_button" && model_has_thread) {
                    aiSpecialActions = {
                        ...aiSpecialActions,
                        sendMessage: (content) =>
                            openFullComposer("message", recordModel, recordId, content),
                        logNote: (content) =>
                            openFullComposer("note", recordModel, recordId, content),
                    };
                }
                thread.ai_prompt_buttons = prompts;
                thread.aiSpecialActions = aiSpecialActions;
                thread.aiChatSource = aiChatSourceId;
                thread.open({ focus: true });
                thread.openChatWindow();
            },
            /**
             * Converts record data to a JSON-serialisable plain object, so we can
             * pass it to the AI record's context.
             * @param {Object} recordData the record values, keyed by field name
             * @param {Object} fieldsInfo the field descriptions, keyed by field name
             * @returns {Object} the formatted record values
             */
            recordDataToContextJSON(recordData, fieldsInfo) {
                const result = {};

                for (const fieldName in recordData) {
                    if (!Object.hasOwn(recordData, fieldName)) {
                        continue;
                    }
                    const fieldValue = recordData[fieldName];
                    const fieldInfo = fieldsInfo[fieldName] || {};
                    if (fieldInfo.type === "binary") {
                        continue;
                    }
                    if (
                        ["many2one", "many2many", "one2many"].includes(fieldInfo.type)
                    ) {
                        if (
                            fieldValue &&
                            fieldValue.records &&
                            fieldValue.records.length > 50
                        ) {
                            continue;
                        }
                        switch (fieldInfo.type) {
                            case "many2one":
                                result[fieldName] = fieldValue
                                    ? fieldValue.display_name || fieldValue.name
                                    : null;
                                break;
                            case "many2many":
                            case "one2many":
                                if (fieldValue && fieldValue.records) {
                                    result[fieldName] = fieldValue.records.map(
                                        (record) =>
                                            record.data.display_name ||
                                            record.data.name,
                                    );
                                } else {
                                    result[fieldName] = [];
                                }
                                break;
                        }
                    } else if (fieldInfo.type === "date" && fieldValue) {
                        const date = isDateOrDateTimeValue(fieldValue)
                            ? fieldValue
                            : parseISO(fieldValue);
                        result[fieldName] = date ? formatDate(date) : fieldValue;
                    } else if (fieldInfo.type === "datetime" && fieldValue) {
                        const datetime = isDateTimeValue(fieldValue)
                            ? fieldValue
                            : parseISO(fieldValue);
                        result[fieldName] = datetime
                            ? formatDateTime(datetime)
                            : fieldValue;
                    } else {
                        result[fieldName] = fieldValue;
                    }
                }
                return result;
            },
        };
    },
};

registry.category("services").add("aiChatLauncher", aiChatLauncherService);
