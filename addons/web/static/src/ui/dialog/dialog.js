// @ts-check
/** @odoo-module native */

import { Component, onWillDestroy, proxy, t, useListener, useProps } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import {
    provideChildDialogContext,
    useDialogContext,
} from "@web/core/dialog_context_hooks";
import { useHotkey } from "@web/core/hotkeys/hotkey_hook";
import { inputModality } from "@web/core/input_modality";
import { makeDraggableHook } from "@web/core/utils/dnd/draggable_hook_builder_owl";
import { elementRef } from "@web/core/utils/element_ref";
import { uniqueId } from "@web/core/utils/functions";
import { useForwardRefToParent, useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useThrottleForAnimation } from "@web/core/utils/timing";
import { useActiveElement } from "@web/ui/active_element";
import { inertAnchorOf, inertOutside } from "@web/ui/dialog/inert_outside";

const useDialogDraggable = makeDraggableHook(
    /** @type {any} */ ({
        name: "useDialogDraggable",
        onWillStartDrag(
            /** @type {{ ctx: { current: any }, addCleanup: Function, addStyle: Function, getRect: Function }} */ {
                ctx,
                addCleanup,
                addStyle,
                getRect,
            },
        ) {
            const { height, width } = getRect(ctx.current.element);
            ctx.current.container = document.createElement("div");
            addStyle(ctx.current.container, {
                position: "fixed",
                top: "0",
                bottom: `${70 - height}px`,
                left: `${70 - width}px`,
                right: `${70 - width}px`,
            });
            ctx.current.element.after(ctx.current.container);
            addCleanup(() => ctx.current.container.remove());
        },
        onDrop(
            /** @type {{ ctx: { current: any }, getRect: Function }} */ {
                ctx,
                getRect,
            },
        ) {
            const { top, left } = getRect(ctx.current.element);
            return {
                left: left - ctx.current.elementRect.left,
                top: top - ctx.current.elementRect.top,
            };
        },
    }),
);

const log = makeLogger("web.ui.dialog");

export class Dialog extends Component {
    static template = "web.Dialog";
    static props = {
        contentClass: t.string().optional(""),
        bodyClass: t.string().optional(""),
        fullscreen: t.boolean().optional(false),
        footer: t.boolean().optional(true),
        header: t.boolean().optional(true),
        size: t
            .customValidator(t.string(), (/** @type {any} */ s) =>
                ["sm", "md", "lg", "xl", "fs", "fullscreen"].includes(s),
            )
            .optional("lg"),
        technical: t.boolean().optional(true),
        title: t.string().optional("Odoo"),
        modalRef: t.function().optional(),
        slots: t.object({
            default: t.object(),
            header: t.object().optional(),
            footer: t.object().optional(),
        }),
        withBodyPadding: t.boolean().optional(true),
        onExpand: t.function().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.dialogContext = useDialogContext();
        this.ui = useService("ui");
        useLifecycleLog(log);
        this.modalRefRef = elementRef();
        this.modalRef = useForwardRefToParent("modalRef", this.modalRefRef);
        useActiveElement(this.modalRefRef);
        this.data = proxy(this.dialogContext.dialogData);
        useLayoutEffect(
            (el, isActive) => {
                if (!el || !isActive) {
                    return;
                }
                const release = inertOutside(inertAnchorOf(el));
                this.data.releasePage = release;
                return release;
            },
            () => [this.modalRefRef.el, this.data.isActive],
        );
        useHotkey("escape", () => this.onEscape());
        useHotkey(
            "control+enter",
            () => {
                const btns = /** @type {HTMLButtonElement[]} */ ([
                    ...(this.modalRef.el?.querySelectorAll(".modal-footer button") ??
                        []),
                ]);
                const firstActiveBtn = btns.find(
                    (btn) => !btn.disabled && getComputedStyle(btn).display !== "none",
                );
                firstActiveBtn?.click();
            },
            { bypassEditableProtection: true },
        );
        this.id = uniqueId("dialog_");
        provideChildDialogContext({ inDialog: true, dialogId: this.id });
        this.isMovable = this.props.header;
        if (this.isMovable) {
            this.position = proxy({ left: 0, top: 0 });
            useDialogDraggable(
                /** @type {any} */ ({
                    enable: () => !this.ui.isSmall,
                    ref: this.modalRef,
                    elements: ".modal-content",
                    handle: ".modal-header",
                    ignore: "button, input",
                    edgeScrolling: { enabled: false },
                    onDrop: (
                        /** @type {{ top: number, left: number }} */ { top, left },
                    ) => {
                        this.position.left += left;
                        this.position.top += top;
                    },
                }),
            );
            const throttledResize = useThrottleForAnimation(this.onResize.bind(this));
            useListener(window, "resize", throttledResize);
        }
        onWillDestroy(() => {
            if (this.ui.isSmall) {
                this.data.scrollToOrigin?.();
            }
        });
        this.bodyTabIndex = inputModality.isTouch ? "0" : undefined;
    }

    /** @returns {boolean} */
    get isFullscreen() {
        return this.props.fullscreen || this.ui.isSmall;
    }

    /** @returns {string} */
    get contentStyle() {
        if (this.isMovable) {
            return `top: ${this.position.top}px; left: ${this.position.left}px;`;
        }
        return "";
    }

    onResize() {
        this.position.left = 0;
        this.position.top = 0;
    }

    onEscape() {
        return this.dismiss();
    }

    async dismiss() {
        if ((await this.data.dismiss?.()) === false) {
            return;
        }
        return this.data.close({ dismiss: true });
    }
}
