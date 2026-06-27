# 子实验二：工业条码识别系统组件

这个文件夹用于放置 2.3 子实验二需要的组件代码。

## 当前实验2目录数据检查结果

[实验2](../) 目录当前只有演出票务相关数据：

- [data(1).csv](../data(1).csv)：字段为 `title,href,date,city,theatre,price,type,subclass,status`
- [清洗后数据(1).csv](../清洗后数据(1).csv)：在票务数据基础上增加 `min_price,max_price`

没有发现 10 张 EAN-13 条码图片，也没有发现条码上传结果 CSV、预处理结果 CSV、识别结果 CSV。
因此：当前目录不包含报告中“2.3 子实验二：工业条码识别系统”的数据源。

## 组件文件

- [barcode_components.py](barcode_components.py)

包含四个函数，对应报告中的四个组件：

| 组件 | 函数 | 输入 | 输出 |
| --- | --- | --- | --- |
| MinIO 上传 | `upload` | 本地单张图片路径或图片文件夹路径 | `upload_csv_url`，CSV 包含 `filename,image_url` |
| 图像预处理 | `clean` | `upload_csv_url` 或本地 CSV | `clean_csv_url`，CSV 包含 `filename,cleaned_image_url` |
| 条码识别 | `input` | `clean_csv_url` 或本地 CSV | `result_csv_url`，CSV 包含 `filename,type,data` |
| 结果记录 | `data_record` | `result_csv_url` 或本地 CSV | `final_csv_url`，最终结果 CSV |

## 依赖

在原有依赖基础上，需要增加：

```txt
Pillow
pyzbar
```

注意：`pyzbar` 运行时通常还需要系统安装 zbar 动态库。Windows 上如果报找不到 zbar，需要额外安装 zbar 或把 DLL 加入 PATH。

## 示例调用

```python
from barcode_components import upload, clean, input, data_record

r1 = upload({"local_path": r"G:\\大三下\\工业微服务架构\\实验2\\barcode_images"})
r2 = clean({"upload_csv_url": r1["data"]["upload_csv_url"]})
r3 = input({"clean_csv_url": r2["data"]["clean_csv_url"]})
r4 = data_record({"result_csv_url": r3["data"]["result_csv_url"]})
print(r4)
```
