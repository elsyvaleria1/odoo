from odoo.libs.parse_version import parse_version
from odoo.modules.module import adapt_version
from odoo.tools.module_data import drop_views, fold_module, move_xmlids

# resource_asset 2.0 moved the asset tree onto resource_resource; its
# migrations leave with the module, so no database may cross the fold below it
RESOURCE_ASSET_FOLDABLE = "2.0"


def _prepare_resource_asset_fold(cr) -> bool:
    cr.execute(
        "SELECT db_version FROM ir_module_module "
        "WHERE name = 'resource_asset' AND state != 'uninstalled'"
    )
    if not (row := cr.fetchone()):
        return False
    (installed,) = row
    if parse_version(installed or "") < parse_version(
        adapt_version(RESOURCE_ASSET_FOLDABLE)
    ):
        raise RuntimeError(
            f"resource_asset is at {installed}: upgrade it to "
            f"{RESOURCE_ASSET_FOLDABLE} on a commit before its fold into "
            "resource, then upgrade again"
        )
    # the kind column it added to resource's list is now that list's own
    drop_views(cr, "resource_asset", ["resource_identifier_type_view_list"])
    # it switched resource's administrator right off for an identical row of
    # its own, which no longer ships
    cr.execute(
        """
        UPDATE ir_access SET active = TRUE
         WHERE id = (SELECT res_id FROM ir_model_data
                      WHERE module = 'resource'
                        AND name = 'access_resource_assignment_system_cud')
        """
    )
    return True


def migrate(cr, version):
    if not version:
        return
    # an asset is a resource of a kind: the module that added the kind to
    # resource.resource dissolves into it, and its messages into resource_mail
    if not _prepare_resource_asset_fold(cr):
        return
    fold_module(cr, "resource_asset", "resource")
    # what posts a hand-over is resource_mail's
    move_xmlids(
        cr,
        ["mt_asset_operator_updated", "mt_asset_future_operator_scheduled"],
        "resource",
        "resource_mail",
    )
