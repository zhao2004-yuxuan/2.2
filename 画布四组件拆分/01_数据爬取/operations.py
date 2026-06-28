#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import re
import tempfile
import uuid
from urllib.parse import urlparse

import pandas as pd
import requests
from pyecharts import options as opts
from pyecharts.charts import Bar, Pie, Page
from pyecharts.components import Table
from pyecharts.options import ComponentTitleOpts

from storage import upload_to_minio, DEFAULT_BUCKET


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SOURCE_CSV = os.path.join(BASE_DIR, "data(1).csv")


def _ok(data):
    return {"msg": "success", "data": data}


def _download_file(url, suffix=".csv"):
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(resp.content)
    return path


def _read_csv(source):
    if source.startswith("http://") or source.startswith("https://"):
        local_path = _download_file(source, ".csv")
        return pd.read_csv(local_path)
    return pd.read_csv(source)


def _safe_name(prefix, ext):
    return f"{prefix}_{uuid.uuid4().hex[:12]}{ext}"


def _clean_title(title):
    if pd.isna(title):
        return title
    return re.sub(r"[《》【】#\-—_\[\]（）()]", "", str(title)).strip()


def _parse_price(value):
    if pd.isna(value):
        return None, None
    nums = re.findall(r"\d+(?:\.\d+)?", str(value))
    if not nums:
        return None, None
    prices = [float(x) for x in nums]
    return min(prices), max(prices)


def _price_bucket(price):
    if pd.isna(price):
        return "未知"
    if price < 100:
        return "100以下"
    if price < 300:
        return "100-299"
    if price < 600:
        return "300-599"
    if price < 1000:
        return "600-999"
    return "1000以上"


def _write_html(title, body, output_path):
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{ margin: 0; padding: 24px; background: #0f172a; color: #e5e7eb; font-family: Arial, 'Microsoft YaHei', sans-serif; }}
        h1 {{ margin: 0 0 20px; }}
        .kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 18px; box-shadow: 0 8px 24px rgba(0,0,0,.25); }}
        .label {{ color: #94a3b8; font-size: 14px; }}
        .value {{ color: #38bdf8; font-size: 30px; font-weight: bold; margin-top: 8px; }}
        .chart {{ background: #ffffff; border-radius: 12px; padding: 12px; margin-bottom: 18px; }}
    </style>
</head>
<body>
{body}
</body>
</html>"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def crawl_execute(data):
    """
    数据爬取/读取组件。
    输入 local_path 可指定本地 CSV；不传时读取实验2/data(1).csv。
    输出原始 CSV 的 MinIO 链接和行数。
    """
    local_path = data.get("local_path") or data.get("csv_path") or DEFAULT_SOURCE_CSV
    bucket_name = data.get("bucket_name", DEFAULT_BUCKET)

    if not os.path.exists(local_path):
        raise Exception(f"CSV 文件不存在: {local_path}")

    df = pd.read_csv(local_path)
    object_name = data.get("object_name") or _safe_name("raw_ticket", ".csv")
    csv_url = upload_to_minio(local_path, bucket_name, object_name)
    return _ok({"csv_url": csv_url, "rows": int(len(df))})


def clean_execute(data):
    """
    数据清洗组件。
    输入 csv_url 或 local_path，输出清洗后 CSV 的 MinIO 链接。
    """
    source = data.get("csv_url") or data.get("local_path") or data.get("csv_path") or DEFAULT_SOURCE_CSV
    bucket_name = data.get("bucket_name", DEFAULT_BUCKET)

    df = _read_csv(source)
    df = df.drop_duplicates()
    df = df.dropna(subset=["title", "price", "city"])

    df["title"] = df["title"].apply(_clean_title)
    prices = df["price"].apply(_parse_price)
    df["min_price"] = prices.apply(lambda x: x[0])
    df["max_price"] = prices.apply(lambda x: x[1])
    df = df.dropna(subset=["min_price", "max_price"])

    output_path = os.path.join(tempfile.gettempdir(), _safe_name("clean_ticket", ".csv"))
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    clean_csv_url = upload_to_minio(output_path, bucket_name, os.path.basename(output_path))
    return _ok({"clean_csv_url": clean_csv_url, "rows": int(len(df))})


def _build_charts(df):
    city_counts = df["city"].value_counts().head(10)
    type_counts = df["type"].value_counts().head(8)
    theatre_counts = df["theatre"].value_counts().head(10)
    city_avg = df.groupby("city")["min_price"].mean().sort_values(ascending=False).head(10).round(2)
    bucket_counts = df["min_price"].apply(_price_bucket).value_counts()

    city_bar = (
        Bar()
        .add_xaxis(city_counts.index.tolist())
        .add_yaxis("演出数量", city_counts.astype(int).tolist())
        .set_global_opts(title_opts=opts.TitleOpts(title="城市演出数量 Top10"), xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=30)))
    )

    type_pie = (
        Pie()
        .add("演出类型", [list(z) for z in zip(type_counts.index.tolist(), type_counts.astype(int).tolist())])
        .set_global_opts(title_opts=opts.TitleOpts(title="演出类型构成"), legend_opts=opts.LegendOpts(orient="vertical", pos_left="left"))
        .set_series_opts(label_opts=opts.LabelOpts(formatter="{b}: {d}%"))
    )

    price_bar = (
        Bar()
        .add_xaxis(bucket_counts.index.tolist())
        .add_yaxis("数量", bucket_counts.astype(int).tolist())
        .set_global_opts(title_opts=opts.TitleOpts(title="最低票价区间分布"))
    )

    theatre_bar = (
        Bar()
        .add_xaxis(theatre_counts.index.tolist())
        .add_yaxis("演出数量", theatre_counts.astype(int).tolist())
        .set_global_opts(title_opts=opts.TitleOpts(title="热门场馆 Top10"), xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=30)))
    )

    avg_bar = (
        Bar()
        .add_xaxis(city_avg.index.tolist())
        .add_yaxis("平均最低票价", city_avg.tolist())
        .set_global_opts(title_opts=opts.TitleOpts(title="城市平均最低票价 Top10"), xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=30)))
    )

    return city_bar, type_pie, price_bar, theatre_bar, avg_bar


def multi_chart_render(data):
    """
    多维图表组件。
    输入 clean_csv_url，输出 multi_chart HTML 的 MinIO 链接。
    """
    source = data.get("clean_csv_url") or data.get("csv_url") or data.get("local_path")
    if not source:
        raise Exception("缺少 clean_csv_url 参数")

    bucket_name = data.get("bucket_name", DEFAULT_BUCKET)
    df = _read_csv(source)
    page = Page(layout=Page.SimplePageLayout)
    for chart in _build_charts(df):
        page.add(chart)

    output_path = os.path.join(tempfile.gettempdir(), _safe_name("multi_chart", ".html"))
    page.render(output_path)
    chart_url = upload_to_minio(output_path, bucket_name, os.path.basename(output_path))
    return _ok({"chart_url": chart_url})


def dashboard_render(data):
    """
    监控大屏组件。
    输入 clean_csv_url，输出 dashboard HTML 的 MinIO 链接。
    """
    source = data.get("clean_csv_url") or data.get("csv_url") or data.get("local_path")
    if not source:
        raise Exception("缺少 clean_csv_url 参数")

    bucket_name = data.get("bucket_name", DEFAULT_BUCKET)
    df = _read_csv(source)
    total = int(len(df))
    city_total = int(df["city"].nunique())
    avg_min = round(float(df["min_price"].mean()), 2)
    avg_max = round(float(df["max_price"].mean()), 2)

    charts = _build_charts(df)
    chart_html = "".join([f'<div class="chart">{chart.render_embed()}</div>' for chart in charts])
    body = f"""
<h1>演唱会票务数据监控大屏</h1>
<div class="kpis">
    <div class="card"><div class="label">总演出数</div><div class="value">{total}</div></div>
    <div class="card"><div class="label">覆盖城市数</div><div class="value">{city_total}</div></div>
    <div class="card"><div class="label">平均最低票价</div><div class="value">{avg_min}</div></div>
    <div class="card"><div class="label">平均最高票价</div><div class="value">{avg_max}</div></div>
</div>
{chart_html}
"""

    output_path = os.path.join(tempfile.gettempdir(), _safe_name("dashboard", ".html"))
    _write_html("演唱会票务数据监控大屏", body, output_path)
    dashboard_url = upload_to_minio(output_path, bucket_name, os.path.basename(output_path))
    return _ok({"dashboard_url": dashboard_url, "total": total, "city_total": city_total})
