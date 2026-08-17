"""
插件管理器 - 自动发现、注册、调用插件
新增能力零侵入核心代码
"""
import os
import importlib
from utils.logging import get_loguru_logger as get_logger
from plugins.base_plugin import BasePlugin
logger = get_logger("plugin_manager")
class PluginManager:
    """插件自动发现与注册管理器（单例）"""
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.plugins = {
            "recognize": {},
            "quality": {},
            "correct": {},
        }
        self._discover_plugins()
        total = sum(len(v) for v in self.plugins.values())
        logger.info(f"插件管理器初始化完成，共加载{total}个插件")
    def _discover_plugins(self):
        """自动扫描plugins/目录下所有插件并注册"""
        plugin_dirs = ["recognize", "quality", "correct"]
        for category in plugin_dirs:
            dir_path = os.path.join("plugins", category)
            if not os.path.exists(dir_path):
                logger.warning(f"插件目录不存在: {dir_path}")
                continue
            for filename in sorted(os.listdir(dir_path)):
                if not filename.endswith("_plugin.py"):
                    continue
                module_name = f"plugins.{category}.{filename[:-3]}"
                try:
                    module = importlib.import_module(module_name)
                    for attr_name in dir(module):
                        cls = getattr(module, attr_name)
                        if (
                            isinstance(cls, type)
                            and issubclass(cls, BasePlugin)
                            and cls != BasePlugin
                        ):
                            plugin = cls()
                            self.plugins[category][plugin.name] = plugin
                            logger.debug(f"注册插件: {category}/{plugin.name}")
                            break
                except Exception as e:
                    logger.error(f"加载插件失败 {filename}: {e}")
    def get_plugin(self, category: str, name: str) -> BasePlugin | None:
        """获取指定分类与名称的插件"""
        return self.plugins.get(category, {}).get(name)
    def list_plugins(self, category: str = None) -> dict:
        """列出所有已注册插件"""
        if category:
            return list(self.plugins.get(category, {}).keys())
        return {k: list(v.keys()) for k, v in self.plugins.items()}
    def run_plugin(self, category: str, name: str, material_id: int, video_path: str) -> dict:
        """安全执行指定插件，带异常捕获"""
        plugin = self.get_plugin(category, name)
        if plugin is None:
            logger.error(f"插件不存在: {category}/{name}")
            return {"status": "failed", "error": f"插件不存在: {category}/{name}"}
        try:
            return plugin.run(material_id, video_path)
        except Exception as e:
            logger.error(f"插件执行失败 {category}/{name}: {e}")
            return {"status": "failed", "error": str(e)}
# 全局单例
plugin_manager = PluginManager()
