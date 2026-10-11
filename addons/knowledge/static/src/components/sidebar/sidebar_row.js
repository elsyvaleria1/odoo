/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import {
    Component,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";

export class KnowledgeSidebarRow extends Component {
    static props = {
        article: t.object(),
        unfolded: t.boolean(),
        unfoldedIds: t.instanceOf(Set),
        record: t.object(),
    };
    static template = "knowledge.SidebarRow";
    static components = {
        KnowledgeSidebarRow,
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
        this.orm = useService("orm");

        this.state = proxy({
            unfolded: false,
        });

        onWillStart(async () => {
            this.canCreateArticle = await user.checkAccessRight(
                "knowledge.article",
                "create",
            );
        });

        onWillUpdateProps((nextProps) => {
            if (this.state.loading && nextProps.unfolded === true) {
                this.state.loading = false;
            }
        });
    }

    get hasChildren() {
        return this.props.article.has_article_children;
    }

    get isActive() {
        return this.props.record.resId === this.props.article.id;
    }

    get isLocked() {
        return this.props.article.is_locked;
    }

    get isReadonly() {
        return !this.props.article.user_can_write;
    }

    createChild() {
        this.knowledgeContext.createArticle(
            this.props.article.category,
            this.props.article.id,
        );
    }

    onCaretClick() {
        if (this.props.unfolded) {
            this.knowledgeContext.fold(this.props.article.id);
        } else if (!this.state.loading) {
            this.state.loading = true;
            if (this.props.article.child_ids.length > 500) {
                setTimeout(
                    () => this.knowledgeContext.unfold(this.props.article.id),
                    0,
                );
            } else {
                this.knowledgeContext.unfold(this.props.article.id);
            }
        }
    }

    onNameClick() {
        this.knowledgeContext.openArticle(this.props.article.id);
    }
}
