#!/usr/bin/env python
# -*- coding: utf-8 -*-
from barcode_core import (
    DEFAULT_BUCKET,
    MINIO_ACCESS_KEY,
    MINIO_ENDPOINT,
    MINIO_PUBLIC_URL,
    MINIO_SECRET_KEY,
    _upload_file as upload_to_minio,
)
