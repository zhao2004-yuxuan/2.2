# 实验3 BYTwin 机械臂组件拆分

本目录按实验三流程整理为可上传的组件目录。

| 目录 | 组件 | 接口 | 主要输入 | 主要输出 |
| --- | --- | --- | --- | --- |
| 01_仿真拍照相机 | 仿真拍照相机 | photograph | SCAN_SIGNAL, SCAN_DONE_SIGNAL, SCAN_RESULT_SIGNAL | miniopath |
| 02_视觉识别 | 视觉识别 | shibie123 | miniopath/path, carfront/carback/tireraised/tireplaced | targetTcp, imgPath |
| 03_机械臂移动 | 机械臂移动 | move | position | - |
| 04_吸嘴操作 | 吸嘴操作 | robotSuck | suck | - |
| 05_法兰吸盘操作 | 法兰吸盘操作 | suckEnabled | suck | - |
| 06_夹爪操作_可选 | 夹爪操作 | gripperEnabled | enable | - |

推荐基础连线：

1. photograph.miniopath -> shibie123.miniopath
2. shibie123.targetTcp -> move.position（用于视觉引导移动节点）

固定点位移动时，在对应 move 节点的 position 默认值中填写 6 维位姿数组，例如：

```json
[-0.0664, 0.3564, 0.631, 180, 0, 0]
```

注意：当前代码中 BYTwin Socket 默认地址为 10.44.102.171:1024，拍照组件和视觉识别组件 MinIO 默认地址为 10.44.102.171:9000。若实验环境 IP 不同，需要在 operations.py 或组件启动参数中修改。
