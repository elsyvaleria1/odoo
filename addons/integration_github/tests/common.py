import hashlib
import hmac
import pathlib
import uuid

from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tools.files import file_path


def fixture(name: str) -> dict:
    return json_loads(
        pathlib.Path(
            file_path(f"integration_github/tests/data/{name}.json")
        ).read_bytes()
    )


class WebhookDelivery:
    """Deliver a payload as GitHub does: signed with the hook's secret, named by
    its event and a delivery id."""

    @classmethod
    def _create_hook(cls):
        cls.hook = cls.env["integration.github.webhook"].create({"name": "App"})
        action = cls.hook.action_issue_secret()
        cls.secret = action["params"]["message"].split("\n", 1)[0]

    def _deliver(self, event, payload, *, delivery=None, secret=None, hook=None):
        self.env.flush_all()
        body = json_dumps(payload).encode()
        signature = hmac.new(
            (secret or self.secret).encode(), body, hashlib.sha256
        ).hexdigest()
        response = self.url_open(
            f"/integration_github/webhook/{(hook or self.hook).hook_uuid}",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": event,
                "X-GitHub-Delivery": delivery or str(uuid.uuid4()),
                "X-Hub-Signature-256": f"sha256={signature}",
            },
        )
        self.env.invalidate_all()
        return response
