/** @odoo-module native */
import { createElement } from "@web/core/utils/dom/xml";
import { formView, objectToString } from "@web/views/form";
import { isComponentNode } from "@web/views/view_compiler";
import {
    applyInvisible,
    computeXpath,
} from "@web_studio/client_action/view_editor/editors/xml_utils";

const interestingSelector = [
    ":not(field) sheet",
    ":not(field) field:not([data-used-by])",
    ":not(field) notebook",
    ":not(field) page",
    ":not(field) button",
    ":not(field) label",
    ":not(field) group",
    ":not(field) group:not(:has(> group)) > *",
    ":not(field) chatter",
    ":not(field) .oe_avatar",
    ":not(field) widget",
].join(", ");

export class FormEditorCompiler extends formView.Compiler {
    compile(key, params = {}) {
        const xml = this.templates[key];

        for (const el of xml.querySelectorAll(interestingSelector)) {
            const xpath = computeXpath(el);
            el.setAttribute("studioXpath", xpath);
        }

        this.addChatter = true;
        this.chatterData = {
            remove_message_ids: false,
            remove_follower_ids: false,
            remove_activity_ids: false,
        };
        this.avatars = [];

        const mainSheet = xml.querySelector("sheet:not(field sheet)");
        const isSheetEmpty = !mainSheet || !mainSheet.firstElementChild;

        const compiled = super.compile(key, params);

        const sheetBg = compiled.querySelector(".o_form_sheet_bg");
        if (sheetBg) {
            let studioHook;
            if (isSheetEmpty) {
                studioHook = createElement("StudioHook", {
                    xpath: `"${sheetBg.getAttribute("studioXpath")}"`,
                    position: "'inside'",
                    type: "'insideSheet'",
                });
            } else {
                studioHook = createElement("StudioHook", {
                    xpath: `"${sheetBg.getAttribute("studioXpath")}/*[1]"`,
                    position: "'before'",
                    type: "'insideSheet'",
                });
            }

            sheetBg.querySelector(".o_form_sheet").prepend(studioHook);
        }

        if (this.addChatter) {
            const chatterContainerHook = createElement("ChatterContainerHook", {
                threadModel: `__comp__.props.record.resModel`,
                chatterData: objectToString(this.chatterData),
            });
            const el = compiled.querySelector(".o_form_sheet") || compiled;
            el.after(chatterContainerHook);
        } else {
            const parent = compiled.querySelector(".o-mail-Form-chatter");
            parent.removeAttribute("t-attf-class");
            parent.removeAttribute("t-if");
        }

        const checkStatusBarButtons = compiled.querySelector("StatusBarButtons");
        if (!checkStatusBarButtons) {
            const addButtonAction = createElement("AddButtonAction");
            const el = compiled.querySelector(".o_form_sheet_bg") || compiled;
            el.prepend(addButtonAction);
        }

        const fieldStatus = compiled.querySelector(`Field[type="'statusbar'"]`);
        if (!fieldStatus) {
            const addStatusBar = !compiled.querySelector(".o_form_statusbar");
            const statusBarFieldHook = createElement("StatusBarFieldHook", {
                addStatusBar,
            });
            const el = compiled.querySelector(".o_form_sheet_bg") || compiled;
            el.prepend(statusBarFieldHook);
        }

        const buttonBoxXml = xml.querySelector("div[name='button_box']:not(field div)");
        let buttonBox;
        if (buttonBoxXml) {
            for (const child of [...buttonBoxXml.children]) {
                if (child.matches("span,field")) {
                    buttonBoxXml.removeChild(child);
                }
            }
            buttonBox = this.compileNode(buttonBoxXml, params);
        } else {
            buttonBox = createElement("ButtonBox");
        }
        const el = compiled.querySelector(".o_form_sheet_bg") || compiled;
        el.prepend(buttonBox);

        const buttonHook = createElement(
            "t",
            [createElement("ButtonHook", { add_buttonbox: !buttonBoxXml })],
            { "t-set-slot": `slot_button_hook` },
        );

        buttonBox.insertAdjacentElement("afterbegin", buttonHook);

        const title = compiled.querySelector(".oe_title");
        if (title) {
            if (
                !title.querySelector(":scope > h1 > [isAvatar]") &&
                !title.parentElement.querySelector(":scope > [isAvatar]")
            ) {
                const avatarHook = createElement("AvatarHook", {
                    fields: `__comp__.props.record.fields`,
                });
                title.before(avatarHook);
            }
        }
        for (const el of this.avatars) {
            el.removeAttribute("isAvatar");
        }

        compiled.querySelectorAll(":not(.o_form_statusbar) Field").forEach((el) => {
            el.setAttribute("hasEmptyPlaceholder", "true");
        });

        compiled
            .querySelectorAll(
                `InnerGroup > t[t-set-slot][subType="'item_component'"] Field`,
            )
            .forEach((el) => {
                el.setAttribute("hasLabel", "true");
            });

        return compiled;
    }

    applyInvisible(invisible, compiled, params) {
        return applyInvisible(invisible, compiled, params);
    }

    createLabelFromField(fieldId, fieldName, fieldString, label, params) {
        const studioXpath = label.getAttribute("studioXpath");
        const formLabel = super.createLabelFromField(...arguments);
        formLabel.setAttribute("studioXpath", `"${studioXpath}"`);
        if (formLabel.hasAttribute("t-if")) {
            formLabel.setAttribute("studioIsVisible", formLabel.getAttribute("t-if"));
            formLabel.removeAttribute("t-if");
        }
        return formLabel;
    }

    compileNode(node, params = {}, evalInvisible = true) {
        if (node.tagName === "field" && node.hasAttribute("data-used-by")) {
            return;
        }
        const nodeType = node.nodeType;
        const currentSlot = params.currentSlot;
        if (nodeType === 1 && currentSlot && !currentSlot.hasAttribute("studioXpath")) {
            const parentElement = node.parentElement;
            if (parentElement && parentElement.tagName === "page") {
                const xpath = computeXpath(node.parentElement);
                currentSlot.setAttribute("studioXpath", `"${xpath}"`);
                if (!parentElement.querySelector(":scope > group:last-child > group")) {
                    const pageHookProps = {
                        position: "'inside'",
                        type: "'page'",
                        xpath: `"${xpath}"`,
                    };
                    currentSlot.setAttribute(
                        "studioHookProps",
                        objectToString(pageHookProps),
                    );
                }
            } else {
                const xpath = node.getAttribute("studioXpath");
                currentSlot.setAttribute("studioXpath", `"${xpath}"`);
            }
        }

        if (nodeType === 1 && node.getAttribute("studio_no_fetch")) {
            return;
        }

        const compiled = super.compileNode(
            node,
            { ...params, compileInvisibleNodes: true },
            true,
        );

        if (nodeType === 1) {
            if (node.hasAttribute("studioXpath")) {
                const xpath = node.getAttribute("studioXpath");
                if (isComponentNode(compiled)) {
                    compiled.setAttribute("studioXpath", `"${xpath}"`);
                } else if (!compiled.hasAttribute("studioXpath")) {
                    compiled.setAttribute("studioXpath", xpath);
                }
            }

            if (node.tagName === "notebook") {
                const originalChildren = Array.from(node.children).filter(
                    (e) => e.tagName === "page",
                );
                Array.from(compiled.children).forEach((elem, index) => {
                    if (!elem.hasAttribute("studioXpath")) {
                        const studioXpath =
                            originalChildren[index].getAttribute("studioXpath");
                        elem.setAttribute("studioXpath", `"${studioXpath}"`);
                        const pageHookProps = {
                            position: "'inside'",
                            type: "'page'",
                            xpath: `"${studioXpath}"`,
                        };
                        elem.setAttribute(
                            "studioHookProps",
                            objectToString(pageHookProps),
                        );
                    }
                });
            }

            if (node.tagName === "chatter") {
                this.addChatter = false;
                const chatterNode = compiled.querySelector(
                    "t[t-component='__comp__.mailComponents.Chatter']",
                );
                const xpath = node.getAttribute("studioXpath");
                chatterNode.setAttribute("studioXpath", `"${xpath}"`);
                compiled.setAttribute("data-studio-xpath", xpath);
                compiled.classList.add("o-web-studio-editor--element-clickable");
            }
            if (node.classList.contains("oe_avatar")) {
                compiled.setAttribute("isAvatar", true);
                this.avatars.push(compiled);
            }

            if (
                node.classList.contains("o_td_label") &&
                !node.children.length &&
                !node.textContent.trim()
            ) {
                compiled.classList.add("o-web-studio-editor--element-clickable");
                const xpath = node.getAttribute("studioXpath");
                compiled.setAttribute(
                    "t-on-click",
                    `(ev) => __comp__.viewConfig.onNodeClicked("${xpath}")`,
                );
            }

            const name = node.getAttribute("name");
            if (name === "message_ids") {
                this.chatterData.remove_message_ids = true;
            } else if (name === "message_follower_ids") {
                this.chatterData.remove_follower_ids = true;
            } else if (name === "activity_ids") {
                this.chatterData.remove_activity_ids = true;
            }
        }
        return compiled;
    }
}
