from lxml import etree

from . import controllers
from . import models
from . import wizards

from odoo.exceptions import UserError


def pre_init_knowledge(env) -> None:
    """Some lxml arm64 versions cannot decode icons and cause the installation to crash.
    This will test to decode an emoji before the installation of the app, and show
    a helper message if it crashed.
    """
    try:
        etree.fromstring("<p>😀</p>")
    except etree.XMLSyntaxError:
        raise UserError(
            env._(
                "The version of the lxml package used is not supported. "
                "Consider reinstalling lxml package using 'pip install --nobinary :all: lxml'"
            )
        ) from None


def _uninstall_knowledge(env) -> None:
    env.cr.execute("""
        DROP TEXT SEARCH CONFIGURATION IF EXISTS knowledge_config CASCADE;
    """)
    env.cr.execute("""
        DROP TEXT SEARCH DICTIONARY IF EXISTS knowledge_dictionary;
    """)


def _init_private_article_per_user(env) -> None:
    env["res.users"].search([("partner_share", "=", False)])._create_tutorial_articles()
