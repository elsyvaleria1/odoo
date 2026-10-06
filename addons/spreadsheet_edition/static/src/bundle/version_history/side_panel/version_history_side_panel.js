/** @odoo-module native */
import { components } from "@odoo/o-spreadsheet";
import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

import { VersionHistoryItem } from "./version_history_item.js";

const { Section } = components;

export class VersionHistorySidePanel extends Component {
    static template = "spreadsheet_edition.VersionHistory";
    static props = {
        onCloseSidePanel: t.function(),
        getRevisions: t.function(),
        forkHistory: t.function(),
        restoreRevision: t.function(),
        renameRevision: t.function(),
        loadToRevision: t.function(),
        getCurrentRevisionId: t.function(),
        getLocale: t.function(),
    };
    static components = {
        VersionHistoryItem,
        Section,
    };
    props = useProps(this.constructor.props);

    revNbr = 50;

    setup() {
        this.containerRef = elementRef();

        this.state = proxy({
            currentRevisionId: this.props.getCurrentRevisionId(),
            isEditingName: false,
            loaded: this.revNbr,
        });

        useLayoutEffect(() => {
            this.focus();
        });
    }

    get revisions() {
        return this.props.getRevisions();
    }

    get loadedRevisions() {
        return this.revisions.slice(0, this.state.loaded);
    }

    focus() {
        this.containerRef.el?.focus();
    }

    onRevisionClick(revisionId) {
        this.state.currentRevisionId = revisionId;
        this.props.loadToRevision(revisionId);
    }

    onLoadMoreClicked() {
        this.state.loaded = Math.min(
            this.state.loaded + this.revNbr,
            this.revisions.length,
        );
    }

    onKeyDown(ev) {
        let increment = 0;
        switch (ev.key) {
            case "ArrowUp":
                increment = -1;
                ev.preventDefault();
                break;
            case "ArrowDown":
                increment = 1;
                ev.preventDefault();
                break;
        }
        if (increment) {
            const revisions = this.loadedRevisions;
            const currentIndex = revisions.findIndex(
                (r) => r.nextRevisionId === this.state.currentRevisionId,
            );
            const nextIndex = Math.max(
                0,
                Math.min(revisions.length - 1, currentIndex + increment),
            );
            if (nextIndex !== currentIndex) {
                this.state.currentRevisionId = revisions[nextIndex].nextRevisionId;
                this.props.loadToRevision(this.state.currentRevisionId);
            }
        }
    }
}
