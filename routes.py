import operations


def refresh(cfg):
    for item in list:
        item.recv_topic = cfg.SUB_TOPIC + "/" + item.operation
        item.send_topic = cfg.PUB_TOPIC + "/" + item.operation


class Route(object):
    def __init__(self, desc, operation):
        self.desc = desc
        self.operation = operation
        self.func = getattr(operations, operation)


list = [
    Route(desc="""数据爬取""",
          operation="crawl_execute",
          ),
    Route(desc="""数据清洗""",
          operation="clean_execute",
          ),
    Route(desc="""多维图表""",
          operation="multi_chart_render",
          ),
    Route(desc="""监控大屏""",
          operation="dashboard_render",
          )
]
