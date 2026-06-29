#!/usr/bin/env python
# -*- coding: utf-8 -*-
import json
import sys

import routes
import server


class Config(object):
    def __init__(self, server_id, device_ip):
        self.SERVER_ID = server_id
        self.DEVICE_IP = device_ip
        self.SUB_TOPIC = "e/req/" + server_id
        self.PUB_TOPIC = "e/resp/" + server_id


envStr = sys.argv[1]
env = json.loads(envStr)
if env.get("isdp.instance-id") is None:
    raise Exception("Can't get isdp.instance-id")
cfg = Config(server_id=env.get("isdp.instance-id"), device_ip=env.get("isdp.instance-ip", env.get("isdp.instance-id")))

if __name__ == '__main__':
    print("project: ", 'admin_simulated-arm-py')
    print("启动参数: ", envStr)
    addr = env.get("isdp.nacos", "http://nacos:8848")

    client = server.init(cfg, addr, "component")

    server.load(client, cfg)

    routes.refresh(cfg)

    server.init_mqtt()

