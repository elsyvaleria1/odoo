/** @odoo-module native */
import { useBuilderContext } from "@html_builder/core/builder_context";
import { getSnippetName, isElementInViewport } from "@html_builder/utils/utils";
import {
    Component,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
} from "@odoo/owl";

/**
 * @typedef {((snippetEl: HTMLElement) => void)[]} on_reveal_target_handlers
 */

export class InvisibleElementsPanel extends Component {
    static template = "html_builder.InvisibleElementsPanel";
    static props = { invisibleEls: t.array(), invisibleSelector: t.string() };
    props = useProps(this.constructor.props);

    setup() {
        this.builderContext = useBuilderContext();
        this.state = proxy({ invisibleEntries: null });

        onWillStart(() => this.updateInvisibleElementsPanel(this.props.invisibleEls));

        onWillUpdateProps((nextProps) => {
            const { invisibleEls, invisibleSelector } = nextProps;
            this.updateInvisibleElementsPanel(invisibleEls, invisibleSelector);
        });
    }

    get shared() {
        return this.builderContext.editor.shared;
    }

    updateInvisibleElementsPanel(
        invisibleEls,
        invisibleSelector = this.props.invisibleSelector,
    ) {
        const descendantPerSnippet = new Map();
        const rootInvisibleSnippetEls = invisibleEls.filter((invisibleSnippetEl) => {
            const ancestorInvisibleEl =
                invisibleSnippetEl.parentElement.closest(invisibleSelector);
            if (!ancestorInvisibleEl) {
                return true;
            }
            const descendantSnippets =
                descendantPerSnippet.get(ancestorInvisibleEl) || [];
            descendantPerSnippet.set(ancestorInvisibleEl, [
                ...descendantSnippets,
                invisibleSnippetEl,
            ]);
            return false;
        });
        const createInvisibleEntries = (snippetEls, parentEl = null) =>
            snippetEls.map((snippetEl) => {
                const descendantSnippetEls = descendantPerSnippet.get(snippetEl);
                const invisibleElement = {
                    snippetEl: snippetEl,
                    name: getSnippetName(snippetEl),
                    isRootParent: !parentEl && !!descendantSnippetEls,
                    isDescendant: !!parentEl,
                    isVisible: snippetEl.dataset.invisible !== "1",
                    children: [],
                    parentEl,
                };
                if (descendantSnippetEls) {
                    invisibleElement.children = createInvisibleEntries(
                        descendantSnippetEls,
                        invisibleElement,
                    );
                }
                return invisibleElement;
            });
        this.state.invisibleEntries = createInvisibleEntries(rootInvisibleSnippetEls);
    }

    toggleElementVisibility(invisibleEntry) {
        const snippetEl = invisibleEntry.snippetEl;
        if (snippetEl.dataset.invisible !== "1") {
            this.shared.visibility.toggleTargetVisibility(snippetEl, false);
            this.shared.builderOptions.deactivateContainers();
        } else {
            this.shared.visibility.toggleTargetVisibility(snippetEl, true);
            this.builderContext.editor.dispatchTo(
                "on_reveal_target_handlers",
                snippetEl,
            );
            this.shared.builderOptions.updateContainers(snippetEl);
            if (!isElementInViewport(snippetEl) && !snippetEl.matches(".s_popup")) {
                snippetEl.scrollIntoView({ behavior: "smooth", block: "start" });
            }
        }
        this.shared.disableSnippets.disableUndroppableSnippets();
        this.updateInvisibleElementsPanel(this.props.invisibleEls);
    }
}
