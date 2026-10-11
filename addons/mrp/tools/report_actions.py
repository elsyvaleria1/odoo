from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    from odoo.api import Environment


class OverviewRecordAction(TypedDict):
    type: Literal["ir.actions.act_window"]
    res_model: str
    res_id: int
    views: list[tuple[Literal[False], Literal["form"]]]
    target: Literal["current"]


def prepare_overview_record_action(
    env: Environment, report_id: int, line_id: str
) -> OverviewRecordAction:
    report = env["report.formula"].browse(report_id)
    model, record_id = report._get_model_info_from_id(line_id)
    return {
        "type": "ir.actions.act_window",
        "res_model": model,
        "res_id": record_id,
        "views": [(False, "form")],
        "target": "current",
    }
