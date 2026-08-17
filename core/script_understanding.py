"""
树剪 — 脚本语义理解模块 (Script Understanding)
================================================================
使用 DeepSeek API 对视频脚本进行深度语义解析，提取可视化需求。

用法:
  from core.script_understanding import ScriptParser
  parser = ScriptParser()
  result = parser.parse("岛台装修别踩坑了！内嵌烤箱精准开孔...")
  # result = {
  #   "segments": [{
  #     "text": "...", "duration_sec": 2.5,
  #     "visual_requirements": {"scene":[...], "objects":[...], ...}
  #   }],
  #   "global_style": "极简风", "overall_mood": "专业、科技感"
  # }
"""
import json
import re
from typing import Optional, List, Dict


DEFAULT_DURATION_PER_CHAR = 0.28  # 秒/字 (TTS语速 ~3.6字/秒)


class ScriptParser:
    """
    脚本语义解析器 — DeepSeek API 优先 + 本地规则降级

    提示词工程: 严格要求 JSON 格式返回，禁止自由文本。
    超时: 15秒。失败时使用本地规则兜底。
    """

    SYSTEM_PROMPT = """你是视频脚本视觉化分析专家。分析口播脚本，输出每句对应的视觉需求。

输出必须是纯 JSON 对象（不要 Markdown 标记），格式:
{
  "segments": [
    {
      "text": "原文句子",
      "duration_sec": 2.5,
      "visual_requirements": {
        "scene": ["厨房", "岛台"],
        "objects": ["烤箱", "抽屉"],
        "actions": ["拉开", "展示"],
        "style": ["极简风"],
        "materials": ["岩板"],
        "colors": ["白色"],
        "emotion": ["高级感"]
      }
    }
  ],
  "global_style": "极简风",
  "overall_mood": "专业、科技感"
}

规则:
1. 每个句子独立分析。duration_sec ≈ 字数 × 0.28 秒。
2. visual_requirements 中每个字段为数组，无匹配时用空数组。
3. scene: 场景类型; objects: 物体/家具/家电; actions: 动作/交互; style: 风格; materials: 材质; colors: 色调; emotion: 画面情绪。
4. 不要编造内容。只从脚本中提取真实描述的信息。
5. 输出纯 JSON，不要 ```json 或任何解释文字。"""

    def __init__(self, use_ai: bool = True, timeout: int = 20):
        self.use_ai = use_ai
        self.timeout = timeout

    def parse(self, copy_text: str) -> Dict:
        """解析完整脚本 → 结构化视觉需求"""
        if not copy_text or len(copy_text) < 10:
            return self._empty_result()

        if self.use_ai:
            try:
                return self._parse_with_deepseek(copy_text)
            except Exception as e:
                print(f"   [ScriptUnderstanding] DeepSeek 解析失败: {e}，使用规则降级")

        return self._parse_with_rules(copy_text)

    # ═══════════════════ DeepSeek 解析 ═══════════════════

    def _parse_with_deepseek(self, text: str) -> Dict:
        """调用 DeepSeek API 进行语义解析"""
        from core.deepseek_client import get_deepseek

        ds = get_deepseek()
        if not ds.available:
            raise RuntimeError("DeepSeek API Key 未配置，无法进行语义解析。"
                               "请在系统设置中配置 API Key 或关闭「智能匹配」。")

        prompt = (
            f"分析以下口播脚本，输出每句的视觉需求 JSON:\n\n{text}"
        )
        response = ds._call(
            self.SYSTEM_PROMPT, prompt,
            max_tokens=1500, temperature=0.3
        )
        if not response:
            raise RuntimeError("DeepSeek 返回空结果")

        # 清理可能的 Markdown 包裹
        response = response.strip()
        if response.startswith("```"):
            response = re.sub(r'^```(?:json)?\s*', '', response)
            response = re.sub(r'\s*```$', '', response)

        result = json.loads(response)

        # 验证必要字段
        if "segments" not in result:
            raise RuntimeError("DeepSeek 返回格式错误: 缺少 'segments' 字段")

        return self._normalize(result)
    # ═══════════════════ 规则降级 ═══════════════════

    def _parse_with_rules(self, text: str) -> Dict:
        """本地规则: 使用知识库提取关键词"""
        sentences = self._split_sentences(text)
        segments = []

        try:
            from utils.knowledge import get_bridge
            kb = get_bridge()
        except Exception:
            kb = None

        for sent in sentences:
            dur = max(1.0, len(sent) * DEFAULT_DURATION_PER_CHAR)
            req = {
                "scene": [], "objects": [], "actions": [],
                "style": [], "materials": [], "colors": [], "emotion": [],
            }

            if kb:
                kws = kb.extract_copy_keywords(sent)
                if kws.get("stones"):
                    req["materials"] = list(kws["stones"])[:3]
                if kws.get("styles"):
                    req["style"] = list(kws["styles"])[:2]
                if kws.get("crafts"):
                    req["actions"].extend(list(kws["crafts"])[:2])
                if kws.get("island_types"):
                    req["scene"] = list(kws["island_types"])[:2]

            # 简单关键词匹配
            lower = sent.lower()
            if any(k in lower for k in ["岛台", "厨房", "中岛"]):
                req["scene"].append("岛台厨房")
            if any(k in lower for k in ["抽屉", "烤箱", "插座", "水槽", "灯带"]):
                for k in ["抽屉", "烤箱", "插座", "水槽", "灯带", "冰箱", "拉篮"]:
                    if k in lower:
                        req["objects"].append(k)
            if any(k in lower for k in ["白", "黑", "灰", "奶油", "岩板"]):
                for k in ["白色", "黑色", "灰色", "奶油色", "岩板色"]:
                    if k[0] in lower:
                        req["colors"].append(k)
            if any(k in lower for k in ["极简", "奶油风", "中古风", "侘寂风", "轻奢"]):
                for k in ["极简风", "奶油风", "侘寂风", "轻奢风", "中古风"]:
                    if k in lower:
                        req["style"].append(k)

            segments.append({
                "text": sent,
                "duration_sec": round(dur, 1),
                "visual_requirements": req,
            })

        return {
            "segments": segments,
            "global_style": (
                segments[0]["visual_requirements"]["style"][0]
                if segments and segments[0]["visual_requirements"]["style"]
                else "通用"
            ),
            "overall_mood": "专业展示",
            "_method": "规则降级",
        }

    # ═══════════════════ 工具方法 ═══════════════════

    def _split_sentences(self, text: str) -> List[str]:
        """按标点分句"""
        raw = re.split(r'(?<=[。！？.!?])', text)
        return [s.strip() for s in raw if len(s.strip()) > 3]

    def _normalize(self, result: Dict) -> Dict:
        """确保返回格式一致"""
        if "global_style" not in result:
            result["global_style"] = "通用"
        if "overall_mood" not in result:
            result["overall_mood"] = "专业展示"
        for seg in result.get("segments", []):
            req = seg.get("visual_requirements", {})
            for field in ["scene", "objects", "actions", "style", "materials", "colors", "emotion"]:
                if field not in req:
                    req[field] = []
                if not isinstance(req[field], list):
                    req[field] = [req[field]]
            seg["visual_requirements"] = req
        return result

    def _empty_result(self) -> Dict:
        return {"segments": [], "global_style": "通用", "overall_mood": "通用"}
