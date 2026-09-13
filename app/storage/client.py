from functools import lru_cache

import boto3
from minio import Minio

from app.core.config import get_settings


@lru_cache
def get_minio_client() -> Minio:
    settings = get_settings()
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.resolved_minio_access_key,
        secret_key=settings.resolved_minio_secret_key,
        secure=settings.minio_secure,
    )


@lru_cache
def get_aws_s3_client():
    """Create the S3 client from the configured AWS profile or runtime role."""

    settings = get_settings()
    session = boto3.Session(
        profile_name=settings.aws_profile or None,
        region_name=settings.resolved_aws_s3_region,
    )
    return session.client("s3", region_name=settings.resolved_aws_s3_region)
