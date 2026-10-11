/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { elementRef } from "@web/core/utils/element_ref";
import { throttleForAnimation } from "@web/core/utils/timing";
import { useRecordObserver } from "@web/fields/hooks/record_observer";
import { standardWidgetProps } from "@web/views/widgets";

class KnowledgeCover extends Component {
    static props = standardWidgetProps;
    static template = "knowledge.KnowledgeCover";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
        this.root = elementRef();
        this.image = elementRef();
        this.state = proxy({
            repositioning: false,
            grabbing: false,
            verticalPosition: this.props.record.data.cover_image_position || 50,
        });

        onWillStart(async () => {
            this.isInternalUser = await user.hasGroup("base.group_user");
        });

        let previousArticleId = this.props.record.resId;
        useRecordObserver((record) => {
            if (!previousArticleId || previousArticleId !== record.resId) {
                previousArticleId = record.resId;
                this.state.repositioning = false;
                this.state.grabbing = false;
                this.state.verticalPosition = record.data.cover_image_position || 50;
            }
        });
    }

    /**
     * @returns {boolean} - True if the article is editable
     */
    get isEditable() {
        const recordData = this.props.record.data;
        return (
            !recordData.is_locked &&
            recordData.user_can_write &&
            recordData.active &&
            this.isInternalUser
        );
    }

    changeCover() {
        this.knowledgeContext.ensureArticleName();
        this.knowledgeContext.openCoverSelector();
    }

    removeCover() {
        this.props.record.update({ cover_image_id: false });
    }

    repositionCover() {
        this.state.repositioning = true;
        const cover = this.image.el;
        let prevPos;

        const moveCover = throttleForAnimation((ev) => {
            if (prevPos !== ev.y) {
                const verticalPosition =
                    this.state.verticalPosition + (prevPos - ev.y) / 5;
                this.state.verticalPosition = Math.max(
                    0.01,
                    Math.min(100, verticalPosition),
                );
                prevPos = ev.y;
            }
        });

        const onPointerUp = () => {
            this.state.grabbing = false;
            document.removeEventListener("pointermove", moveCover);
            document.removeEventListener("pointerup", onPointerUp);
            document.removeEventListener("pointercancel", onPointerUp);
        };

        const onPointerDown = (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            prevPos = ev.y;
            this.state.grabbing = true;
            document.addEventListener("pointermove", moveCover);
            document.addEventListener("pointerup", onPointerUp, { once: true });
            document.addEventListener("pointercancel", onPointerUp, { once: true });
        };

        cover.addEventListener("pointerdown", onPointerDown);

        document.addEventListener(
            "pointerdown",
            (ev) => {
                cover.removeEventListener("pointerdown", onPointerDown);
                this.state.repositioning = false;
                if (ev.target.classList.contains("o_knowledge_undo_cover_move")) {
                    this.state.verticalPosition =
                        this.props.record.data.cover_image_position || 50;
                } else {
                    this.props.record.update({
                        cover_image_position: this.state.verticalPosition,
                    });
                }
            },
            { once: true },
        );
    }
}

export const knowledgeCover = {
    component: KnowledgeCover,
};
registry.category("view_widgets").add("knowledge_cover", knowledgeCover);
