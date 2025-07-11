import json
import random
import unittest
import warnings
from datetime import datetime, timezone
from time import sleep
from uuid import uuid4

import boto3
import pytest
from botocore.exceptions import ClientError

from moto import mock_aws, settings
from moto.core import DEFAULT_ACCOUNT_ID as ACCOUNT_ID
from moto.core.utils import iso_8601_datetime_without_milliseconds
from tests import allow_aws_request, aws_verified

RULES = [
    {"Name": "test1", "ScheduleExpression": "rate(5 minutes)"},
    {
        "Name": "test2",
        "ScheduleExpression": "rate(1 minute)",
        "Tags": [{"Key": "tagk1", "Value": "tagv1"}],
    },
    {"Name": "test3", "EventPattern": '{"source": ["test-source"]}'},
]

TARGETS = {
    "test-target-1": {
        "Id": "test-target-1",
        "Arn": "arn:aws:lambda:us-west-2:111111111111:function:test-function-1",
        "Rules": ["test1", "test2"],
    },
    "test-target-2": {
        "Id": "test-target-2",
        "Arn": "arn:aws:lambda:us-west-2:111111111111:function:test-function-2",
        "Rules": ["test1", "test3"],
    },
    "test-target-3": {
        "Id": "test-target-3",
        "Arn": "arn:aws:lambda:us-west-2:111111111111:function:test-function-3",
        "Rules": ["test1", "test2"],
    },
    "test-target-4": {
        "Id": "test-target-4",
        "Arn": "arn:aws:lambda:us-west-2:111111111111:function:test-function-4",
        "Rules": ["test1", "test3"],
    },
    "test-target-5": {
        "Id": "test-target-5",
        "Arn": "arn:aws:lambda:us-west-2:111111111111:function:test-function-5",
        "Rules": ["test1", "test2"],
    },
    "test-target-6": {
        "Id": "test-target-6",
        "Arn": "arn:aws:lambda:us-west-2:111111111111:function:test-function-6",
        "Rules": ["test1", "test3"],
    },
}


def get_random_rule():
    return RULES[random.randint(0, len(RULES) - 1)]


def generate_environment(add_targets=True):
    client = boto3.client("events", "us-west-2")

    for rule in RULES:
        client.put_rule(
            Name=rule["Name"],
            ScheduleExpression=rule.get("ScheduleExpression", ""),
            EventPattern=rule.get("EventPattern", ""),
            Tags=rule.get("Tags", []),
        )

        if add_targets:
            targets = []
            for target in TARGETS:
                if rule["Name"] in TARGETS[target].get("Rules"):
                    targets.append({"Id": target, "Arn": TARGETS[target]["Arn"]})

            client.put_targets(Rule=rule["Name"], Targets=targets)

    return client


@mock_aws
def test_put_rule():
    client = boto3.client("events", "us-west-2")
    assert len(client.list_rules()["Rules"]) == 0

    rule_data = {
        "Name": "my-event",
        "ScheduleExpression": "rate(5 minutes)",
        "EventPattern": '{"source": ["test-source"]}',
    }

    client.put_rule(**rule_data)

    rules = client.list_rules()["Rules"]

    assert len(rules) == 1
    assert rules[0]["Name"] == rule_data["Name"]
    assert rules[0]["ScheduleExpression"] == rule_data["ScheduleExpression"]
    assert rules[0]["EventPattern"] == rule_data["EventPattern"]
    assert rules[0]["State"] == "ENABLED"


@mock_aws
def test_put_rule__where_event_bus_name_is_arn():
    client = boto3.client("events", "us-west-2")
    event_bus_name = "test-bus"
    event_bus_arn = client.create_event_bus(Name=event_bus_name)["EventBusArn"]

    rule_arn = client.put_rule(
        Name="my-event",
        EventPattern='{"source": ["test-source"]}',
        EventBusName=event_bus_arn,
    )["RuleArn"]
    assert rule_arn == f"arn:aws:events:us-west-2:{ACCOUNT_ID}:rule/test-bus/my-event"


@mock_aws
def test_put_rule_error_schedule_expression_custom_event_bus():
    # given
    client = boto3.client("events", "eu-central-1")
    event_bus_name = "test-bus"
    client.create_event_bus(Name=event_bus_name)

    # when
    with pytest.raises(ClientError) as e:
        client.put_rule(
            Name="test-rule",
            ScheduleExpression="rate(5 minutes)",
            EventBusName=event_bus_name,
        )

    # then
    ex = e.value
    assert ex.operation_name == "PutRule"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"]
        == "ScheduleExpression is supported only on the default event bus."
    )


@mock_aws
def test_list_rules():
    client = generate_environment()
    response = client.list_rules()
    rules = response["Rules"]
    assert len(rules) == len(RULES)


@mock_aws
def test_list_rules_with_token():
    client = generate_environment()
    response = client.list_rules()
    assert "NextToken" not in response
    rules = response["Rules"]
    assert len(rules) == len(RULES)
    #
    response = client.list_rules(Limit=1)
    assert "NextToken" in response
    rules = response["Rules"]
    assert len(rules) == 1
    #
    response = client.list_rules(NextToken=response["NextToken"])
    assert "NextToken" not in response
    rules = response["Rules"]
    assert len(rules) == 2


@mock_aws
def test_list_rules_with_prefix_and_token():
    client = generate_environment()
    response = client.list_rules(NamePrefix="test")
    assert "NextToken" not in response
    rules = response["Rules"]
    assert len(rules) == len(RULES)
    #
    response = client.list_rules(NamePrefix="test", Limit=1)
    assert "NextToken" in response
    rules = response["Rules"]
    assert len(rules) == 1
    #
    response = client.list_rules(NamePrefix="test", NextToken=response["NextToken"])
    assert "NextToken" not in response
    rules = response["Rules"]
    assert len(rules) == 2


@mock_aws
def test_describe_rule():
    rule_name = get_random_rule()["Name"]
    client = generate_environment()
    response = client.describe_rule(Name=rule_name)

    assert response["Name"] == rule_name
    assert response["Arn"] == f"arn:aws:events:us-west-2:{ACCOUNT_ID}:rule/{rule_name}"


@mock_aws
def test_describe_rule_with_event_bus_name():
    # given
    client = boto3.client("events", "eu-central-1")
    event_bus_name = "test-bus"
    rule_name = "test-rule"
    client.create_event_bus(Name=event_bus_name)
    client.put_rule(
        Name=rule_name,
        EventPattern=json.dumps({"account": [ACCOUNT_ID]}),
        State="DISABLED",
        Description="test rule",
        RoleArn=f"arn:aws:iam::{ACCOUNT_ID}:role/test-role",
        EventBusName=event_bus_name,
    )

    # when
    response = client.describe_rule(Name=rule_name, EventBusName=event_bus_name)

    # then
    assert (
        response["Arn"]
        == f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:rule/{event_bus_name}/{rule_name}"
    )
    assert response["CreatedBy"] == ACCOUNT_ID
    assert response["Description"] == "test rule"
    assert response["EventBusName"] == event_bus_name
    assert json.loads(response["EventPattern"]) == {"account": [ACCOUNT_ID]}
    assert response["Name"] == rule_name
    assert response["RoleArn"] == f"arn:aws:iam::{ACCOUNT_ID}:role/test-role"
    assert response["State"] == "DISABLED"

    assert "ManagedBy" not in response
    assert "ScheduleExpression" not in response


@mock_aws
def test_enable_disable_rule():
    rule_name = get_random_rule()["Name"]
    client = generate_environment()

    # Rules should start out enabled in these tests.
    rule = client.describe_rule(Name=rule_name)
    assert rule["State"] == "ENABLED"

    client.disable_rule(Name=rule_name)
    rule = client.describe_rule(Name=rule_name)
    assert rule["State"] == "DISABLED"

    client.enable_rule(Name=rule_name)
    rule = client.describe_rule(Name=rule_name)
    assert rule["State"] == "ENABLED"

    # Test invalid name
    with pytest.raises(ClientError) as ex:
        client.enable_rule(Name="junk")

    err = ex.value.response["Error"]
    assert err["Code"] == "ResourceNotFoundException"


@mock_aws
def test_disable_unknown_rule():
    client = generate_environment()

    with pytest.raises(ClientError) as ex:
        client.disable_rule(Name="unknown")
    err = ex.value.response["Error"]
    assert err["Message"] == "Rule unknown does not exist."


@mock_aws
def test_list_rule_names_by_target():
    test_1_target = TARGETS["test-target-1"]
    test_2_target = TARGETS["test-target-2"]
    client = generate_environment()

    rules = client.list_rule_names_by_target(TargetArn=test_1_target["Arn"])
    assert len(rules["RuleNames"]) == len(test_1_target["Rules"])
    for rule in rules["RuleNames"]:
        assert rule in test_1_target["Rules"]

    rules = client.list_rule_names_by_target(TargetArn=test_2_target["Arn"])
    assert len(rules["RuleNames"]) == len(test_2_target["Rules"])
    for rule in rules["RuleNames"]:
        assert rule in test_2_target["Rules"]


@mock_aws
def test_list_rule_names_by_target_using_limit():
    test_1_target = TARGETS["test-target-1"]
    client = generate_environment()

    response = client.list_rule_names_by_target(TargetArn=test_1_target["Arn"], Limit=1)
    assert "NextToken" in response
    assert len(response["RuleNames"]) == 1
    #
    response = client.list_rule_names_by_target(
        TargetArn=test_1_target["Arn"], NextToken=response["NextToken"]
    )
    assert "NextToken" not in response
    assert len(response["RuleNames"]) == 1


@mock_aws
def test_delete_rule():
    client = generate_environment(add_targets=False)

    client.delete_rule(Name=RULES[0]["Name"])
    rules = client.list_rules()
    assert len(rules["Rules"]) == len(RULES) - 1


@mock_aws
def test_delete_rule_with_targets():
    # given
    client = generate_environment()

    # when
    with pytest.raises(ClientError) as e:
        client.delete_rule(Name=RULES[0]["Name"])

    # then
    ex = e.value
    assert ex.operation_name == "DeleteRule"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"] == "Rule can't be deleted since it has targets."
    )


@mock_aws
def test_delete_unknown_rule():
    client = boto3.client("events", "us-west-1")
    resp = client.delete_rule(Name="unknown")

    # this fails silently - it just returns an empty 200. Verified against AWS.
    assert resp["ResponseMetadata"]["HTTPStatusCode"] == 200


@mock_aws
def test_list_targets_by_rule():
    rule_name = get_random_rule()["Name"]
    client = generate_environment()
    targets = client.list_targets_by_rule(Rule=rule_name)

    expected_targets = []
    for target in TARGETS:
        if rule_name in TARGETS[target].get("Rules"):
            expected_targets.append(target)

    assert len(targets["Targets"]) == len(expected_targets)


@mock_aws
def test_list_targets_by_rule_pagination():
    rule_name = "test1"
    client = generate_environment()
    page1 = client.list_targets_by_rule(Rule=rule_name, Limit=1)
    assert len(page1["Targets"]) == 1
    assert "NextToken" in page1

    page2 = client.list_targets_by_rule(Rule=rule_name, NextToken=page1["NextToken"])
    assert len(page2["Targets"]) == 5

    large_page = client.list_targets_by_rule(Rule=rule_name, Limit=4)
    assert len(large_page["Targets"]) == 4


@mock_aws
def test_list_targets_by_rule_for_different_event_bus():
    client = generate_environment()

    client.create_event_bus(Name="newEventBus")

    client.put_rule(Name="test1", EventBusName="newEventBus", EventPattern="{}")
    client.put_targets(
        Rule="test1",
        EventBusName="newEventBus",
        Targets=[
            {
                "Id": "newtarget",
                "Arn": "arn:",
            }
        ],
    )

    # Total targets with this rule is 7, but, from the docs:
    # If you omit [the eventBusName-parameter], the default event bus is used.
    targets = client.list_targets_by_rule(Rule="test1")["Targets"]
    assert len([t["Id"] for t in targets]) == 6

    targets = client.list_targets_by_rule(Rule="test1", EventBusName="default")[
        "Targets"
    ]
    assert len([t["Id"] for t in targets]) == 6

    targets = client.list_targets_by_rule(Rule="test1", EventBusName="newEventBus")[
        "Targets"
    ]
    assert [t["Id"] for t in targets] == ["newtarget"]


@mock_aws
def test_remove_targets():
    rule_name = get_random_rule()["Name"]
    client = generate_environment()

    targets = client.list_targets_by_rule(Rule=rule_name)["Targets"]
    targets_before = len(targets)
    assert targets_before > 0

    response = client.remove_targets(Rule=rule_name, Ids=[targets[0]["Id"]])
    assert response["FailedEntryCount"] == 0
    assert len(response["FailedEntries"]) == 0

    targets = client.list_targets_by_rule(Rule=rule_name)["Targets"]
    targets_after = len(targets)
    assert targets_before - 1 == targets_after


@mock_aws
def test_update_rule_with_targets():
    client = boto3.client("events", "us-west-2")
    client.put_rule(Name="test1", ScheduleExpression="rate(5 minutes)", EventPattern="")

    client.put_targets(
        Rule="test1",
        Targets=[
            {
                "Id": "test-target-1",
                "Arn": "arn:aws:lambda:us-west-2:111111111111:function:test-function-1",
            }
        ],
    )

    targets = client.list_targets_by_rule(Rule="test1")["Targets"]
    targets_before = len(targets)
    assert targets_before == 1

    client.put_rule(Name="test1", ScheduleExpression="rate(1 minute)", EventPattern="")

    targets = client.list_targets_by_rule(Rule="test1")["Targets"]

    assert len(targets) == 1
    assert targets[0].get("Id") == "test-target-1"


@mock_aws
def test_remove_targets_error_unknown_rule():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.remove_targets(Rule="unknown", Ids=["something"])

    # then
    ex = e.value
    assert ex.operation_name == "RemoveTargets"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceNotFoundException"
    assert (
        ex.response["Error"]["Message"]
        == "Rule unknown does not exist on EventBus default."
    )


@mock_aws
def test_put_targets():
    client = boto3.client("events", "us-west-2")
    rule_name = "my-event"
    rule_data = {
        "Name": rule_name,
        "ScheduleExpression": "rate(5 minutes)",
        "EventPattern": '{"source": ["test-source"]}',
    }

    client.put_rule(**rule_data)

    targets = client.list_targets_by_rule(Rule=rule_name)["Targets"]
    targets_before = len(targets)
    assert targets_before == 0

    targets_data = [{"Arn": "arn:aws:s3:::test-arn", "Id": "test_id"}]
    resp = client.put_targets(Rule=rule_name, Targets=targets_data)
    assert resp["FailedEntryCount"] == 0
    assert len(resp["FailedEntries"]) == 0

    targets = client.list_targets_by_rule(Rule=rule_name)["Targets"]
    targets_after = len(targets)
    assert targets_before + 1 == targets_after

    assert targets[0]["Arn"] == "arn:aws:s3:::test-arn"
    assert targets[0]["Id"] == "test_id"


@mock_aws
def test_put_targets_error_invalid_arn():
    # given
    client = boto3.client("events", "eu-central-1")
    rule_name = "test-rule"
    client.put_rule(
        Name=rule_name,
        EventPattern=json.dumps({"account": [ACCOUNT_ID]}),
        State="ENABLED",
    )

    # when
    with pytest.raises(ClientError) as e:
        client.put_targets(
            Rule=rule_name,
            Targets=[
                {"Id": "s3", "Arn": "arn:aws:s3:::test-bucket"},
                {"Id": "s3", "Arn": "test-bucket"},
            ],
        )

    # then
    ex = e.value
    assert ex.operation_name == "PutTargets"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"]
        == "Parameter test-bucket is not valid. Reason: Provided Arn is not in correct format."
    )


@mock_aws
def test_put_targets_error_unknown_rule():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.put_targets(
            Rule="unknown", Targets=[{"Id": "s3", "Arn": "arn:aws:s3:::test-bucket"}]
        )

    # then
    ex = e.value
    assert ex.operation_name == "PutTargets"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceNotFoundException"
    assert (
        ex.response["Error"]["Message"]
        == "Rule unknown does not exist on EventBus default."
    )


@mock_aws
def test_put_targets_error_missing_parameter_sqs_fifo():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.put_targets(
            Rule="unknown",
            Targets=[
                {
                    "Id": "sqs-fifo",
                    "Arn": f"arn:aws:sqs:eu-central-1:{ACCOUNT_ID}:test-queue.fifo",
                }
            ],
        )

    # then
    ex = e.value
    assert ex.operation_name == "PutTargets"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"]
        == "Parameter(s) SqsParameters must be specified for target: sqs-fifo."
    )


@mock_aws
def test_permissions():
    client = boto3.client("events", "eu-central-1")

    client.put_permission(
        Action="events:PutEvents", Principal="111111111111", StatementId="Account1"
    )
    client.put_permission(
        Action="events:PutEvents", Principal="222222222222", StatementId="Account2"
    )

    resp = client.describe_event_bus()
    resp_policy = json.loads(resp["Policy"])
    assert len(resp_policy["Statement"]) == 2

    client.remove_permission(StatementId="Account2")

    resp = client.describe_event_bus()
    resp_policy = json.loads(resp["Policy"])
    assert len(resp_policy["Statement"]) == 1
    assert resp_policy["Statement"][0]["Sid"] == "Account1"


@mock_aws
def test_permission_policy():
    client = boto3.client("events", "eu-central-1")

    policy = {
        "Statement": [
            {
                "Sid": "asdf",
                "Action": "events:PutEvents",
                "Principal": "111111111111",
                "StatementId": "Account1",
                "Effect": "n/a",
                "Resource": "n/a",
            }
        ]
    }
    client.put_permission(Policy=json.dumps(policy))

    resp = client.describe_event_bus()
    resp_policy = json.loads(resp["Policy"])
    assert len(resp_policy["Statement"]) == 1
    assert resp_policy["Statement"][0]["Sid"] == "asdf"


@mock_aws
def test_put_permission_errors():
    client = boto3.client("events", "us-east-1")
    client.create_event_bus(Name="test-bus")

    with pytest.raises(ClientError) as exc:
        client.put_permission(
            EventBusName="non-existing",
            Action="events:PutEvents",
            Principal="111111111111",
            StatementId="test",
        )
    err = exc.value.response["Error"]
    assert err["Message"] == "Event bus non-existing does not exist."

    with pytest.raises(ClientError) as exc:
        client.put_permission(
            EventBusName="test-bus",
            Action="events:PutPermission",
            Principal="111111111111",
            StatementId="test",
        )
    err = exc.value.response["Error"]
    assert err["Message"] == "Provided value in parameter 'action' is not supported."


@mock_aws
def test_remove_permission_errors():
    client = boto3.client("events", "us-east-1")
    client.create_event_bus(Name="test-bus")

    with pytest.raises(ClientError) as exc:
        client.remove_permission(EventBusName="non-existing", StatementId="test")
    err = exc.value.response["Error"]
    assert err["Message"] == "Event bus non-existing does not exist."

    with pytest.raises(ClientError) as exc:
        client.remove_permission(EventBusName="test-bus", StatementId="test")
    err = exc.value.response["Error"]
    assert err["Message"] == "EventBus does not have a policy."

    client.put_permission(
        EventBusName="test-bus",
        Action="events:PutEvents",
        Principal="111111111111",
        StatementId="test",
    )

    with pytest.raises(ClientError) as exc:
        client.remove_permission(EventBusName="test-bus", StatementId="non-existing")
    err = exc.value.response["Error"]
    assert err["Message"] == "Statement with the provided id does not exist."


@mock_aws
def test_put_events():
    client = boto3.client("events", "eu-central-1")

    event = {
        "Source": "com.mycompany.myapp",
        "Detail": '{"key1": "value3", "key2": "value4"}',
        "Resources": ["resource1", "resource2"],
        "DetailType": "myDetailType",
    }

    response = client.put_events(Entries=[event])
    # Boto3 would error if it didn't return 200 OK
    assert response["FailedEntryCount"] == 0
    assert len(response["Entries"]) == 1

    if settings.TEST_DECORATOR_MODE:
        event["Detail"] = json.dumps([{"Key": "k", "Value": "v"}])
        with warnings.catch_warnings(record=True) as ws:
            client.put_events(Entries=[event])
        messages = [str(w.message) for w in ws]
        assert any(["EventDetail should be of type dict" in msg for msg in messages])


@mock_aws
def test_put_events_error_too_many_entries():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.put_events(
            Entries=[
                {
                    "Source": "source",
                    "DetailType": "type",
                    "Detail": '{ "key1": "value1" }',
                },
            ]
            * 11
        )

    # then
    ex = e.value
    assert ex.operation_name == "PutEvents"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"]
        == "1 validation error detected: Value '[PutEventsRequestEntry]' at 'entries' failed to satisfy constraint: Member must have length less than or equal to 10"
    )


@mock_aws
@pytest.mark.parametrize(
    "argument,entries",
    [
        ("Source", [{}]),
        ("Source", [{"Source": ""}]),
        ("DetailType", [{"Source": "source"}]),
        ("DetailType", [{"Source": "source", "DetailType": ""}]),
        ("Detail", [{"Source": "source", "DetailType": "type"}]),
        ("Detail", [{"Source": "source", "DetailType": "typee", "Detail": ""}]),
    ],
)
def test_put_events_error_missing_or_empty_required_argument(argument, entries):
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    response = client.put_events(Entries=entries)

    # then
    assert response["FailedEntryCount"] == 1
    assert len(response["Entries"]) == 1
    assert response["Entries"][0] == {
        "ErrorCode": "InvalidArgument",
        "ErrorMessage": f"Parameter {argument} is not valid. Reason: {argument} is a required argument.",
    }


@mock_aws
def test_put_events_error_invalid_json_detail():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    response = client.put_events(
        Entries=[{"Detail": "detail", "DetailType": "type", "Source": "source"}]
    )

    # then
    assert response["FailedEntryCount"] == 1
    assert len(response["Entries"]) == 1
    assert response["Entries"][0] == {
        "ErrorCode": "MalformedDetail",
        "ErrorMessage": "Detail is malformed.",
    }


@mock_aws
def test_put_events_with_mixed_entries():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    response = client.put_events(
        Entries=[
            {"Source": "source"},
            {"Detail": '{"key": "value"}', "DetailType": "type", "Source": "source"},
            {"Detail": "detail", "DetailType": "type", "Source": "source"},
            {"Detail": '{"key2": "value2"}', "DetailType": "type", "Source": "source"},
        ]
    )

    # then
    assert response["FailedEntryCount"] == 2
    assert len(response["Entries"]) == 4
    assert len([entry for entry in response["Entries"] if "EventId" in entry]) == 2
    assert len([entry for entry in response["Entries"] if "ErrorCode" in entry]) == 2


@mock_aws
def test_create_event_bus():
    client = boto3.client("events", "us-east-1")
    response = client.create_event_bus(Name="test-bus")

    assert (
        response["EventBusArn"]
        == f"arn:aws:events:us-east-1:{ACCOUNT_ID}:event-bus/test-bus"
    )


@mock_aws
def test_create_event_bus_errors():
    client = boto3.client("events", "us-east-1")
    client.create_event_bus(Name="test-bus")

    with pytest.raises(ClientError) as exc:
        client.create_event_bus(Name="test-bus")
    err = exc.value.response["Error"]
    assert err["Message"] == "Event bus test-bus already exists."

    # the 'default' name is already used for the account's default event bus.
    with pytest.raises(ClientError) as exc:
        client.create_event_bus(Name="default")
    err = exc.value.response["Error"]
    assert err["Message"] == "Event bus default already exists."

    # non partner event buses can't contain the '/' character
    with pytest.raises(ClientError) as exc:
        client.create_event_bus(Name="test/test-bus")
    err = exc.value.response["Error"]
    assert err["Message"] == "Event bus name must not contain '/'."

    with pytest.raises(ClientError) as exc:
        client.create_event_bus(
            Name="aws.partner/test/test-bus",
            EventSourceName="aws.partner/test/test-bus",
        )
    err = exc.value.response["Error"]
    assert err["Message"] == "Event source aws.partner/test/test-bus does not exist."


@mock_aws
def test_describe_event_bus():
    client = boto3.client("events", "us-east-1")

    response = client.describe_event_bus()
    assert response["Name"] == "default"
    assert response["Arn"] == f"arn:aws:events:us-east-1:{ACCOUNT_ID}:event-bus/default"
    assert "Policy" not in response
    assert "CreationTime" in response
    assert "LastModifiedTime" in response

    bus_name = "test-bus"
    client.create_event_bus(
        Name=bus_name,
        Description="Test description",
        KmsKeyIdentifier="arn:aws:kms:us-east-1:123456789012:key/test",
        DeadLetterConfig={"Arn": "arn:aws:sqs:us-east-1:123456789012:dlq"},
    )

    client.put_permission(
        EventBusName=bus_name,
        Action="events:PutEvents",
        Principal="111111111111",
        StatementId="test",
    )

    response = client.describe_event_bus(Name=bus_name)

    assert response["Name"] == bus_name
    assert (
        response["Arn"] == f"arn:aws:events:us-east-1:{ACCOUNT_ID}:event-bus/{bus_name}"
    )
    assert "CreationTime" in response
    assert "LastModifiedTime" in response
    assert json.loads(response["Policy"]) == {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "test",
                "Effect": "Allow",
                "Principal": {"AWS": "arn:aws:iam::111111111111:root"},
                "Action": "events:PutEvents",
                "Resource": f"arn:aws:events:us-east-1:{ACCOUNT_ID}:event-bus/{bus_name}",
            }
        ],
    }

    assert response["Description"] == "Test description"
    assert response["KmsKeyIdentifier"] == "arn:aws:kms:us-east-1:123456789012:key/test"
    assert response["DeadLetterConfig"] == {
        "Arn": "arn:aws:sqs:us-east-1:123456789012:dlq"
    }


@mock_aws
def test_describe_event_bus_errors():
    client = boto3.client("events", "us-east-1")

    with pytest.raises(ClientError) as exc:
        client.describe_event_bus(Name="non-existing")
    err = exc.value.response["Error"]
    assert err["Message"] == "Event bus non-existing does not exist."


@mock_aws
def test_list_event_buses():
    client = boto3.client("events", "us-east-1")
    client.create_event_bus(Name="test-bus-1")
    client.create_event_bus(Name="test-bus-2")
    client.create_event_bus(Name="other-bus-1")
    client.create_event_bus(Name="other-bus-2")

    response = client.list_event_buses()

    assert len(response["EventBuses"]) == 5
    assert sorted(response["EventBuses"], key=lambda i: i["Name"]) == [
        {
            "Name": "default",
            "Arn": f"arn:aws:events:us-east-1:{ACCOUNT_ID}:event-bus/default",
        },
        {
            "Name": "other-bus-1",
            "Arn": f"arn:aws:events:us-east-1:{ACCOUNT_ID}:event-bus/other-bus-1",
        },
        {
            "Name": "other-bus-2",
            "Arn": f"arn:aws:events:us-east-1:{ACCOUNT_ID}:event-bus/other-bus-2",
        },
        {
            "Name": "test-bus-1",
            "Arn": f"arn:aws:events:us-east-1:{ACCOUNT_ID}:event-bus/test-bus-1",
        },
        {
            "Name": "test-bus-2",
            "Arn": f"arn:aws:events:us-east-1:{ACCOUNT_ID}:event-bus/test-bus-2",
        },
    ]

    response = client.list_event_buses(NamePrefix="other-bus")

    assert len(response["EventBuses"]) == 2
    assert sorted(response["EventBuses"], key=lambda i: i["Name"]) == [
        {
            "Name": "other-bus-1",
            "Arn": f"arn:aws:events:us-east-1:{ACCOUNT_ID}:event-bus/other-bus-1",
        },
        {
            "Name": "other-bus-2",
            "Arn": f"arn:aws:events:us-east-1:{ACCOUNT_ID}:event-bus/other-bus-2",
        },
    ]


@mock_aws
def test_delete_event_bus():
    client = boto3.client("events", "us-east-1")
    client.create_event_bus(Name="test-bus")

    response = client.list_event_buses()
    assert len(response["EventBuses"]) == 2

    client.delete_event_bus(Name="test-bus")

    response = client.list_event_buses()
    assert len(response["EventBuses"]) == 1
    assert response["EventBuses"] == [
        {
            "Name": "default",
            "Arn": f"arn:aws:events:us-east-1:{ACCOUNT_ID}:event-bus/default",
        }
    ]

    # deleting non existing event bus should be successful
    client.delete_event_bus(Name="non-existing")


@mock_aws
def test_delete_event_bus_errors():
    client = boto3.client("events", "us-east-1")

    with pytest.raises(ClientError) as exc:
        client.delete_event_bus(Name="default")
    err = exc.value.response["Error"]
    assert err["Message"] == "Cannot delete event bus default."


@mock_aws
def test_create_rule_with_tags():
    client = generate_environment()
    rule_name = "test2"
    rule_arn = client.describe_rule(Name=rule_name).get("Arn")

    actual = client.list_tags_for_resource(ResourceARN=rule_arn)["Tags"]
    assert actual == [{"Key": "tagk1", "Value": "tagv1"}]


@mock_aws
def test_delete_rule_with_tags():
    client = generate_environment(add_targets=False)
    rule_name = "test2"
    rule_arn = client.describe_rule(Name=rule_name).get("Arn")
    client.delete_rule(Name=rule_name)

    with pytest.raises(ClientError) as ex:
        client.list_tags_for_resource(ResourceARN=rule_arn)
    err = ex.value.response["Error"]
    assert err["Message"] == "Rule test2 does not exist on EventBus default."

    with pytest.raises(ClientError) as ex:
        client.describe_rule(Name=rule_name)
    err = ex.value.response["Error"]
    assert err["Message"] == "Rule test2 does not exist."


@mock_aws
def test_rule_tagging_happy():
    client = generate_environment()
    rule_name = "test1"
    rule_arn = client.describe_rule(Name=rule_name).get("Arn")

    tags = [{"Key": "key1", "Value": "value1"}, {"Key": "key2", "Value": "value2"}]
    client.tag_resource(ResourceARN=rule_arn, Tags=tags)

    actual = client.list_tags_for_resource(ResourceARN=rule_arn).get("Tags")
    tc = unittest.TestCase("__init__")
    expected = [{"Value": "value1", "Key": "key1"}, {"Value": "value2", "Key": "key2"}]
    tc.assertTrue(
        (expected[0] == actual[0] and expected[1] == actual[1])
        or (expected[1] == actual[0] and expected[0] == actual[1])
    )

    client.untag_resource(ResourceARN=rule_arn, TagKeys=["key1"])

    actual = client.list_tags_for_resource(ResourceARN=rule_arn).get("Tags")
    expected = [{"Key": "key2", "Value": "value2"}]
    assert expected == actual


@mock_aws
def test_tag_resource_error_unknown_arn():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.tag_resource(
            ResourceARN=f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:rule/unknown",
            Tags=[],
        )

    # then
    ex = e.value
    assert ex.operation_name == "TagResource"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceNotFoundException"
    assert (
        ex.response["Error"]["Message"]
        == "Rule unknown does not exist on EventBus default."
    )


@mock_aws
def test_untag_resource_error_unknown_arn():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.untag_resource(
            ResourceARN=f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:rule/unknown",
            TagKeys=[],
        )

    # then
    ex = e.value
    assert ex.operation_name == "UntagResource"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceNotFoundException"
    assert (
        ex.response["Error"]["Message"]
        == "Rule unknown does not exist on EventBus default."
    )


@mock_aws
def test_list_tags_for_resource_error_unknown_arn():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.list_tags_for_resource(
            ResourceARN=f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:rule/unknown"
        )

    # then
    ex = e.value
    assert ex.operation_name == "ListTagsForResource"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceNotFoundException"
    assert (
        ex.response["Error"]["Message"]
        == "Rule unknown does not exist on EventBus default."
    )


@mock_aws
def test_create_archive():
    # given
    client = boto3.client("events", "eu-central-1")
    archive_name = "test-archive"

    # when
    response = client.create_archive(
        ArchiveName=archive_name,
        EventSourceArn=f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default",
    )

    # then
    assert (
        response["ArchiveArn"]
        == f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:archive/{archive_name}"
    )
    assert isinstance(response["CreationTime"], datetime)
    assert response["State"] == "ENABLED"

    # check for archive rule existence
    rule_name = f"Events-Archive-{archive_name}"
    response = client.describe_rule(Name=rule_name)

    assert (
        response["Arn"] == f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:rule/{rule_name}"
    )
    assert response["CreatedBy"] == ACCOUNT_ID
    assert response["EventBusName"] == "default"
    assert json.loads(response["EventPattern"]) == {"replay-name": [{"exists": False}]}
    assert response["ManagedBy"] == "prod.vhs.events.aws.internal"
    assert response["Name"] == rule_name
    assert response["State"] == "ENABLED"

    assert "Description" not in response
    assert "RoleArn" not in response
    assert "ScheduleExpression" not in response


@mock_aws
def test_create_archive_custom_event_bus():
    # given
    client = boto3.client("events", "eu-central-1")
    event_bus_arn = client.create_event_bus(Name="test-bus")["EventBusArn"]

    # when
    response = client.create_archive(
        ArchiveName="test-archive",
        EventSourceArn=event_bus_arn,
        EventPattern=json.dumps(
            {
                "key_1": {
                    "key_2": {"key_3": ["value_1", "value_2"], "key_4": ["value_3"]}
                }
            }
        ),
    )

    # then
    assert (
        response["ArchiveArn"]
        == f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:archive/test-archive"
    )
    assert isinstance(response["CreationTime"], datetime)
    assert response["State"] == "ENABLED"


@mock_aws
def test_create_archive_error_long_name():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "a" * 49

    # when
    with pytest.raises(ClientError) as e:
        client.create_archive(
            ArchiveName=name,
            EventSourceArn=(
                f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
            ),
        )

    # then
    ex = e.value
    assert ex.operation_name == "CreateArchive"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"]
        == f" 1 validation error detected: Value '{name}' at 'archiveName' failed to satisfy constraint: Member must have length less than or equal to 48"
    )


@mock_aws
def test_create_archive_error_invalid_event_pattern():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.create_archive(
            ArchiveName="test-archive",
            EventSourceArn=(
                f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
            ),
            EventPattern="invalid",
        )

    # then
    ex = e.value
    assert ex.operation_name == "CreateArchive"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "InvalidEventPatternException"
    assert (
        ex.response["Error"]["Message"]
        == "Event pattern is not valid. Reason: Invalid JSON"
    )


@mock_aws
def test_create_archive_error_invalid_event_pattern_not_an_array():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.create_archive(
            ArchiveName="test-archive",
            EventSourceArn=(
                f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
            ),
            EventPattern=json.dumps(
                {
                    "key_1": {
                        "key_2": {"key_3": ["value_1"]},
                        "key_4": {"key_5": ["value_2"], "key_6": "value_3"},
                    }
                }
            ),
        )

    # then
    ex = e.value
    assert ex.operation_name == "CreateArchive"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "InvalidEventPatternException"
    assert (
        ex.response["Error"]["Message"]
        == "Event pattern is not valid. Reason: 'key_6' must be an object or an array"
    )


@mock_aws
def test_create_archive_error_unknown_event_bus():
    # given
    client = boto3.client("events", "eu-central-1")
    event_bus_name = "unknown"

    # when
    with pytest.raises(ClientError) as e:
        client.create_archive(
            ArchiveName="test-archive",
            EventSourceArn=(
                f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/{event_bus_name}"
            ),
        )

    # then
    ex = e.value
    assert ex.operation_name == "CreateArchive"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceNotFoundException"
    assert (
        ex.response["Error"]["Message"] == f"Event bus {event_bus_name} does not exist."
    )


@mock_aws
def test_create_archive_error_duplicate():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "test-archive"
    source_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    client.create_archive(ArchiveName=name, EventSourceArn=source_arn)

    # when
    with pytest.raises(ClientError) as e:
        client.create_archive(ArchiveName=name, EventSourceArn=source_arn)

    # then
    ex = e.value
    assert ex.operation_name == "CreateArchive"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceAlreadyExistsException"
    assert ex.response["Error"]["Message"] == "Archive test-archive already exists."


@mock_aws
def test_describe_archive():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "test-archive"
    source_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    event_pattern = json.dumps({"key": ["value"]})
    client.create_archive(
        ArchiveName=name,
        EventSourceArn=source_arn,
        Description="test archive",
        EventPattern=event_pattern,
    )

    # when
    response = client.describe_archive(ArchiveName=name)

    # then
    assert (
        response["ArchiveArn"]
        == f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:archive/{name}"
    )
    assert response["ArchiveName"] == name
    assert isinstance(response["CreationTime"], datetime)
    assert response["Description"] == "test archive"
    assert response["EventCount"] == 0
    assert response["EventPattern"] == event_pattern
    assert response["EventSourceArn"] == source_arn
    assert response["RetentionDays"] == 0
    assert response["SizeBytes"] == 0
    assert response["State"] == "ENABLED"


@mock_aws
def test_describe_archive_error_unknown_archive():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "unknown"

    # when
    with pytest.raises(ClientError) as e:
        client.describe_archive(ArchiveName=name)

    # then
    ex = e.value
    assert ex.operation_name == "DescribeArchive"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceNotFoundException"
    assert ex.response["Error"]["Message"] == f"Archive {name} does not exist."


@mock_aws
def test_list_archives():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "test-archive"
    source_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    event_pattern = json.dumps({"key": ["value"]})
    client.create_archive(
        ArchiveName=name,
        EventSourceArn=source_arn,
        Description="test archive",
        EventPattern=event_pattern,
    )

    # when
    archives = client.list_archives()["Archives"]

    # then
    assert len(archives) == 1
    archive = archives[0]
    assert archive["ArchiveName"] == name
    assert isinstance(archive["CreationTime"], datetime)
    assert archive["EventCount"] == 0
    assert archive["EventSourceArn"] == source_arn
    assert archive["RetentionDays"] == 0
    assert archive["SizeBytes"] == 0
    assert archive["State"] == "ENABLED"

    assert "ArchiveArn" not in archive
    assert "Description" not in archive
    assert "EventPattern" not in archive


@mock_aws
def test_list_archives_with_name_prefix():
    # given
    client = boto3.client("events", "eu-central-1")
    source_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    client.create_archive(ArchiveName="test", EventSourceArn=source_arn)
    client.create_archive(ArchiveName="test-archive", EventSourceArn=source_arn)

    # when
    archives = client.list_archives(NamePrefix="test-")["Archives"]

    # then
    assert len(archives) == 1
    assert archives[0]["ArchiveName"] == "test-archive"


@mock_aws
def test_list_archives_with_source_arn():
    # given
    client = boto3.client("events", "eu-central-1")
    source_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    source_arn_2 = client.create_event_bus(Name="test-bus")["EventBusArn"]
    client.create_archive(ArchiveName="test", EventSourceArn=source_arn)
    client.create_archive(ArchiveName="test-archive", EventSourceArn=source_arn_2)

    # when
    archives = client.list_archives(EventSourceArn=source_arn)["Archives"]

    # then
    assert len(archives) == 1
    assert archives[0]["ArchiveName"] == "test"


@mock_aws
def test_list_archives_with_state():
    # given
    client = boto3.client("events", "eu-central-1")
    source_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    client.create_archive(ArchiveName="test", EventSourceArn=source_arn)
    client.create_archive(ArchiveName="test-archive", EventSourceArn=source_arn)

    # when
    archives = client.list_archives(State="DISABLED")["Archives"]

    # then
    assert len(archives) == 0


@mock_aws
def test_list_archives_error_multiple_filters():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.list_archives(NamePrefix="test", State="ENABLED")

    # then
    ex = e.value
    assert ex.operation_name == "ListArchives"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"]
        == "At most one filter is allowed for ListArchives. Use either : State, EventSourceArn, or NamePrefix."
    )


@mock_aws
def test_list_archives_error_invalid_state():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.list_archives(State="invalid")

    # then
    ex = e.value
    assert ex.operation_name == "ListArchives"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"]
        == "1 validation error detected: Value 'invalid' at 'state' failed to satisfy constraint: Member must satisfy enum value set: [ENABLED, DISABLED, CREATING, UPDATING, CREATE_FAILED, UPDATE_FAILED]"
    )


@mock_aws
def test_update_archive():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "test-archive"
    source_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    event_pattern = json.dumps({"key": ["value"]})
    archive_arn = client.create_archive(ArchiveName=name, EventSourceArn=source_arn)[
        "ArchiveArn"
    ]

    # when
    response = client.update_archive(
        ArchiveName=name,
        Description="test archive",
        EventPattern=event_pattern,
        RetentionDays=14,
    )

    # then
    assert response["ArchiveArn"] == archive_arn
    assert response["State"] == "ENABLED"
    creation_time = response["CreationTime"]
    assert isinstance(creation_time, datetime)

    response = client.describe_archive(ArchiveName=name)
    assert response["ArchiveArn"] == archive_arn
    assert response["ArchiveName"] == name
    assert response["CreationTime"] == creation_time
    assert response["Description"] == "test archive"
    assert response["EventCount"] == 0
    assert response["EventPattern"] == event_pattern
    assert response["EventSourceArn"] == source_arn
    assert response["RetentionDays"] == 14
    assert response["SizeBytes"] == 0
    assert response["State"] == "ENABLED"


@mock_aws
def test_update_archive_error_invalid_event_pattern():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "test-archive"
    client.create_archive(
        ArchiveName=name,
        EventSourceArn=f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default",
    )

    # when
    with pytest.raises(ClientError) as e:
        client.update_archive(ArchiveName=name, EventPattern="invalid")

    # then
    ex = e.value
    assert ex.operation_name == "UpdateArchive"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "InvalidEventPatternException"
    assert (
        ex.response["Error"]["Message"]
        == "Event pattern is not valid. Reason: Invalid JSON"
    )


@mock_aws
def test_update_archive_error_unknown_archive():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "unknown"

    # when
    with pytest.raises(ClientError) as e:
        client.update_archive(ArchiveName=name)

    # then
    ex = e.value
    assert ex.operation_name == "UpdateArchive"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceNotFoundException"
    assert ex.response["Error"]["Message"] == f"Archive {name} does not exist."


@mock_aws
def test_delete_archive():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "test-archive"
    client.create_archive(
        ArchiveName=name,
        EventSourceArn=f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default",
    )

    # when
    client.delete_archive(ArchiveName=name)

    # then
    response = client.list_archives(NamePrefix="test")["Archives"]
    assert len(response) == 0


@mock_aws
def test_delete_archive_error_unknown_archive():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "unknown"

    # when
    with pytest.raises(ClientError) as e:
        client.delete_archive(ArchiveName=name)

    # then
    ex = e.value
    assert ex.operation_name == "DeleteArchive"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceNotFoundException"
    assert ex.response["Error"]["Message"] == f"Archive {name} does not exist."


@aws_verified
@pytest.mark.aws_verified
def test_archive_actual_events():
    # given
    sts = boto3.client("sts", "us-east-1")
    account_id = sts.get_caller_identity()["Account"]
    client = boto3.client("events", "eu-central-1")
    name = "test-archive"
    name_2 = "test-archive-no-match"
    name_3 = "test-archive-matches"
    event_bus_arn = f"arn:aws:events:eu-central-1:{account_id}:event-bus/default"
    event = {
        "Source": "source",
        "DetailType": "type",
        "Detail": '{ "key1": "value1" }',
    }
    client.create_archive(ArchiveName=name, EventSourceArn=event_bus_arn)
    client.create_archive(
        ArchiveName=name_2,
        EventSourceArn=event_bus_arn,
        EventPattern=json.dumps({"detail-type": ["type"], "source": ["test"]}),
    )
    client.create_archive(
        ArchiveName=name_3,
        EventSourceArn=event_bus_arn,
        EventPattern=json.dumps({"detail-type": ["type"], "source": ["source"]}),
    )

    # then
    rules = client.list_rules()["Rules"]
    assert len(rules) >= 3
    for rule in rules:
        assert rule["Name"] in [
            f"Events-Archive-{name}",
            f"Events-Archive-{name_2}",
            f"Events-Archive-{name_3}",
        ]
        assert rule["ManagedBy"] == "prod.vhs.events.aws.internal"
        if rule["Name"] == f"Events-Archive-{name}":
            assert json.loads(rule["EventPattern"]) == {
                "replay-name": [{"exists": False}]
            }
        if rule["Name"] == f"Events-Archive-{name_2}":
            assert json.loads(rule["EventPattern"]) == {
                "detail-type": ["type"],
                "replay-name": [{"exists": False}],
                "source": ["test"],
            }
        if rule["Name"] == f"Events-Archive-{name_3}":
            assert json.loads(rule["EventPattern"]) == {
                "detail-type": ["type"],
                "replay-name": [{"exists": False}],
                "source": ["source"],
            }

        targets = client.list_targets_by_rule(Rule=rule["Name"])["Targets"]
        assert len(targets) == 1
        assert targets[0]["Arn"] == "arn:aws:events:eu-central-1:::"

        transformer = targets[0]["InputTransformer"]
        assert transformer["InputPathsMap"] == {}

        template = transformer["InputTemplate"]
        assert '"archive-arn"' in template
        assert '"event": <aws.events.event.json>' in template
        assert '"ingestion-time": <aws.events.event.ingestion-time>' in template

    # when
    response = client.put_events(Entries=[event])
    assert response["FailedEntryCount"] == 0
    assert len(response["Entries"]) == 1

    # then
    if not allow_aws_request():
        # AWS doesn't (immediately) update the EventCount
        # Only test this against Moto
        response = client.describe_archive(ArchiveName=name)
        assert response["EventCount"] == 1
        assert response["SizeBytes"] > 0

        response = client.describe_archive(ArchiveName=name_2)
        assert response["EventCount"] == 0
        assert response["SizeBytes"] == 0

        response = client.describe_archive(ArchiveName=name_3)
        assert response["EventCount"] == 1
        assert response["SizeBytes"] > 0

    client.delete_archive(ArchiveName=name)
    client.delete_archive(ArchiveName=name_2)
    client.delete_archive(ArchiveName=name_3)

    rules = client.list_rules()["Rules"]
    assert rules == []


@mock_aws
def test_archive_event_with_bus_arn():
    # given
    client = boto3.client("events", "eu-central-1")
    event_bus_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    archive_name = "mock_archive"
    event_with_bus_arn = {
        "Source": "source",
        "DetailType": "type",
        "Detail": '{ "key1": "value1" }',
        "EventBusName": event_bus_arn,
    }
    client.create_archive(ArchiveName=archive_name, EventSourceArn=event_bus_arn)

    # when
    response = client.put_events(Entries=[event_with_bus_arn])

    # then
    assert response["FailedEntryCount"] == 0
    assert len(response["Entries"]) == 1

    response = client.describe_archive(ArchiveName=archive_name)
    assert response["EventCount"] == 1
    assert response["SizeBytes"] > 0


@mock_aws
def test_start_replay():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "test-replay"
    event_bus_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    archive_arn = client.create_archive(
        ArchiveName="test-archive", EventSourceArn=event_bus_arn
    )["ArchiveArn"]

    # when
    response = client.start_replay(
        ReplayName=name,
        EventSourceArn=archive_arn,
        EventStartTime=datetime(2021, 2, 1),
        EventEndTime=datetime(2021, 2, 2),
        Destination={"Arn": event_bus_arn},
    )

    # then
    assert (
        response["ReplayArn"]
        == f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:replay/{name}"
    )
    assert isinstance(response["ReplayStartTime"], datetime)
    assert response["State"] == "STARTING"


@mock_aws
def test_start_replay_error_unknown_event_bus():
    # given
    client = boto3.client("events", "eu-central-1")
    event_bus_name = "unknown"

    # when
    with pytest.raises(ClientError) as e:
        client.start_replay(
            ReplayName="test",
            EventSourceArn=f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:archive/test",
            EventStartTime=datetime(2021, 2, 1),
            EventEndTime=datetime(2021, 2, 2),
            Destination={
                "Arn": f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/{event_bus_name}",
            },
        )

    # then
    ex = e.value
    assert ex.operation_name == "StartReplay"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceNotFoundException"
    assert (
        ex.response["Error"]["Message"] == f"Event bus {event_bus_name} does not exist."
    )


@mock_aws
def test_start_replay_error_invalid_event_bus_arn():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.start_replay(
            ReplayName="test",
            EventSourceArn=f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:archive/test",
            EventStartTime=datetime(2021, 2, 1),
            EventEndTime=datetime(2021, 2, 2),
            Destination={
                "Arn": "invalid",
            },
        )

    # then
    ex = e.value
    assert ex.operation_name == "StartReplay"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"]
        == "Parameter Destination.Arn is not valid. Reason: Must contain an event bus ARN."
    )


@mock_aws
def test_start_replay_error_unknown_archive():
    # given
    client = boto3.client("events", "eu-central-1")
    archive_name = "unknown"

    # when
    with pytest.raises(ClientError) as e:
        client.start_replay(
            ReplayName="test",
            EventSourceArn=f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:archive/{archive_name}",
            EventStartTime=datetime(2021, 2, 1),
            EventEndTime=datetime(2021, 2, 2),
            Destination={
                "Arn": f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default",
            },
        )

    # then
    ex = e.value
    assert ex.operation_name == "StartReplay"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"]
        == f"Parameter EventSourceArn is not valid. Reason: Archive {archive_name} does not exist."
    )


@mock_aws
def test_start_replay_error_cross_event_bus():
    # given
    client = boto3.client("events", "eu-central-1")
    archive_arn = client.create_archive(
        ArchiveName="test-archive",
        EventSourceArn=f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default",
    )["ArchiveArn"]
    event_bus_arn = client.create_event_bus(Name="test-bus")["EventBusArn"]

    # when
    with pytest.raises(ClientError) as e:
        client.start_replay(
            ReplayName="test",
            EventSourceArn=archive_arn,
            EventStartTime=datetime(2021, 2, 1),
            EventEndTime=datetime(2021, 2, 2),
            Destination={"Arn": event_bus_arn},
        )

    # then
    ex = e.value
    assert ex.operation_name == "StartReplay"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"]
        == "Parameter Destination.Arn is not valid. Reason: Cross event bus replay is not permitted."
    )


@mock_aws
def test_start_replay_error_invalid_end_time():
    # given
    client = boto3.client("events", "eu-central-1")
    event_bus_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    archive_arn = client.create_archive(
        ArchiveName="test-archive", EventSourceArn=event_bus_arn
    )["ArchiveArn"]

    # when
    with pytest.raises(ClientError) as e:
        client.start_replay(
            ReplayName="test",
            EventSourceArn=archive_arn,
            EventStartTime=datetime(2021, 2, 2),
            EventEndTime=datetime(2021, 2, 1),
            Destination={"Arn": event_bus_arn},
        )

    # then
    ex = e.value
    assert ex.operation_name == "StartReplay"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"]
        == "Parameter EventEndTime is not valid. Reason: EventStartTime must be before EventEndTime."
    )


@mock_aws
def test_start_replay_error_duplicate():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "test-replay"
    event_bus_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    archive_arn = client.create_archive(
        ArchiveName="test-archive", EventSourceArn=event_bus_arn
    )["ArchiveArn"]
    client.start_replay(
        ReplayName=name,
        EventSourceArn=archive_arn,
        EventStartTime=datetime(2021, 2, 1),
        EventEndTime=datetime(2021, 2, 2),
        Destination={"Arn": event_bus_arn},
    )

    # when
    with pytest.raises(ClientError) as e:
        client.start_replay(
            ReplayName=name,
            EventSourceArn=archive_arn,
            EventStartTime=datetime(2021, 2, 1),
            EventEndTime=datetime(2021, 2, 2),
            Destination={"Arn": event_bus_arn},
        )

    # then
    ex = e.value
    assert ex.operation_name == "StartReplay"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceAlreadyExistsException"
    assert ex.response["Error"]["Message"] == f"Replay {name} already exists."


@mock_aws
def test_describe_replay():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "test-replay"
    event_bus_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    archive_arn = client.create_archive(
        ArchiveName="test-archive", EventSourceArn=event_bus_arn
    )["ArchiveArn"]
    client.start_replay(
        ReplayName=name,
        Description="test replay",
        EventSourceArn=archive_arn,
        EventStartTime=datetime(2021, 2, 1, tzinfo=timezone.utc),
        EventEndTime=datetime(2021, 2, 2, tzinfo=timezone.utc),
        Destination={"Arn": event_bus_arn},
    )

    # when
    response = client.describe_replay(ReplayName=name)

    # then
    assert response["Description"] == "test replay"
    assert response["Destination"] == {"Arn": event_bus_arn}
    assert response["EventSourceArn"] == archive_arn
    assert response["EventStartTime"] == datetime(2021, 2, 1, tzinfo=timezone.utc)
    assert response["EventEndTime"] == datetime(2021, 2, 2, tzinfo=timezone.utc)
    assert (
        response["ReplayArn"]
        == f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:replay/{name}"
    )
    assert response["ReplayName"] == name
    assert isinstance(response["ReplayStartTime"], datetime)
    assert isinstance(response["ReplayEndTime"], datetime)
    assert response["State"] == "COMPLETED"


@mock_aws
def test_describe_replay_error_unknown_replay():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "unknown"

    # when
    with pytest.raises(ClientError) as e:
        client.describe_replay(ReplayName=name)

    # then
    ex = e.value
    assert ex.operation_name == "DescribeReplay"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceNotFoundException"
    assert ex.response["Error"]["Message"] == f"Replay {name} does not exist."


@mock_aws
def test_list_replays():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "test-replay"
    event_bus_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    archive_arn = client.create_archive(
        ArchiveName="test-replay", EventSourceArn=event_bus_arn
    )["ArchiveArn"]
    client.start_replay(
        ReplayName=name,
        Description="test replay",
        EventSourceArn=archive_arn,
        EventStartTime=datetime(2021, 2, 1, tzinfo=timezone.utc),
        EventEndTime=datetime(2021, 2, 2, tzinfo=timezone.utc),
        Destination={"Arn": event_bus_arn},
    )

    # when
    replays = client.list_replays()["Replays"]

    # then
    assert len(replays) == 1
    replay = replays[0]
    assert replay["EventSourceArn"] == archive_arn
    assert replay["EventStartTime"] == datetime(2021, 2, 1, tzinfo=timezone.utc)
    assert replay["EventEndTime"] == datetime(2021, 2, 2, tzinfo=timezone.utc)
    assert replay["ReplayName"] == name
    assert isinstance(replay["ReplayStartTime"], datetime)
    assert isinstance(replay["ReplayEndTime"], datetime)
    assert replay["State"] == "COMPLETED"


@mock_aws
def test_list_replays_with_name_prefix():
    # given
    client = boto3.client("events", "eu-central-1")
    event_bus_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    archive_arn = client.create_archive(
        ArchiveName="test-replay", EventSourceArn=event_bus_arn
    )["ArchiveArn"]
    client.start_replay(
        ReplayName="test",
        EventSourceArn=archive_arn,
        EventStartTime=datetime(2021, 1, 1, tzinfo=timezone.utc),
        EventEndTime=datetime(2021, 1, 2, tzinfo=timezone.utc),
        Destination={"Arn": event_bus_arn},
    )
    client.start_replay(
        ReplayName="test-replay",
        EventSourceArn=archive_arn,
        EventStartTime=datetime(2021, 2, 1, tzinfo=timezone.utc),
        EventEndTime=datetime(2021, 2, 2, tzinfo=timezone.utc),
        Destination={"Arn": event_bus_arn},
    )

    # when
    replays = client.list_replays(NamePrefix="test-")["Replays"]

    # then
    assert len(replays) == 1
    assert replays[0]["ReplayName"] == "test-replay"


@mock_aws
def test_list_replays_with_source_arn():
    # given
    client = boto3.client("events", "eu-central-1")
    event_bus_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    archive_arn = client.create_archive(
        ArchiveName="test-replay", EventSourceArn=event_bus_arn
    )["ArchiveArn"]
    client.start_replay(
        ReplayName="test",
        EventSourceArn=archive_arn,
        EventStartTime=datetime(2021, 1, 1, tzinfo=timezone.utc),
        EventEndTime=datetime(2021, 1, 2, tzinfo=timezone.utc),
        Destination={"Arn": event_bus_arn},
    )
    client.start_replay(
        ReplayName="test-replay",
        EventSourceArn=archive_arn,
        EventStartTime=datetime(2021, 2, 1, tzinfo=timezone.utc),
        EventEndTime=datetime(2021, 2, 2, tzinfo=timezone.utc),
        Destination={"Arn": event_bus_arn},
    )

    # when
    replays = client.list_replays(EventSourceArn=archive_arn)["Replays"]

    # then
    assert len(replays) == 2


@mock_aws
def test_list_replays_with_state():
    # given
    client = boto3.client("events", "eu-central-1")
    event_bus_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    archive_arn = client.create_archive(
        ArchiveName="test-replay", EventSourceArn=event_bus_arn
    )["ArchiveArn"]
    client.start_replay(
        ReplayName="test",
        EventSourceArn=archive_arn,
        EventStartTime=datetime(2021, 1, 1, tzinfo=timezone.utc),
        EventEndTime=datetime(2021, 1, 2, tzinfo=timezone.utc),
        Destination={"Arn": event_bus_arn},
    )
    client.start_replay(
        ReplayName="test-replay",
        EventSourceArn=archive_arn,
        EventStartTime=datetime(2021, 2, 1, tzinfo=timezone.utc),
        EventEndTime=datetime(2021, 2, 2, tzinfo=timezone.utc),
        Destination={"Arn": event_bus_arn},
    )

    # when
    replays = client.list_replays(State="FAILED")["Replays"]

    # then
    assert len(replays) == 0


@mock_aws
def test_list_replays_error_multiple_filters():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.list_replays(NamePrefix="test", State="COMPLETED")

    # then
    ex = e.value
    assert ex.operation_name == "ListReplays"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"]
        == "At most one filter is allowed for ListReplays. Use either : State, EventSourceArn, or NamePrefix."
    )


@mock_aws
def test_list_replays_error_invalid_state():
    # given
    client = boto3.client("events", "eu-central-1")

    # when
    with pytest.raises(ClientError) as e:
        client.list_replays(State="invalid")

    # then
    ex = e.value
    assert ex.operation_name == "ListReplays"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ValidationException"
    assert (
        ex.response["Error"]["Message"]
        == "1 validation error detected: Value 'invalid' at 'state' failed to satisfy constraint: Member must satisfy enum value set: [CANCELLED, CANCELLING, COMPLETED, FAILED, RUNNING, STARTING]"
    )


@mock_aws
def test_cancel_replay():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "test-replay"
    event_bus_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    archive_arn = client.create_archive(
        ArchiveName="test-archive", EventSourceArn=event_bus_arn
    )["ArchiveArn"]
    client.start_replay(
        ReplayName=name,
        Description="test replay",
        EventSourceArn=archive_arn,
        EventStartTime=datetime(2021, 2, 1, tzinfo=timezone.utc),
        EventEndTime=datetime(2021, 2, 2, tzinfo=timezone.utc),
        Destination={"Arn": event_bus_arn},
    )

    # when
    response = client.cancel_replay(ReplayName=name)

    # then
    assert (
        response["ReplayArn"]
        == f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:replay/{name}"
    )
    assert response["State"] == "CANCELLING"

    response = client.describe_replay(ReplayName=name)
    assert response["State"] == "CANCELLED"


@mock_aws
def test_cancel_replay_error_unknown_replay():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "unknown"

    # when
    with pytest.raises(ClientError) as e:
        client.cancel_replay(ReplayName=name)

    # then
    ex = e.value
    assert ex.operation_name == "CancelReplay"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "ResourceNotFoundException"
    assert ex.response["Error"]["Message"] == f"Replay {name} does not exist."


@mock_aws
def test_cancel_replay_error_illegal_state():
    # given
    client = boto3.client("events", "eu-central-1")
    name = "test-replay"
    event_bus_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    archive_arn = client.create_archive(
        ArchiveName="test-archive", EventSourceArn=event_bus_arn
    )["ArchiveArn"]
    client.start_replay(
        ReplayName=name,
        Description="test replay",
        EventSourceArn=archive_arn,
        EventStartTime=datetime(2021, 2, 1, tzinfo=timezone.utc),
        EventEndTime=datetime(2021, 2, 2, tzinfo=timezone.utc),
        Destination={"Arn": event_bus_arn},
    )
    client.cancel_replay(ReplayName=name)

    # when
    with pytest.raises(ClientError) as e:
        client.cancel_replay(ReplayName=name)

    # then
    ex = e.value
    assert ex.operation_name == "CancelReplay"
    assert ex.response["ResponseMetadata"]["HTTPStatusCode"] == 400
    assert ex.response["Error"]["Code"] == "IllegalStatusException"
    assert (
        ex.response["Error"]["Message"]
        == f"Replay {name} is not in a valid state for this operation."
    )


@mock_aws
def test_start_replay_send_to_log_group():
    # given
    client = boto3.client("events", "eu-central-1")
    logs_client = boto3.client("logs", "eu-central-1")
    log_group_name = "/test-group"
    rule_name = "test-rule"
    logs_client.create_log_group(logGroupName=log_group_name)
    event_bus_arn = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:event-bus/default"
    client.put_rule(Name=rule_name, EventPattern=json.dumps({"account": [ACCOUNT_ID]}))
    client.put_targets(
        Rule=rule_name,
        Targets=[
            {
                "Id": "test",
                "Arn": f"arn:aws:logs:eu-central-1:{ACCOUNT_ID}:log-group:{log_group_name}",
            }
        ],
    )
    archive_arn = client.create_archive(
        ArchiveName="test-archive", EventSourceArn=event_bus_arn
    )["ArchiveArn"]
    event_time = datetime(2021, 1, 1, 12, 23, 34)
    client.put_events(
        Entries=[
            {
                "Time": event_time,
                "Source": "source",
                "DetailType": "type",
                "Detail": json.dumps({"key": "value"}),
            }
        ]
    )

    # when
    client.start_replay(
        ReplayName="test-replay",
        EventSourceArn=archive_arn,
        EventStartTime=datetime(2021, 1, 1),
        EventEndTime=datetime(2021, 1, 2),
        Destination={"Arn": event_bus_arn},
    )

    # then
    events = sorted(
        logs_client.filter_log_events(logGroupName=log_group_name)["events"],
        key=lambda item: item["eventId"],
    )
    event_original = json.loads(events[0]["message"])
    assert event_original["version"] == "0"
    assert event_original["id"] is not None
    assert event_original["detail-type"] == "type"
    assert event_original["source"] == "source"
    assert event_original["time"] == iso_8601_datetime_without_milliseconds(event_time)
    assert event_original["region"] == "eu-central-1"
    assert event_original["resources"] == []
    assert event_original["detail"] == {"key": "value"}
    assert "replay-name" not in event_original

    event_replay = json.loads(events[1]["message"])
    assert event_replay["version"] == "0"
    assert event_replay["id"] != event_original["id"]
    assert event_replay["detail-type"] == "type"
    assert event_replay["source"] == "source"
    assert event_replay["time"] == event_original["time"]
    assert event_replay["region"] == "eu-central-1"
    assert event_replay["resources"] == []
    assert event_replay["detail"] == {"key": "value"}
    assert event_replay["replay-name"] == "test-replay"


@mock_aws
def test_send_transformed_events_to_log_group():
    # given
    client = boto3.client("events", "eu-central-1")
    logs_client = boto3.client("logs", "eu-central-1")
    log_group_name = "/test-group"
    rule_name = "test-rule"
    logs_client.create_log_group(logGroupName=log_group_name)

    client.put_rule(Name=rule_name, EventPattern=json.dumps({"account": [ACCOUNT_ID]}))
    client.put_targets(
        Rule=rule_name,
        Targets=[
            {
                "Id": "test",
                "Arn": f"arn:aws:logs:eu-central-1:{ACCOUNT_ID}:log-group:{log_group_name}",
                "InputTransformer": {
                    # TODO: validate whether is this a valid template for AWS, or if certain fields are required
                    "InputTemplate": '{"id": "test"}'
                },
            }
        ],
    )

    # when
    client.put_events(
        Entries=[
            {
                "Time": datetime.now(),
                "Source": "source",
                "DetailType": "type",
                "Detail": json.dumps({"key": "value"}),
            }
        ]
    )

    # then
    log_events = logs_client.filter_log_events(logGroupName=log_group_name)["events"]
    assert len(log_events) == 1
    event_original = json.loads(log_events[0]["message"])
    assert event_original == {"id": "test"}


@mock_aws
def test_create_and_list_connections():
    client = boto3.client("events", "eu-central-1")

    response = client.list_connections()

    assert len(response.get("Connections")) == 0

    response = client.create_connection(
        Name="test",
        Description="test description",
        AuthorizationType="API_KEY",
        AuthParameters={
            "ApiKeyAuthParameters": {"ApiKeyName": "test", "ApiKeyValue": "test"}
        },
    )

    assert (
        f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:connection/test/"
        in response["ConnectionArn"]
    )

    response = client.list_connections()

    assert (
        f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:connection/test/"
        in response["Connections"][0]["ConnectionArn"]
    )
    assert response["Connections"][0]["Name"] == "test"


@mock_aws
def test_create_and_describe_connection():
    client = boto3.client("events", "eu-central-1")

    client.create_connection(
        Name="test",
        Description="test description",
        AuthorizationType="API_KEY",
        AuthParameters={
            "ApiKeyAuthParameters": {"ApiKeyName": "test", "ApiKeyValue": "test"}
        },
    )

    description = client.describe_connection(Name="test")

    assert description["Name"] == "test"
    assert description["Description"] == "test description"
    assert description["AuthorizationType"] == "API_KEY"
    assert description["ConnectionState"] == "AUTHORIZED"
    assert description["SecretArn"] is not None
    assert "CreationTime" in description


@mock_aws
def test_create_and_update_connection():
    client = boto3.client("events", "eu-central-1")

    client.create_connection(
        Name="test",
        Description="test description",
        AuthorizationType="API_KEY",
        AuthParameters={
            "ApiKeyAuthParameters": {"ApiKeyName": "test", "ApiKeyValue": "test"}
        },
    )

    client.update_connection(Name="test", Description="updated desc")

    description = client.describe_connection(Name="test")

    assert description["Name"] == "test"
    assert description["Description"] == "updated desc"
    assert description["AuthorizationType"] == "API_KEY"
    assert description["ConnectionState"] == "AUTHORIZED"
    assert "CreationTime" in description


@aws_verified
@pytest.mark.aws_verified
@pytest.mark.parametrize(
    "auth_type,auth_parameters",
    [
        (
            "API_KEY",
            {"ApiKeyAuthParameters": {"ApiKeyName": "test", "ApiKeyValue": "test"}},
        ),
        ("BASIC", {"BasicAuthParameters": {"Username": "un", "Password": "pw"}}),
    ],
    ids=["auth_params", "basic_auth_params"],
)
@pytest.mark.parametrize(
    "with_headers", [True, False], ids=["with_headers", "without_headers"]
)
def test_kms_key_is_created(auth_type, auth_parameters, with_headers):
    client = boto3.client("events", "us-east-1")
    secrets = boto3.client("secretsmanager", "us-east-1")
    sts = boto3.client("sts", "us-east-1")

    name = f"event_{str(uuid4())[0:6]}"
    account_id = sts.get_caller_identity()["Account"]
    connection_deleted = False
    if with_headers:
        auth_parameters["InvocationHttpParameters"] = {
            "HeaderParameters": [
                {"Key": "k1", "Value": "v1", "IsValueSecret": True},
                {"Key": "k2", "Value": "v2", "IsValueSecret": False},
            ]
        }
    else:
        auth_parameters.pop("InvocationHttpParameters", None)

    client.create_connection(
        Name=name,
        AuthorizationType=auth_type,
        AuthParameters=auth_parameters,
    )
    try:
        description = client.describe_connection(Name=name)
        secret_arn = description["SecretArn"]
        assert secret_arn.startswith(
            f"arn:aws:secretsmanager:us-east-1:{account_id}:secret:events!connection/{name}/"
        )

        secret = secrets.describe_secret(SecretId=secret_arn)
        assert secret["Name"].startswith(f"events!connection/{name}/")
        assert secret["Tags"] == [
            {"Key": "aws:secretsmanager:owningService", "Value": "events"}
        ]
        assert secret["OwningService"] == "events"

        if auth_type == "BASIC":
            expected_secret = {"username": "un", "password": "pw"}
        else:
            expected_secret = {"api_key_name": "test", "api_key_value": "test"}
        if with_headers:
            expected_secret["invocation_http_parameters"] = {
                "header_parameters": [
                    {"key": "k1", "value": "v1", "is_value_secret": True},
                    {"key": "k2", "value": "v2", "is_value_secret": False},
                ]
            }

        secret_value = secrets.get_secret_value(SecretId=secret_arn)
        assert json.loads(secret_value["SecretString"]) == expected_secret

        client.delete_connection(Name=name)
        connection_deleted = True

        secret_deleted = False
        attempts = 0
        while not secret_deleted and attempts < 5:
            try:
                attempts += 1
                secrets.describe_secret(SecretId=secret_arn)
                sleep(1)
            except ClientError as e:
                secret_deleted = (
                    e.response["Error"]["Code"] == "ResourceNotFoundException"
                )

        if not secret_deleted:
            assert False, f"Should have automatically deleted secret {secret_arn}"
    finally:
        if not connection_deleted:
            client.delete_connection(Name=name)


@mock_aws
def test_update_unknown_connection():
    client = boto3.client("events", "eu-north-1")

    with pytest.raises(ClientError) as ex:
        client.update_connection(Name="unknown")
    err = ex.value.response["Error"]
    assert err["Message"] == "Connection 'unknown' does not exist."


@mock_aws
def test_delete_connection():
    client = boto3.client("events", "eu-central-1")

    conns = client.list_connections()["Connections"]
    assert len(conns) == 0

    client.create_connection(
        Name="test",
        Description="test description",
        AuthorizationType="API_KEY",
        AuthParameters={
            "ApiKeyAuthParameters": {"ApiKeyName": "test", "ApiKeyValue": "test"}
        },
    )

    conns = client.list_connections()["Connections"]
    assert len(conns) == 1

    client.delete_connection(Name="test")

    conns = client.list_connections()["Connections"]
    assert len(conns) == 0


@mock_aws
def test_create_and_list_api_destinations():
    client = boto3.client("events", "eu-central-1")

    response = client.create_connection(
        Name="test",
        Description="test description",
        AuthorizationType="API_KEY",
        AuthParameters={
            "ApiKeyAuthParameters": {"ApiKeyName": "test", "ApiKeyValue": "test"}
        },
    )

    destination_response = client.create_api_destination(
        Name="test",
        Description="test-description",
        ConnectionArn=response.get("ConnectionArn"),
        InvocationEndpoint="www.google.com",
        HttpMethod="GET",
    )

    arn_without_uuid = f"arn:aws:events:eu-central-1:{ACCOUNT_ID}:api-destination/test/"
    assert destination_response.get("ApiDestinationArn").startswith(arn_without_uuid)
    assert destination_response.get("ApiDestinationState") == "ACTIVE"

    destination_response = client.describe_api_destination(Name="test")

    assert destination_response.get("ApiDestinationArn").startswith(arn_without_uuid)

    assert destination_response.get("Name") == "test"
    assert destination_response.get("ApiDestinationState") == "ACTIVE"

    destination_response = client.list_api_destinations()
    assert (
        destination_response.get("ApiDestinations")[0]
        .get("ApiDestinationArn")
        .startswith(arn_without_uuid)
    )

    assert destination_response.get("ApiDestinations")[0].get("Name") == "test"
    assert (
        destination_response.get("ApiDestinations")[0].get("ApiDestinationState")
        == "ACTIVE"
    )


@pytest.mark.parametrize(
    "key,initial_value,updated_value",
    [
        ("Description", "my aspi dest", "my actual api dest"),
        ("InvocationEndpoint", "www.google.com", "www.google.cz"),
        ("InvocationRateLimitPerSecond", 1, 32),
        ("HttpMethod", "GET", "PATCH"),
    ],
)
@mock_aws
def test_create_and_update_api_destination(key, initial_value, updated_value):
    client = boto3.client("events", "eu-central-1")

    response = client.create_connection(
        Name="test",
        Description="test description",
        AuthorizationType="API_KEY",
        AuthParameters={
            "ApiKeyAuthParameters": {"ApiKeyName": "test", "ApiKeyValue": "test"}
        },
    )

    default_params = {
        "Name": "test",
        "Description": "test-description",
        "ConnectionArn": response.get("ConnectionArn"),
        "InvocationEndpoint": "www.google.com",
        "HttpMethod": "GET",
    }
    default_params.update({key: initial_value})

    client.create_api_destination(**default_params)
    destination = client.describe_api_destination(Name="test")
    assert destination[key] == initial_value

    client.update_api_destination(Name="test", **dict({key: updated_value}))

    destination = client.describe_api_destination(Name="test")
    assert destination[key] == updated_value


@mock_aws
def test_delete_api_destination():
    client = boto3.client("events", "eu-central-1")

    assert len(client.list_api_destinations()["ApiDestinations"]) == 0

    response = client.create_connection(
        Name="test",
        AuthorizationType="API_KEY",
        AuthParameters={
            "ApiKeyAuthParameters": {"ApiKeyName": "test", "ApiKeyValue": "test"}
        },
    )

    client.create_api_destination(
        Name="testdest",
        ConnectionArn=response.get("ConnectionArn"),
        InvocationEndpoint="www.google.com",
        HttpMethod="GET",
    )

    assert len(client.list_api_destinations()["ApiDestinations"]) == 1

    client.delete_api_destination(Name="testdest")

    assert len(client.list_api_destinations()["ApiDestinations"]) == 0


@mock_aws
def test_describe_unknown_api_destination():
    client = boto3.client("events", "eu-central-1")

    with pytest.raises(ClientError) as ex:
        client.describe_api_destination(Name="unknown")
    err = ex.value.response["Error"]
    assert err["Message"] == "An api-destination 'unknown' does not exist."


@mock_aws
def test_delete_unknown_api_destination():
    client = boto3.client("events", "eu-central-1")

    with pytest.raises(ClientError) as ex:
        client.delete_api_destination(Name="unknown")
    err = ex.value.response["Error"]
    assert err["Message"] == "An api-destination 'unknown' does not exist."


# Scenarios for describe_connection
# Scenario 01: Success
# Scenario 02: Failure - Connection not present
@mock_aws
def test_describe_connection_success():
    # Given
    conn_name = "test_conn_name"
    conn_description = "test_conn_description"
    auth_type = "API_KEY"
    auth_params = {
        "ApiKeyAuthParameters": {"ApiKeyName": "test", "ApiKeyValue": "test"}
    }

    client = boto3.client("events", "eu-central-1")
    _ = client.create_connection(
        Name=conn_name,
        Description=conn_description,
        AuthorizationType=auth_type,
        AuthParameters=auth_params,
    )

    # When
    response = client.describe_connection(Name=conn_name)

    # Then
    assert response["Name"] == conn_name
    assert response["Description"] == conn_description
    assert response["AuthorizationType"] == auth_type
    expected_auth_param = {"ApiKeyAuthParameters": {"ApiKeyName": "test"}}
    assert response["AuthParameters"] == expected_auth_param


@mock_aws
def test_describe_connection_not_present():
    conn_name = "test_conn_name"

    client = boto3.client("events", "eu-central-1")

    # When/Then
    with pytest.raises(ClientError):
        _ = client.describe_connection(Name=conn_name)


# Scenarios for delete_connection
# Scenario 01: Success
# Scenario 02: Failure - Connection not present


@mock_aws
def test_delete_connection_success():
    # Given
    conn_name = "test_conn_name"
    conn_description = "test_conn_description"
    auth_type = "API_KEY"
    auth_params = {
        "ApiKeyAuthParameters": {"ApiKeyName": "test", "ApiKeyValue": "test"}
    }

    client = boto3.client("events", "eu-central-1")
    created_connection = client.create_connection(
        Name=conn_name,
        Description=conn_description,
        AuthorizationType=auth_type,
        AuthParameters=auth_params,
    )

    # When
    response = client.delete_connection(Name=conn_name)

    # Then
    assert response["ConnectionArn"] == created_connection["ConnectionArn"]
    assert response["ConnectionState"] == created_connection["ConnectionState"]
    assert response["CreationTime"] == created_connection["CreationTime"]

    with pytest.raises(ClientError):
        _ = client.describe_connection(Name=conn_name)


@mock_aws
def test_delete_connection_not_present():
    conn_name = "test_conn_name"

    client = boto3.client("events", "eu-central-1")

    # When/Then
    with pytest.raises(ClientError):
        _ = client.delete_connection(Name=conn_name)
