import {
    lang,
    oop,
    TextMode,
    WorkerClient,
    XmlBehaviour,
    XmlFoldMode,
    XmlHighlightRules,
} from "ace";

var QWebHighlightRules = function () {
    XmlHighlightRules.call(this);
    const xmlRules = this.$rules;

    const tagRegex = xmlRules.attributes[0].regex;

    this.$rules = Object.assign({},
        xmlRules,
        {
            attributes: [{
                include: "attributes_odoo",
            }, {
                include: "attributes_qweb",
            }, {
                include: "attributes_groups",
            }, {
                include: "attributes_sample",
            }],

            attributes_odoo: [{
                token: ["entity.other.attribute-name.xml.odoo", "keyword.operator.attribute-equals.xml", "text", "string.attribute-value.xml.start", "string.attribute-value.xml.code", "string.attribute-value.xml.end"],
                regex: '(domain|attrs|options)(=)(\\s*)(")([^"]*)(")',
            }, {
                token: ["entity.other.attribute-name.xml.odoo", "keyword.operator.attribute-equals.xml", "text", "string.attribute-value.xml.start", "string.attribute-value.xml.code", "string.attribute-value.xml.end"],
                regex: "(domain|attrs|options)(=)(\\s*)(')([^']*)(')",
            }],

            attributes_qweb: [{
                token: ["entity.other.attribute-name.xml.qweb", "keyword.operator.attribute-equals.xml", "text", "string.attribute-value.xml.start", "string.attribute-value.xml", "string.attribute-value.xml.end"],
                regex: '(t-name|t-call-assets|t-js|t-css)(=)(\\s*)(")([^"]*)(")',
            }, {
                token: ["entity.other.attribute-name.xml.qweb", "keyword.operator.attribute-equals.xml", "text", "string.attribute-value.xml.start", "string.attribute-value.xml", "string.attribute-value.xml.end"],
                regex: "(t-name|t-call-assets|t-js|t-css)(=)(\\s*)(')([^']*)(')",
            }, {
                token: ["entity.other.attribute-name.xml.qweb", "keyword.operator.attribute-equals.xml", "text", "string.attribute-value.xml.start", "string.attribute-value.xml", "string.attribute-value.xml", "string.attribute-value.xml.code", "string.attribute-value.xml", "string.attribute-value.xml", "string.attribute-value.xml.end"],
                regex: '(t-call|t-attf-(?:' + tagRegex + '))(=)(\\s*)(")([^"#{]*)(?:([#{]\\{)([^"}]+)(\\}[}]?))?([^"]*)(")',
            }, {
                token: ["entity.other.attribute-name.xml.qweb", "keyword.operator.attribute-equals.xml", "text", "string.attribute-value.xml.start", "string.attribute-value.xml", "string.attribute-value.xml", "string.attribute-value.xml.code", "string.attribute-value.xml", "string.attribute-value.xml", "string.attribute-value.xml.end"],
                regex: "(t-call|t-attf-(?:" + tagRegex + "))(=)(\\s*)(')([^'#{]*)(?:([#{]\\{)([^'}]+)(\\}[}]?))?([^']*)(')",
            }, {
                token: ["entity.other.attribute-name.xml.qweb", "keyword.operator.attribute-equals.xml", "text", "string.attribute-value.xml.start", "string.attribute-value.xml.code", "string.attribute-value.xml.end"],
                regex: '(t-(?:' + tagRegex + '))(=)(\\s*)(")([^"]*)(")',
            }, {
                token: ["entity.other.attribute-name.xml.qweb", "keyword.operator.attribute-equals.xml", "text", "string.attribute-value.xml.start", "string.attribute-value.xml.code", "string.attribute-value.xml.end"],
                regex: "(t-(?:" + tagRegex + "))(=)(\\s*)(')([^']*)(')",
            }],

            attributes_groups: [{
                token: ["entity.other.attribute-name.xml.qweb", "keyword.operator.attribute-equals.xml", "text", "string.attribute-value.xml.start", "string.attribute-value.xml", "string.attribute-value.xml.end"],
                regex: '(groups)(=)(\\s*)(")([\\s\\na-zA-Z0-9.,_-]*)(")',
            }, {
                token: ["entity.other.attribute-name.xml.qweb", "keyword.operator.attribute-equals.xml", "text", "string.attribute-value.xml.start", "string.attribute-value.xml", "string.attribute-value.xml.end"],
                regex: "(groups)(=)(\\s*)(')((?:[\\s\\na-zA-Z0-9.,_-]*)*)(')",
            }],

            attributes_sample: [{
                token: "entity.other.attribute-name.xml",
                regex: tagRegex,
            }, {
                token: "keyword.operator.attribute-equals.xml",
                regex: "=",
            }, {
                include: "tag_whitespace",
            }, {
                include: "attribute_value",
            }],

            tag: [{
                token: ["meta.tag.punctuation.tag-open.xml", "meta.tag.punctuation.end-tag-open.xml", "meta.tag.tag-name.xml"],
                regex: "(?:(<)|(</))((?:" + tagRegex + ":)?" + tagRegex + ")",
                next: [{
                        include: "attributes",
                    }, {
                        token: ["meta.tag.punctuation.end-tag-close.xml", "meta.tag.punctuation.tag-close.xml"],
                        regex: "(/>)|(>)",
                        next: "start",
                    },
                ],
            }],
        },
    );

    if (this.constructor === QWebHighlightRules) {
        this.normalizeRules();
    }
};

oop.inherits(QWebHighlightRules, XmlHighlightRules);

export { QWebHighlightRules };

export const Mode = function () {
    this.HighlightRules = QWebHighlightRules;
    this.$behaviour = new XmlBehaviour();
    this.foldingRules = new XmlFoldMode();
};

oop.inherits(Mode, TextMode);

(function () {
    this.voidElements = lang.arrayToMap([]);

    this.blockComment = { start: "<!--", end: "-->" };

    this.createWorker = function (session) {
        const worker = new WorkerClient(["ace"], "ace/mode/xml_worker", "Worker");
        worker.attachToDocument(session.getDocument());

        worker.on("error", function (e) {
            session.setAnnotations(e.data);
        });

        worker.on("terminate", function () {
            session.clearAnnotations();
        });

        return worker;
    };

    this.$id = "ace/mode/qweb";
}).call(Mode.prototype);
