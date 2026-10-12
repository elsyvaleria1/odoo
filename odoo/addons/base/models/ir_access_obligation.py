from typing import Any

from odoo import models


class IrAccessObligation(models.AbstractModel):
    _name = "ir.access.obligation"
    _description = "Access Obligation"

    def _at_door(self, records: models.BaseModel, verb: str, call: Any) -> Any:
        with records.env.transaction.admitting(records._name, verb, records._ids):
            return call(records)

    def _at_checkpoint(self, records: models.BaseModel, verb: str) -> None:
        return

    def _after_move(self, records: models.BaseModel, verb: str) -> None:
        return

    def _explain_obligations(self, record: models.BaseModel, verb: str) -> list[dict]:
        return []
