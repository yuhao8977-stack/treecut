"""
插件基类 - 所有业务插件的标准接口
"""
from abc import ABC, abstractmethod
class BasePlugin(ABC):
    """所有插件的抽象基类"""
    name: str = "base_plugin"
    category: str = "base"
    description: str = "基础插件"
    @abstractmethod
    def run(self, material_id: int, video_path: str) -> dict:
        """
        执行插件逻辑
        Args:
            material_id: 素材数据库ID
            video_path: 视频文件路径
        Returns:
            {"status": "success|cached|skipped|failed", ...}
        """
        ...
