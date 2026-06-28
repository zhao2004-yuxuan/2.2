#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
工业条码识别系统组件代码。

组件划分：
1. upload       本地单张/批量条码图片上传 MinIO，输出 filename,image_url CSV
2. clean        读取图片 URL，灰度化、对比度增强、锐化，输出 cleaned_image_url CSV
3. input        使用 pyzbar 识别 EAN13 条码，输出 filename,type,data CSV
4. data_record  记录条码号、时间和类型，输出最终结果 CSV
"""
import csv
import os
import tempfile
import uuid
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
import requests
from minio import Minio
from minio.error import S3Error
from PIL import Image, ImageEnhance, ImageFilter
from pyzbar.pyzbar import decode


MINIO_ENDPOINT = "10.21.221.12:9000"
MINIO_PUBLIC_URL = "http://10.21.221.12:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "Admin@hd2019"
DEFAULT_BUCKET = "timedata"
DEFAULT_BARCODE_IMAGE_DIR = r"G:\大三下\工业微服务架构\tiaoma_data"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _ok(data):
    return {"msg": "success", "data": data}


def _safe_name(prefix, ext):
    return f"{prefix}_{uuid.uuid4().hex[:12]}{ext}"


def _minio_client():
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )


def _upload_file(local_path, bucket_name=DEFAULT_BUCKET, object_name=None):
    try:
        client = _minio_client()
        if object_name is None:
            object_name = _safe_name("barcode", os.path.splitext(local_path)[1])
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
        client.fput_object(bucket_name, object_name, local_path)
        return f"{MINIO_PUBLIC_URL}/{bucket_name}/{object_name}"
    except S3Error as err:
        raise Exception(f"上传 MinIO 失败: {err}")


def _latest_minio_url(bucket_name, prefix):
    client = _minio_client()
    try:
        objects = list(client.list_objects(bucket_name, prefix=prefix, recursive=True))
    except Exception:
        objects = []
    if not objects:
        return None
    latest = max(objects, key=lambda item: item.last_modified)
    return f"{MINIO_PUBLIC_URL}/{bucket_name}/{latest.object_name}"


def _download_file(url, suffix=None):
    if suffix is None:
        suffix = os.path.splitext(urlparse(url).path)[1] or ".tmp"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(resp.content)
    return path


def _read_csv(source):
    if source.startswith("http://") or source.startswith("https://"):
        source = _download_file(source, ".csv")
    return pd.read_csv(source)


def _collect_images(path):
    if os.path.isdir(path):
        images = []
        for name in sorted(os.listdir(path)):
            full_path = os.path.join(path, name)
            ext = os.path.splitext(name)[1].lower()
            if os.path.isfile(full_path) and ext in IMAGE_EXTENSIONS:
                images.append(full_path)
        return images
    return [path]


def upload(data):
    """
    MinIO 上传组件。

    输入参数：
    - local_path: 单张条码图片路径或图片文件夹路径
    - bucket_name: 可选，MinIO bucket，默认 timedata

    输出：
    - upload_csv_url: 包含 filename,image_url 两列的 CSV 地址
    - image_count: 上传图片数量
    """
    local_path = data.get("local_path") or data.get("image_path") or data.get("folder_path") or DEFAULT_BARCODE_IMAGE_DIR
    if not local_path:
        raise Exception("缺少 local_path/image_path/folder_path 参数")
    if not os.path.exists(local_path):
        raise Exception(f"路径不存在: {local_path}")

    bucket_name = data.get("bucket_name", DEFAULT_BUCKET)
    image_paths = _collect_images(local_path)
    if not image_paths:
        raise Exception(f"未找到条码图片: {local_path}")

    rows = []
    for image_path in image_paths:
        filename = os.path.basename(image_path)
        object_name = f"barcode/source/{_safe_name(os.path.splitext(filename)[0], os.path.splitext(filename)[1])}"
        image_url = _upload_file(image_path, bucket_name, object_name)
        rows.append({"filename": filename, "image_url": image_url})

    output_path = os.path.join(tempfile.gettempdir(), _safe_name("barcode_upload", ".csv"))
    pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")
    upload_csv_url = _upload_file(output_path, bucket_name, f"barcode/csv/{os.path.basename(output_path)}")
    return _ok({"upload_csv_url": upload_csv_url, "csv_url": upload_csv_url, "image_count": len(rows)})


def clean(data):
    """
    图像预处理组件。

    输入参数：
    - upload_csv_url/csv_url/local_path: upload 组件输出 CSV 或本地 CSV

    输出：
    - clean_csv_url: 包含 filename,cleaned_image_url 两列的 CSV 地址
    """
    bucket_name = data.get("bucket_name", DEFAULT_BUCKET)
    source = data.get("upload_csv_url") or data.get("csv_url") or data.get("local_path") or _latest_minio_url(bucket_name, "barcode/csv/barcode_upload_")
    if not source:
        raise Exception("缺少 upload_csv_url/csv_url/local_path 参数，且 MinIO 中没有找到 barcode_upload CSV")

    df = _read_csv(source)
    if "image_url" not in df.columns:
        raise Exception("输入 CSV 必须包含 image_url 列")

    rows = []
    for _, row in df.iterrows():
        filename = row.get("filename", os.path.basename(urlparse(row["image_url"]).path))
        local_image = _download_file(row["image_url"])
        image = Image.open(local_image).convert("L")
        image = ImageEnhance.Contrast(image).enhance(1.8)
        image = image.filter(ImageFilter.SHARPEN)

        output_path = os.path.join(tempfile.gettempdir(), _safe_name("cleaned_barcode", ".png"))
        image.save(output_path)
        cleaned_url = _upload_file(output_path, bucket_name, f"barcode/cleaned/{os.path.basename(output_path)}")
        rows.append({"filename": filename, "cleaned_image_url": cleaned_url})

    output_csv = os.path.join(tempfile.gettempdir(), _safe_name("barcode_clean", ".csv"))
    pd.DataFrame(rows).to_csv(output_csv, index=False, encoding="utf-8-sig")
    clean_csv_url = _upload_file(output_csv, bucket_name, f"barcode/csv/{os.path.basename(output_csv)}")
    return _ok({"clean_csv_url": clean_csv_url, "csv_url": clean_csv_url, "image_count": len(rows)})


def input(data):
    """
    条码识别组件。

    输入参数：
    - clean_csv_url/csv_url/local_path: clean 组件输出 CSV 或本地 CSV

    输出：
    - result_csv_url: 包含 filename,type,data 三列的识别结果 CSV 地址
    """
    bucket_name = data.get("bucket_name", DEFAULT_BUCKET)
    source = data.get("clean_csv_url") or data.get("csv_url") or data.get("local_path") or _latest_minio_url(bucket_name, "barcode/csv/barcode_clean_")
    if not source:
        raise Exception("缺少 clean_csv_url/csv_url/local_path 参数，且 MinIO 中没有找到 barcode_clean CSV")

    df = _read_csv(source)
    url_col = "cleaned_image_url" if "cleaned_image_url" in df.columns else "image_url"
    if url_col not in df.columns:
        raise Exception("输入 CSV 必须包含 cleaned_image_url 或 image_url 列")

    rows = []
    for _, row in df.iterrows():
        filename = row.get("filename", os.path.basename(urlparse(row[url_col]).path))
        local_image = _download_file(row[url_col])
        image = Image.open(local_image)
        codes = decode(image)

        ean13_codes = [code for code in codes if code.type == "EAN13"]
        if ean13_codes:
            for code in ean13_codes:
                rows.append({"filename": filename, "type": code.type, "data": code.data.decode("utf-8")})
        else:
            rows.append({"filename": filename, "type": "", "data": ""})

    output_csv = os.path.join(tempfile.gettempdir(), _safe_name("barcode_result", ".csv"))
    pd.DataFrame(rows).to_csv(output_csv, index=False, encoding="utf-8-sig")
    result_csv_url = _upload_file(output_csv, bucket_name, f"barcode/csv/{os.path.basename(output_csv)}")
    return _ok({"result_csv_url": result_csv_url, "csv_url": result_csv_url, "recognized_count": int(sum(1 for r in rows if r["data"]))})


def data_record(data):
    """
    结果记录组件。

    输入参数：
    - result_csv_url/csv_url/local_path: input 组件输出 CSV 或本地 CSV

    输出：
    - final_csv_url: 最终可追溯结果 CSV，字段为 filename,type,data,record_time,status
    """
    bucket_name = data.get("bucket_name", DEFAULT_BUCKET)
    source = data.get("result_csv_url") or data.get("csv_url") or data.get("local_path") or _latest_minio_url(bucket_name, "barcode/csv/barcode_result_")
    if not source:
        raise Exception("缺少 result_csv_url/csv_url/local_path 参数，且 MinIO 中没有找到 barcode_result CSV")

    df = _read_csv(source)
    for col in ["filename", "type", "data"]:
        if col not in df.columns:
            raise Exception(f"识别结果 CSV 缺少 {col} 列")

    df["record_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df["status"] = df["data"].apply(lambda x: "success" if pd.notna(x) and str(x).strip() else "failed")

    output_csv = os.path.join(tempfile.gettempdir(), _safe_name("barcode_final", ".csv"))
    df.to_csv(output_csv, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    final_csv_url = _upload_file(output_csv, bucket_name, f"barcode/csv/{os.path.basename(output_csv)}")
    return _ok({"final_csv_url": final_csv_url, "csv_url": final_csv_url, "rows": int(len(df))})
