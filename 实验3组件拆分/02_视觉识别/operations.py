import cv2
import numpy as np
from ultralytics import YOLO
import urllib.request
import urllib.error
from minio import Minio
import os
import io


# MinIO 配置
minioEndpoint = '10.44.102.171:9000'
minioAsscessKey = 'minioadmin'
minioSecret_key = 'Admin@hd2019'
bucketName = "depth-camera"

# 初始化 MinIO 客户端
minioClient = Minio(minioEndpoint,
                    access_key=minioAsscessKey,
                    secret_key=minioSecret_key,
                    secure=False)

# 类别名称列表
cls_list = ['carfront', 'carback', 'tireplaced', 'tireraised']

# 创建保存模板图的文件夹
templates_folder = "templates"
os.makedirs(templates_folder, exist_ok=True)
m = [[-1.10403847e-03,  9.79534130e-06, -3.17081933e-01],
 [-9.66100811e-06,-1.08463990e-03,  7.21789958e-01]]

def get_points_robot(x_camera, y_camera):
    robot_x = (m[0][0] * x_camera) + (m[0][1] * y_camera) + m[0][2]
    robot_y = (m[1][0] * x_camera) + (m[1][1] * y_camera) + m[1][2]
    return robot_x, robot_y

def download_png_image(url, local_filename):
    """
    从 URL 下载图片并保存到本地
    :param url: 图片的 URL
    :param local_filename: 本地保存的文件名
    """
    # 定义要下载的远程图像的 URL
    remote_url = url

    # 指定本地保存的文件名
    if not local_filename.endswith('.jpg'):
        local_filename += '.jpg'  # 如果没有提供 jpg 后缀，则添加上

    try:
        # 创建并打开本地文件以写入
        with open(local_filename, 'wb') as f:
            # 发送 HTTP 请求获取远程文件
            response = urllib.request.urlopen(remote_url)

            # 将远程文件的内容写入本地文件
            f.write(response.read())

        print(f"成功下载图片至 {local_filename}")
    except urllib.error.HTTPError as e:
        print(f"下载失败：HTTP 错误 - {e.code}")
    except urllib.error.URLError as e:
        print(f"下载失败：URL 错误 - {e.reason}")
    except Exception as e:
        print(f"下载过程中发生错误：{e}")

def uploadToMinio(localPath):
    """
    将本地文件上传到 MinIO
    :param localPath: 本地文件路径
    :return: 上传后的 MinIO URL
    """
    # 保存图片
    objectName = os.path.basename(localPath)
    minioPath = f"http://{minioEndpoint}/{bucketName}/{objectName}"
    with open(localPath, "br") as f:
        data = f.read()
        # 保存至 MinIO
        try:
            minioClient.put_object(bucket_name=bucketName, object_name=objectName, data=io.BytesIO(data),
                                  length=len(data))
            minioClient.stat_object(bucket_name=bucketName, object_name=objectName)
        except Exception as e:
            raise Exception("minio save failed!cause:", e)
    return minioPath

def Angle_calculation(input_img, template_img):
    """
    计算两张图片之间的旋转角度。

    :param input_img: 输入图像（截取的检测框内容）
    :param template_img: 模板图像
    :return: 旋转角度, 匹配成功标志
    """
    # 初始化SIFT检测器
    sift = cv2.SIFT_create()

    # 检测关键点和计算描述符
    keypoints1, descriptors1 = sift.detectAndCompute(input_img, None)
    keypoints2, descriptors2 = sift.detectAndCompute(template_img, None)

    # 使用FLANN匹配器进行匹配
    FLANN_INDEX_KDTREE = 1
    index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
    search_params = dict(checks=50)
    flann = cv2.FlannBasedMatcher(index_params, search_params)
    matches = flann.knnMatch(descriptors1, descriptors2, k=2)

    # 筛选好的匹配点
    good_matches = []
    for m, n in matches:
        if m.distance < 0.7 * n.distance:
            good_matches.append(m)

    # 获取匹配点的坐标
    src_pts = np.float32([keypoints1[m.queryIdx].pt for m in good_matches]).reshape(-1, 2)
    dst_pts = np.float32([keypoints2[m.trainIdx].pt for m in good_matches]).reshape(-1, 2)

    # 计算仿射变换矩阵
    if len(good_matches) >= 3:  # 至少需要3个点来计算仿射变换
        M, _ = cv2.estimateAffine2D(src_pts, dst_pts)

        if M is not None:
            # 从仿射变换矩阵中提取旋转角度
            # 仿射变换矩阵 M 的形式：
            # [ a  b  tx ]
            # [ c  d  ty ]
            # 旋转角度 theta = arctan2(c, a)
            rotation_angle = np.degrees(np.arctan2(M[1, 0], M[0, 0]))
            print(f"Rotation angle from affine matrix: {rotation_angle:.2f} degrees")
            return rotation_angle, True
        else:
            print("Failed to compute affine transformation matrix.")
            return None, False
    else:
        print("Not enough good matches to compute affine transformation.")
        return None, False

def centerPoint(data):
    """
    centerPoint 接口: 输入车身，车体，躺的轮子，立的轮子，输出图像中对应物体的像素中心点

    data 字典数据:
        path: str 图片路径
        carfront: bool 无描述
        carback: bool 无描述
        tireraised: bool 无描述
        tireplaced: bool 无描述

    返回数据中 data 字段必填并以约定格式返回 data 字典:
        carfrontPoint: str 可选，检测到该类别的中心点坐标，以逗号分隔的字符串形式
        carbackPoint: str 可选，检测到该类别的中心点坐标，以逗号分隔的字符串形式
        tireraisedPoint: str 可选，检测到该类别的中心点坐标，以逗号分隔的字符串形式
        tireplacedPoint: str 可选，检测到该类别的中心点坐标，以逗号分隔的字符串形式
        imgPath: str 输出图片路径
    """
    # 提取输入数据
    image_path = data.get('path')
    target_classes = [key for key in data if data.get(key, False) and key in ['carfront', 'carback', 'tireraised', 'tireplaced']]

    # 下载图片
    download_png_image(image_path, "image")

    # 加载 YOLO 模型
    model_path = "weight/best-new.pt"  # 替换为你的模型路径
    model = YOLO(model_path)

    # 加载图像
    image = cv2.imread("image.jpg")
    if image is None:
        return {
            'msg': 'error',
            'data': {
                'carfrontPoint': None,
                'carbackPoint': None,
                'tireraisedPoint': None,
                'tireplacedPoint': None,
                'imgPath': None
            }
        }

    # 对图像进行目标检测
    results = model(image, conf=0.5)  # 提高置信度阈值

    # 初始化返回数据
    result_data = {
        'carfrontPoint': [],
        'carbackPoint': [],
        'tireraisedPoint': [],
        'tireplacedPoint': [],
        'imgPath': None
    }

    # 遍历每个检测结果
    for result in results:
        boxes = result.boxes  # 获取检测框
        for box in boxes:
            # 提取边界框的坐标 (x1, y1, x2, y2)
            x1, y1, x2, y2 = map(int, box.xyxy[0])

            # 计算检测框的中心点
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2


            # 获取类别索引
            cls_index = int(box.cls[0])

            # 获取类别名称（假设类别名称列表为 cls_list）
            cls_name = cls_list[cls_index]

            # 检查是否为目标类别
            if cls_name in target_classes:
                # 将中心点坐标添加到对应类别的列表
                # result_data[f"{cls_name}Point"].append([center_x,center_y])
                result_data[f"{cls_name}Point"] = ([center_x,center_y])

                # 绘制检测框和中心点
                cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)  # 绿色框
                cv2.circle(image, (center_x, center_y), 5, (0, 0, 255), -1)  # 红色圆

                # 在图像上标记类别名称
                cv2.putText(image, cls_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

                # 截取检测框内容
                cropped_image = image[y1:y2, x1:x2]

                # 加载模板图
                template_img_path = os.path.join(templates_folder, f"template_{cls_name}.jpg")
                template_img = cv2.imread(template_img_path, cv2.IMREAD_COLOR)

                # 检查模板图是否加载成功
                if template_img is None:
                    print(f"Error: Unable to load template image '{template_img_path}'")
                    continue

                # 计算旋转角度
                rotation_angle, success = Angle_calculation(cropped_image, template_img)
                # if success:
                #     # 更新结果数据，格式为 "x,y,rad"
                #     result_data[f"{cls_name}Point"][-1] += [rotation_angle]


    # 将列表中的中心点坐标转换为以分号分隔的字符
    # print(result_data)
    print("carbackPoint:", result_data['carbackPoint'])
    # result_data['carbackPoint'][0], result_data['carbackPoint'][1] = get_points_robot(result_data['carbackPoint'][0],result_data['carbackPoint'][1])
    print("carbackPoint:", result_data['carbackPoint'])
    for key in ['carfrontPoint', 'carbackPoint', 'tireraisedPoint', 'tireplacedPoint']:

        if result_data[key]:
            if len(result_data[key]) > 1:
                result_data[key][0], result_data[key][1] = get_points_robot(result_data[key][0], result_data[key][1])
    print(result_data)
    for  key in ['carfrontPoint', 'carbackPoint', 'tireraisedPoint', 'tireplacedPoint']:
        if key == 'carfrontPoint':
            if result_data[key]:
                if len(result_data[key]) > 1:
                    result_data[key] = [result_data[key][0], 0.0524, result_data[key][1], -180, 0, 0]
                else:
                    result_data[key] = None
        if key == 'carbackPoint':
            if result_data[key]:
                if len(result_data[key]) > 1:
                    result_data[key] = [result_data[key][0], 0.0201, result_data[key][1], -180, 0, 0]
                else:
                    result_data[key] = None
        if key == 'tireraisedPoint':
            if result_data[key]:
                if len(result_data[key]) > 1:
                    result_data[key] = [result_data[key][0], 0.0177, result_data[key][1], -180, 0, 0]
                else:
                    result_data[key] = None
        if key == 'tireplacedPoint':
            if result_data[key]:
                if len(result_data[key]) > 1:
                    result_data[key] = [result_data[key][0], 0.0177, result_data[key][1], -180, 0, 0]
                else:
                    result_data[key] = None




    # 保存带有检测框和中心点的图像到本
    output_path = "output.jpg"
    cv2.imwrite(output_path, image)

    # 上传输出图像到 MinIO
    result_data['imgPath'] = uploadToMinio(output_path)

    return {
        'msg': 'success',
        'data': result_data
    }


def shibie123(data):
    """视觉识别接口。

    兼容实验报告中的 shibie123 命名：
    - 输入 miniopath/path：拍照组件输出的图片地址
    - 输出 targetTcp：优先选取检测到的目标位姿
    同时保留 centerPoint 的 carfrontPoint/carbackPoint/tireraisedPoint/tireplacedPoint/imgPath 输出。
    """
    req = dict(data or {})
    if req.get('miniopath') and not req.get('path'):
        req['path'] = req.get('miniopath')

    # 如果画布没有指定识别类别，默认四类都检测，便于流程直接运行。
    if not any(req.get(k) for k in ['carfront', 'carback', 'tireraised', 'tireplaced']):
        req.update({
            'carfront': True,
            'carback': True,
            'tireraised': True,
            'tireplaced': True,
        })

    result = centerPoint(req)
    data_out = result.get('data', {}) if isinstance(result, dict) else {}
    target = None
    for key in ['carfrontPoint', 'carbackPoint', 'tireraisedPoint', 'tireplacedPoint']:
        value = data_out.get(key)
        if isinstance(value, list) and len(value) >= 6:
            target = value
            break
    data_out['targetTcp'] = target
    return {'msg': result.get('msg', 'success') if isinstance(result, dict) else 'success', 'data': data_out}
