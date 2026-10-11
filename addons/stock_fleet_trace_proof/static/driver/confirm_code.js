const ROUTE = "/stock_fleet_trace/driver/confirm_code";

function confirmCode(kind, stop, api) {
    if (kind !== "deliver" || !stop) {
        return null;
    }
    const { h, fmt, rpc, terms: T } = api;
    const status = h("p", { class: "sft-muted" });
    const input = h("input", {
        type: "text",
        class: "sft-input",
        inputmode: "numeric",
        autocomplete: "one-time-code",
        maxlength: 6,
    });
    let challenge = null;
    const check = h(
        "button",
        {
            type: "button",
            class: "sft-btn sft-btn-primary",
            hidden: true,
            onclick: async () => {
                let result;
                try {
                    result = await rpc(`${ROUTE}/prove`, {
                        picking_id: stop.picking_id,
                        token: challenge.token,
                        method: challenge.method,
                        code: input.value.trim(),
                    });
                } catch (error) {
                    api.showMessage("warn", error.message);
                    return;
                }
                if (result.error) {
                    api.showMessage("warn", result.error);
                    return;
                }
                box.replaceChildren(h("p", { class: "sft-ok" }, T.confirm_code_done));
            },
        },
        T.confirm_code_check,
    );
    const send = h(
        "button",
        {
            type: "button",
            class: "sft-btn sft-btn-light",
            onclick: async () => {
                if (!api.isOnline()) {
                    api.showMessage("warn", T.confirm_code_offline);
                    return;
                }
                try {
                    challenge = await rpc(`${ROUTE}/issue`, {
                        picking_id: stop.picking_id,
                    });
                } catch (error) {
                    api.showMessage("warn", error.message);
                    return;
                }
                status.textContent = fmt(T.confirm_code_sent, {
                    sent_to: challenge.sent_to,
                });
                input.hidden = false;
                check.hidden = false;
            },
        },
        T.confirm_code_send,
    );
    input.hidden = true;
    input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") {
            ev.preventDefault();
            check.click();
        }
    });
    const box = h("div", {}, send, status, input, check);
    return api.field(T.confirm_code, box);
}

window.sftDriverPlugins = window.sftDriverPlugins || [];
window.sftDriverPlugins.push({ actionFields: confirmCode });
