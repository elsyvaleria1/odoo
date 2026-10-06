/** @odoo-module native */
import {
    provideChildKnowledgeContext,
    useKnowledgeContext,
} from "@knowledge/js/knowledge_context";
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useRecordObserver } from "@web/fields/hooks/record_observer";

import { KnowledgeSidebarRow } from "./sidebar_row.js";

/**
 * This file defines the different sections used in the sidebar.
 * Each section is responsible of displaying an array of root articles and
 * their children.
 */

export class KnowledgeSidebarSection extends Component {
    static template = "";
    static props = {
        rootIds: t.array(),
        unfoldedIds: t.instanceOf(Set),
        record: t.object(),
    };
    static components = {
        KnowledgeSidebarRow,
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        const foldedSections = JSON.parse(
            browser.localStorage.getItem("knowledge.folded.sections") ?? "{}",
        );
        this.state = proxy({
            isFolded:
                foldedSections[this.getSectionIdentifier()] ||
                this.props.rootIds.length === 0,
        });

        // Unfold the section of the current article:
        useRecordObserver((record) => {
            if (record.data.category === this.getSectionIdentifier()) {
                this.state.isFolded = false;
            }
        });

        onWillStart(async () => {
            this.isInternalUser = await user.hasGroup("base.group_user");
            this.canCreateArticle = await user.checkAccessRight(
                "knowledge.article",
                "create",
            );
        });
    }

    toggleSidebarSection() {
        this.state.isFolded = !this.state.isFolded;
        // Persist the new folding state in local storage:
        const foldedSections = JSON.parse(
            browser.localStorage.getItem("knowledge.folded.sections") ?? "{}",
        );
        foldedSections[this.getSectionIdentifier()] = this.state.isFolded;
        browser.localStorage.setItem(
            "knowledge.folded.sections",
            JSON.stringify(foldedSections),
        );
    }
}

export class KnowledgeSidebarFavoriteSection extends KnowledgeSidebarSection {
    static template = "knowledge.SidebarFavoriteSection";

    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();

        // (Un)fold in the favorite tree by default.
        provideChildKnowledgeContext({
            fold: (id) => this.knowledgeContext.fold(id, true),
            unfold: (id) => this.knowledgeContext.unfold(id, true),
        });
    }

    getSectionIdentifier() {
        return "favorites";
    }
}

export class KnowledgeSidebarWorkspaceSection extends KnowledgeSidebarSection {
    static template = "knowledge.SidebarWorkspaceSection";

    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
        this.command = useService("command");
    }

    createRoot() {
        this.knowledgeContext.createArticle("workspace");
    }

    searchHiddenArticle() {
        this.command.openMainPalette({ searchValue: "$" });
    }

    getSectionIdentifier() {
        return "workspace";
    }
}

export class KnowledgeSidebarSharedSection extends KnowledgeSidebarSection {
    static template = "knowledge.SidebarSharedSection";

    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
    }

    getSectionIdentifier() {
        return "shared";
    }
}

export class KnowledgeSidebarPrivateSection extends KnowledgeSidebarSection {
    static template = "knowledge.SidebarPrivateSection";

    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
    }

    createRoot() {
        this.knowledgeContext.createArticle("private");
    }

    getSectionIdentifier() {
        return "private";
    }
}
