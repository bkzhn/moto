"""ComprehendBackend class with methods for supported APIs."""

import random
from typing import Any, Dict, Iterable, List, Optional, Tuple

from moto.core.base_backend import BackendDict, BaseBackend
from moto.core.common_models import BaseModel
from moto.utilities.tagging_service import TaggingService
from moto.utilities.utils import get_partition

from .exceptions import (
    DetectPIIValidationException,
    ResourceNotFound,
    TextSizeLimitExceededException,
)

CANNED_DETECT_RESPONSE = [
    {
        "Score": 0.9999890923500061,
        "Type": "NAME",
        "BeginOffset": 50,
        "EndOffset": 58,
    },
    {
        "Score": 0.9999966621398926,
        "Type": "EMAIL",
        "BeginOffset": 230,
        "EndOffset": 259,
    },
    {
        "Score": 0.9999954700469971,
        "Type": "BANK_ACCOUNT_NUMBER",
        "BeginOffset": 334,
        "EndOffset": 349,
    },
]

CANNED_PHRASES_RESPONSE = [
    {
        "Score": 0.9999890923500061,
        "BeginOffset": 50,
        "EndOffset": 58,
    },
    {
        "Score": 0.9999966621398926,
        "BeginOffset": 230,
        "EndOffset": 259,
    },
    {
        "Score": 0.9999954700469971,
        "BeginOffset": 334,
        "EndOffset": 349,
    },
]

CANNED_SENTIMENT_RESPONSE = {
    "Sentiment": "NEUTRAL",
    "SentimentScore": {
        "Positive": 0.008101312443614006,
        "Negative": 0.0002824589901138097,
        "Neutral": 0.9916020035743713,
        "Mixed": 1.4156351426208857e-05,
    },
}


class EntityRecognizer(BaseModel):
    def __init__(
        self,
        region_name: str,
        account_id: str,
        language_code: str,
        input_data_config: Dict[str, Any],
        data_access_role_arn: str,
        version_name: str,
        recognizer_name: str,
        volume_kms_key_id: str,
        vpc_config: Dict[str, List[str]],
        model_kms_key_id: str,
        model_policy: str,
    ):
        self.name = recognizer_name
        self.arn = f"arn:{get_partition(region_name)}:comprehend:{region_name}:{account_id}:entity-recognizer/{recognizer_name}"
        if version_name:
            self.arn += f"/version/{version_name}"
        self.language_code = language_code
        self.input_data_config = input_data_config
        self.data_access_role_arn = data_access_role_arn
        self.version_name = version_name
        self.volume_kms_key_id = volume_kms_key_id
        self.vpc_config = vpc_config
        self.model_kms_key_id = model_kms_key_id
        self.model_policy = model_policy
        self.status = "TRAINED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "EntityRecognizerArn": self.arn,
            "LanguageCode": self.language_code,
            "Status": self.status,
            "InputDataConfig": self.input_data_config,
            "DataAccessRoleArn": self.data_access_role_arn,
            "VersionName": self.version_name,
            "VolumeKmsKeyId": self.volume_kms_key_id,
            "VpcConfig": self.vpc_config,
            "ModelKmsKeyId": self.model_kms_key_id,
            "ModelPolicy": self.model_policy,
        }


class DocumentClassifier(BaseModel):
    def __init__(
        self,
        region_name: str,
        account_id: str,
        language_code: str,
        version_name: str,
        input_data_config: Dict[str, Any],
        output_data_config: Dict[str, Any],
        data_access_role_arn: str,
        document_classifier_name: str,
        volume_kms_key_id: str,
        client_request_token: str,
        mode: str,
        vpc_config: Dict[str, List[str]],
        model_kms_key_id: str,
        model_policy: str,
    ):
        self.name = document_classifier_name
        self.arn = f"arn:{get_partition(region_name)}:comprehend:{region_name}:{account_id}:document-classifier/{document_classifier_name}/{version_name}"
        self.language_code = language_code
        self.version_name = version_name
        self.input_data_config = input_data_config
        self.output_data_config = output_data_config
        self.data_access_role_arn = data_access_role_arn
        self.volume_kms_key_id = volume_kms_key_id
        self.client_request_token = client_request_token
        self.mode = mode
        self.vpc_config = vpc_config
        self.model_kms_key_id = model_kms_key_id
        self.model_policy = model_policy
        self.status = "TRAINING"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "DocumentClassifierArn": self.arn,
            "LanguageCode": self.language_code,
            "Status": self.status,
            "InputDataConfig": self.input_data_config,
            "DataAccessRoleArn": self.data_access_role_arn,
            "VolumeKmsKeyId": self.volume_kms_key_id,
            "Mode": self.mode,
            "VpcConfig": self.vpc_config,
            "ModelKmsKeyId": self.model_kms_key_id,
            "ModelPolicy": self.model_policy,
        }


class Endpoint(BaseModel):
    def __init__(
        self,
        endpoint_name: str,
        region_name: str,
        account_id: str,
        model_arn: str,
        client_request_token: str,
        data_access_role_arn: str,
        flywheel_arn: str,
        desired_inference_units: int,
    ):
        self.name = endpoint_name
        self.arn = f"arn:{get_partition(region_name)}:comprehend:{region_name}:{account_id}:endpoint/{endpoint_name}/{model_arn}"
        self.model_arn = model_arn
        self.client_request_token = client_request_token
        self.data_access_role_arn = data_access_role_arn
        self.flywheel_arn = flywheel_arn
        self.desired_inference_units = desired_inference_units
        self.status = "IN_SERVICE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "EndpointArn": self.arn,
            "ModelArn": self.model_arn,
            "ClientRequestToken": self.client_request_token,
            "DataAccessRoleArn": self.data_access_role_arn,
            "FlywheelArn": self.flywheel_arn,
            "DesiredInferenceUnits": self.desired_inference_units,
            "Status": self.status,
        }


class Flywheel(BaseModel):
    def __init__(
        self,
        region_name: str,
        account_id: str,
        flywheel_name: str,
        active_model_arn: str,
        data_access_role_arn: str,
        task_config: Dict[str, Any],
        model_type: str,
        data_lake_s3_uri: str,
        data_security_config: Dict[str, Any],
        client_request_token: str,
    ):
        self.name = flywheel_name
        self.arn = f"arn:{get_partition(region_name)}:comprehend:{region_name}:{account_id}:flywheel/{flywheel_name}"
        self.active_model_arn = active_model_arn
        self.data_access_role_arn = data_access_role_arn
        self.task_config = task_config
        self.model_type = model_type
        self.data_lake_s3_uri = data_lake_s3_uri
        self.data_security_config = data_security_config
        self.client_request_token = client_request_token
        self.status = "ACTIVE"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "FlywheelArn": self.arn,
            "ActiveModelArn": self.active_model_arn,
            "DataAccessRoleArn": self.data_access_role_arn,
            "TaskConfig": self.task_config,
            "ModelType": self.model_type,
            "DataLakeS3Uri": self.data_lake_s3_uri,
            "DataSecurityConfig": self.data_security_config,
            "ClientRequestToken": self.client_request_token,
        }


class ComprehendBackend(BaseBackend):
    """Implementation of Comprehend APIs."""

    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/comprehend/client/detect_key_phrases.html
    detect_key_phrases_languages = [
        "ar",
        "hi",
        "ko",
        "zh-TW",
        "ja",
        "zh",
        "de",
        "pt",
        "en",
        "it",
        "fr",
        "es",
    ]
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/comprehend/client/detect_pii_entities.html
    detect_pii_entities_languages = ["en"]

    def __init__(self, region_name: str, account_id: str):
        super().__init__(region_name, account_id)
        self.recognizers: Dict[str, EntityRecognizer] = dict()
        self.tagger = TaggingService()
        self.endpoints: Dict[str, Endpoint] = dict()
        self.classifiers: Dict[str, DocumentClassifier] = dict()
        self.flywheels: Dict[str, Flywheel] = dict()

    def list_entity_recognizers(
        self, _filter: Dict[str, Any]
    ) -> Iterable[EntityRecognizer]:
        """
        Pagination is not yet implemented.
        The following filters are not yet implemented: Status, SubmitTimeBefore, SubmitTimeAfter
        """
        if "RecognizerName" in _filter:
            return [
                entity
                for entity in self.recognizers.values()
                if entity.name == _filter["RecognizerName"]
            ]
        return self.recognizers.values()

    def create_entity_recognizer(
        self,
        recognizer_name: str,
        version_name: str,
        data_access_role_arn: str,
        tags: List[Dict[str, str]],
        input_data_config: Dict[str, Any],
        language_code: str,
        volume_kms_key_id: str,
        vpc_config: Dict[str, List[str]],
        model_kms_key_id: str,
        model_policy: str,
    ) -> str:
        """
        The ClientRequestToken-parameter is not yet implemented
        """
        recognizer = EntityRecognizer(
            region_name=self.region_name,
            account_id=self.account_id,
            language_code=language_code,
            input_data_config=input_data_config,
            data_access_role_arn=data_access_role_arn,
            version_name=version_name,
            recognizer_name=recognizer_name,
            volume_kms_key_id=volume_kms_key_id,
            vpc_config=vpc_config,
            model_kms_key_id=model_kms_key_id,
            model_policy=model_policy,
        )
        self.recognizers[recognizer.arn] = recognizer
        self.tagger.tag_resource(recognizer.arn, tags)
        return recognizer.arn

    def describe_entity_recognizer(
        self, entity_recognizer_arn: str
    ) -> EntityRecognizer:
        if entity_recognizer_arn not in self.recognizers:
            raise ResourceNotFound
        return self.recognizers[entity_recognizer_arn]

    def stop_training_entity_recognizer(self, entity_recognizer_arn: str) -> None:
        recognizer = self.describe_entity_recognizer(entity_recognizer_arn)
        if recognizer.status == "TRAINING":
            recognizer.status = "STOP_REQUESTED"

    def list_tags_for_resource(self, resource_arn: str) -> List[Dict[str, str]]:
        return self.tagger.list_tags_for_resource(resource_arn)["Tags"]

    def delete_entity_recognizer(self, entity_recognizer_arn: str) -> None:
        self.recognizers.pop(entity_recognizer_arn, None)

    def tag_resource(self, resource_arn: str, tags: List[Dict[str, str]]) -> None:
        self.tagger.tag_resource(resource_arn, tags)

    def untag_resource(self, resource_arn: str, tag_keys: List[str]) -> None:
        self.tagger.untag_resource_using_names(resource_arn, tag_keys)

    def detect_pii_entities(self, text: str, language: str) -> List[Dict[str, Any]]:
        if language not in self.detect_pii_entities_languages:
            raise DetectPIIValidationException(
                language, self.detect_pii_entities_languages
            )
        text_size = len(text)
        if text_size > 100000:
            raise TextSizeLimitExceededException(text_size)
        return CANNED_DETECT_RESPONSE

    def detect_key_phrases(self, text: str, language: str) -> List[Dict[str, Any]]:
        if language not in self.detect_key_phrases_languages:
            raise DetectPIIValidationException(
                language, self.detect_key_phrases_languages
            )
        text_size = len(text)
        if text_size > 100000:
            raise TextSizeLimitExceededException(text_size)
        return CANNED_PHRASES_RESPONSE

    def detect_sentiment(self, text: str, language: str) -> Dict[str, Any]:
        if language not in self.detect_key_phrases_languages:
            raise DetectPIIValidationException(
                language, self.detect_key_phrases_languages
            )
        text_size = len(text)
        if text_size > 5000:
            raise TextSizeLimitExceededException(text_size)
        return CANNED_SENTIMENT_RESPONSE

    def create_document_classifier(
        self,
        document_classifier_name: str,
        version_name: str,
        data_access_role_arn: str,
        tags: List[Dict[str, str]],
        input_data_config: Dict[str, Any],
        output_data_config: Dict[str, Any],
        client_request_token: str,
        language_code: str,
        volume_kms_key_id: str,
        vpc_config: Dict[str, List[str]],
        mode: str,
        model_kms_key_id: str,
        model_policy: str,
    ) -> str:
        classifier = DocumentClassifier(
            region_name=self.region_name,
            account_id=self.account_id,
            language_code=language_code,
            version_name=version_name,
            input_data_config=input_data_config,
            output_data_config=output_data_config,
            client_request_token=client_request_token,
            data_access_role_arn=data_access_role_arn,
            document_classifier_name=document_classifier_name,
            volume_kms_key_id=volume_kms_key_id,
            mode=mode,
            vpc_config=vpc_config,
            model_kms_key_id=model_kms_key_id,
            model_policy=model_policy,
        )
        self.classifiers[classifier.arn] = classifier
        self.tagger.tag_resource(classifier.arn, tags)
        return classifier.arn

    def create_endpoint(
        self,
        endpoint_name: str,
        model_arn: str,
        desired_inference_units: int,
        client_request_token: str,
        tags: List[Dict[str, str]],
        data_access_role_arn: str,
        flywheel_arn: str,
    ) -> Tuple[str, str]:
        endpoint = Endpoint(
            endpoint_name=endpoint_name,
            region_name=self.region_name,
            account_id=self.account_id,
            model_arn=model_arn,
            client_request_token=client_request_token,
            data_access_role_arn=data_access_role_arn,
            flywheel_arn=flywheel_arn,
            desired_inference_units=desired_inference_units,
        )
        self.endpoints[endpoint.arn] = endpoint
        self.tagger.tag_resource(endpoint.arn, tags)
        return endpoint.arn, model_arn

    def create_flywheel(
        self,
        flywheel_name: str,
        active_model_arn: str,
        data_access_role_arn: str,
        task_config: Dict[str, Any],
        model_type: str,
        data_lake_s3_uri: str,
        data_security_config: Dict[str, Any],
        client_request_token: str,
        tags: List[Dict[str, str]],
    ) -> Tuple[str, str]:
        flywheel = Flywheel(
            region_name=self.region_name,
            account_id=self.account_id,
            flywheel_name=flywheel_name,
            active_model_arn=active_model_arn,
            data_access_role_arn=data_access_role_arn,
            task_config=task_config,
            model_type=model_type,
            data_lake_s3_uri=data_lake_s3_uri,
            data_security_config=data_security_config,
            client_request_token=client_request_token,
        )
        self.flywheels[flywheel.arn] = flywheel
        self.tagger.tag_resource(flywheel.arn, tags)
        return flywheel.arn, active_model_arn

    def describe_document_classifier(
        self, document_classifier_arn: str
    ) -> DocumentClassifier:
        if document_classifier_arn not in self.classifiers:
            raise ResourceNotFound
        return self.classifiers[document_classifier_arn]

    def describe_endpoint(self, endpoint_arn: str) -> Endpoint:
        if endpoint_arn not in self.endpoints:
            raise ResourceNotFound
        return self.endpoints[endpoint_arn]

    def describe_flywheel(self, flywheel_arn: str) -> Flywheel:
        if flywheel_arn not in self.flywheels:
            raise ResourceNotFound
        return self.flywheels[flywheel_arn]

    def delete_document_classifier(self, document_classifier_arn: str) -> None:
        self.classifiers.pop(document_classifier_arn, None)

    def delete_endpoint(self, endpoint_arn: str) -> None:
        self.endpoints.pop(endpoint_arn, None)

    def delete_flywheel(self, flywheel_arn: str) -> None:
        self.flywheels.pop(flywheel_arn, None)

    def list_document_classifiers(
        self,
        filter: Optional[Dict[str, Any]] = None,
        next_token: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], None]:
        """
        List document classifiers with optional filtering.
        Pagination is not yet implemented.
        """
        filter = filter or {}

        if "DocumentClassifierName" in filter:
            classifiers = [
                classifier.to_dict()
                for classifier in self.classifiers.values()
                if classifier.name == filter["DocumentClassifierName"]
            ]
        elif "Status" in filter:
            classifiers = [
                classifier.to_dict()
                for classifier in self.classifiers.values()
                if classifier.status == filter["Status"]
            ]
        else:
            classifiers = [
                classifier.to_dict() for classifier in self.classifiers.values()
            ]

        return classifiers, None

    def list_endpoints(
        self,
        filter: Optional[Dict[str, Any]] = None,
        next_token: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], None]:
        """
        List endpoints with optional filtering.
        Pagination is not yet implemented.
        """
        filter = filter or {}

        if "ModelArn" in filter:
            endpoints = [
                endpoint.to_dict()
                for endpoint in self.endpoints.values()
                if endpoint.model_arn == filter["ModelArn"]
            ]
        elif "Status" in filter:
            endpoints = [
                endpoint.to_dict()
                for endpoint in self.endpoints.values()
                if endpoint.status == filter["Status"]
            ]
        else:
            endpoints = [endpoint.to_dict() for endpoint in self.endpoints.values()]

        return endpoints, None

    def list_flywheels(
        self,
        filter: Optional[Dict[str, Any]] = None,
        next_token: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], None]:
        """
        List flywheels with optional filtering.
        Pagination is not yet implemented.
        """
        # Ensure filter is not None
        filter = filter or {}

        # Apply filtering based on Status
        if "Status" in filter:
            flywheels = [
                flywheel.to_dict()
                for flywheel in self.flywheels.values()
                if flywheel.status == filter["Status"]
            ]
        else:
            flywheels = [flywheel.to_dict() for flywheel in self.flywheels.values()]

        # Return the list of flywheels and a placeholder for next_token
        return flywheels, None

    def stop_training_document_classifier(self, document_classifier_arn: str) -> None:
        if document_classifier_arn not in self.classifiers:
            raise ResourceNotFound
        classifier = self.describe_document_classifier(document_classifier_arn)
        if classifier.status == "TRAINING":
            classifier.status = "STOP_REQUESTED"

    def start_flywheel_iteration(
        self, flywheel_arn: str, client_request_token: str
    ) -> Tuple[str, int]:
        if flywheel_arn not in self.flywheels:
            raise ResourceNotFound
        flywheel_iteration_id = int(random.randint(0, 1000000))
        return flywheel_arn, flywheel_iteration_id

    def update_endpoint(
        self,
        endpoint_arn: str,
        desired_model_arn: str,
        desired_inference_units: str,
        desired_data_access_role_arn: str,
        flywheel_arn: str,
    ) -> str:
        return desired_model_arn


comprehend_backends = BackendDict(ComprehendBackend, "comprehend")
