import pkgutil
from uuid import uuid4

import boto3
import pytest

from moto import mock_aws
from tests.markers import requires_docker

from .utilities import _process_lambda, get_role_name

PYTHON_VERSION = "python3.11"
_lambda_region = "us-west-2"


def get_requests_zip_file():
    pfunc = """
import requests
def lambda_handler(event, context):
    return requests.__version__
"""
    return _process_lambda(pfunc)


@requires_docker
@mock_aws
@pytest.mark.filterwarnings("ignore:Error extracting layer to Lambda")
def test_invoke_local_lambda_layers():
    conn = boto3.client("lambda", _lambda_region)
    lambda_name = str(uuid4())[0:6]
    #
    # Info about KLayers, including ARNs
    # https://api.klayers.cloud/api/v2/p3.11/layers/latest/us-east-1/json
    #
    # Get all info about a specific layer
    # aws lambda get-layer-version-by-arn --arn "..."
    #
    # Download layer as a ZIP file
    # curl $(aws lambda get-layer-version-by-arn --arn "..." --query "Content.Location" --output text) --output klayer.zip
    requests_location = "resources/klayer_311_16.zip"
    requests_layer = pkgutil.get_data(__name__, requests_location)

    layer_arn = conn.publish_layer_version(
        LayerName=str(uuid4())[0:6],
        Content={"ZipFile": requests_layer},
        CompatibleRuntimes=["python3.11"],
        LicenseInfo="MIT",
    )["LayerArn"]

    bogus_layer_arn = conn.publish_layer_version(
        LayerName=str(uuid4())[0:6],
        Content={"ZipFile": b"zipfile"},
        CompatibleRuntimes=["python3.11"],
        LicenseInfo="MIT",
    )["LayerArn"]

    function_arn = conn.create_function(
        FunctionName=lambda_name,
        Runtime="python3.11",
        Role=get_role_name(),
        Handler="lambda_function.lambda_handler",
        Code={"ZipFile": get_requests_zip_file()},
        Timeout=3,
        MemorySize=128,
        Publish=True,
        Layers=[f"{layer_arn}:1", f"{bogus_layer_arn}:1"],
    )["FunctionArn"]

    success_result = conn.invoke(
        FunctionName=function_arn, Payload="{}", LogType="Tail"
    )
    msg = success_result["Payload"].read().decode("utf-8")
    assert msg == '"2.32.3"'
