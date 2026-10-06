from odoo.addons.integration.tools.api_client import get_api_client


class GitHubClientBase:
    def __init__(self, env, company_id=None) -> None:
        self.env = env
        self.company_id = company_id
        self._client = get_api_client(env, "github", company_id)

    def paginate(self, url, params=None, max_pages=10):
        params = params or {}
        params.setdefault("per_page", 100)

        page = 1
        while page <= max_pages:
            params["page"] = page
            response = self._client.get(url, params=params)
            items = response["body"]

            if not items:
                break

            yield from items

            page += 1

    def graphql_query(self, query, variables=None):
        payload = {"query": query}

        if variables:
            payload["variables"] = variables

        return self._client.post("/graphql", json=payload)["body"]

    def get_authenticated_user(self):
        return self._client.get("/user")["body"]

    def get_user(self, username):
        return self._client.get(f"/users/{username}")["body"]

    def get_organization(self, org):
        return self._client.get(f"/orgs/{org}")["body"]
