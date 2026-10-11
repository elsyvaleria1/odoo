import re
from urllib.parse import urlsplit

from lxml import etree, html

from odoo.tools.misc import hmac, register_signed_scope

from odoo.addons.website.theme_colors import ELEMENT_KEYS, PRESET_KEYS

FORM_SIGNATURE_SCOPE = register_signed_scope(
    "website_form_signature",
    purpose="the recipients a mail form was rendered with, so a visitor cannot "
    "redirect the mail it sends",
    lifetime="undated: carried by the rendered page",
)

THEME_VALUES_URL = "/website/static/src/scss/options/user_values.scss"

COLOR_PALETTE_URL = "/website/static/src/scss/options/colors/user_color_palette.scss"

THEME_COLOR_PALETTE_URL = (
    "/website/static/src/scss/options/colors/user_theme_color_palette.scss"
)

GRAY_COLOR_PALETTE_URL = (
    "/website/static/src/scss/options/colors/user_gray_color_palette.scss"
)

THEME_CUSTOMIZATION_URLS = {
    "values": THEME_VALUES_URL,
    "palette": COLOR_PALETTE_URL,
    "theme_palette": THEME_COLOR_PALETTE_URL,
    "gray_palette": GRAY_COLOR_PALETTE_URL,
}
THEME_CUSTOMIZATION_GROUPS = {
    url: group for group, url in THEME_CUSTOMIZATION_URLS.items()
}

RUNTIME_HEADING_KEYS = frozenset(
    f"{level}-{prop}"
    for level in (
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "display-1",
        "display-2",
        "display-3",
        "display-4",
    )
    for prop in ("line-height", "margin-top", "margin-bottom")
)

RE_LENGTHS = re.compile(
    r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:px|rem|em|%)?(?: -?(?:\d+(?:\.\d*)?|\.\d+)(?:px|rem|em|%)?){0,3}"
)

RE_MENU_BOX_VALUES = {
    "menu-border-width": RE_LENGTHS,
    "menu-border-radius": RE_LENGTHS,
    "menu-border-style": re.compile(
        r"none|hidden|dotted|dashed|solid|double|groove|ridge|inset|outset"
    ),
    "menu-box-shadow": re.compile(r"none|[\w\s(),.%#-]+"),
}

RUNTIME_HEADING_SIZE_KEYS = frozenset(
    {
        *(f"h{level}-font-size" for level in range(1, 7)),
        *(f"display-{level}-font-size" for level in range(1, 5)),
    }
)

RUNTIME_THEME_KEYS = (
    frozenset(
        {
            "paragraph-margin-top",
            "paragraph-margin-bottom",
            "headings-line-height",
            "headings-margin-top",
            "headings-margin-bottom",
            "btn-padding-y",
            "btn-padding-y-sm",
            "btn-padding-y-lg",
            "btn-border-width",
            "btn-border-radius",
            "btn-border-radius-sm",
            "btn-border-radius-lg",
            "input-border-width",
            "input-border-radius-sm",
            "input-border-radius-lg",
            "btn-padding-x",
            "btn-padding-x-sm",
            "btn-padding-x-lg",
            "input-padding-y",
            "input-padding-y-sm",
            "input-padding-y-lg",
            "input-padding-x",
            "input-padding-x-sm",
            "input-padding-x-lg",
            "btn-font-size",
            "btn-font-size-sm",
            "btn-font-size-lg",
            "input-font-size",
            "input-font-size-sm",
            "input-font-size-lg",
            "btn-primary-outline-border-width",
            "btn-secondary-outline-border-width",
            "sidebar-width",
            "header-font-size",
            "logo-height",
            "body-line-height",
            "small-font-size",
            "fixed-logo-height",
            "input-border-radius",
        }
    )
    | frozenset(RE_MENU_BOX_VALUES)
    | RUNTIME_HEADING_KEYS
    | RUNTIME_HEADING_SIZE_KEYS
)

RUNTIME_FONT_SIZE_KEYS = frozenset(
    {
        *(
            f"{part}-font-size{size}"
            for part in ("btn", "input")
            for size in ("", "-sm", "-lg")
        ),
        "small-font-size",
    }
)

RFS_BASE_REM = 1.25
RFS_REM_PX = 16

RUNTIME_PRESET_KEYS = frozenset(
    f"o-cc{index}-{key}" for index in range(2, 6) for key in PRESET_KEYS
)

RUNTIME_GRADIENT_KEYS = frozenset(
    {
        *(f"o-cc{index}-bg-gradient" for index in range(1, 6)),
        "menu-gradient",
        "menu-secondary-gradient",
        "footer-gradient",
        "copyright-gradient",
    }
)

RUNTIME_PALETTE_KEYS = RUNTIME_PRESET_KEYS | ELEMENT_KEYS

SALES_HEADER_KEYS = frozenset(
    key for key in ELEMENT_KEYS if key.startswith("header-sales_")
)

RUNTIME_SET_ONLY_KEYS = frozenset(
    {
        "header-font-size",
        "logo-height",
        "header-text-color",
        "menu-border-width",
        "menu-border-radius",
        "menu-box-shadow",
        "fixed-logo-height",
        "input-border-radius",
    }
)

RUNTIME_THEME_COLOR_KEYS = frozenset({"header-text-color", "menu-border-color"})

RUNTIME_KEYS_BY_URL = {
    THEME_VALUES_URL: RUNTIME_THEME_KEYS
    | RUNTIME_GRADIENT_KEYS
    | RUNTIME_THEME_COLOR_KEYS,
    COLOR_PALETTE_URL: RUNTIME_PALETTE_KEYS | {"menu-border-color"},
}

RUNTIME_KEYS = frozenset().union(*RUNTIME_KEYS_BY_URL.values())

RE_THEME_LENGTH = re.compile(r"-?(?:\d+(?:\.\d*)?|\.\d+)(?:px|rem|em|%)?")

UNSET_THEME_VALUES = frozenset({"", "null", "NULL"})

UNSET_OVERRIDE_VALUES = frozenset({"", "null"})

RE_THEME_GRADIENT = re.compile(
    r"(?:repeating-)?(?:linear|radial|conic)-gradient\([\w\s(),.%#+-]*\)"
)

THEME_GRADIENT_FUNCTIONS = frozenset(
    {
        *(
            f"{repeating}{shape}-gradient"
            for repeating in ("", "repeating-")
            for shape in ("linear", "radial", "conic")
        ),
        "rgb",
        "rgba",
        "hsl",
        "hsla",
    }
)


def is_theme_gradient(value) -> bool:
    return RE_THEME_GRADIENT.fullmatch(value) is not None and all(
        name in THEME_GRADIENT_FUNCTIONS for name in re.findall(r"([\w-]+)\(", value)
    )


RE_SCSS_MAP_ENTRY = re.compile(r"^ *'(?P<key>[\w-]+)': (?P<value>.+),\n", re.MULTILINE)


def distance(s1="", s2="", limit=4):
    BIG = 100000
    if len(s1) > len(s2):
        s1, s2 = s2, s1
    l1 = len(s1)
    l2 = len(s2)
    if l2 - l1 > limit:
        return -1
    boundary = min(l1, limit) + 1
    p = [i if i < boundary else BIG for i in range(l1 + 1)]
    d = [BIG for _ in range(l1 + 1)]
    for j in range(1, l2 + 1):
        j2 = s2[j - 1]
        d[0] = j
        range_min = max(1, j - limit)
        range_max = min(l1, j + limit)
        if range_min > 1:
            d[range_min - 1] = BIG
        for i in range(range_min, range_max + 1):
            if s1[i - 1] == j2:
                d[i] = p[i - 1]
            else:
                d[i] = 1 + min(d[i - 1], p[i], p[i - 1])
        p, d = d, p
    return p[l1] if p[l1] <= limit else -1


def similarity_score(s1, s2):
    dist = distance(s1, s2)
    if dist == -1:
        return -1
    if not s1 or not s2:
        return -1
    set1 = set(s1)
    score = len(set1.intersection(s2)) / len(set1)
    score -= dist / len(s1)
    score -= len(set1.symmetric_difference(s2)) / (len(s1) + len(s2))
    return score


_TEXT_EXCLUDED_XPATHS = (
    "//script",
    "//style",
    "//svg",
    '//*[@class="css_non_editable_mode_hidden"]',
)


def _remove_keeping_tail(element) -> None:
    parent = element.getparent()
    if parent is None:
        return
    if element.tail:
        previous = element.getprevious()
        if previous is not None:
            previous.tail = (previous.tail or "") + element.tail
        else:
            parent.text = (parent.text or "") + element.tail
    parent.remove(element)


def text_from_html(html_fragment, collapse_whitespace=False):
    tree = html.fromstring("<div>%s</div>" % (html_fragment or ""))

    for xpath_filter in _TEXT_EXCLUDED_XPATHS:
        for element in tree.xpath(xpath_filter):
            _remove_keeping_tail(element)

    content = " ".join(tree.itertext())
    if collapse_whitespace:
        content = re.sub(r"\s+", " ", content).strip()
    return content


def get_base_hostname(url, strip_www=False):
    if not url:
        return ""

    url = urlsplit(url).netloc
    if strip_www and url.startswith("www."):
        url = url[4:]
    return url


def website_form_signature_payload(email_to, extra_recipients) -> str:
    parts = [email_to or ""]
    parts.extend(
        "%s=%s" % (name, extra_recipients[name])
        for name in ("email_cc", "email_bcc")
        if extra_recipients.get(name)
    )
    return "\x00".join(parts)


def add_form_signature(html_fragment, env_sudo) -> None:
    for form in html_fragment.iter("form"):
        if "/website/form/" not in form.attrib.get("action", ""):
            continue

        existing_hash_node = form.find(
            './/input[@type="hidden"][@name="website_form_signature"]'
        )
        if existing_hash_node is not None:
            existing_hash_node.getparent().remove(existing_hash_node)
        input_nodes = form.xpath('.//input[contains(@name, "email_")]')
        form_values = {
            input_node.attrib["name"]: input_node for input_node in input_nodes
        }
        if "email_to" not in form_values:
            continue

        email_to_value = form_values["email_to"].attrib.get("value")
        if not email_to_value or (
            email_to_value == "info@yourcompany.example.com"
            and html_fragment.xpath('//span[@data-for="contactus_form"]')
        ):
            email_to_value = env_sudo.company.email or ""

        extra_recipients = {
            name: form_values[name].attrib.get("value") or ""
            for name in ("email_cc", "email_bcc")
            if name in form_values
        }
        value = website_form_signature_payload(email_to_value, extra_recipients)
        hash_value = hmac(env_sudo, FORM_SIGNATURE_SCOPE, value)
        hash_node = etree.Element(
            "input",
            attrib={
                "type": "hidden",
                "value": hash_value,
                "class": "form-control s_website_form_input s_website_form_custom",
                "name": "website_form_signature",
            },
        )
        form_values["email_to"].addnext(hash_node)


def create_image_attachment(env, image_path, image_name):
    Attachments = env["ir.attachment"]
    return Attachments.create(
        {
            "public": True,
            "name": image_name,
            "type": "url",
            "url": Attachments.get_base_url() + image_path,
        }
    )
