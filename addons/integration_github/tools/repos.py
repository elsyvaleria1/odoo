class RepositoryMixin:
    def get_repository(self, owner, repo):
        return self._client.get(f"/repos/{owner}/{repo}")["body"]

    def list_repositories(
        self,
        org=None,
        user=None,
        repo_type="all",
        sort="updated",
        per_page=100,
        max_pages=10,
    ):
        if org:
            url = f"/orgs/{org}/repos"
        elif user:
            url = f"/users/{user}/repos"
        else:
            url = "/user/repos"

        params = {"type": repo_type, "sort": sort, "per_page": per_page}
        return list(self.paginate(url, params=params, max_pages=max_pages))

    def create_repository(
        self,
        name,
        description=None,
        private=False,
        org=None,
        **kwargs,
    ):
        payload = {
            "name": name,
            "private": private,
            **kwargs,
        }

        if description:
            payload["description"] = description

        if org:
            url = f"/orgs/{org}/repos"
        else:
            url = "/user/repos"

        return self._client.post(url, json=payload)["body"]

    def list_branches(self, owner, repo, protected=None, per_page=100, max_pages=10):
        params = {"per_page": per_page}

        if protected is not None:
            params["protected"] = protected
        return list(
            self.paginate(
                f"/repos/{owner}/{repo}/branches",
                params=params,
                max_pages=max_pages,
            ),
        )

    def get_branch(self, owner, repo, branch):
        return self._client.get(f"/repos/{owner}/{repo}/branches/{branch}")["body"]

    def list_commits(
        self,
        owner,
        repo,
        sha=None,
        path=None,
        author=None,
        per_page=100,
        max_pages=10,
    ):
        params = {"per_page": per_page}

        if sha:
            params["sha"] = sha
        if path:
            params["path"] = path
        if author:
            params["author"] = author
        return list(
            self.paginate(
                f"/repos/{owner}/{repo}/commits",
                params=params,
                max_pages=max_pages,
            )
        )

    def get_commit(self, owner, repo, ref):
        return self._client.get(f"/repos/{owner}/{repo}/commits/{ref}")["body"]

    def list_webhooks(self, owner, repo, per_page=100, max_pages=10):
        params = {"per_page": per_page}
        return list(
            self.paginate(
                f"/repos/{owner}/{repo}/hooks",
                params=params,
                max_pages=max_pages,
            ),
        )

    def create_webhook(
        self,
        owner,
        repo,
        url,
        events=None,
        active=True,
        content_type="json",
        secret=None,
    ):
        if events is None:
            events = ["push"]

        config = {
            "url": url,
            "content_type": content_type,
        }

        if secret:
            config["secret"] = secret

        payload = {
            "name": "web",
            "active": active,
            "events": events,
            "config": config,
        }

        return self._client.post(f"/repos/{owner}/{repo}/hooks", json=payload)["body"]

    def remove_webhook(self, owner, repo, hook_id) -> bool:
        response = self._client.delete(f"/repos/{owner}/{repo}/hooks/{hook_id}")
        return response["status_code"] == 204
