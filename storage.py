#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import uuid

from minio import Minio
from minio.error import S3Error


MINIO_ENDPOINT = "10.21.221.12:9000"
MINIO_PUBLIC_URL = "http://10.21.221.12:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "Admin@hd2019"
DEFAULT_BUCKET = "timedata"


def get_client():
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )


def upload_to_minio(local_path, bucket_name=DEFAULT_BUCKET, object_name=None):
    try:
        client = get_client()
        if object_name is None:
            ext = os.path.splitext(local_path)[1]
            object_name = f"{uuid.uuid4()}{ext}"

        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)

        client.fput_object(bucket_name, object_name, local_path)
        return f"{MINIO_PUBLIC_URL}/{bucket_name}/{object_name}"
    except S3Error as err:
        raise Exception(f"上传 MinIO 失败: {err}")
