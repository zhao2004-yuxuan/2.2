#!/usr/bin/env python
# -*- coding: utf-8 -*-
import socket
import json
import time
import base64
import uuid
from io import BytesIO
from minio import Minio

# 全局配置
HOST = "10.44.102.171"
PORT = 1024
MINIO_CFG = {
    "endpoint": "10.44.102.171:9000",
    "access_key": "minioadmin",
    "secret_key": "Admin@hd2019",
    "bucket": "camera-picture"
}

# 1. 创建并连接socket
def create_socket():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        sock.connect((HOST, PORT))
        return sock
    except Exception as e:
        raise ConnectionError(f"socket连接失败: {e}")

# 2. 发送指令
def send_cmd(sock, cmd):
    try:
        msg = json.dumps(cmd) + "\n"
        sock.sendall(msg.encode("utf-8"))
    except Exception as e:
        raise ConnectionError(f"发送指令失败: {e}")

# 3. 接收响应
def recv_data(sock):
    buf = ""
    sock.settimeout(2)
    while True:
        try:
            chunk = sock.recv(8192)
        except socket.timeout:
            raise TimeoutError("接收超时")
        except Exception as e:
            raise ConnectionError(f"接收数据失败: {e}")

        if not chunk:
            raise ConnectionError("连接断开")
        buf += chunk.decode("utf-8", errors="ignore")
        try:
            return json.loads(buf.strip())
        except json.JSONDecodeError:
            continue

# 4. 上传MinIO
def upload_minio(img_bytes):
    try:
        minio = Minio(
            MINIO_CFG["endpoint"],
            MINIO_CFG["access_key"],
            MINIO_CFG["secret_key"],
            secure=False
        )
        if not minio.bucket_exists(MINIO_CFG["bucket"]):
            minio.make_bucket(MINIO_CFG["bucket"])
        file_name = f"{uuid.uuid4()}.bmp"
        minio.put_object(
            MINIO_CFG["bucket"],
            file_name,
            BytesIO(img_bytes),
            len(img_bytes),
            content_type="image/bmp"
        )
        return f"http://{MINIO_CFG['endpoint']}/{MINIO_CFG['bucket']}/{file_name}"
    except Exception as e:
        raise RuntimeError(f"MinIO上传失败: {e}")

# 主函数
def photograph(data):
    sock = None
    try:
        scan_sig = data["SCAN_SIGNAL"] # 拍照对象
        done_sig = data["SCAN_DONE_SIGNAL"] # 拍照状态
        res_sig = data["SCAN_RESULT_SIGNAL"] # 图片数据

        # 连接
        sock = create_socket()

        # 【关键修改】先检查当前拍摄完成状态
        send_cmd(sock, {"type": 1, "data": {done_sig: done_sig}})
        resp = recv_data(sock)
        current_done = resp.get("data", {}).get(done_sig)

        # 如果已经是True，说明上次拍照没清状态，先复位
        if current_done is True:
            # 把完成信号清为False，让设备回到空闲状态
            send_cmd(sock, {"type": 2, "data": {done_sig: False}})
            time.sleep(0.2)
            # 再确认一下状态
            send_cmd(sock, {"type": 1, "data": {done_sig: done_sig}})
            resp = recv_data(sock)
            current_done = resp.get("data", {}).get(done_sig)
            if current_done is True:
                raise RuntimeError("无法复位拍摄完成状态，设备忙")

        # 此时current_done为False，设备空闲，可以拍照
        print("设备空闲，开始触发拍照")

        # 复位+触发拍照
        send_cmd(sock, {"type": 2, "data": {scan_sig: False}})
        time.sleep(0.1)
        send_cmd(sock, {"type": 2, "data": {scan_sig: True}})
        time.sleep(0.1)

        # 等待本次拍照完成（done_sig变为True）
        done_flag = False
        for _ in range(5):
            send_cmd(sock, {"type": 1, "data": {done_sig: done_sig}})
            time.sleep(0.5)
            try:
                resp = recv_data(sock)
                if resp.get("data", {}).get(done_sig) is True:
                    done_flag = True
                    break
            except Exception:
                continue
        if not done_flag:
            raise TimeoutError("拍照超时")

        # 获取图片
        send_cmd(sock, {"type": 1, "data": {res_sig: res_sig}})
        resp = recv_data(sock)
        b64_data = resp.get("data", {}).get(res_sig, "")
        if not isinstance(b64_data, str) or len(b64_data) < 10:
            raise ValueError("无效图片数据")

        # 清理信号，为下一次拍照做准备
        send_cmd(sock, {"type": 2, "data": {res_sig: ""}})
        send_cmd(sock, {"type": 2, "data": {done_sig: False}})
        send_cmd(sock, {"type": 2, "data": {scan_sig: False}})

        # 解码+上传
        img_bytes = base64.b64decode(b64_data)
        minio_path = upload_minio(img_bytes)

        return {"msg": "success", "data": {"miniopath": minio_path}}

    except Exception as e:
        return {"msg": f"fail：{str(e)}", "data": {"miniopath": None}}

    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass