import re
from urllib.parse import quote, unquote, urlsplit

import boto3
from botocore.exceptions import ClientError

from odoo.exceptions import UserError
from odoo.libs.json import dumps as json_dumps

PARAM_BUCKET = "cloud_storage_s3_bucket_name"
PARAM_REGION = "cloud_storage_s3_region"
PARAM_ENDPOINT = "cloud_storage_s3_endpoint_url"
# cloud_storage_provider values served by this module; every one speaks S3
PROVIDERS = ("s3", "ovh")
CREDENTIAL_CATEGORY_XMLID = "cloud_storage_s3.credential_category_cloud_storage_s3"
CREDENTIAL_NAME = "Cloud Storage S3"

AWS_URL_PATTERN = re.compile(
    r"^https://(?P<bucket_name>[\w\-.]+)\.s3\.(?P<region>[\w\-.]+)\.amazonaws\.com/(?P<blob_name>[^?]+)$"
)

_ClientCache = {}


def get_credential(env):
    category = env.ref(CREDENTIAL_CATEGORY_XMLID, raise_if_not_found=False)
    if not category:
        return env["credential.credential"].sudo()
    return (
        env["credential.credential"]
        .sudo()
        .search(
            [("category_id", "=", category.id), ("active", "=", True)],
            order="write_date desc, id desc",
            limit=1,
        )
    )


def get_keys(env):
    credential = get_credential(env)
    keys = credential.get_credential_dict() if credential else {}
    if not (keys.get("access_key_id") and keys.get("secret_access_key")):
        return {}
    return keys


def store_keys(env, access_key_id, secret_access_key) -> None:
    payload = json_dumps(
        {"access_key_id": access_key_id, "secret_access_key": secret_access_key}
    )
    credential = get_credential(env)
    if credential:
        credential.credential_data = payload
    else:
        env["credential.credential"].sudo().create(
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
    return normalize_endpoint(
        env["ir.config_parameter"].sudo().get_param(PARAM_ENDPOINT)
    )


def get_config(env):
    icp = env["ir.config_parameter"].sudo()
    credential = get_credential(env)
    config = {
        "bucket_name": icp.get_param(PARAM_BUCKET),
        "region": icp.get_param(PARAM_REGION),
        "credential": f"{credential.id}:{credential.write_date}"
        if credential and credential.storage_method == "json"
        else False,
    }
    if not all(config.values()):
        return {}
    config["endpoint_url"] = get_endpoint(env)
    if not config["endpoint_url"] and icp.get_param("cloud_storage_provider") == "ovh":
        # without its endpoint an OVHcloud bucket would be looked up on Amazon
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
    keys = get_keys(env)
    if not keys:
        raise UserError(env._("The S3 access keys are missing or unreadable."))
    client = boto3.client(  # noqa: E8518 - botocore opens its own connections and takes no requests session
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
    """Split a virtual-hosted object URL into bucket, region and key.

    :param str url: the attachment URL
    :param str region: region reported for URLs of the configured endpoint
    :param str endpoint_url: the configured S3-compatible endpoint, if any
    :return: ``bucket_name``, ``region`` and ``blob_name``, or ``None``
    :rtype: dict | None
    """
    # Amazon URLs stay recognized so attachments stored before an endpoint
    # was configured keep resolving.
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
