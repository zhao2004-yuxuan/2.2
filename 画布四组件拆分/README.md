# 画布四组件拆分

这个目录按你当前画布里的 4 个组件拆分代码。

| 目录 | 画布组件 | 接口 | 推荐连线 |
| --- | --- | --- | --- |
| 01_数据爬取 | 数据爬取 | crawl_execute | 输出 csv_url 接数据清洗 csv_url |
| 02_数据清洗 | 数据清洗 | clean_execute | 输出 clean_csv_url 接多维图表/监控大屏 |
| 03_多维图表 | 多维图表 | multi_chart_render | 输入 clean_csv_url，输出 chart_url |
| 04_监控大屏 | 监控大屏 | dashboard_render | 输入 clean_csv_url，输出 dashboard_url |

画布连线：

1. 数据爬取.csv_url -> 数据清洗.csv_url
2. 数据清洗.clean_csv_url -> 多维图表.clean_csv_url
3. 数据清洗.clean_csv_url -> 监控大屏.clean_csv_url
4. 多维图表.chart_url -> 结束
5. 监控大屏.dashboard_url -> 结束
