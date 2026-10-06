// @ts-check
/** @odoo-module native */
import { htmlEscape, markup } from "@odoo/owl";
import { loadEmoji, loader } from "@web/components/emoji_picker";
import { router } from "@web/core/browser/router";
import { normalize } from "@web/core/l10n/utils";
import {
    createDocumentFragmentFromContent,
    createElementWithContent,
    htmlFormatList,
    htmlJoin,
    htmlReplace,
    htmlReplaceAll,
    htmlTrim,
    isHtmlEmpty,
    setElementContent,
} from "@web/core/utils/dom/html";
import { setAttributes } from "@web/core/utils/dom/xml";
import { getOrigin } from "@web/core/utils/urls";
const Markup = markup("").constructor;
const urlRegexp =
    /\b(?:https?:\/\/\d{1,3}(?:\.\d{1,3}){3}|(?:https?:\/\/|(?:www\.))[-a-z0-9@:%._+~#=\u00C0-\u024F\u1E00-\u1EFF]{1,256}(?:\.{1})?(?:[a-z]{2,13}))\b(?:[-a-z0-9@:%_+~#?&[\]^|{}`\\'$//=\u00C0-\u024F\u1E00-\u1EFF]|[.]*[-a-z0-9@:%_+~#?&[\]^|{}`\\'$//=\u00C0-\u024F\u1E00-\u1EFF]|,(?!$| )|\.(?!$| |\.)|;(?!$| ))*/gi;
/** @type {RegExp|undefined} */
let messageUrlRegExp;
/** @type {string|undefined} */
let messageUrlRegExpOrigin;
function getMessageUrlRegExp() {
    const origin = getOrigin();
    if (messageUrlRegExpOrigin !== origin) {
        messageUrlRegExpOrigin = origin;
        messageUrlRegExp = new RegExp(`^${RegExp.escape(origin)}/mail/message/(\\d+)$`);
    }
    return messageUrlRegExp;
}

/**
 * @param {string|import("@odoo/owl").Markup} rawBody
 * @param {Object} [param1]
 * @param {Object} [param1.validMentions]
 * @param {(Pick<import("models").ResPartner, "id" | "name"> & {displayName?: string})[]} [param1.validMentions.partners]
 * @param {import("models").ResRole[]} [param1.validMentions.roles]
 * @param {import("models").Thread[]} [param1.validMentions.threads]
 * @param {string[]} [param1.validMentions.specialMentions]
 * @param {import("models").Thread} [param1.thread]
 * @returns {string|import("@odoo/owl").Markup}
 */
export function prettifyMessageText(rawBody, { validMentions = {}, thread } = {}) {
    if (rawBody instanceof Markup) {
        return rawBody;
    }
    let body = htmlTrim(rawBody);
    body = htmlReplace(body, /(\r|\n){2,}/g, () => markup`<br/><br/>`);
    body = htmlReplace(body, /(\r|\n)/g, () => markup`<br/>`);
    body = htmlReplace(body, /&nbsp;/g, () => " ");
    body = htmlTrim(body);
    body = generateMentionsLinks(body, { ...validMentions, thread });
    body = parseAndTransform(body, addLink);
    return body;
}

/**
 * @param {string|import("@odoo/owl").Markup} htmlBody
 * @param {Object} [options]
 * @param {boolean} [options.allowEmojiLoading=true]
 * @returns {Promise<string|import("@odoo/owl").Markup>}
 */
export async function generateEmojisOnHtml(
    htmlBody,
    { allowEmojiLoading = true } = {},
) {
    let body = htmlBody;
    if (allowEmojiLoading || loader.loaded) {
        body = await _generateEmojisOnHtml(body);
    }
    return body;
}

/**
 * @param {string|import("@odoo/owl").Markup} rawBody
 * @param {Object} [param1]
 * @param {Object} [param1.validMentions]
 * @param {(Pick<import("models").ResPartner, "id" | "name"> & {displayName?: string})[]} [param1.validMentions.partners]
 * @param {boolean} [param1.allowEmojiLoading=true]
 * @returns {Promise<string|import("@odoo/owl").Markup>}
 */
export async function prettifyMessageContent(
    rawBody,
    { validMentions = {}, allowEmojiLoading = true } = {},
) {
    let body = prettifyMessageText(rawBody, { validMentions });
    body = await generateEmojisOnHtml(body, { allowEmojiLoading });
    return body;
}

/**
 * @param {string|import("@odoo/owl").Markup} htmlString
 * @param {function} transformFunction
 * @returns {import("@odoo/owl").Markup}
 */
export function parseAndTransform(htmlString, transformFunction) {
    return _parseAndTransform(
        Array.from(parseHtmlLeniently(htmlString).childNodes),
        transformFunction,
    );
}

/**
 * @param {string|import("@odoo/owl").Markup} htmlString
 * @returns {HTMLDivElement} the parsed content, or the raw text in a <pre> when it does not parse
 */
function parseHtmlLeniently(htmlString) {
    const div = document.createElement("div");
    try {
        setElementContent(div, htmlString);
    } catch {
        div.appendChild(createElementWithContent("pre", htmlString));
    }
    return div;
}

/**
 * @param {Node[]|NodeListOf<ChildNode>} nodes
 * @param {function} transformFunction
 * @return {import("@odoo/owl").Markup}
 */
function _parseAndTransform(nodes, transformFunction) {
    if (!nodes) {
        return;
    }
    return htmlJoin(
        Object.values(nodes).map((node) =>
            transformFunction(node, function () {
                return _parseAndTransform(node.childNodes, transformFunction);
            }),
        ),
    );
}

/**
 * @param {string} text
 * @return {import("@odoo/owl").Markup}
 */
function linkify(text) {
    let curIndex = 0;
    /** @type {string|import("@odoo/owl").Markup} */
    let result = "";
    let match;
    while ((match = urlRegexp.exec(text)) !== null) {
        const url = match[0];
        const fixedUrl = !/^https?:\/\//i.test(url) ? `http://${url}` : url;
        if (!URL.canParse(fixedUrl)) {
            continue;
        }
        result = htmlJoin([result, text.slice(curIndex, match.index)]);
        const { href } = URL.parse(fixedUrl);
        const link = document.createElement("a");
        setAttributes(link, {
            target: "_blank",
            rel: "noreferrer noopener",
            href,
        });
        link.textContent = url;
        const messageMatch = getMessageUrlRegExp().exec(fixedUrl);
        if (messageMatch !== null) {
            setAttributes(link, {
                "data-oe-id": messageMatch[1],
                "data-oe-model": "mail.message",
            });
            link.classList.add("o_message_redirect");
        }
        result = htmlJoin([result, markup(link.outerHTML)]);
        curIndex = match.index + match[0].length;
    }
    return htmlJoin([result, text.slice(curIndex)]);
}

/**
 * @param {Node} node
 * @param {function} transformChildren
 * @returns {string|import("@odoo/owl").Markup}
 */
export function addLink(node, transformChildren) {
    const element = /** @type {Element} */ (node);
    if (node.nodeType === 3) {
        const linkified = linkify(node.textContent);
        if (linkified.toString() !== htmlEscape(node.textContent).toString()) {
            const div = createElementWithContent("div", linkified);
            for (const childNode of [...div.childNodes]) {
                node.parentNode.insertBefore(childNode, node);
            }
            node.parentNode.removeChild(node);
            return linkified;
        }
        return node.textContent;
    }
    if (element.tagName === "A") {
        return markup(element.outerHTML);
    }
    transformChildren();
    return markup(element.outerHTML);
}

/**
 * @param {Object} mention
 * @param {string} mention.className
 * @param {string | number} mention.id
 * @param {string} mention.model
 * @param {string} mention.text
 * @returns {HTMLAnchorElement}
 */
function generateMentionElement({ className, id, model, text }) {
    const link = document.createElement("a");
    setAttributes(link, {
        href: router.stateToUrl({ model: model, resId: id }),
        class: className,
        "data-oe-id": id,
        "data-oe-model": model,
        target: "_blank",
        contenteditable: "false",
    });
    link.textContent = text;
    return link;
}

/**
 * @param {Pick<import("models").ResPartner, "id" | "name"> & {displayName?: string}} partner
 * @param {import("models").Thread} thread
 */
export function generatePartnerMentionElement(partner, thread) {
    return generateMentionElement({
        className: "o_mail_redirect",
        id: partner.id,
        model: "res.partner",
        text: `@${thread?.getPersonaName(partner) ?? partner.name}`,
    });
}

/** @param {import("models").ResRole} role */
export function generateRoleMentionElement(role) {
    return generateMentionElement({
        className: "o-discuss-mention",
        id: role.id,
        model: "res.role",
        text: `@${role.name}`,
    });
}

/** @param {string} label */
export function generateSpecialMentionElement(label) {
    const link = document.createElement("a");
    setAttributes(link, {
        class: "o-discuss-mention",
        contenteditable: "false",
    });
    link.textContent = `@${label}`;
    return link;
}

/** @param {Pick<import("models").Thread, "id" | "model"> & Partial<Pick<import("models").DiscussChannel, "parent_channel_id" | "fullNameWithParent">>} thread */
export function generateThreadMentionElement(thread) {
    return generateMentionElement({
        className: `o_channel_redirect${
            thread.parent_channel_id ? " o_channel_redirect_asThread" : ""
        }`,
        id: thread.id,
        model: "discuss.channel",
        text: `#${thread.fullNameWithParent}`,
    });
}

/**
 * @param {string|import("@odoo/owl").Markup} body
 * @param {Object} param1
 * @param {(Pick<import("models").ResPartner, "id" | "name"> & {displayName?: string})[]} [param1.partners]
 * @param {import("models").ResRole[]} [param1.roles]
 * @param {import("models").Thread[]} [param1.threads]
 * @param {string[]} [param1.specialMentions]
 * @param {import("models").Thread} param1.thread
 * @return {import("@odoo/owl").Markup}
 */
function generateMentionsLinks(
    body,
    { partners = [], roles = [], threads = [], specialMentions = [], thread },
) {
    /** @type {{text: string, link: HTMLElement}[]} */
    const mentions = [];
    for (const partner of partners) {
        mentions.push({
            text: `@${thread?.getPersonaName(partner) ?? partner.name}`,
            link: generatePartnerMentionElement(partner, thread),
        });
    }
    for (const channel of threads) {
        mentions.push({
            text: `#${channel.fullNameWithParent}`,
            link: generateThreadMentionElement(channel),
        });
    }
    for (const special of specialMentions) {
        mentions.push({
            text: `@${special}`,
            link: generateSpecialMentionElement(special),
        });
    }
    for (const role of roles) {
        mentions.push({
            text: `@${role.name}`,
            link: generateRoleMentionElement(role),
        });
    }
    /** @type {Map<string, {links: HTMLElement[], seen: number}>} */
    const mentionsByEscapedText = new Map();
    for (const { text, link } of mentions) {
        const escapedText = htmlEscape(text).toString();
        if (!mentionsByEscapedText.has(escapedText)) {
            mentionsByEscapedText.set(escapedText, { links: [], seen: 0 });
        }
        mentionsByEscapedText.get(escapedText).links.push(link);
    }
    if (!mentionsByEscapedText.size) {
        return htmlEscape(body);
    }
    const mentionRegExp = new RegExp(
        [...mentionsByEscapedText.keys()]
            .sort((a, b) => b.length - a.length)
            .map(RegExp.escape)
            .join("|"),
        "g",
    );
    return htmlReplace(body, mentionRegExp, (/** @type {string} */ escapedText) => {
        const group = mentionsByEscapedText.get(escapedText);
        const link = group.links[Math.min(group.seen++, group.links.length - 1)];
        return markup(link.outerHTML);
    });
}

/**
 * @typedef {Object} EmojiRecord
 * @property {string[]} shortcodes
 * @property {string[]} emoticons
 * @property {string} codepoints
 */
/** @type {{ emojis: EmojiRecord[], codepointsBySource: Map<string, string>, regex: RegExp|null, }|undefined} */
let emojiSourceCache;

/**
 * @param {EmojiRecord[]} emojis
 * @returns {{emojis: EmojiRecord[], codepointsBySource: Map<string, string>, regex: RegExp|null}}
 */
function getEmojiSourceCache(emojis) {
    if (emojiSourceCache?.emojis !== emojis) {
        /** @type {Map<string, string>} */
        const codepointsBySource = new Map();
        for (const emoji of emojis) {
            for (const source of [...emoji.shortcodes, ...emoji.emoticons]) {
                const escapedSource = htmlEscape(String(source)).toString();
                if (!codepointsBySource.has(escapedSource)) {
                    codepointsBySource.set(escapedSource, emoji.codepoints);
                }
            }
        }
        const alternation = [...codepointsBySource.keys()]
            .sort((source1, source2) => source2.length - source1.length)
            .map(RegExp.escape)
            .join("|");
        emojiSourceCache = {
            emojis,
            codepointsBySource,
            regex: alternation
                ? new RegExp(`(\\s|^)(${alternation})(?=\\s|$|<)`, "g")
                : null,
        };
    }
    return emojiSourceCache;
}

/**
 * @param {string|import("@odoo/owl").Markup} htmlString
 * @returns {Promise<import("@odoo/owl").Markup>}
 */
async function _generateEmojisOnHtml(htmlString) {
    const { emojis } = await loadEmoji();
    const { codepointsBySource, regex } = getEmojiSourceCache(emojis);
    if (regex) {
        htmlString = htmlReplace(
            htmlString,
            regex,
            /**
             * @param {string} _
             * @param {string} whitespace
             * @param {string} source
             */
            (_, whitespace, source) => whitespace + codepointsBySource.get(source),
        );
    }
    return htmlEscape(htmlString);
}

/**
 * @param {string|import("@odoo/owl").Markup} body
 * @returns {import("@odoo/owl").Markup}
 */
export function getNonEditableMentions(body) {
    const doc = createDocumentFragmentFromContent(body);
    for (const block of doc.body.querySelectorAll(".o_mail_reply_hide")) {
        block.classList.remove("o_mail_reply_hide");
    }
    for (const mention of doc.body.querySelectorAll(
        ".o_mail_redirect, .o_channel_redirect, .o-discuss-mention",
    )) {
        mention.setAttribute("contenteditable", "false");
    }
    return markup(doc.body.innerHTML);
}

/**
 * @param {string|import("@odoo/owl").Markup} htmlString
 * @returns {string}
 */
export function htmlToTextContentInline(htmlString) {
    htmlString = htmlReplace(htmlString, /<br\s*\/?>/gi, () => " ");
    return parseHtmlLeniently(htmlString)
        .textContent.trim()
        .replace(/[\n\r]/g, "")
        .replace(/\s\s+/g, " ");
}

/**
 * @param {string|import("@odoo/owl").Markup} str
 * @returns {string}
 */
export function convertBrToLineBreak(str) {
    str = htmlReplace(str, /<br\s*\/?>/gi, () => "\n");
    return createDocumentFragmentFromContent(str).body.textContent;
}

const EMPTY_BLOCK_CONTENT = new Set([
    "B",
    "BR",
    "EM",
    "FONT",
    "I",
    "S",
    "SMALL",
    "SPAN",
    "STRONG",
    "SUB",
    "SUP",
    "U",
]);

/** @param {Element} block */
function isEmptyBlock(block) {
    return (
        !block.textContent.trim() &&
        [...block.querySelectorAll("*")].every(
            (element) => EMPTY_BLOCK_CONTENT.has(element.tagName) && !element.className,
        )
    );
}

/**
 * @param {string|import("@odoo/owl").Markup} content
 * @returns {string|import("@odoo/owl").Markup}
 */
export function trimEmptyBlocksAround(content) {
    if (isHtmlEmpty(content)) {
        return content;
    }
    const body = createDocumentFragmentFromContent(content).body;
    let changed = false;

    /** @param {Node} node */
    const removeNode = (node) => {
        /** @type {ChildNode} */ (node).remove();
        changed = true;
    };

    /** @typedef {"start" | "end"} BoundarySide */
    /**
     * @param {Element | null | undefined} element
     * @param {BoundarySide} side
     * @returns {ChildNode | null}
     */
    const getBoundaryChild = (element, side) => {
        if (!element) {
            return null;
        }
        return side === "start" ? element.firstChild : element.lastChild;
    };

    /**
     * @param {Element | null | undefined} element
     * @param {BoundarySide} side
     * @returns {Element | null}
     */
    const getBoundaryElement = (element, side) => {
        if (!element) {
            return null;
        }
        return side === "start" ? element.firstElementChild : element.lastElementChild;
    };

    /**
     * @param {Element|null|undefined} element
     * @param {BoundarySide} side
     */
    const trimTextNodes = (element, side) => {
        let node = getBoundaryChild(element, side);
        while (node?.nodeType === Node.TEXT_NODE && !node.textContent.trim()) {
            removeNode(node);
            node = getBoundaryChild(element, side);
        }
    };

    /** @param {BoundarySide} side */
    const trimEmptyParagraphs = (side) => {
        trimTextNodes(body, side);
        let paragraph = getBoundaryElement(body, side);
        while (["P", "DIV"].includes(paragraph?.tagName) && isEmptyBlock(paragraph)) {
            removeNode(paragraph);
            trimTextNodes(body, side);
            paragraph = getBoundaryElement(body, side);
        }
    };

    /** @param {BoundarySide} side */
    const trimBoundaryParagraph = (side) => {
        trimEmptyParagraphs(side);
        const paragraph = getBoundaryElement(body, side);
        if (!paragraph || !["P", "DIV"].includes(paragraph.tagName)) {
            return;
        }
        trimTextNodes(paragraph, side);
        let node = getBoundaryChild(paragraph, side);
        while (node?.nodeName === "BR") {
            removeNode(node);
            trimTextNodes(paragraph, side);
            node = getBoundaryChild(paragraph, side);
        }
        trimEmptyParagraphs(side);
        if (getBoundaryElement(body, side) !== paragraph) {
            trimBoundaryParagraph(side);
        }
    };
    trimBoundaryParagraph("start");
    trimBoundaryParagraph("end");
    return changed ? markup(body.innerHTML) : content;
}

/**
 * @param {*} term
 * @returns {string}
 */
export function cleanTerm(term) {
    return typeof term === "string" ? normalize(term) : "";
}

const EMAIL_TOKEN_SEPARATORS = new Set(' \t\n\r\f\v,;<>"()');
const DISPLAY_NAME_TRAILING_JUNK = new Set(" \t\n\r\f\v,;<");

/**
 * @param {string} rawName
 * @param {string} email
 * @returns {[string, string]}
 */
function displayNameAndEmail(rawName, email) {
    let end = rawName.length;
    while (end > 0 && DISPLAY_NAME_TRAILING_JUNK.has(rawName[end - 1])) {
        end--;
    }
    let name = rawName.slice(0, end).trim();
    if (name.length > 1 && name.startsWith('"') && name.endsWith('"')) {
        name = name.slice(1, -1).replace(/\\(.)/g, "$1");
    } else {
        name = name.replace(/^"|"$/g, "").trim();
    }
    return [name || email, email];
}

/**
 * @param {string} text
 * @param {boolean} honourQuotes
 * @returns {[string, string]|null}
 */
function findFirstEmail(text, honourQuotes) {
    let tokenStart = 0;
    let tokenHasAt = false;
    let quoted = false;
    let nextClose = text.indexOf(">");
    for (let index = 0; index < text.length; index++) {
        const char = text[index];
        if (quoted) {
            if (char === "\\") {
                index++;
            } else if (char === '"') {
                quoted = false;
                tokenStart = index + 1;
            }
            continue;
        }
        if (!EMAIL_TOKEN_SEPARATORS.has(char)) {
            tokenHasAt ||= char === "@";
            continue;
        }
        if (tokenHasAt) {
            return displayNameAndEmail(
                text.slice(0, tokenStart),
                text.slice(tokenStart, index),
            );
        }
        tokenStart = index + 1;
        if (char === '"' && honourQuotes) {
            quoted = true;
        } else if (char === "<" && nextClose !== -1) {
            if (nextClose < index) {
                nextClose = text.indexOf(">", index);
            }
            const nextOpen = text.indexOf("<", index + 1);
            if (nextClose !== -1 && (nextOpen === -1 || nextClose < nextOpen)) {
                const address = text.slice(index + 1, nextClose).trim();
                if (address.includes("@")) {
                    return displayNameAndEmail(text.slice(0, index), address);
                }
            }
        }
    }
    if (tokenHasAt && !quoted) {
        return displayNameAndEmail(text.slice(0, tokenStart), text.slice(tokenStart));
    }
    return null;
}

/**
 * @param {string} text
 * @returns {[string, string|false]|undefined} the display name and the first address of
 *  `text`, the name falling back to the address; `[text, false]` without an address
 */
export function parseEmail(text) {
    if (!text) {
        return;
    }
    const found = findFirstEmail(text, true) ?? findFirstEmail(text, false);
    return found ?? [text, false];
}

const r = String.raw;
const SUBDIVISION_FLAG = r`\uD83C\uDFF4[\u{E0020}-\u{E007E}]+\u{E007F}`;
const KEYCAP = r`[#*\d]\uFE0F\u20E3`;
const EMOJI_WITH_SKIN_TONE = r`\p{Emoji_Modifier_Base}\p{Emoji_Modifier}`;
const EMOJI_PRESENTATION = r`\p{Emoji_Presentation}\uFE0F?`;
const QUALIFIED_TEXT = r`(?![#*\d])\p{Emoji}\uFE0F`;
const EMOJI = r`(?:${SUBDIVISION_FLAG}|${KEYCAP}|${EMOJI_WITH_SKIN_TONE}|${EMOJI_PRESENTATION}|${QUALIFIED_TEXT})`;
export const EMOJI_REGEX = new RegExp(
    r`\p{Regional_Indicator}{2}|` + r`${EMOJI}(?:\u200d${EMOJI})*`,
    "gu",
);

/**
 * @param {string|import("@odoo/owl").Markup} content
 * @returns {string|import("@odoo/owl").Markup}
 */
export function decorateEmojis(content) {
    if (!loader.loaded || !content) {
        return content;
    }
    const doc = createDocumentFragmentFromContent(content);
    const nodes = doc.evaluate(
        ".//text()",
        doc.body,
        null,
        XPathResult.UNORDERED_NODE_SNAPSHOT_TYPE,
        null,
    );
    for (let i = 0; i < nodes.snapshotLength; i++) {
        const node = nodes.snapshotItem(i);
        const span = document.createElement("span");
        setElementContent(
            span,
            htmlReplaceAll(
                node.textContent,
                loader.loaded.emojiRegex,
                /** @param {string} codepoints */
                (codepoints) =>
                    markup`<span class="o-mail-emoji" title="${htmlFormatList(
                        loader.loaded.emojiValueToShortcodes[codepoints],
                        { style: "unit-narrow" },
                    )}">${codepoints}</span>`,
            ),
        );
        /** @type {ChildNode} */ (node).replaceWith(...span.childNodes);
    }
    return markup(doc.body.innerHTML);
}

/**
 * @param {Object<string, any>} obj
 * @returns {string}
 */
export function attClassObjectToString(obj) {
    return Object.entries(obj)
        .filter(([_, val]) => val)
        .map(([key, _]) => key)
        .join(" ");
}
