import os
import re
from urllib.parse import quote, unquote, urlsplit

import boto3
from botocore.exceptions import ClientError

from odoo.exceptions import UserError
from odoo.libs.json import dumps as json_dumps

PARAM_BUCKET = "cloud_storage_s3_bucket_name"
PARAM_REGION = "cloud_storage_s3_region"
PARAM_ENDPOINT = "cloud_storage_s3_endpoint_url"
PROVIDERS = ("s3", "ovh")
CREDENTIAL_CATEGORY_XMLID = "cloud_storage_s3.credential_category_cloud_storage_s3"
CREDENTIAL_NAME = "Cloud Storage S3"

AWS_URL_PATTERN = re.compile(
    r"^https://(?P<bucket_name>[\w\-.]+)\.s3\.(?P<region>[\w\-.]+)\.amazonaws\.com/(?P<blob_name>[^?]+)$"
)

# A neutralized copy has no storage settings (neutralize.sql drops them), so it
# cannot reach the source's bucket. On a developer machine these variables
# give it a key that can only read that bucket: its documents show, and
# nothing it does can write or delete there. The key lives in the machine's
# environment, never in a database or in the neutralization.
READONLY_ENVIRON = {
    "endpoint": "ODOO_CLOUD_READONLY_ENDPOINT",
    "region": "ODOO_CLOUD_READONLY_REGION",
    "access_key_id": "ODOO_CLOUD_READONLY_KEY_ID",
    "secret_access_key": "ODOO_CLOUD_READONLY_SECRET",
}

_ClientCache = {}


def get_readonly_source(env) -> dict:
    """The read-only key of a neutralized copy, or ``{}`` anywhere else."""
    neutralized = env.registry.settings.get(env, "database.is_neutralized", False)
    if str(neutralized).lower() != "true":
        return {}
    values = {
        name: os.environ.get(variable, "").strip()
        for name, variable in READONLY_ENVIRON.items()
    }
    if not all(values.values()):
        return {}
    values["endpoint"] = normalize_endpoint(values["endpoint"])
    return values


def get_credential(env, credentials=None):
    if credentials is None:
        credentials = env["credential.credential"].with_privilege(
            "cloud_storage_s3.privilege_read_s3_credential",
            reason="sign S3 requests with the storage keys",
        )
    category = env.ref(CREDENTIAL_CATEGORY_XMLID, raise_if_not_found=False)
    if not category:
        return credentials
    return credentials.search(
        [("category_id", "=", category.id), ("active", "=", True)],
        order="write_date desc, id desc",
        limit=1,
    )


def get_keys(env):
    credential = get_credential(env)
    keys = (
        credential.sudo()._use_secret_payload("cloud_storage_s3:sign")
        if credential
        else {}
    )
    if not (keys.get("access_key_id") and keys.get("secret_access_key")):
        return {}
    return keys


def store_keys(env, access_key_id, secret_access_key) -> None:
    payload = json_dumps(
        {"access_key_id": access_key_id, "secret_access_key": secret_access_key}
    )
    credential = get_credential(
        env,
        env["credential.credential"].with_privilege(
            "cloud_storage_s3.privilege_store_s3_credential",
            reason="store the S3 keys entered in Settings",
        ),
    )
    if credential:
        credential.credential_data = payload
    else:
        credential.create(
            {
                "name": CREDENTIAL_NAME,
                "category_id": env.ref(CREDENTIAL_CATEGORY_XMLID).id,
                "credential_data": payload,
            }
        )
    clear_cache(env)


def normalize_endpoint(endpoint) -> str:
    endpoint = (endpoint or "").strip().rstrip("/")
    if endpoint and "://" not in endpoint:
        endpoint = f"https://{endpoint}"
    return endpoint


def get_endpoint(env) -> str:
    endpoint = env.registry.settings.get(env, PARAM_ENDPOINT, False)
    if not endpoint:
        endpoint = get_readonly_source(env).get("endpoint")
    return normalize_endpoint(endpoint)


def get_config(env):
    settings = env.registry.settings
    credential = get_credential(env)
    config = {
        "bucket_name": settings.get(env, PARAM_BUCKET, False),
        "region": settings.get(env, PARAM_REGION, False),
        "credential": f"{credential.id}:{credential.write_date}"
        if credential and credential.storage_method == "json"
        else False,
    }
    if not all(config.values()):
        readonly = get_readonly_source(env)
        if not readonly:
            return {}
        return {
            "bucket_name": False,
            "region": readonly["region"],
            "credential": f"readonly:{readonly['access_key_id']}",
            "endpoint_url": readonly["endpoint"],
            "readonly": True,
        }
    config["endpoint_url"] = get_endpoint(env)
    if (
        not config["endpoint_url"]
        and settings.get(env, "cloud_storage_provider", False) == "ovh"
    ):
        return {}
    return config


def get_client(env):
    config = get_config(env)
    if not config:
        raise UserError(
            env._(
                "S3 storage is not fully configured: set the bucket, region, "
                "keys and, for OVHcloud, the endpoint in Settings → Cloud Storage."
            )
        )
    signature = (config["region"], config["endpoint_url"], config["credential"])
    db_name = env.registry.db_name
    cached_signature, cached_client = _ClientCache.get(db_name, (None, None))
    if cached_signature == signature and cached_client:
        return cached_client
    keys = get_readonly_source(env) if config.get("readonly") else get_keys(env)
    if not keys:
        raise UserError(env._("The S3 access keys are missing or unreadable."))
    client = boto3.client(  # noqa: E8518 -- botocore opens its own connections and takes no requests session
        "s3",
        aws_access_key_id=keys["access_key_id"],
        aws_secret_access_key=keys["secret_access_key"],
        region_name=config["region"],
        endpoint_url=config["endpoint_url"] or None,
    )
    _ClientCache[db_name] = (signature, client)
    return client


def clear_cache(env=None) -> None:
    if env is None:
        _ClientCache.clear()
    else:
        _ClientCache.pop(env.registry.db_name, None)


def object_exists(client, bucket, key) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in (
            "404",
            "NoSuchKey",
            "NotFound",
        ):
            return False
        raise
    return True


def object_url(bucket, region, key, endpoint_url="") -> str:
    if endpoint_url:
        host = urlsplit(normalize_endpoint(endpoint_url)).netloc
        return f"https://{bucket}.{host}/{quote(key)}"
    return f"https://{bucket}.s3.{region}.amazonaws.com/{quote(key)}"


def parse_object_url(url, region, endpoint_url=""):
    match = AWS_URL_PATTERN.fullmatch(url or "")
    if match:
        return {
            "bucket_name": match["bucket_name"],
            "region": match["region"],
            "blob_name": unquote(match["blob_name"]),
        }
    if not endpoint_url:
        return None
    host = urlsplit(normalize_endpoint(endpoint_url)).netloc
    match = re.fullmatch(
        rf"https://(?P<bucket_name>[\w\-.]+)\.{re.escape(host)}/(?P<blob_name>[^?]+)",
        url or "",
    )
    if not match:
        return None
    return {
        "bucket_name": match["bucket_name"],
        "region": region,
        "blob_name": unquote(match["blob_name"]),
    }
