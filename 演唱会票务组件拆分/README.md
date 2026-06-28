# 演唱会票务数据清洗与可视化 - 组件拆分

每个子目录对应平台上的一个组件，并且 routes.py 里只保留一个接口。

| 目录 | 组件名称 | 接口 |
| --- | --- | --- |
| 01_数据爬取 | 数据爬取 | crawl_execute |
| 02_数据清洗 | 数据清洗 | clean_execute |
| 03_多维图表 | 多维图表 | multi_chart_render |
| 04_监控大屏 | 监控大屏 | dashboard_render |

上传到平台时，可以分别上传这 4 个目录；每个组件的启动命令仍然是：

```bash
python -u init.py '<平台传入的JSON参数>'
```
