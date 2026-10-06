import re

from odoo.tests import BaseCase, tagged
from odoo.tools import file_open


def _read(path):
    with file_open(path) as f:
        return f.read()


def _js_icon_classes():
    source = _read("web/static/src/core/utils/icons.js")
    styles = re.search(r"FA_STYLE_CLASSES = \[([^\]]*)\]", source).group(1)
    classes = re.search(r"iconClasses = \[([^\]]*)\]", source).group(1)
    classes = classes.replace("...FA_STYLE_CLASSES", styles)
    return re.findall(r'"([\w-]+)"', classes)


def _scss_icon_classes():
    source = _read("web/static/src/webclient/icons.variables.scss")
    value = re.search(r'\$o-icon-selector:\s*"([^"]*)"', source).group(1)
    return [cls.strip().removeprefix(".") for cls in value.split(",")]


@tagged("post_install", "-at_install", "web_unit")
class TestIconClasses(BaseCase):
    def test_the_stylesheets_and_the_scripts_name_the_same_icons(self):
        self.assertEqual(_scss_icon_classes(), _js_icon_classes())
        self.assertIn("fa-solid", _js_icon_classes())
