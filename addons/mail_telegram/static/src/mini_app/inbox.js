(() => {
    "use strict";

    const tg = window.Telegram.WebApp;
    const botId = Number(document.body.dataset.botId);
    const $ = (id) => document.getElementById(id);
    const state = { tab: "notifications", data: null, thread: null, labels: {} };

    async function call(path, params = {}) {
        const response = await fetch(`/telegram/inbox/${path}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "call",
                params: { bot_id: botId, init_data: tg.initData, ...params },
            }),
        });
        const payload = await response.json();
        if (payload.error) {
            throw new Error(payload.error.message || "error");
        }
        if (payload.result && payload.result.error) {
            throw new Error(payload.result.error);
        }
        return payload.result;
    }

    function showError(error) {
        const node = $("error");
        node.textContent =
            error.message === "auth"
                ? state.labels.auth || "…"
                : state.labels.error || "…";
        node.hidden = false;
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) {
            node.className = className;
        }
        if (text) {
            node.textContent = text;
        }
        return node;
    }

    function when(iso) {
        return iso
            ? new Date(`${iso}Z`).toLocaleString([], {
                  dateStyle: "short",
                  timeStyle: "short",
              })
            : "";
    }

    function renderList() {
        const items = $("items");
        items.replaceChildren();
        for (const tab of document.querySelectorAll(".tab")) {
            tab.classList.toggle("active", tab.dataset.tab === state.tab);
            tab.textContent = state.labels[tab.dataset.tab] || "";
        }
        const entries = state.data[state.tab];
        for (const entry of entries) {
            const item = el("button", "item");
            item.type = "button";
            if (state.tab === "notifications") {
                item.append(
                    el("span", "item-title", entry.thread || entry.author),
                    el("span", "item-meta", `${entry.author} · ${when(entry.date)}`),
                    el("span", "item-body", entry.body),
                );
                item.addEventListener("click", () =>
                    openThread(entry.model, entry.res_id, { message_ids: [entry.id] }),
                );
            } else {
                const title = el("span", "item-title", entry.name);
                title.append(el("span", "badge", String(entry.unread)));
                item.append(title);
                if (entry.preview) {
                    item.append(
                        el(
                            "span",
                            "item-body",
                            `${entry.preview.author}: ${entry.preview.body}`,
                        ),
                    );
                }
                item.addEventListener("click", () =>
                    openThread("discuss.channel", entry.id, { channel_id: entry.id }),
                );
            }
            items.append(item);
        }
        const empty = $("empty");
        empty.textContent = state.labels[`empty_${state.tab}`];
        empty.hidden = entries.length > 0;
    }

    function renderThread() {
        const thread = state.thread;
        $("thread-title").textContent = thread.title;
        const messages = $("messages");
        messages.replaceChildren();
        for (const message of thread.messages) {
            const bubble = el(
                "div",
                `message${message.own ? " own" : ""}${message.note ? " note" : ""}`,
            );
            bubble.append(
                el("span", "message-meta", `${message.author} · ${when(message.date)}`),
                el("span", "message-body", message.body),
            );
            messages.append(bubble);
        }
        messages.scrollTop = messages.scrollHeight;
        $("note").hidden = !thread.can_note;
    }

    function show(view) {
        for (const section of document.querySelectorAll("[data-view]")) {
            section.hidden = section.dataset.view !== view;
        }
        if (view === "thread") {
            tg.BackButton.show();
        } else {
            tg.BackButton.hide();
        }
    }

    async function loadOverview() {
        state.data = await call("overview");
        state.labels = state.data.labels;
        $("composer-text").placeholder = state.labels.reply;
        $("send").textContent = state.labels.send;
        $("note").textContent = state.labels.note;
        $("open").textContent = state.labels.open;
        renderList();
        show("list");
    }

    async function openThread(model, resId, read) {
        try {
            state.thread = {
                model,
                res_id: resId,
                ...(await call("thread", { model, res_id: resId })),
            };
            renderThread();
            show("thread");
            await call("read", read);
        } catch (error) {
            showError(error);
        }
    }

    async function post(note) {
        const text = $("composer-text").value.trim();
        if (!text || !state.thread) {
            return;
        }
        try {
            const message = await call("post", {
                model: state.thread.model,
                res_id: state.thread.res_id,
                text,
                note,
            });
            $("composer-text").value = "";
            state.thread.messages.push(message);
            renderThread();
        } catch (error) {
            showError(error);
        }
    }

    for (const tab of document.querySelectorAll(".tab")) {
        tab.addEventListener("click", () => {
            state.tab = tab.dataset.tab;
            renderList();
        });
    }
    $("composer").addEventListener("submit", (event) => {
        event.preventDefault();
        post(false);
    });
    $("note").addEventListener("click", () => post(true));
    $("open").addEventListener(
        "click",
        () => state.thread && tg.openLink(state.thread.url),
    );
    tg.BackButton.onClick(() => loadOverview().catch(showError));
    tg.ready();
    tg.expand();
    loadOverview().catch(showError);
})();
