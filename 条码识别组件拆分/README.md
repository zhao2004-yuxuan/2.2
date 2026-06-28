# 条码识别组件拆分

该目录按照“演唱会票务组件拆分”的形式，将工业条码识别流程拆成 4 个独立组件子文件夹。

| 子文件夹 | 组件名称 | 接口名称 | 输入参数 | 输出参数 |
| --- | --- | --- | --- | --- |
| 01_条码图片上传 | 条码图片上传 | `upload` | `local_path`, `bucket_name` | `upload_csv_url`, `image_count` |
| 02_图像预处理 | 条码图像预处理 | `clean` | `upload_csv_url`, `bucket_name` | `clean_csv_url`, `image_count` |
| 03_EAN13条码识别 | EAN13条码识别 | `input` | `clean_csv_url`, `bucket_name` | `result_csv_url`, `recognized_count` |
| 04_结果记录 | 条码识别结果记录 | `data_record` | `result_csv_url`, `bucket_name` | `final_csv_url`, `rows` |

## 画布连接方式

```txt
开始 -> 条码图片上传 -> 条码图像预处理 -> EAN13条码识别 -> 条码识别结果记录 -> 结束
```

参数映射：

```txt
upload.upload_csv_url -> clean.upload_csv_url
clean.clean_csv_url -> input.clean_csv_url
input.result_csv_url -> data_record.result_csv_url
```

每个子文件夹都是一个独立组件目录，包含 `init.py`、`server.py`、`routes.py`、`operations.py`、`storage.py`、`functions.py`、`Dockerfile`、`requirements.txt` 等文件。
