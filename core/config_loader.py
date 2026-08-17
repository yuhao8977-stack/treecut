"""
配置加载器 - 全局配置单例，支持热重载
"""
import os
import yaml
CONFIG_PATH = "./config/system_config.yaml"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)
def reload_config():
    """热重载配置（命令行参数变更后调用）"""
    global CONFIG
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        CONFIG = yaml.safe_load(f)
