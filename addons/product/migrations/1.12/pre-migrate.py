from odoo.db.schema import column_exists, create_column
from odoo.exceptions import UserError

LINE = "product_template_attribute_line"


def migrate(cr, version):
    if not version:
        return
    if not column_exists(cr, LINE, "purpose"):
        create_column(cr, LINE, "purpose", "varchar")
        cr.execute("UPDATE product_template_attribute_line SET purpose = 'variant'")

    cr.execute(
        """
        WITH line AS (
            SELECT line.id, line.product_tmpl_id, line.attribute_id,
                   (SELECT count(*)
                      FROM product_attribute_value_product_template_attribute_line_rel rel
                     WHERE rel.product_template_attribute_line_id = line.id) AS value_count,
                   EXISTS (
                       SELECT 1
                         FROM product_attribute_value_product_template_attribute_line_rel rel
                         JOIN product_attribute_value value
                           ON value.id = rel.product_attribute_value_id
                        WHERE rel.product_template_attribute_line_id = line.id
                          AND value.is_custom
                   ) AS has_custom_value,
                   EXISTS (
                       SELECT 1
                         FROM product_template_attribute_value ptav
                        WHERE ptav.attribute_line_id = line.id
                          AND ptav.ptav_active
                          AND COALESCE(ptav.price_extra, 0) != 0
                   ) AS has_price_extra
              FROM product_template_attribute_line line
             WHERE line.active
        )
        SELECT line.product_tmpl_id, line.attribute_id, array_agg(line.id ORDER BY line.id),
               bool_and(
                   line.value_count = 1
                   AND NOT line.has_custom_value
                   AND NOT line.has_price_extra
               )
               AND attribute.display_type IS DISTINCT FROM 'multi'
          FROM line
          JOIN product_attribute attribute ON attribute.id = line.attribute_id
      GROUP BY line.product_tmpl_id, line.attribute_id, attribute.display_type
        HAVING count(*) > 1
      ORDER BY line.product_tmpl_id, line.attribute_id
        """
    )
    groups = cr.fetchall()
    refused = [group for group in groups if not group[3]]
    if refused:
        raise UserError(
            "product 1.12 keeps each attribute on one line per product. An attribute"
            " repeated on lines of one ordinary value each becomes a specification on"
            " its own; these products repeat an attribute on a line of several values,"
            " of a custom value, or of a multi-choice attribute, where each line may be"
            " a separate input a customer gives, or on a line whose value adds an extra"
            " price, which a specification does not charge. Merge each group into one"
            " line (or use a second attribute; move an extra price into the sales"
            " price), then upgrade again:\n"
            + "\n".join(
                f"- product.template {template_id}, product.attribute {attribute_id}:"
                f" lines {line_ids}"
                for template_id, attribute_id, line_ids, _single in refused
            )
        )
    for _template_id, _attribute_id, line_ids, _single in groups:
        _fold_into_specification(cr, line_ids)


def _fold_into_specification(cr, line_ids):
    kept, folded = line_ids[0], line_ids[1:]
    cr.execute(
        """
        INSERT INTO product_attribute_value_product_template_attribute_line_rel
               (product_template_attribute_line_id, product_attribute_value_id)
        SELECT %s, product_attribute_value_id
          FROM product_attribute_value_product_template_attribute_line_rel
         WHERE product_template_attribute_line_id = ANY(%s)
        ON CONFLICT DO NOTHING
        """,
        [kept, folded],
    )
    cr.execute(
        """
        DELETE FROM product_attribute_value_product_template_attribute_line_rel
         WHERE product_template_attribute_line_id = ANY(%s)
        """,
        [folded],
    )
    cr.execute(
        "UPDATE product_template_attribute_line SET purpose = 'specification' WHERE id = %s",
        [kept],
    )
    cr.execute(
        "UPDATE product_template_attribute_line SET active = false WHERE id = ANY(%s)",
        [folded],
    )
    # A specification is no variant dimension: its values leave every variant
    # and are archived, not deleted, since documents may still name them.
    cr.execute(
        """
        UPDATE product_template_attribute_value
           SET ptav_active = false
         WHERE attribute_line_id = ANY(%s)
     RETURNING id
        """,
        [line_ids],
    )
    value_ids = [row[0] for row in cr.fetchall()]
    cr.execute(
        """
        DELETE FROM product_variant_combination
         WHERE product_template_attribute_value_id = ANY(%s)
     RETURNING product_product_id
        """,
        [value_ids],
    )
    variant_ids = sorted({row[0] for row in cr.fetchall()})
    if variant_ids:
        cr.execute(
            """
            UPDATE product_product variant
               SET combination_indices = COALESCE(
                       (SELECT string_agg(
                                   combination.product_template_attribute_value_id::text,
                                   ',' ORDER BY combination.product_template_attribute_value_id)
                          FROM product_variant_combination combination
                         WHERE combination.product_product_id = variant.id),
                       '')
             WHERE variant.id = ANY(%s)
            """,
            [variant_ids],
        )
