from uuid import uuid4

from odoo.tests.common import TransactionCase


class SpreadsheetTestCase(TransactionCase):
    def new_revision_data(self, spreadsheet, **kwargs):
        return {
            "id": spreadsheet.id,
            "model": spreadsheet._name,
            "type": "REMOTE_REVISION",
            "clientId": "john",
            "commands": [{"type": "A_COMMAND"}],
            "nextRevisionId": uuid4().hex,
            "serverRevisionId": spreadsheet.current_revision_uuid,
            **kwargs,
        }

    def snapshot(self, spreadsheet, current_revision_uuid, snapshot_revision_id, data):
        return spreadsheet.dispatch_spreadsheet_message(
            {
                "type": "SNAPSHOT",
                "nextRevisionId": snapshot_revision_id,
                "serverRevisionId": current_revision_uuid,
                "data": data,
            }
        )
