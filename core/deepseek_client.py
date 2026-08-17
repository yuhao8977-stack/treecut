"""
树剪 — DeepSeek API 全局客户端封装
支持 deepseek-chat / deepseek-coder | 流式+非流式 | 自动重试 | 日志
"""
import os, re, json, time, logging, threading
from pathlib import Path
from typing import Optional, List, Dict, Callable
from datetime import datetime

logger = logging.getLogger("deepseek_client")

class DeepSeekClient:
    """DeepSeek API 统一调用封装"""

    def __init__(self, api_key: str = None, model: str = "deepseek-chat", timeout: int = 30):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = model
        self.timeout = timeout
        self.base_url = "https://api.deepseek.com"
        self._client = None
        self._init_client()

    # v12.0: 预编译正则 — 避免每次 _is_valid_key 调用时重新编译
    _PLACEHOLDER_PATTERNS = (
        re.compile(r'your[_\-]?'),
        re.compile(r'[Pp]laceholder'),
        re.compile(r'xxxx+'),
        re.compile(r'^sk-0+$'),
        re.compile(r'^[0]+$'),
    )

    def _is_valid_key(self, key: str) -> bool:
        """增强密钥验证 — 格式检查 + 占位符过滤"""
        if not key or len(key) < 10:
            return False
        for pattern in self._PLACEHOLDER_PATTERNS:
            if pattern.search(key):
                return False
        return True

    def _init_client(self):
        if self.api_key and self._is_valid_key(self.api_key):
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            except ImportError:
                logger.warning("openai not installed, DeepSeek unavailable")

    @property
    def available(self) -> bool:
        return self._client is not None and bool(self.api_key)

    def _call(self, system_prompt: str, user_prompt: str, max_tokens: int = 1000,
              temperature: float = 0.7, stream: bool = False) -> Optional[str]:
        """核心调用方法 — 集成指数退避重试 + 熔断保护"""
        if not self.available:
            return None

        from utils.retry import call_with_retry

        def _do_call():
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                stream=stream,
                timeout=self.timeout,
            )
            if stream:
                return response
            return response.choices[0].message.content.strip()

        return call_with_retry(_do_call, max_attempts=3, base_delay=1.0,
                               fallback=None)

    def test_connection(self) -> tuple[bool, str]:
        """测试连接"""
        if not self.available:
            return False, "API Key 未配置或无效"
        result = self._call("你是一个助手", "你好", max_tokens=20)
        if result:
            return True, f"连接成功! 回复: {result[:50]}"
        return False, "连接失败，请检查API Key和网络"

    def generate_script(self, prompt: str) -> Optional[str]:
        """生成视频脚本"""
        system = """你是小红书爆款文案专家。生成口播脚本:
1. 钩子开头(3秒) 2. 卖点展开(20秒) 3. CTA结尾(5秒)
口语化，短句，有感染力。"""
        return self._call(system, prompt, max_tokens=600, temperature=0.9)

    def optimize_labels(self, raw_labels: Dict[str, List[str]]) -> Optional[str]:
        """优化4个模型输出的原始标签"""
        labels_text = "\n".join(f"{m}: {', '.join(tags)}" for m, tags in raw_labels.items())
        system = """你是家居家装行业标签优化专家。根据4个AI模型的原始识别标签，输出优化后的统一标签。
规则: 1.去重合并 2.纠正明显错误 3.补充遗漏的关键材质/风格 4.只输出标签，逗号分隔，不超过15个"""
        return self._call(system, f"原始标签:\n{labels_text}", max_tokens=200, temperature=0.3)

    def analyze_usage_records(self, records: List[Dict]) -> Optional[str]:
        """分析使用记录并生成优化规则"""
        if not records:
            return None
        summary = json.dumps(records[-50:], ensure_ascii=False, indent=2)  # 最近50条
        system = """你是AI系统优化专家。分析用户的使用记录，输出优化建议。
格式: 每行一条建议，格式为 [类别] 建议内容。类别: 标签优化/工作流优化/模型调优/其他"""
        return self._call(system, f"使用记录(最近50条):\n{summary}", max_tokens=500, temperature=0.5)

    def fix_issue(self, error_log: str) -> Optional[str]:
        """根据错误日志生成解决方案"""
        system = """你是Python程序调试专家。根据错误日志输出修复方案。
格式: [问题] 描述 [方案] 具体解决步骤"""
        return self._call(system, f"错误日志:\n{error_log[:2000]}", max_tokens=800, temperature=0.3)

    def auto_adjust_weights(self, accuracy_records: List[Dict]) -> Optional[str]:
        """根据标注记录自动调整4模型权重"""
        summary = json.dumps(accuracy_records[-100:], ensure_ascii=False)
        system = """你是模型评估专家。根据4个视觉模型的标注准确率记录，输出新的推荐权重分配。
输出格式: Qwen2.5-VL:0.xx, CLIP-ViT-L:0.xx, YOLOv8n:0.xx, KnowledgeBridge:0.xx
权重总和必须为1.0"""
        return self._call(system, f"准确率记录:\n{summary}", max_tokens=100, temperature=0.2)


# 全局单例 — v12.0 修复: 双重检查锁定, 线程安全
_deepseek: Optional[DeepSeekClient] = None
_deepseek_lock = threading.Lock()

def get_deepseek() -> DeepSeekClient:
    global _deepseek
    if _deepseek is None:
        with _deepseek_lock:
            if _deepseek is None:
                _deepseek = DeepSeekClient()
    return _deepseek
