#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import logging
import socket
import threading
import json
from typing import List, Dict, Any, Optional
import sys
import os
import re

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# 仿真常量配置 - 与Java代码完全一致
class SimulatedConstant:
    GET_COMPLETION_STATUS_MAX_RETRY = 20  # 获取完成状态的最大重试次数
    GET_COMPLETION_STATUS_INTERVAL_MILLS_SECOND = 250  # 获取完成状态的间隔(毫秒)
    GET_TARGET_POSITION_MAX_RETRY = 10  # 获取目标位置的最大重试次数
    GET_TARGET_POSITION_INTERVAL_MILLS_SECOND = 1000  # 获取目标位置的间隔(毫秒)


# 信号映射配置 - 与yaml配置完全一致
SIGNAL_MAPPING = {
    "TargetTcp": "CurrentTcp",  # 移动操作和当前位置信号
    "RobotSuck": "RobotSuckState",  # 吸嘴操作和状态信号
    "SuckEnabled": "SuckState",  # 吸取使能和状态信号
    "GripperEnabled": "GripperState",  # 夹爪使能和状态信号
    "PolishEnabled": "PolishState"  # 抛光使能和状态信号
}


class SocketClient:
    """Socket客户端"""

    def __init__(self, ip: str, port: int):
        self.ip = ip
        self.port = port
        self.socket = None
        self.connected = False
        self.lock = threading.Lock()

    def connect(self) -> bool:
        """连接服务器"""
        with self.lock:
            try:
                if self.connected and self.socket:
                    try:
                        self.socket.settimeout(1.0)
                        self.socket.send(b'')
                        return True
                    except:
                        self.connected = False
                        if self.socket:
                            try:
                                self.socket.close()
                            except:
                                pass
                            self.socket = None

                logger.info(f"尝试连接服务器 {self.ip}:{self.port}")
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(10)
                self.socket.connect((self.ip, self.port))
                self.socket.settimeout(None)
                self.connected = True
                logger.info(f"Socket连接服务器 {self.ip}:{self.port} 成功!")
                return True

            except Exception as e:
                logger.error(f"Socket连接服务器 {self.ip}:{self.port} 失败: {e}")
                self.connected = False
                if self.socket:
                    try:
                        self.socket.close()
                    except:
                        pass
                    self.socket = None
                return False

    def send(self, message: str) -> bool:
        """发送消息"""
        with self.lock:
            try:
                if not self.connected or not self.socket:
                    if not self.connect():
                        raise Exception("连接失败")

                if not message.endswith('\n'):
                    message += '\n'

                self.socket.sendall(message.encode('utf-8'))
                logger.debug(f"成功发送消息: {message.strip()}")
                return True

            except Exception as e:
                logger.error(f"发送消息失败: {e}")
                self.connected = False
                if self.socket:
                    try:
                        self.socket.close()
                    except:
                        pass
                    self.socket = None
                raise Exception(f"发送失败: {e}")

    def shutdown(self):
        """关闭连接"""
        self.connected = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None


class ResultHandler:
    """结果处理器 - 完全按照Java逻辑实现"""

    def __init__(self):
        self.latest_position = []
        self.completion_status = {}  # 存储各种完成状态
        self.socket_client = None
        self.receive_thread = None
        self.running = False
        self.lock = threading.Lock()

    def set_socket_client(self, client: SocketClient):
        """设置Socket客户端"""
        self.socket_client = client
        self.start_receiving()

    def start_receiving(self):
        """启动消息接收线程"""
        if self.receive_thread and self.receive_thread.is_alive():
            return

        self.running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()

    def _receive_loop(self):
        """接收消息循环"""
        buffer = ""
        while self.running:
            try:
                if not self.socket_client or not self.socket_client.connected or not self.socket_client.socket:
                    time.sleep(1)
                    continue

                self.socket_client.socket.settimeout(1.0)
                try:
                    data = self.socket_client.socket.recv(1024)
                    if data:
                        message = data.decode('utf-8')
                        buffer += message

                        lines = buffer.split('\n')
                        buffer = lines[-1]

                        for line in lines[:-1]:
                            line = line.strip()
                            if line:
                                self._process_message(line)

                except socket.timeout:
                    continue
                except (ConnectionResetError, BrokenPipeError):
                    logger.warning("连接异常，等待重连...")
                    time.sleep(1)

            except Exception as e:
                if self.running:
                    logger.error(f"接收消息错误: {e}")
                time.sleep(1)

    def _process_message(self, message: str):
        """处理接收到的消息"""
        try:
            logger.info(f"收到原始消息: {message}")

            if "java.lang.NullPointerException" in message or "Exception" in message:
                logger.warning(f"服务器返回异常: {message}")
                return

            try:
                if not (message.startswith('{') and message.endswith('}')):
                    logger.warning(f"消息格式不正确: {message}")
                    return

                response_data = json.loads(message)
            except json.JSONDecodeError as e:
                logger.warning(f"无法解析为JSON的消息: {message}, 错误: {e}")
                return

            if not response_data:
                logger.error("空的消息响应")
                return

            msg_type = response_data.get("type")
            if msg_type is None:
                logger.debug("忽略无type字段的消息")
                return

            data = response_data.get("data")
            if data is None:
                logger.warning("响应数据中无data字段")
                return

            with self.lock:
                available_keys = list(data.keys()) if isinstance(data, dict) else []
                logger.info(f"服务器返回的数据键: {available_keys}")

                # 处理当前位置
                current_tcp = data.get("CurrentTcp")
                if current_tcp and isinstance(current_tcp, str):
                    try:
                        position_str = current_tcp.strip('()')
                        position_list = [float(x.strip()) for x in position_str.split(',')]
                        if len(position_list) >= 6:
                            self.latest_position = [round(x, 3) for x in position_list[:6]]
                            logger.info(f"更新TCP位置: {self.latest_position}")
                    except (ValueError, Exception) as e:
                        logger.error(f"解析TCP位置数据错误: {e}")

                # 处理各种完成状态 - 动态处理所有可能的完成信号
                for signal_name in list(SIGNAL_MAPPING.values()):  # 处理所有完成信号
                    signal_value = data.get(signal_name)
                    if signal_value is not None:
                        self.completion_status[signal_name] = bool(signal_value)
                        logger.info(f"更新完成状态 {signal_name}: {signal_value}")

        except Exception as e:
            logger.error(f"处理消息错误: {e}")

    def get_latest_position(self) -> List[float]:
        """获取最新位置"""
        with self.lock:
            return self.latest_position.copy()

    def get_latest_completion_status(self, action_done_signal: str) -> bool:
        """获取最新完成状态 - 对应Java中的getLatestCompletionStatus"""
        with self.lock:
            return self.completion_status.get(action_done_signal, False)

    def reset_latest_position(self):
        """重置最新位置 - 对应Java中的resetLatestPosition"""
        with self.lock:
            self.latest_position = []

    def shutdown(self):
        """关闭结果处理器"""
        self.running = False
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=2.0)


class SimulatedHandler:
    """仿真处理器 - 完全按照Java逻辑实现"""

    def __init__(self, client: SocketClient, result_handler: ResultHandler):
        self.client = client
        self.result_handler = result_handler

    def generate_action_status_command(self, action_done_signal: str) -> str:
        """生成动作状态查询命令 - 对应Java中的generateActionStatusCommand"""
        # Java格式：{"type":1,"data":{"RobotSuckState":"RobotSuckState"}} 注意：有引号
        command = f'{{"type":1,"data":{{"{action_done_signal}":"{action_done_signal}"}}}}' + '\n'
        logger.info(f"生成状态查询命令: {command.strip()}")
        return command

    def generate_boolean_action_command(self, action_signal: str, action: bool) -> str:
        """生成布尔动作命令 - 对应Java中的generateBooleanActionSignalCommand"""
        # Java格式：{"type":2,"data":{"RobotSuck":true}}
        command = f'{{"type":2,"data":{{"{action_signal}":{str(action).lower()}}}}}' + '\n'
        logger.info(f"生成布尔动作命令: {command.strip()}")
        return command

    def generate_string_action_command(self, action_signal: str, action: str) -> str:
        """生成字符串动作命令 - 修复版本"""
        # 修复：action参数如果是字符串，需要正确转义
        if action == '""':
            # 空字符串特殊情况
            command = f'{{"type":2,"data":{{"{action_signal}":""}}}}' + '\n'
        else:
            # 普通字符串，确保正确转义
            command = f'{{"type":2,"data":{{"{action_signal}":"{action}"}}}}' + '\n'

        logger.info(f"生成字符串动作命令: {command.strip()}")
        return command

    def send_command(self, command: str) -> None:
        """发送命令"""
        logger.info(f"发送命令: {command.strip()}")
        try:
            self.client.send(command)
            logger.info("命令发送成功")
        except Exception as e:
            logger.error(f"命令发送失败: {e}")
            raise Exception(f"发送命令失败: {e}")

    def execute_string_action(self, action_signal: str, action: str) -> None:
        """执行字符串动作 - 对应Java中的executeStringAction"""
        logger.info(f"执行字符串动作: {action_signal} = {action}")
        command = self.generate_string_action_command(action_signal, action)
        self.send_command(command)

    def execute_boolean_action(self, action_signal: str, action: bool) -> None:
        """执行布尔动作 - 对应Java中的executeBooleanAction"""
        logger.info(f"执行布尔动作: {action_signal} = {action}")
        command = self.generate_boolean_action_command(action_signal, action)
        self.send_command(command)

    def wait_boolean_action_complete(self, action_done_signal: str) -> bool:
        """等待布尔动作完成 - 对应Java中的waitBooleanActionComplete"""
        count = 0
        logger.info(f"开始等待动作完成: {action_done_signal}")

        while count < SimulatedConstant.GET_COMPLETION_STATUS_MAX_RETRY:
            try:
                # 发送获取是否到达的请求 - 对应Java逻辑
                self.send_command(self.generate_action_status_command(action_done_signal))

                # 检查完成状态 - 对应Java逻辑
                if self.result_handler.get_latest_completion_status(action_done_signal):
                    logger.info(f"动作完成, actionDoneSignal: {action_done_signal}")
                    return True

                count += 1
                time.sleep(SimulatedConstant.GET_COMPLETION_STATUS_INTERVAL_MILLS_SECOND / 1000.0)  # 毫秒转秒

            except Exception as e:
                logger.warning(f"等待动作完成时发生错误: {e}")
                time.sleep(SimulatedConstant.GET_COMPLETION_STATUS_INTERVAL_MILLS_SECOND / 1000.0)

        logger.warning("等待动作完成超时")
        return False

    def wait_string_action_complete_with_position(self, action_done_signal: str, target_position: List[float]) -> bool:
        """等待字符串动作完成（带位置检查）- 对应Java中的waitStringActionCompleteWithPosition"""
        count = 0
        logger.info(f"开始等待位置到达: {target_position}")

        while count < SimulatedConstant.GET_TARGET_POSITION_MAX_RETRY:
            try:
                # 发送获取是否到达的请求
                self.send_command(self.generate_action_status_command(action_done_signal))

                # 获取当前位置并检查
                latest_position = self.result_handler.get_latest_position()
                if latest_position and len(latest_position) >= 6:
                    current_x, current_y, current_z = latest_position[0], latest_position[1], latest_position[2]
                    target_x, target_y, target_z = target_position[0], target_position[1], target_position[2]

                    diff_x = abs(current_x - target_x)
                    diff_y = abs(current_y - target_y)
                    diff_z = abs(current_z - target_z)

                    logger.debug(f"当前坐标:({current_x},{current_y},{current_z})")

                    if diff_x < 0.01 and diff_y < 0.01 and diff_z < 0.01:
                        logger.info("位置到达目标")
                        return True

                    self.result_handler.reset_latest_position()

                count += 1
                time.sleep(SimulatedConstant.GET_TARGET_POSITION_INTERVAL_MILLS_SECOND / 1000.0)  # 毫秒转秒

            except Exception as e:
                logger.warning(f"等待位置到达时发生错误: {e}")
                time.sleep(SimulatedConstant.GET_TARGET_POSITION_INTERVAL_MILLS_SECOND / 1000.0)

        logger.warning("等待位置到达超时")
        return False

    def execute_string_action(self, action_signal: str, action: str) -> None:
        """执行字符串动作 - 新增方法"""
        logger.info(f"执行字符串动作: {action_signal} = {action}")
        command = self.generate_string_action_command(action_signal, action)
        self.send_command(command)

    def move_to_position(self, position: List[float]) -> None:
        """移动到指定位置"""
        position_str = self._generate_position_string(position)
        command = self.generate_string_action_command("TargetTcp", position_str)
        self.send_command(command)

    def _generate_position_string(self, position: List[float]) -> str:
        """生成位置字符串"""
        if len(position) < 6:
            raise ValueError("位置需要6个坐标值")

        x, y, z, rx, ry, rz = position[:6]
        x, y, z, rx, ry, rz = round(x, 3), round(y, 3), round(z, 3), round(rx, 3), round(ry, 3), round(rz, 3)
        return f"({x},{y},{z},{rx},{ry},{rz})"

    def check_class_action_signal(self, action_signal: str) -> tuple:
        """检查类动作信号 - 对应Java中的checkClassActionSignal"""
        if action_signal not in SIGNAL_MAPPING:
            raise ValueError(f"未找到动作信号对应的完成信号: {action_signal}")

        action_done_signal = SIGNAL_MAPPING[action_signal]
        logger.info(f"获取信号对: {action_signal} -> {action_done_signal}")
        return action_signal, action_done_signal


# 全局变量
simulated_handler = None
socket_client = None
result_handler = None
is_initialized = False


def parse_startup_arguments():
    """解析启动参数"""
    if len(sys.argv) > 1:
        try:
            args_str = sys.argv[1]
            args_str = args_str.strip()
            args_str = args_str.replace('\\"', '"')
            args_str = args_str.replace('\\n', '')
            args_str = args_str.replace('\\r', '')
            args_str = args_str.replace('\\t', '')

            # 修正：添加了缺失的右括号
            if not (args_str.startswith('{') and args_str.endswith('}')):
                logger.warning(f"启动参数格式不正确: {args_str}")
                return {}

            startup_args = json.loads(args_str)
            logger.info(f"解析启动参数: {startup_args}")
            return startup_args
        except Exception as e:
            logger.error(f"解析启动参数失败: {e}")
            return {}
    return {}


def init_simulated_system(startup_args: Dict):
    """初始化仿真系统"""
    global simulated_handler, socket_client, result_handler, is_initialized

    if is_initialized and socket_client and socket_client.connected:
        logger.info("现有连接有效")
        return

    ip = startup_args.get('simulated.ip', '10.44.102.171')
    port = int(startup_args.get('simulated.port', '1024'))

    socket_client = SocketClient(ip, port)
    result_handler = ResultHandler()
    simulated_handler = SimulatedHandler(socket_client, result_handler)

    result_handler.set_socket_client(socket_client)

    if socket_client.connect():
        time.sleep(1)
        is_initialized = True
        logger.info("仿真系统初始化完成")
    else:
        logger.error("仿真系统初始化失败")
        is_initialized = False


def robotSuck(data):
    """
    robotSuck接口 - 对应RobotSuckOperation
    特点：不等待完成状态
    """
    global is_initialized

    try:
        suck = data.get('suck', True)  # 默认值为True，与Java逻辑一致
        logger.info(f"收到吸嘴控制请求: {suck}")

        if not is_initialized:
            startup_args = parse_startup_arguments()
            init_simulated_system(startup_args)
            time.sleep(1)

        if not socket_client or not socket_client.connected:
            raise RuntimeError("仿真系统连接未就绪")

        # 获取信号对
        action_signal = "RobotSuck"  # 注解值
        action_done_signal = SIGNAL_MAPPING.get(action_signal)

        if not action_done_signal:
            raise ValueError(f"未找到动作信号对应的完成信号: {action_signal}")

        logger.info(f"使用信号对: {action_signal} -> {action_done_signal}")

        # 执行布尔动作 - 发送RobotSuck字段
        logger.info(f"执行吸嘴控制: {action_signal} = {suck}")
        simulated_handler.execute_boolean_action(action_signal, suck)

        # RobotSuck操作不等待完成状态，直接返回成功
        logger.info("RobotSuck操作完成（不等待状态）")
        return {
            'msg': 'success',
            'data': {}
        }

    except Exception as e:
        logger.error(f"Robot suck operation failed: {e}")
        is_initialized = False
        return {
            'msg': f'error: {str(e)}',
            'data': {}
        }


def gripperEnabled(data):
    """
    gripperEnabled接口 - 对应GripperEnabledOperation
    特点：不等待完成状态
    """
    global is_initialized

    try:
        enable = data.get('enable', True)  # 默认值为True
        logger.info(f"收到夹爪使能请求: {enable}")

        if not is_initialized:
            startup_args = parse_startup_arguments()
            init_simulated_system(startup_args)
            time.sleep(1)

        if not socket_client or not socket_client.connected:
            raise RuntimeError("仿真系统连接未就绪")

        # 获取信号对
        action_signal = "GripperEnabled"  # 注解值
        action_done_signal = SIGNAL_MAPPING.get(action_signal)

        if not action_done_signal:
            raise ValueError(f"未找到动作信号对应的完成信号: {action_signal}")

        logger.info(f"使用信号对: {action_signal} -> {action_done_signal}")

        # 执行布尔动作
        logger.info(f"执行夹爪使能控制: {action_signal} = {enable}")
        simulated_handler.execute_boolean_action(action_signal, enable)

        # GripperEnabled操作不等待完成状态，直接返回成功
        logger.info("GripperEnabled操作完成（不等待状态）")
        return {
            'msg': 'success',
            'data': {}
        }

    except Exception as e:
        logger.error(f"Gripper enabled operation failed: {e}")
        return {
            'msg': f'error: {str(e)}',
            'data': {}
        }


def polishingEnabled(data):
    """
    polishingEnabled接口 - 对应PolishingEnabledOperation
    特点：需要等待完成状态
    """
    global is_initialized

    try:
        enable = data.get('enable', True)  # 默认值为True
        logger.info(f"收到抛光使能请求: {enable}")

        if not is_initialized:
            startup_args = parse_startup_arguments()
            init_simulated_system(startup_args)
            time.sleep(1)

        if not socket_client or not socket_client.connected:
            raise RuntimeError("仿真系统连接未就绪")

        # 获取信号对
        action_signal = "PolishEnabled"  # 注解值
        action_done_signal = SIGNAL_MAPPING.get(action_signal)

        if not action_done_signal:
            raise ValueError(f"未找到动作信号对应的完成信号: {action_signal}")

        logger.info(f"使用信号对: {action_signal} -> {action_done_signal}")

        # 执行布尔动作
        logger.info(f"执行抛光使能控制: {action_signal} = {enable}")
        simulated_handler.execute_boolean_action(action_signal, enable)

        # PolishingEnabled操作需要等待完成状态
        logger.info("等待抛光操作完成...")
        success = simulated_handler.wait_boolean_action_complete(action_done_signal)

        if success:
            logger.info("抛光操作完成")
            return {
                'msg': 'success',
                'data': {}
            }
        else:
            raise Exception("抛光操作超时")

    except Exception as e:
        logger.error(f"Polishing enabled operation failed: {e}")
        return {
            'msg': f'error: {str(e)}',
            'data': {}
        }


def suckEnabled(data):
    """
    suckEnabled接口 - 对应SuckEnabledOperation
    特点：不等待完成状态
    """
    global is_initialized

    try:
        suck = data.get('suck', True)  # 默认值为True
        logger.info(f"收到吸取使能请求: {suck}")

        if not is_initialized:
            startup_args = parse_startup_arguments()
            init_simulated_system(startup_args)
            time.sleep(1)

        if not socket_client or not socket_client.connected:
            raise RuntimeError("仿真系统连接未就绪")

        # 获取信号对
        action_signal = "SuckEnabled"  # 注解值
        action_done_signal = SIGNAL_MAPPING.get(action_signal)

        if not action_done_signal:
            raise ValueError(f"未找到动作信号对应的完成信号: {action_signal}")

        logger.info(f"使用信号对: {action_signal} -> {action_done_signal}")

        # 执行布尔动作
        logger.info(f"执行吸取使能控制: {action_signal} = {suck}")
        simulated_handler.execute_boolean_action(action_signal, suck)

        # SuckEnabled操作不等待完成状态，直接返回成功
        logger.info("SuckEnabled操作完成（不等待状态）")
        return {
            'msg': 'success',
            'data': {}
        }

    except Exception as e:
        logger.error(f"Suck enabled operation failed: {e}")
        return {
            'msg': f'error: {str(e)}',
            'data': {}
        }


def move(data):
    """
    move接口 - 修复版本
    """
    global is_initialized

    try:
        position = data.get('position', [])
        logger.info(f"收到移动请求，位置: {position}")

        # 1. 坐标验证
        if position is None or len(position) < 6:
            raise ValueError("position坐标不正确，需要6个坐标值")
        if any(coord is None for coord in position[:6]):
            raise ValueError("position坐标值不能为None")

        if not is_initialized:
            startup_args = parse_startup_arguments()
            init_simulated_system(startup_args)
            time.sleep(1)

        if not socket_client or not socket_client.connected:
            raise RuntimeError("仿真系统连接未就绪")

        # 2. 获取信号对
        action_signal = "TargetTcp"
        action_done_signal = SIGNAL_MAPPING.get(action_signal)
        if not action_done_signal:
            raise ValueError(f"未找到动作信号对应的完成信号: {action_signal}")

        logger.info(f"使用信号对: {action_signal} -> {action_done_signal}")

        # 3. 重置TargetTcp - 使用正确的空字符串格式
        logger.info("重置TargetTcp")
        # 正确的空字符串格式：直接使用空字符串，不要加引号
        simulated_handler.execute_string_action(action_signal, "")

        # 短暂等待重置完成
        time.sleep(0.5)

        # 4. 发送移动命令 - 修复命令格式
        position_str = _generate_position_string(position)
        logger.info(f"发送移动命令: {position_str}")
        # 注意：position_str应该是不带引号的坐标字符串
        simulated_handler.execute_string_action(action_signal, position_str)

        # 5. 等待执行完成
        logger.info("等待移动执行完成...")
        success = simulated_handler.wait_string_action_complete_with_position(
            action_done_signal, position
        )

        if success:
            logger.info("移动操作完成")
            return {
                'msg': 'success',
                'data': {}
            }
        else:
            raise Exception("移动操作超时")

    except Exception as e:
        logger.error(f"Move operation failed: {e}")
        is_initialized = False
        return {
            'msg': f'error: {str(e)}',
            'data': {}
        }



def _generate_position_string(position: List[float]) -> str:
    """
    生成位置字符串 - 正确版本
    应该生成：(-0.0664,0.3564,0.631,180,0,0)  （不带引号）
    """
    if len(position) < 6:
        raise ValueError("位置需要6个坐标值")

    x, y, z, rx, ry, rz = position[:6]

    # 修复：生成不带引号的坐标字符串
    # Java版本发送的是：(-0.0664,0.3564,0.631,180,0,0)
    position_str = f"({x},{y},{z},{rx},{ry},{rz})"
    logger.info(f"生成位置字符串: {position_str}")
    return position_str

def toolEnabled(data):
    """工具使能接口"""
    return {'msg': 'success', 'data': {}}


def _judge_position(position: List[float]) -> None:
    """
    判断坐标是否正确 - 与Java的judgePosition方法完全一致
    """
    if position is None or len(position) < 6:
        raise ValueError("position坐标不正确")

    # 检查前6个坐标值是否都为None
    if any(coord is None for coord in position[:6]):
        raise ValueError("position坐标不正确")




# 主函数 - 用于测试
if __name__ == "__main__":
    # 测试robotSuck功能
    test_data = {"suck": True}
    result = robotSuck(test_data)
    print("测试结果:", result)