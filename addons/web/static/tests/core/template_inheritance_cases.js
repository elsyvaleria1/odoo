/** @odoo-module native */

export const CASES = JSON.parse(String.raw`
{
    "cases": [
        {
            "name": "inside appends after the last child",
            "arch": "<form><group><field name=\"a\"/></group></form>",
            "specs": "<data><xpath expr=\"//group\" position=\"inside\"><field name=\"b\"/></xpath></data>",
            "result": "<form><group><field name=\"a\"/><field name=\"b\"/></group></form>"
        },
        {
            "name": "position defaults to inside",
            "arch": "<form><group/></form>",
            "specs": "<data><xpath expr=\"//group\"><field name=\"b\"/></xpath></data>",
            "result": "<form><group><field name=\"b\"/></group></form>"
        },
        {
            "name": "before inserts in front of the target",
            "arch": "<form><field name=\"a\"/><field name=\"c\"/></form>",
            "specs": "<data><xpath expr=\"//field[@name='c']\" position=\"before\"><field name=\"b\"/></xpath></data>",
            "result": "<form><field name=\"a\"/><field name=\"b\"/><field name=\"c\"/></form>"
        },
        {
            "name": "after inserts behind the target",
            "arch": "<form><field name=\"a\"/><field name=\"c\"/></form>",
            "specs": "<data><xpath expr=\"//field[@name='a']\" position=\"after\"><field name=\"b\"/></xpath></data>",
            "result": "<form><field name=\"a\"/><field name=\"b\"/><field name=\"c\"/></form>"
        },
        {
            "name": "replace swaps the target for the content",
            "arch": "<form><field name=\"a\"/><field name=\"b\"/></form>",
            "specs": "<data><xpath expr=\"//field[@name='a']\" position=\"replace\"><field name=\"x\"/></xpath></data>",
            "result": "<form><field name=\"x\"/><field name=\"b\"/></form>"
        },
        {
            "name": "an empty replace removes the target",
            "arch": "<form><field name=\"a\"/><field name=\"b\"/></form>",
            "specs": "<data><xpath expr=\"//field[@name='a']\" position=\"replace\"></xpath></data>",
            "result": "<form><field name=\"b\"/></form>"
        },
        {
            "name": "replace keeps the text that follows the target",
            "arch": "<p><span>a</span> units</p>",
            "specs": "<data><xpath expr=\"//span\" position=\"replace\"><b/></xpath></data>",
            "result": "<p><b/> units</p>"
        },
        {
            "name": "replace keeps the content's leading text",
            "arch": "<p><span>a</span></p>",
            "specs": "<data><xpath expr=\"//span\" position=\"replace\">x <b/></xpath></data>",
            "result": "<p>x <b/></p>"
        },
        {
            "name": "replace puts a copy of the target at $0",
            "arch": "<form><field name=\"a\"/></form>",
            "specs": "<data><xpath expr=\"//field\" position=\"replace\"><div class=\"wrap\">$0</div></xpath></data>",
            "result": "<form><div class=\"wrap\"><field name=\"a\"/></div></form>"
        },
        {
            "name": "replacing the root keeps its t-name",
            "arch": "<t t-name=\"p\"><div>old</div></t>",
            "specs": "<data><xpath expr=\".\" position=\"replace\"><section>new</section></xpath></data>",
            "result": "<section t-name=\"p\">new</section>"
        },
        {
            "name": "replacing the root can wrap it with $0",
            "arch": "<t t-name=\"p\"><div/></t>",
            "specs": "<data><xpath expr=\"/t\" position=\"replace\"><t><div class=\"w\">$0</div></t></xpath></data>",
            "result": "<t t-name=\"p\"><div class=\"w\"><t t-name=\"p\"><div/></t></div></t>"
        },
        {
            "name": "replacing the root needs an element",
            "arch": "<t t-name=\"p\"><div/></t>",
            "specs": "<data><xpath expr=\".\" position=\"replace\">only text</xpath></data>",
            "error": "needs an element"
        },
        {
            "name": "replace inner swaps the children",
            "arch": "<form><div><span>a</span>b<i/></div></form>",
            "specs": "<data><xpath expr=\"//div\" position=\"replace\" mode=\"inner\"><b>c</b></xpath></data>",
            "result": "<form><div><b>c</b></div></form>"
        },
        {
            "name": "replace inner moves before it clears",
            "arch": "<form><div><span id=\"keep\"/><i/></div></form>",
            "specs": "<data><xpath expr=\"//div\" position=\"replace\" mode=\"inner\"><b/><xpath expr=\"//span\" position=\"move\"/></xpath></data>",
            "result": "<form><div><b/><span id=\"keep\"/></div></form>"
        },
        {
            "name": "an unknown mode is refused",
            "arch": "<form><div/></form>",
            "specs": "<data><xpath expr=\"//div\" position=\"replace\" mode=\"middle\"><b/></xpath></data>",
            "error": "Invalid mode attribute"
        },
        {
            "name": "an unknown position is refused",
            "arch": "<form><div/></form>",
            "specs": "<data><xpath expr=\"//div\" position=\"around\"><b/></xpath></data>",
            "error": "Invalid position attribute"
        },
        {
            "name": "attributes sets and deletes",
            "arch": "<form><field name=\"a\" string=\"A\" invisible=\"1\"/></form>",
            "specs": "<data><xpath expr=\"//field\" position=\"attributes\"><attribute name=\"string\">B</attribute><attribute name=\"invisible\"/></xpath></data>",
            "result": "<form><field name=\"a\" string=\"B\"/></form>"
        },
        {
            "name": "attributes creates a missing attribute",
            "arch": "<form><div/></form>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"id\">x</attribute></xpath></data>",
            "result": "<form><div id=\"x\"/></form>"
        },
        {
            "name": "move before",
            "arch": "<form><field name=\"a\"/><field name=\"b\"/></form>",
            "specs": "<data><xpath expr=\"//field[@name='a']\" position=\"before\"><xpath expr=\"//field[@name='b']\" position=\"move\"></xpath></xpath></data>",
            "result": "<form><field name=\"b\"/><field name=\"a\"/></form>"
        },
        {
            "name": "move with a field locator",
            "arch": "<form><field name=\"a\"/><field name=\"b\"/><field name=\"c\"/></form>",
            "specs": "<data><field name=\"c\" position=\"after\"><field name=\"a\" position=\"move\"/></field></data>",
            "result": "<form><field name=\"b\"/><field name=\"c\"/><field name=\"a\"/></form>"
        },
        {
            "name": "move inside",
            "arch": "<form><div/><field name=\"a\"/></form>",
            "specs": "<data><xpath expr=\"//div\" position=\"inside\"><xpath expr=\"//field\" position=\"move\"></xpath></xpath></data>",
            "result": "<form><div><field name=\"a\"/></div></form>"
        },
        {
            "name": "a moved node spec holds nothing",
            "arch": "<form><div/><field name=\"a\"/></form>",
            "specs": "<data><xpath expr=\"//div\" position=\"inside\"><xpath expr=\"//field\" position=\"move\"><b/></xpath></xpath></data>",
            "error": "Invalid specification for moved nodes"
        },
        {
            "name": "moving a missing node is refused",
            "arch": "<form><div/></form>",
            "specs": "<data><xpath expr=\"//div\" position=\"inside\"><xpath expr=\"//field\" position=\"move\"></xpath></xpath></data>",
            "error": "cannot be located"
        },
        {
            "name": "a field locator compares the name only",
            "arch": "<form><field name=\"a\" string=\"A\"/></form>",
            "specs": "<data><field name=\"a\" string=\"other\" position=\"attributes\"><attribute name=\"x\">1</attribute></field></data>",
            "result": "<form><field name=\"a\" string=\"A\" x=\"1\"/></form>"
        },
        {
            "name": "a field locator takes the first in document order",
            "arch": "<form><group><field name=\"a\" id=\"1\"/></group><field name=\"a\" id=\"2\"/></form>",
            "specs": "<data><field name=\"a\" position=\"attributes\"><attribute name=\"x\">1</attribute></field></data>",
            "result": "<form><group><field name=\"a\" id=\"1\" x=\"1\"/></group><field name=\"a\" id=\"2\"/></form>"
        },
        {
            "name": "another locator compares every attribute",
            "arch": "<form><div class=\"x\"/><div class=\"y\" id=\"t\"/></form>",
            "specs": "<data><div class=\"y\" position=\"inside\"><b/></div></data>",
            "result": "<form><div class=\"x\"/><div class=\"y\" id=\"t\"><b/></div></form>"
        },
        {
            "name": "another locator refuses a partial match",
            "arch": "<form><div class=\"y\" id=\"t\"/></form>",
            "specs": "<data><div class=\"y\" id=\"u\" position=\"inside\"><b/></div></data>",
            "error": "cannot be located"
        },
        {
            "name": "the root is a candidate",
            "arch": "<list><field name=\"a\"/></list>",
            "specs": "<data><list position=\"attributes\"><attribute name=\"editable\">bottom</attribute></list></data>",
            "result": "<list editable=\"bottom\"><field name=\"a\"/></list>"
        },
        {
            "name": "the root is tried before its descendants",
            "arch": "<div><div/></div>",
            "specs": "<data><div position=\"attributes\"><attribute name=\"class\">x</attribute></div></data>",
            "result": "<div class=\"x\"><div/></div>"
        },
        {
            "name": "mode is not compared on a replace",
            "arch": "<form><div class=\"a\"><b/></div></form>",
            "specs": "<data><div class=\"a\" position=\"replace\" mode=\"inner\"><i/></div></data>",
            "result": "<form><div class=\"a\"><i/></div></form>"
        },
        {
            "name": "data-oe attributes are not compared",
            "arch": "<form><div class=\"a\"/></form>",
            "specs": "<data><div class=\"a\" data-oe-id=\"7\" position=\"inside\"><i/></div></data>",
            "result": "<form><div class=\"a\"><i/></div></form>"
        },
        {
            "name": "an xpath locating nothing is refused",
            "arch": "<form><div/></form>",
            "specs": "<data><xpath expr=\"//span\" position=\"inside\"><b/></xpath></data>",
            "error": "cannot be located"
        },
        {
            "name": "an xpath without expr is refused",
            "arch": "<form><div/></form>",
            "specs": "<data><xpath position=\"inside\"><b/></xpath></data>",
            "error": "missing 'expr' attribute"
        },
        {
            "name": "an xpath selecting a value is refused",
            "arch": "<form><div/></form>",
            "specs": "<data><xpath expr=\"count(//div)\" position=\"inside\"><b/></xpath></data>",
            "error": "must select elements"
        },
        {
            "name": "an xpath selecting text is refused",
            "arch": "<form><div>t</div></form>",
            "specs": "<data><xpath expr=\"//div/text()\" position=\"inside\"><b/></xpath></data>",
            "error": "must select elements"
        },
        {
            "name": "an invalid xpath is refused",
            "arch": "<form><div/></form>",
            "specs": "<data><xpath expr=\"//div[\" position=\"inside\"><b/></xpath></data>",
            "error": "Invalid Expression"
        },
        {
            "name": "an xpath takes the first match in document order",
            "arch": "<form><div id=\"1\"><div id=\"2\"/></div><div id=\"3\"/></form>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"x\">1</attribute></xpath></data>",
            "result": "<form><div id=\"1\" x=\"1\"><div id=\"2\"/></div><div id=\"3\"/></form>"
        },
        {
            "name": "hasclass finds one class among others",
            "arch": "<form><div class=\"d abc e\"/></form>",
            "specs": "<data><xpath expr=\"//div[hasclass('abc')]\" position=\"replace\"></xpath></data>",
            "result": "<form/>"
        },
        {
            "name": "hasclass is not a substring test",
            "arch": "<form><div class=\"abcd\"/></form>",
            "specs": "<data><xpath expr=\"//div[hasclass('abc')]\" position=\"replace\"></xpath></data>",
            "error": "cannot be located"
        },
        {
            "name": "hasclass with several classes needs them all",
            "arch": "<form><div class=\"a\"/><div class=\"a b\"/></form>",
            "specs": "<data><xpath expr=\"//div[hasclass('a', 'b')]\" position=\"attributes\"><attribute name=\"id\">x</attribute></xpath></data>",
            "result": "<form><div class=\"a\"/><div class=\"a b\" id=\"x\"/></form>"
        },
        {
            "name": "hasclass splits on any whitespace",
            "arch": "<form><div class=\"a&#10;b&#9;c\"/></form>",
            "specs": "<data><xpath expr=\"//div[hasclass('b')]\" position=\"replace\"></xpath></data>",
            "result": "<form/>"
        },
        {
            "name": "hasclass takes double quotes",
            "arch": "<form><div class=\"a\"/></form>",
            "specs": "<data><xpath expr=\"//div[hasclass(&quot;a&quot;)]\" position=\"replace\"></xpath></data>",
            "result": "<form/>"
        },
        {
            "name": "hasclass never matches a name holding a space",
            "arch": "<form><div class=\"a b\"/></form>",
            "specs": "<data><xpath expr=\"//div[hasclass('a b')]\" position=\"replace\"></xpath></data>",
            "error": "cannot be located"
        },
        {
            "name": "hasclass combines with other predicates",
            "arch": "<form><div class=\"a\" id=\"1\"/><div class=\"a\" id=\"2\"/></form>",
            "specs": "<data><xpath expr=\"//div[hasclass('a') and @id='2']\" position=\"replace\"></xpath></data>",
            "result": "<form><div class=\"a\" id=\"1\"/></form>"
        },
        {
            "name": "a nested data applies where it stands",
            "arch": "<form><a/></form>",
            "specs": "<data><a position=\"after\"><b/></a><data><a position=\"after\"><c/></a></data><a position=\"after\"><d/></a></data>",
            "result": "<form><a/><d/><c/><b/></form>"
        },
        {
            "name": "comments between specs are skipped",
            "arch": "<form><a/></form>",
            "specs": "<data><!-- note --><a position=\"after\"><b/></a></data>",
            "result": "<form><a/><b/></form>"
        },
        {
            "name": "add to a list defaults to a comma",
            "arch": "<form><field name=\"a\" groups=\"g1\"/></form>",
            "specs": "<data><field name=\"a\" position=\"attributes\"><attribute name=\"groups\" add=\"g2\"/></field></data>",
            "result": "<form><field name=\"a\" groups=\"g1,g2\"/></form>"
        },
        {
            "name": "remove from a comma list",
            "arch": "<form><field name=\"a\" groups=\"g1,g2,g3\"/></form>",
            "specs": "<data><field name=\"a\" position=\"attributes\"><attribute name=\"groups\" remove=\"g2\"/></field></data>",
            "result": "<form><field name=\"a\" groups=\"g1,g3\"/></form>"
        },
        {
            "name": "a space separator edits classes",
            "arch": "<div class=\"a b\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"class\" add=\"c\" remove=\"a\" separator=\" \"/></xpath></data>",
            "result": "<div class=\"b c\"/>"
        },
        {
            "name": "a space separator splits on any whitespace",
            "arch": "<div class=\"a&#10;b&#9;c\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"class\" remove=\"b\" separator=\" \"/></xpath></data>",
            "result": "<div class=\"a c\"/>"
        },
        {
            "name": "a semicolon separator edits styles",
            "arch": "<div style=\"color: red; margin: 0;\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"style\" add=\"padding: 1px\" separator=\";\"/></xpath></data>",
            "result": "<div style=\"color: red;margin: 0;padding: 1px\"/>"
        },
        {
            "name": "removing the last value drops the attribute",
            "arch": "<div class=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"class\" remove=\"a\" separator=\" \"/></xpath></data>",
            "result": "<div/>"
        },
        {
            "name": "add creates a missing list attribute",
            "arch": "<div/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"class\" add=\"x\" separator=\" \"/></xpath></data>",
            "result": "<div class=\"x\"/>"
        },
        {
            "name": "an empty separator is refused",
            "arch": "<div class=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"class\" add=\"x\" separator=\"\"/></xpath></data>",
            "error": "Invalid separator"
        },
        {
            "name": "add keeps a value already present",
            "arch": "<div class=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"class\" add=\"a\" separator=\" \"/></xpath></data>",
            "result": "<div class=\"a a\"/>"
        },
        {
            "name": "add joins an expression with and",
            "arch": "<div invisible=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" add=\"b\" separator=\"and\"/></xpath></data>",
            "result": "<div invisible=\"(a) and (b)\"/>"
        },
        {
            "name": "the operator separator may carry spaces",
            "arch": "<div invisible=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" add=\"b\" separator=\" or \"/></xpath></data>",
            "result": "<div invisible=\"(a) or (b)\"/>"
        },
        {
            "name": "add to a missing expression is the term alone",
            "arch": "<div/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" add=\"b\" separator=\"or\"/></xpath></data>",
            "result": "<div invisible=\"b\"/>"
        },
        {
            "name": "t-if takes the && operator",
            "arch": "<div t-if=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"t-if\" add=\"b\" separator=\"&amp;&amp;\"/></xpath></data>",
            "result": "<div t-if=\"(a) &amp;&amp; (b)\"/>"
        },
        {
            "name": "t-elif takes the || operator",
            "arch": "<div t-elif=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"t-elif\" add=\"b\" separator=\"||\"/></xpath></data>",
            "result": "<div t-elif=\"(a) || (b)\"/>"
        },
        {
            "name": "decoration attributes are expressions",
            "arch": "<div decoration-danger=\"x\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"decoration-danger\" add=\"y\" separator=\"or\"/></xpath></data>",
            "result": "<div decoration-danger=\"(x) or (y)\"/>"
        },
        {
            "name": "an expression needs a separator",
            "arch": "<div t-if=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"t-if\" add=\"x\"/></xpath></data>",
            "error": "needs a separator"
        },
        {
            "name": "a comma does not join an expression",
            "arch": "<div t-if=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"t-if\" add=\"x\" separator=\",\"/></xpath></data>",
            "error": "Invalid separator"
        },
        {
            "name": "a space does not join an expression",
            "arch": "<div t-if=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"t-if\" add=\"x\" separator=\" \"/></xpath></data>",
            "error": "Invalid separator"
        },
        {
            "name": "remove takes out a whole operand",
            "arch": "<div invisible=\"a and b and c\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" remove=\"b\" separator=\"and\"/></xpath></data>",
            "result": "<div invisible=\"a and c\"/>"
        },
        {
            "name": "remove is not a substring test",
            "arch": "<div invisible=\"ba and c\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" remove=\"a\" separator=\"and\"/></xpath></data>",
            "result": "<div invisible=\"ba and c\"/>"
        },
        {
            "name": "remove honours word boundaries",
            "arch": "<div invisible=\"a or order\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" remove=\"order\" separator=\"or\"/></xpath></data>",
            "result": "<div invisible=\"a\"/>"
        },
        {
            "name": "remove skips operators inside quotes",
            "arch": "<div invisible=\"x == &apos;a and b&apos; and c\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" remove=\"c\" separator=\"and\"/></xpath></data>",
            "result": "<div invisible=\"x == 'a and b'\"/>"
        },
        {
            "name": "remove takes out a run of operands",
            "arch": "<div invisible=\"a and b and c\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" remove=\"a and b\" separator=\"and\"/></xpath></data>",
            "result": "<div invisible=\"c\"/>"
        },
        {
            "name": "remove reaches a term an earlier add wrapped",
            "arch": "<div invisible=\"((a) and (b)) and (c)\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" remove=\"b\" separator=\"and\"/></xpath></data>",
            "result": "<div invisible=\"((a)) and (c)\"/>"
        },
        {
            "name": "remove reaches across another operator",
            "arch": "<div invisible=\"((a) or (b)) and (c)\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" remove=\"b\" separator=\"or\"/></xpath></data>",
            "result": "<div invisible=\"((a)) and (c)\"/>"
        },
        {
            "name": "remove never empties a group",
            "arch": "<div invisible=\"(b) or c\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" remove=\"b\" separator=\"and\"/></xpath></data>",
            "result": "<div invisible=\"(b) or c\"/>"
        },
        {
            "name": "removing every operand drops the attribute",
            "arch": "<div invisible=\"((a))\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" remove=\"a\" separator=\"and\"/></xpath></data>",
            "result": "<div/>"
        },
        {
            "name": "remove then add",
            "arch": "<div invisible=\"a and b\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" remove=\"b\" add=\"c\" separator=\"and\"/></xpath></data>",
            "result": "<div invisible=\"(a) and (c)\"/>"
        },
        {
            "name": "removing an absent term changes nothing",
            "arch": "<div invisible=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"invisible\" remove=\"z\" separator=\"or\"/></xpath></data>",
            "result": "<div invisible=\"a\"/>"
        },
        {
            "name": "remove with the && operator",
            "arch": "<div t-if=\"a &amp;&amp; b\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"t-if\" remove=\"b\" separator=\"&amp;&amp;\"/></xpath></data>",
            "result": "<div t-if=\"a\"/>"
        },
        {
            "name": "an unknown key on attribute is refused",
            "arch": "<div class=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"class\" add=\"b\" separator=\" \" sepparator=\",\"/></xpath></data>",
            "error": "Invalid attributes"
        },
        {
            "name": "a data-oe key on attribute is allowed",
            "arch": "<div class=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"class\" data-oe-id=\"1\">b</attribute></xpath></data>",
            "result": "<div class=\"b\"/>"
        },
        {
            "name": "add with text is refused",
            "arch": "<div class=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute name=\"class\" add=\"b\" separator=\" \">c</attribute></xpath></data>",
            "error": "cannot contain text"
        },
        {
            "name": "an attribute without name is refused",
            "arch": "<div class=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attribute>b</attribute></xpath></data>",
            "error": "missing its 'name'"
        },
        {
            "name": "only attribute elements may edit attributes",
            "arch": "<div class=\"a\"/>",
            "specs": "<data><xpath expr=\"//div\" position=\"attributes\"><attributes name=\"class\">b</attributes></xpath></data>",
            "error": "Invalid element <attributes>"
        },
        {
            "name": "inside appends text",
            "arch": "<p>a</p>",
            "specs": "<data><xpath expr=\"/p\" position=\"inside\">b</xpath></data>",
            "result": "<p>ab</p>"
        },
        {
            "name": "before inserts text",
            "arch": "<p>x<b/></p>",
            "specs": "<data><xpath expr=\"//b\" position=\"before\">y</xpath></data>",
            "result": "<p>xy<b/></p>"
        },
        {
            "name": "after inserts text",
            "arch": "<p><b/>z</p>",
            "specs": "<data><xpath expr=\"//b\" position=\"after\">y</xpath></data>",
            "result": "<p><b/>yz</p>"
        },
        {
            "name": "replace inner puts text",
            "arch": "<p>x<b/>y</p>",
            "specs": "<data><xpath expr=\"/p\" position=\"replace\" mode=\"inner\">t</xpath></data>",
            "result": "<p>t</p>"
        },
        {
            "name": "inside an indented group",
            "arch": "<form>\n    <group>\n        <field name=\"a\"/>\n    </group>\n</form>",
            "specs": "<data>\n    <xpath expr=\"//group\" position=\"inside\">\n        <field name=\"b\"/>\n    </xpath>\n</data>",
            "result": "<form>\n    <group>\n        <field name=\"a\"/>\n        <field name=\"b\"/>\n    </group>\n</form>"
        },
        {
            "name": "after an indented field",
            "arch": "<form>\n    <group>\n        <field name=\"a\"/>\n    </group>\n</form>",
            "specs": "<data>\n    <xpath expr=\"//field\" position=\"after\">\n        <field name=\"b\"/>\n    </xpath>\n</data>",
            "result": "<form>\n    <group>\n        <field name=\"a\"/>\n        <field name=\"b\"/>\n    </group>\n</form>"
        },
        {
            "name": "before an indented field",
            "arch": "<form>\n    <group>\n        <field name=\"a\"/>\n    </group>\n</form>",
            "specs": "<data>\n    <xpath expr=\"//field\" position=\"before\">\n        <field name=\"b\"/>\n    </xpath>\n</data>",
            "result": "<form>\n    <group>\n        <field name=\"b\"/>\n        <field name=\"a\"/>\n    </group>\n</form>"
        },
        {
            "name": "replace an indented field",
            "arch": "<form>\n    <group>\n        <field name=\"a\"/>\n    </group>\n</form>",
            "specs": "<data>\n    <xpath expr=\"//field\" position=\"replace\">\n        <field name=\"b\"/>\n    </xpath>\n</data>",
            "result": "<form>\n    <group>\n        <field name=\"b\"/>\n    </group>\n</form>"
        },
        {
            "name": "replace inner of an indented group",
            "arch": "<form>\n    <group>\n        <field name=\"a\"/>\n    </group>\n</form>",
            "specs": "<data>\n    <xpath expr=\"//group\" position=\"replace\" mode=\"inner\">\n        <field name=\"b\"/>\n    </xpath>\n</data>",
            "result": "<form>\n    <group>\n        <field name=\"b\"/></group>\n</form>"
        },
        {
            "name": "move an indented field",
            "arch": "<form>\n    <group>\n        <field name=\"a\"/>\n        <field name=\"b\"/>\n    </group>\n</form>",
            "specs": "<data>\n    <xpath expr=\"//field[@name='a']\" position=\"before\">\n        <xpath expr=\"//field[@name='b']\" position=\"move\"/>\n    </xpath>\n</data>",
            "result": "<form>\n    <group>\n        <field name=\"b\"/>\n        <field name=\"a\"/>\n        \n    </group>\n</form>"
        },
        {
            "name": "$0 stands where its text stands",
            "arch": "<form><field name=\"a\"/></form>",
            "specs": "<data><xpath expr=\"//field\" position=\"replace\"><div>$0<b/></div></xpath></data>",
            "result": "<form><div><field name=\"a\"/><b/></div></form>"
        },
        {
            "name": "$0 may follow a sibling",
            "arch": "<form><field name=\"a\"/></form>",
            "specs": "<data><xpath expr=\"//field\" position=\"replace\"><div><b/>$0</div></xpath></data>",
            "result": "<form><div><b/><field name=\"a\"/></div></form>"
        },
        {
            "name": "$0 copies the target without the text after it",
            "arch": "<p><span>a</span> units</p>",
            "specs": "<data><xpath expr=\"//span\" position=\"replace\"><b>$0</b></xpath></data>",
            "result": "<p><b><span>a</span></b> units</p>"
        },
        {
            "name": "a replace with nothing takes the target's layout with it",
            "arch": "<form>\n    <field name=\"a\"/>\n    <field name=\"b\"/>\n</form>",
            "specs": "<data>\n    <xpath expr=\"//field[@name='a']\" position=\"replace\"/>\n</data>",
            "result": "<form>\n    <field name=\"b\"/>\n</form>"
        },
        {
            "name": "replace keeps the text after a moved node",
            "arch": "<p><i/><span/></p>",
            "specs": "<data><xpath expr=\"//span\" position=\"replace\"><xpath expr=\"//i\" position=\"move\"></xpath> after</xpath></data>",
            "result": "<p><i/> after</p>"
        },
        {
            "name": "hasclass without a class matches any element",
            "arch": "<form><div/></form>",
            "specs": "<data><xpath expr=\"//div[hasclass()]\" position=\"replace\"></xpath></data>",
            "result": "<form/>"
        },
        {
            "name": "text-only content gives way to the target's indentation",
            "arch": "<t><div><span class=\"a\"/>\n        <span class=\"b\"/>\n    </div></t>",
            "specs": "<data><xpath expr=\"//span[@class='b']\" position=\"before\">just text</xpath></data>",
            "result": "<t><div><span class=\"a\"/>just text\n        <span class=\"b\"/>\n    </div></t>"
        },
        {
            "name": "the content's trailing text gives way to the target's indentation",
            "arch": "<t><div><span class=\"a\"/>\n        <span class=\"b\"/>\n    </div></t>",
            "specs": "<data><xpath expr=\"//span[@class='b']\" position=\"before\"><p class=\"new\"/> </xpath></data>",
            "result": "<t><div><span class=\"a\"/><p class=\"new\"/>\n        <span class=\"b\"/>\n    </div></t>"
        },
        {
            "name": "after keeps the indentation that follows the target",
            "arch": "<t><div><span class=\"a\"/>\n        <span class=\"b\"/>\n    </div></t>",
            "specs": "<data><xpath expr=\"//span[@class='a']\" position=\"after\"><p class=\"new\"/></xpath></data>",
            "result": "<t><div><span class=\"a\"/><p class=\"new\"/>\n        <span class=\"b\"/>\n    </div></t>"
        },
        {
            "name": "inside keeps the closing indentation",
            "arch": "<t><div>\n        <span class=\"a\"/>\n    </div></t>",
            "specs": "<data><xpath expr=\"//div\" position=\"inside\"><p class=\"new\"/></xpath></data>",
            "result": "<t><div>\n        <span class=\"a\"/><p class=\"new\"/>\n    </div></t>"
        },
        {
            "name": "replace keeps the indentation that followed the target",
            "arch": "<t><div><span class=\"a\"/>\n        <span class=\"b\"/>\n    </div></t>",
            "specs": "<data><xpath expr=\"//span[@class='b']\" position=\"replace\"><p class=\"new\"/></xpath></data>",
            "result": "<t><div><span class=\"a\"/>\n        <p class=\"new\"/>\n    </div></t>"
        },
        {
            "name": "replace inner drops the content's trailing whitespace",
            "arch": "<t> <div> A <span/> B <span/> C </div> </t>",
            "specs": "<data><xpath expr=\"./div\" position=\"replace\" mode=\"inner\"> E <div/> F <span attr1=\"12\"/> </xpath></data>",
            "result": "<t> <div> E <div/> F <span attr1=\"12\"/></div> </t>"
        },
        {
            "name": "a moved node carries the text that followed its spec",
            "arch": "<t> <div> AAB is the best <h2>Title</h2> <div id=\"1\"/> <div id=\"2\"/> </div> </t>",
            "specs": "<data><xpath expr=\"./div/h2\" position=\"after\"> Hop! <xpath expr=\"./div/div[@id=2]\" position=\"move\" /> <span>Yellow</span> </xpath></data>",
            "result": "<t> <div> AAB is the best <h2>Title</h2> Hop! <div id=\"2\"/> <span>Yellow</span> <div id=\"1\"/>  </div> </t>"
        }
    ]
}
`).cases;
