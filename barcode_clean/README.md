# 条码图像预处理组件

该目录是工业条码识别流程中的独立组件目录。

## 接口

- 接口名称：`clean`
- 组件说明：条码图像预处理

## 启动方式

在该目录下运行平台生成的启动命令，例如：

```bash
python -u init.py '{"isdp.instance-id":"3223005413_clean","isdp.nacos-namespace":"component","isdp.instance-name":"条码图像预处理","isdp.nacos":"10.21.221.12:8848","isdp.ip":"10.21.221.12"}'
```

## 代码文件

- `init.py`：组件启动入口
- `server.py`：Nacos/MQTT/Redis 服务框架
- `routes.py`：只注册当前组件的一个接口
- `operations.py`：暴露当前组件接口函数
- `barcode_core.py`：条码识别公共实现代码
- `requirements.txt`：依赖列表
