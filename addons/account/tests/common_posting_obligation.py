from contextlib import contextmanager
from unittest.mock import patch

from odoo.exceptions import UserError


def _is_invoice(move):
    return move.move_type != "entry"


@contextmanager
def holding_invoice_posting(env, holds=_is_invoice):
    """An obligation on posting that holds every move `holds` names (every
    invoice-type move by default), as an approval required of each would: its
    door asks instead of posting, and its checkpoint refuses. A move the
    transaction admitted for `post` passes."""
    Obligation = type(env["ir.access.obligation"])
    at_door, at_checkpoint = Obligation._at_door, Obligation._at_checkpoint

    def held(moves):
        admitted = moves.env.transaction.admitted_ids(moves._name, "post")
        return moves.filtered(lambda move: holds(move) and move.id not in admitted)

    def holding_door(self, records, verb, call):
        if records._name == "account.move" and verb == "post" and held(records):
            return None
        return at_door(self, records, verb, call)

    def holding_checkpoint(self, records, verb):
        if records._name == "account.move" and verb == "post" and held(records):
            raise UserError("held for approval")
        return at_checkpoint(self, records, verb)

    with (
        patch.object(Obligation, "_at_door", holding_door),
        patch.object(Obligation, "_at_checkpoint", holding_checkpoint),
        patch.object(type(env["account.move"]), "_get_held_for_posting_approval", held),
    ):
        yield


def exemption_notes(moves, reason):
    return moves.message_ids.filtered(
        lambda message: f"({reason})" in str(message.body)
    )
