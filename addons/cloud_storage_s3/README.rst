Cloud Storage S3
================

Store Odoo attachments in Amazon S3 using the built-in cloud storage provider framework.

Configuration
-------------

Go to **Settings → Technical → Cloud Storage** and select *Amazon S3*.
Fill in the S3 bucket name, AWS region, access key ID, and secret access key.

Click **Test Connection** to validate the credentials and configure CORS on the bucket.

Required IAM permissions
------------------------

The IAM user needs the following S3 permissions on the configured bucket::

    s3:PutObject
    s3:GetObject
    s3:DeleteObject
    s3:PutBucketCors

Reading the source's blobs from a neutralized copy
--------------------------------------------------

Neutralization drops the storage settings, so a restored copy of the
production database cannot reach its bucket and every cloud attachment shows
empty. On a developer machine, a read-only key lets that copy show them
without being able to change the bucket. Export these variables in the
environment that starts Odoo (for example in ``~/.bashrc``)::

    export ODOO_CLOUD_READONLY_ENDPOINT=s3.bhs.io.cloud.ovh.net
    export ODOO_CLOUD_READONLY_REGION=bhs
    export ODOO_CLOUD_READONLY_KEY_ID=<access key of the read-only user>
    export ODOO_CLOUD_READONLY_SECRET=<its secret>

They are used only when ``database.is_neutralized`` is set. The copy then reads
and signs downloads with that key, while ``cloud_storage_s3_enabled`` stays
unset, so it never uploads, moves or deletes a blob. The key must belong to a
storage user whose policy grants only ``s3:GetObject``, ``s3:ListBucket`` and
``s3:GetBucketLocation`` on the bucket, so the store refuses any write even
if one were attempted. Never put it in a database or in a neutralization
script.
