/** @odoo-module native */
import { createElement, getTag } from "@web/core/utils/dom/xml";
import { KanbanCompiler } from "@web/views/kanban";
import { isComponentNode } from "@web/views/view_compiler";
import { toStringExpression } from "@web/views/view_utils";

import { applyInvisible, computeXpath } from "../xml_utils.js";

const interestingSelector = [
    "div",
    "aside",
    "footer",
    "field:not([data-used-by])",
    "main",
    "kanban",
    "widget",
    "a",
    "button",
].join(", ");

/**
 * @param {Element} el
 * @returns {string}
 */
function getElementXpath(el) {
    const xpath = el.getAttribute("studioXpath");
    if (isComponentNode(el)) {
        return xpath;
    }
    return `"${xpath}"`;
}

/**
 * @param {Element} el
 * @param {string} xpath
 */
function setElementXpath(el, xpath) {
    if (isComponentNode(el)) {
        el.setAttribute("studioXpath", `'${xpath}'`);
    } else {
        el.setAttribute("studioXpath", xpath);
    }
}

export class KanbanEditorCompiler extends KanbanCompiler {
    applyInvisible(invisible, compiled, params) {
        return applyInvisible(invisible, compiled, params);
    }

    /**
     * Insert a StudioHook as a sibling of the given node (after it; also before
     * it when `wrap` is set).
     * @param {Element} node - The node to attach hooks to
     * @param {string} type - The type of the hook
     * @param {string} template - The template to use for the hook
     * @param {Object} [options]
     * @param {Object} [options.structures]
     * @param {boolean} [options.wrap=false] - Whether to also insert a hook before the node
     */
    addStudioHook(node, type, template, { structures, wrap = false } = {}) {
        const xpath = getElementXpath(node);
        if (wrap) {
            const studioHookBefore = createElement("StudioHook", {
                xpath,
                position: "'before'",
                type: `'${type}'`,
                subTemplate: `'${template}'`,
                structures,
            });
            node.insertAdjacentElement("beforebegin", studioHookBefore);
        }
        const studioHookAfter = createElement("StudioHook", {
            xpath,
            position: "'after'",
            type: `'${type}'`,
            subTemplate: `'${template}'`,
            structures,
        });
        node.insertAdjacentElement("afterend", studioHookAfter);
    }

    wrapNodesInMain(node) {
        const elementsToWrap = Array.from(node.children).filter((e) => {
            if (e.tagName === "widget") {
                return e.getAttribute("name") !== "web_ribbon";
            }
            if (e.tagName === "t" && e.getAttribute("t-name") === "menu") {
                return false;
            }
            return !["aside"].includes(e.tagName);
        });
        return createElement("main", elementsToWrap);
    }

    compile(key, params = {}) {
        const xml = this.templates[key];
        const interestingArchNodes = [...xml.querySelectorAll(interestingSelector)];
        for (const el of interestingArchNodes) {
            const xpath = computeXpath(el, "kanban");
            setElementXpath(el, xpath);
        }
        const compiled = super.compile(key, params);
        return compiled;
    }

    compileButton(el, params) {
        const compiled = super.compileButton(...arguments);
        setElementXpath(compiled, el.getAttribute("studioXpath"));
        return compiled;
    }

    compileCard(node, params) {
        const mainNode = node.querySelector("main");
        if (!mainNode) {
            const mainEl = this.wrapNodesInMain(node);
            setElementXpath(mainEl, "kanban");
            node.append(mainEl);
        }
        const asideNode = node.querySelector("aside");
        const ribbonNode = node.querySelector("widget[name='web_ribbon']");
        const compiledCard = super.compileNode(node, params);
        const compiledMain = compiledCard.querySelector("main");
        if (!ribbonNode) {
            this.addStudioHook(compiledMain, "ribbon", "kanbanRibbon");
        }
        if (!asideNode) {
            this.addStudioHook(compiledMain, "kanbanAsideHook", "kanbanAsideHook", {
                wrap: true,
            });
        }
        return compiledCard;
    }

    compileField(el, params) {
        const compiled = super.compileField(...arguments);
        if (!el.hasAttribute("widget")) {
            compiled.classList.add("o-web-studio-editor--element-clickable");

            const nameExpr = toStringExpression(el.getAttribute("name"));
            const recordValueExpr = `__comp__.props.record.data[${nameExpr}]`;
            const isEmptyExpr = `__comp__.isFieldValueEmpty(${recordValueExpr})`;
            compiled.setAttribute(
                "t-attf-class",
                `{{ ${isEmptyExpr} ? "o_web_studio_widget_empty" : "" }}`,
            );
            const fieldNameExpr = `__comp__.props.record.fields[${nameExpr}].string`;
            const originalTOut = compiled.getAttribute("t-out");
            compiled.setAttribute(
                "t-out",
                `${isEmptyExpr} ? ${fieldNameExpr} : ${originalTOut}`,
            );
        } else {
            compiled.setAttribute("hasEmptyPlaceholder", true);
        }
        return compiled;
    }

    compileInnerSection(compiled) {
        const interestingNodes = [...compiled.querySelectorAll("[studioXpath]")].filter(
            (e) => e.getAttribute("studioXpath") !== "null" && !e.closest("ViewButton"),
        );
        const otherNodes = [...compiled.querySelectorAll("div[studioXpath]")].filter(
            (e) => !e.getAttribute("t-out"),
        );
        for (const child of otherNodes) {
            child.classList.add("o_inner_section");
            child.classList.add("o-web-studio-editor--element-clickable");
        }
        for (const child of interestingNodes) {
            if (
                [...child.getAttributeNames()].filter((e) =>
                    ["t-if", "t-elif", "t-else"].includes(e),
                ).length
            ) {
                continue;
            }
            this.addStudioHook(
                child,
                "field",
                child.tagName === "span" ? "kanbanInline" : "defaultTemplate",
                { structures: `'field'`, wrap: true },
            );
        }
        if (!interestingNodes.length) {
            const hook = createElement("StudioHook", {
                xpath: `"${compiled.getAttribute("studioXpath")}"`,
                position: "'inside'",
                type: "'field'",
                subTemplate: "defaultTemplate",
                structures: `'field'`,
            });
            compiled.appendChild(hook);
        }
    }

    compileNode(node, params) {
        if (node.tagName === "field" && node.hasAttribute("data-used-by")) {
            return;
        }
        let compiled;
        if (node.getAttribute?.("t-name") === "card") {
            compiled = this.compileCard(node);
        } else {
            compiled = super.compileNode(node, {
                ...params,
                compileInvisibleNodes: true,
            });
        }
        if (["aside", "footer"].includes(getTag(node))) {
            compiled.classList.add("o_inner_section");
            compiled.classList.add("o-web-studio-editor--element-clickable");
            this.compileInnerSection(compiled);
        } else if (getTag(node) === "main") {
            this.compileInnerSection(compiled);
            if (!compiled.querySelector("footer")) {
                const footerHook = createElement("StudioHook", {
                    xpath: `"${compiled.getAttribute("studioXpath")}"`,
                    position: "'after'",
                    type: `'footer'`,
                    subTemplate: `'defaultTemplate'`,
                    structures: `'footer'`,
                });
                compiled.appendChild(footerHook);
            }
        }
        if (node.nodeType === 1 && compiled && !compiled.attributes.studioXpath) {
            setElementXpath(compiled, node.getAttribute("studioXpath"));
        }
        return compiled;
    }
}
