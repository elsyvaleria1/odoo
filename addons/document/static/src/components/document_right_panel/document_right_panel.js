/** @odoo-module native */
import { DocumentsDetailsPanel } from "@document/components/document_details_panel/document_details_panel";
import { DocumentsChatter } from "@document/views/chatter/document_chatter";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export class DocumentsRightPanel extends Component {
    static template = "document.DocumentsViews.RightPanel";
    static props = { nbViewItems: t.number() };
    static components = {
        Chatter: DocumentsChatter,
        DocumentsDetailsPanel,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.documentService = useService("document.document");
        this.ui = useService("ui");
        this.state = proxy(this.documentService.rightPanelReactive);
        this.panelRef = elementRef();
        // opened, not mounted open: the view reopening on it scrolls nowhere
        let opened = this.state.visible;
        useLayoutEffect(
            (panel) => {
                const wasOpen = opened;
                opened = Boolean(panel);
                if (!panel || wasOpen) {
                    return;
                }
                return this.isMobile
                    ? this._scrollToChatterOnceShown(panel)
                    : this._scrollSelectionIntoView(panel);
            },
            () => [this.panelRef.el],
        );
    }

    get isMobile() {
        return this.ui.isSmall;
    }

    get panelDisabled() {
        return (
            !this.state.focusedRecord ||
            !this.state.focusedRecord.data ||
            typeof this.state.focusedRecord.data.id !== "number"
        );
    }

    /**
     * The panel narrows the view: the selected document is brought back in sight.
     *
     * @param {HTMLElement} panel
     */
    _scrollSelectionIntoView(panel) {
        const selected = panel
            .closest(".o_documents_content")
            ?.querySelector(
                ".o_kanban_record.o_record_selected, .o_data_row.o_data_row_selected",
            );
        selected?.scrollIntoView({
            behavior: "instant",
            block: selected.classList.contains("o_data_row") ? "center" : "start",
        });
    }

    /**
     * On a small screen the panel opens below the view: shown, its chatter is
     * scrolled to, once it has rendered.
     *
     * @param {HTMLElement} panel
     * @returns {() => void} what stops waiting
     */
    _scrollToChatterOnceShown(panel) {
        const scroll = () => {
            const thread = panel.querySelector(".o-mail-Thread");
            if (thread) {
                thread.scrollIntoView({ behavior: "smooth" });
            }
            return Boolean(thread);
        };
        if (scroll()) {
            return () => {};
        }
        const observer = new MutationObserver(() => scroll() && observer.disconnect());
        observer.observe(panel, { childList: true, subtree: true });
        return () => observer.disconnect();
    }
}
