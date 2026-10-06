// @ts-check
/** @odoo-module native */
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

const log = makeLogger("mail.debug_manager");
/**
 * @param {Object} params
 * @param {import("@odoo/owl").Component} [params.component]
 * @param {import("@web/env").OdooEnv} params.env
 * @returns {import("registries").DebugRegistryItemShapeResult}
 */
export function manageMessages({ component, env }) {
    const resId = component?.model.root.resId;
    if (!resId) {
        return null;
    }
    const description = _t("Messages");
    return {
        type: "item",
        description,
        callback: async () => {
            const model = await env.services.orm.call(
                component.props.resModel,
                "mail_get_reference_model_name",
            );
            log.logic("manageMessages", () => ({
                resModel: component.props.resModel,
                model,
                resId,
            }));
            env.services.action.doAction({
                res_model: "mail.message",
                name: description,
                views: [
                    [false, "list"],
                    [false, "form"],
                ],
                type: "ir.actions.act_window",
                domain: [
                    ["res_id", "=", resId],
                    ["model", "=", model],
                ],
                context: {
                    default_res_model: model,
                    default_res_id: resId,
                },
            });
        },
        sequence: 130,
        section: "record",
    };
}

registry.category("debug").category("form").add("mail.manageMessages", manageMessages);
