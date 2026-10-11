import logging

from odoo import tools

_logger = logging.getLogger(__name__)


def post_init_hook(env) -> None:
    _load_unspsc_codes(env)
    _update_uom_codes(env)
    demo_product = env.ref("product.consu_delivery_03", raise_if_not_found=False)
    if demo_product:
        _update_demo_codes(env)


def uninstall_hook(env):
    env.cr.execute("DELETE FROM product_unspsc_code;")
    env.cr.execute("DELETE FROM ir_model_data WHERE model='product.unspsc.code';")


def _load_unspsc_codes(env) -> None:
    csv_path = "product_unspsc/data/product.unspsc.code.csv"
    with tools.misc.file_open(csv_path, "rb") as csv_file:
        csv_file.readline()
        with env.cr.copy(
            "COPY product_unspsc_code (code, name, applies_to, active)"
            " FROM STDIN WITH (FORMAT csv, DELIMITER '|',"
            " QUOTE E'\\x01', NULL E'\\x02')"
        ) as copy:
            while data := csv_file.read(8192):
                copy.write(data)
    env.cr.execute(
        """INSERT INTO ir_model_data
           (name, res_id, module, model, noupdate)
           SELECT concat('unspsc_code_', code), id, 'product_unspsc', 'product.unspsc.code', 't'
           FROM product_unspsc_code"""
    )


def _update_uom_codes(env) -> None:
    tools.convert.convert_file(
        env, "product_unspsc", "data/product_data.xml", None, mode="init"
    )


def _update_demo_codes(env) -> None:
    tools.convert.convert_file(
        env, "product_unspsc", "demo/product_demo.xml", None, mode="init"
    )
