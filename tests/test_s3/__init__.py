import os
from functools import wraps
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

from moto import mock_aws
from moto.s3.responses import DEFAULT_REGION_NAME


def s3_aws_verified(func):
    """
    Function that is verified to work against AWS.
    Can be run against AWS at any time by setting:
      MOTO_TEST_ALLOW_AWS_REQUEST=true

    If this environment variable is not set, the function runs in a `mock_aws` context.

    This decorator will:
      - Create a bucket
      - Run the test and pass the bucket_name as an argument
      - Delete the objects and the bucket itself
    """

    @wraps(func)
    def pagination_wrapper(**kwargs):
        bucket_name = str(uuid4())

        allow_aws_request = (
            os.environ.get("MOTO_TEST_ALLOW_AWS_REQUEST", "false").lower() == "true"
        )

        if allow_aws_request:
            print(f"Test {func} will create {bucket_name}")  # noqa: T201
            resp = create_bucket_and_test(bucket_name, **kwargs)
        else:
            with mock_aws():
                resp = create_bucket_and_test(bucket_name, **kwargs)
        return resp

    def create_bucket_and_test(bucket_name, **kwargs):
        client = boto3.client("s3", region_name=DEFAULT_REGION_NAME)

        client.create_bucket(Bucket=bucket_name)
        client.put_bucket_tagging(
            Bucket=bucket_name,
            Tagging={"TagSet": [{"Key": "environment", "Value": "moto_tests"}]},
        )
        try:
            resp = func(**kwargs, bucket_name=bucket_name)
        finally:
            ### CLEANUP ###

            empty_bucket(client, bucket_name)
            client.delete_bucket(Bucket=bucket_name)

        return resp

    return pagination_wrapper


def empty_bucket(client, bucket_name):
    # Delete any object lock config, if set before
    try:
        client.get_object_lock_configuration(Bucket=bucket_name)
        kwargs = {"BypassGovernanceRetention": True}
    except ClientError:
        # No ObjectLock set
        kwargs = {}

    versions = client.list_object_versions(Bucket=bucket_name).get("Versions", [])
    for key in versions:
        client.delete_object(
            Bucket=bucket_name, Key=key["Key"], VersionId=key.get("VersionId"), **kwargs
        )
    delete_markers = client.list_object_versions(Bucket=bucket_name).get(
        "DeleteMarkers", []
    )
    for key in delete_markers:
        client.delete_object(
            Bucket=bucket_name, Key=key["Key"], VersionId=key.get("VersionId"), **kwargs
        )


def generate_content_md5(content: bytes) -> str:
    import base64
    import hashlib

    md = hashlib.md5(content).digest()
    content_md5 = base64.b64encode(md).decode("utf-8")
    return content_md5
