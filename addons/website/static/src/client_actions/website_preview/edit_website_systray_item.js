/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useBus, useService } from "@web/core/utils/hooks";

const websiteSystrayRegistry = registry.category("website_systray");

const log = makeLogger("website.systray.edit_website");

export class EditWebsiteSystrayItem extends Component {
    static template = "website.EditWebsiteSystrayItem";
    static props = {
        onNewPage: t.function(),
        onEditPage: t.function(),
        iframeEl: t.instanceOf(HTMLElement),
    };
    static components = {
        Dropdown,
        DropdownItem,
    };
    props = useProps(this.constructor.props);

    setup() {
        useLifecycleLog(log);
        this.websiteService = useService("website");
        this.notification = useService("notification");
        this.websiteContext = proxy(this.websiteService.context);
        useBus(websiteSystrayRegistry, "CONTENT-UPDATED", () =>
            this.checkPendingTranslations(),
        );
        this.isEnteringTranslateMode = false;
        this.pendingTranslationsByPath = new Map();
        this.translationCheckSeq = 0;
    }

    onClickEditPage() {
        log.logic("onClickEditPage");
        this.pendingTranslationsByPath.clear();
        this.websiteContext.edition = true;
        this.props.onEditPage();
    }

    onEditDropdownClick() {
        this.closeNotification?.();
    }

    get currentWebsiteInfo() {
        return this.websiteService.currentWebsite?.metadata;
    }

    get translatable() {
        return this.websiteService.currentWebsite?.metadata.translatable;
    }

    async attemptStartTranslate() {
        if (this.websiteService.isRestrictedEditor && !this.websiteService.isDesigner) {
            const pageModelAndId =
                this.websiteService.currentWebsite.metadata.mainObject;
            const recordsOnPage = pageModelAndId
                ? { [pageModelAndId.model]: pageModelAndId.id }
                : {};
            const endScan = log.perf("attemptStartTranslate scan records");
            const otherRecordEls = this.props.iframeEl.contentDocument.querySelectorAll(
                "[data-res-model][data-res-id]:not([data-res-model='ir.ui.view']), [data-oe-model][data-oe-id]:not([data-oe-model='ir.ui.view'])",
            );
            for (const el of otherRecordEls) {
                const model = el.dataset.resModel || el.dataset.oeModel;
                if (!recordsOnPage[model]) {
                    recordsOnPage[model] = parseInt(
                        el.dataset.resId || el.dataset.oeId,
                    );
                }
            }
            endScan(() => ({ elements: otherRecordEls.length }));
            const endCheck = log.perf("check_can_modify_any", () => ({
                models: Object.keys(recordsOnPage),
            }));
            await rpc("/website/check_can_modify_any", {
                records: Object.entries(recordsOnPage).map(([res_model, res_id]) => ({
                    res_model,
                    res_id,
                })),
            });
            endCheck();
        }
        this.startTranslate();
    }

    getLocation() {
        return this.websiteService.contentWindow.location;
    }

    editFromTranslate() {
        this.pendingTranslationsByPath.clear();
        const { pathname, search, hash } = this.getLocation();
        const languagePrefix = `${pathname}/`.indexOf("/", 1);
        const defaultLanguagePathname = pathname.substring(languagePrefix);
        log.logic("editFromTranslate", { pathname, defaultLanguagePathname });
        this.websiteService.goToWebsite({
            path: defaultLanguagePathname + search + hash,
            lang: "default",
            edition: true,
        });
    }

    startTranslate() {
        log.logic("startTranslate");
        this.pendingTranslationsByPath.clear();
        this.isEnteringTranslateMode = true;
        const { pathname, search, hash } = this.getLocation();
        const searchParams = new URLSearchParams(search);
        searchParams.set("edit_translations", "1");
        this.websiteService.goToWebsite({
            path: pathname + `?${searchParams.toString() + hash}`,
            translation: true,
        });
    }

    async checkPendingTranslations() {
        const entering = this.isEnteringTranslateMode;
        this.isEnteringTranslateMode = false;
        log.logic("checkPendingTranslations", () => ({
            translatable: Boolean(this.translatable),
            entering,
        }));
        if (!this.translatable || entering) {
            return;
        }
        const { pathname, search } = this.getLocation();
        const searchParams = new URLSearchParams(search);
        searchParams.set("edit_translations", "1");
        const path = `${pathname}?${searchParams}`;
        const seq = ++this.translationCheckSeq;
        let pending = this.pendingTranslationsByPath.get(path);
        if (pending === undefined) {
            try {
                pending = await this.fetchPendingTranslations(path);
            } catch (error) {
                log.logic("checkPendingTranslations failed", () => ({
                    path,
                    error: String(error),
                }));
                return;
            }
            this.pendingTranslationsByPath.set(path, pending);
        }
        if (seq !== this.translationCheckSeq) {
            log.logic("checkPendingTranslations: stale answer dropped", { path });
            return;
        }
        this.closeNotification?.();
        this.closeNotification = pending
            ? this.notification.add(
                  _t(
                      'Click on "Edit/Translate" to apply changes made on default language.',
                  ),
                  { type: "info" },
              )
            : undefined;
    }

    async fetchPendingTranslations(path) {
        const endFetch = log.perf("checkPendingTranslations fetch+parse", { path });
        const response = await fetch(path);
        if (!response.ok) {
            throw new Error(`${response.status} ${response.statusText}`);
        }
        const html = await response.text();
        const doc = new DOMParser().parseFromString(html, "text/html");
        endFetch(() => ({ bytes: html.length }));
        return Boolean(doc.querySelector("#wrap .o_delay_translation"));
    }
}
