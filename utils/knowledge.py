"""
╔══════════════════════════════════════════════════════════════╗
║  🧠 V5 知识库桥接模块                                     ║
║                                                            ║
║  将 material_engine_v5 的专业知识库集成到主流程:           ║
║  - 石材库 (Stone Library)                                 ║
║  - 工艺库 (Craft Library)                                 ║
║  - 五金库 (Hardware Library)                              ║
║  - 风格库 (Style Library)                                 ║
║  - 岛台视觉专家 (Island Vision Expert)                    ║
║                                                            ║
║  用于强化文案-画面的智能匹配,提升匹配准确率               ║
║                                                            ║
║  用法:                                                     ║
║    from utils.knowledge_bridge import *            ║
║    kb = KnowledgeBridge()                                  ║
║    matched = kb.match_copy_to_clips(copy, materials)       ║
╚══════════════════════════════════════════════════════════════╝
"""
import re
import json
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict


# ═══════════════════════════════════════════════════════════════
# 岛台行业专业知识库（嵌入代码，无需外部依赖）
# ═══════════════════════════════════════════════════════════════

# ── 石材库 ──
STONE_LIBRARY = {
    "岩板": {
        "brands": ["拉米娜", "德赛斯", "依诺", "东鹏", "冠珠", "诺贝尔"],
        "series": ["潘多拉", "宝格丽", "鱼肚白", "寒江雪", "雪花白", "爵士白",
                   "威尼斯棕", "爱马仕灰", "伯爵灰", "普拉达绿", "香奈儿白",
                   "罗马洞石", "米黄洞石", "卡尔德拉", "艾米利亚棕"],
        "finishes": ["哑光", "亮光", "柔光", "肌理面", "酸洗面"],
        "thicknesses": ["3mm", "6mm", "12mm", "15mm", "20mm"],
        "properties": ["耐高温", "防刮耐磨", "零渗透", "食品级", "UV耐候"],
        "keywords": ["通体岩板", "连纹岩板", "对纹", "无缝拼接", "薄板"],
    },
    "石英石": {
        "brands": ["赛凯隆", "中迅", "万峰", "必图"],
        "series": ["卡拉拉白", "雪花白", "爵士白"],
        "keywords": ["石英石台面", "人造石", "树脂台面"],
    },
    "洞石": {
        "variants": ["罗马洞石", "米黄洞石", "超白洞石", "银白洞石"],
        "keywords": ["洞石台面", "洞石岛台", "天然洞石"],
    },
    "微水泥": {
        "keywords": ["微水泥台面", "微水泥岛台", "微水泥奶油白"],
    },
    "实木": {
        "variants": ["南美柚木", "北美黑胡桃", "兰亭香樟", "橡木", "樱桃木"],
        "keywords": ["实木台面", "原木岛台", "实木拼接"],
    },
    "不锈钢": {
        "keywords": ["不锈钢台面", "拉丝不锈钢", "304不锈钢"],
    },
}

# ── 工艺库 ──
CRAFT_LIBRARY = {
    "边角处理": {
        "海棠角": {"工艺": "45°倒角拼接", "效果": "阳角线条利落"},
        "水磨边": {"工艺": "水磨圆角R3-R5", "效果": "圆润防磕碰"},
        "圆弧倒角": {"工艺": "CNC数控圆弧", "效果": "流畅曲线"},
        "折边": {"工艺": "岩板45°折弯", "效果": "一体成型无拼缝"},
    },
    "拼接工艺": {
        "连纹对纹": {"工艺": "纹理连续拼接", "效果": "天然石材纹理贯通"},
        "无缝拼接": {"工艺": "树脂填缝+打磨", "效果": "视觉无缝"},
        "海棠角拼接": {"工艺": "45°拼角", "效果": "直角阳角"},
    },
    "结构设计": {
        "悬浮式": {"工艺": "钢结构隐藏支撑", "效果": "视觉轻盈漂浮"},
        "嵌入式": {"工艺": "精准开孔预埋", "效果": "家电齐平台面"},
        "一体式": {"工艺": "整体钢架焊接", "效果": "结构稳固不变形"},
    },
    "防护处理": {
        "防潮": {"工艺": "六面封边密封", "效果": "潮湿环境不变形"},
        "防污": {"工艺": "纳米涂层", "效果": "油污水渍不渗透"},
        "耐高温": {"工艺": "岩板烧结工艺", "效果": "高温不炸裂"},
    },
}

# ── 五金库 ──
HARDWARE_LIBRARY = {
    "电力系统": {
        "公牛轨道插座": {"类型": "移动轨道式", "功率": "8000W", "特点": "随意移动"},
        "隐藏式插座": {"类型": "台面弹起式", "特点": "不用时隐藏"},
        "弹出式插座": {"类型": "按压弹起", "特点": "旋转180°"},
    },
    "滑轨系统": {
        "薄抽滑轨": {"类型": "阻尼全拉出", "承重": "45kg"},
        "全推拉抽屉": {"类型": "全推拉+阻尼", "承重": "60kg"},
        "底层抽": {"类型": "重型阻尼轨", "承重": "80kg"},
    },
    "铰链系统": {
        "软关门铰链": {"类型": "液压阻尼", "特点": "无声闭合"},
        "天地铰": {"类型": "天地轴", "特点": "高柜适用"},
    },
    "灯光系统": {
        "感应灯带": {"类型": "人体感应+手扫", "色温": "3000K/4000K"},
        "氛围灯带": {"类型": "柜底/柜内LED", "色温": "2700K暖光"},
    },
    "特殊功能": {
        "升降台面": {"类型": "电动/液压", "行程": "200-400mm"},
        "旋转拉篮": {"类型": "270°旋转", "特点": "角落利用"},
    },
}

# ── 风格库 ──
STYLE_LIBRARY = {
    "意式中古风": {
        "colors": ["柚木色", "深棕", "黑胡桃", "奶油白"],
        "materials": ["南美柚木", "北美黑胡桃", "哑光岩板", "微水泥"],
        "features": ["藤编元素", "复古拉手", "开放格", "圆弧倒角"],
        "mood": "温润复古,沉稳大气",
    },
    "法式奶油风": {
        "colors": ["奶白", "奶油白", "浅米色", "暖白"],
        "materials": ["哑光白岩板", "实木", "微水泥"],
        "features": ["圆弧倒角", "线条装饰", "开放格", "海棠角"],
        "mood": "温柔浪漫,精致优雅",
    },
    "侘寂风": {
        "colors": ["米色", "浅灰", "大地色", "原木色"],
        "materials": ["微水泥", "洞石", "原木", "亚光岩板"],
        "features": ["粗糙肌理", "自然边缘", "不对称设计"],
        "mood": "质朴自然,禅意宁静",
    },
    "极简风": {
        "colors": ["纯白", "纯黑", "深灰", "浅灰"],
        "materials": ["哑光岩板", "不锈钢", "玻璃"],
        "features": ["无拉手", "隐藏式", "直线条", "悬浮式"],
        "mood": "纯粹简约,极致克制",
    },
    "轻奢风": {
        "colors": ["香奈儿白", "宝格丽黑", "金色", "深棕"],
        "materials": ["亮光岩板", "潘多拉", "不锈钢", "玻璃"],
        "features": ["金属线条", "玻璃门", "灯光装饰"],
        "mood": "低调奢华,精致质感",
    },
    "原木风": {
        "colors": ["原木色", "暖白", "浅棕", "米色"],
        "materials": ["实木", "橡木", "柚木", "原木贴皮"],
        "features": ["开放格", "实木台面", "藤编"],
        "mood": "自然温馨,日式简约",
    },
    "新中式": {
        "colors": ["胡桃木色", "深棕", "黑色", "米白"],
        "materials": ["黑胡桃", "岩板", "实木"],
        "features": ["线条装饰", "对称设计", "镂空腰线"],
        "mood": "东方韵味,沉稳大气",
    },
    "工业风": {
        "colors": ["黑色", "深灰", "铁锈色", "水泥灰"],
        "materials": ["不锈钢", "微水泥", "黑岩板"],
        "features": ["裸露钢结构", "金属表面", "粗犷质感"],
        "mood": "硬朗粗犷,个性十足",
    },
    "北欧极简": {
        "colors": ["白色", "浅灰", "原木色", "浅蓝"],
        "materials": ["实木", "白色岩板", "橡木"],
        "features": ["简单线条", "功能性", "开放设计"],
        "mood": "简洁实用,自然清新",
    },
}

# ── 岛台品类映射 ──
ISLAND_TYPES = {
    "中岛台": "厨房中央独立岛台",
    "边岛台": "靠墙或L型半岛台",
    "双岛台": "双岛设计(功能+社交)",
    "吧台岛台": "吧台与岛台一体化",
    "餐桌岛台一体": "岛台延伸为餐桌",
    "悬浮岛台": "视觉悬空,钢结构隐藏支撑",
    "落地岛台": "传统落地式,稳定厚重",
    "连岛设计": "岛台与餐边柜/高柜相连",
}


# ═══════════════════════════════════════════════════════════════
# 知识库桥接引擎
# ═══════════════════════════════════════════════════════════════

class KnowledgeBridge:
    """
    V5 知识库桥接 — 为文案-画面匹配提供行业专业规则层。
    当 FAISS 语义检索不可用时,此模块提供比纯文件名匹配更准确的规则匹配。
    """

    def __init__(self):
        self._build_search_index()
        self._build_regex_patterns()  # v2.0: 预编译正则，O(n)单次扫描替代O(n*m)

    def _build_search_index(self):
        """构建所有知识库的扁平化搜索索引"""
        self._stone_index = {}
        for stone_type, data in STONE_LIBRARY.items():
            self._stone_index[stone_type] = stone_type
            for kw_list in [data.get("series", []), data.get("keywords", []),
                           data.get("variants", []), data.get("brands", [])]:
                for kw in kw_list:
                    self._stone_index[kw] = stone_type

        self._craft_index = {}
        for category, techniques in CRAFT_LIBRARY.items():
            for name, info in techniques.items():
                self._craft_index[name] = info.get("工艺", "")
                self._craft_index[category] = category

        self._hardware_index = {}
        for system, items in HARDWARE_LIBRARY.items():
            for name, info in items.items():
                self._hardware_index[name] = info.get("类型", "")
                self._hardware_index[system] = system

        self._style_index = {}
        for style, data in STYLE_LIBRARY.items():
            self._style_index[style] = style
            for kw in data.get("colors", []) + data.get("materials", []) + data.get("features", []):
                if kw not in self._style_index:
                    self._style_index[kw] = style

    def _build_regex_patterns(self):
        """预编译正则模式 — 将所有关键词按类别编译为 | 交替模式，实现O(n)单次扫描"""
        import re
        # 按长度降序排列关键词（长词优先匹配，避免"岛台"匹配到"岛台餐桌一体"的一部分）
        def _make_pattern(index_dict):
            if not index_dict:
                return None
            keys = sorted(index_dict.keys(), key=len, reverse=True)
            # 转义正则特殊字符
            escaped = [re.escape(k) for k in keys if len(k) >= 2]
            if not escaped:
                return None
            return re.compile("|".join(escaped))

        self._stone_re = _make_pattern(self._stone_index)
        self._craft_re = _make_pattern(self._craft_index)
        self._hardware_re = _make_pattern(self._hardware_index)
        self._style_re = _make_pattern(self._style_index)
        # 岛台类型
        island_keys = sorted(ISLAND_TYPES.keys(), key=len, reverse=True)
        self._island_re = re.compile("|".join(re.escape(k) for k in island_keys)) if island_keys else None

    def extract_copy_keywords(self, copy_text: str) -> Dict[str, Set[str]]:
        """
        从文案中提取结构化关键词 (v2.0 — 预编译正则 O(n) 单次扫描)。
        返回: {"stones": set, "crafts": set, "hardware": set, "styles": set, "island_types": set}
        """
        result = {
            "stones": set(),
            "crafts": set(),
            "hardware": set(),
            "styles": set(),
            "island_types": set(),
        }

        # 使用预编译正则替代逐个关键词 in 检查
        if self._stone_re:
            for m in self._stone_re.finditer(copy_text):
                result["stones"].add(self._stone_index[m.group()])
        if self._craft_re:
            for m in self._craft_re.finditer(copy_text):
                result["crafts"].add(m.group())
        if self._hardware_re:
            for m in self._hardware_re.finditer(copy_text):
                result["hardware"].add(m.group())
        if self._style_re:
            for m in self._style_re.finditer(copy_text):
                result["styles"].add(self._style_index.get(m.group(), m.group()))
        if self._island_re:
            for m in self._island_re.finditer(copy_text):
                result["island_types"].add(m.group())

        return result

    def extract_clip_keywords(self, clip_path, folder_name: str = "") -> Dict[str, Set[str]]:
        """
        从素材文件名和文件夹名中提取结构化关键词。
        """
        fname = str(clip_path) if isinstance(clip_path, str) else clip_path.name
        searchable = fname + " " + folder_name

        return self.extract_copy_keywords(searchable)

    def match_score(self, copy_kws: Dict[str, Set[str]],
                    clip_kws: Dict[str, Set[str]]) -> Tuple[float, str]:
        """
        计算文案关键词与素材关键词的匹配分数。
        返回: (score 0-1, match_method)
        """
        score = 0.0
        weights = {
            "stones": 0.25,
            "crafts": 0.15,
            "hardware": 0.20,
            "styles": 0.25,
            "island_types": 0.15,
        }
        matched_categories = 0

        for category, weight in weights.items():
            copy_set = copy_kws.get(category, set())
            clip_set = clip_kws.get(category, set())

            if not copy_set:
                # 文案没提该类别,不扣分
                score += weight * 1.0
                matched_categories += 1
                continue

            if not clip_set:
                continue

            overlap = len(copy_set & clip_set)
            coverage = overlap / len(copy_set) if copy_set else 1.0
            score += weight * coverage

            if coverage > 0:
                matched_categories += 1

        match_method = "knowledge"
        if matched_categories >= 4:
            match_method = "knowledge_precise"
        elif matched_categories >= 2:
            match_method = "knowledge_partial"
        elif score < 0.3:
            match_method = "knowledge_weak"

        return round(score, 3), match_method

    def match_copy_to_clips(self, copy_text: str, sentences: List[str],
                            clip_pool: List[Dict]) -> List[Dict]:
        """
        核心方法：将文案句子与素材池进行知识库规则匹配。

        返回: 带匹配分和匹配方式的素材列表
        """
        # 预计算每个素材的关键词签名
        clip_sigs = {}
        for i, clip in enumerate(clip_pool):
            path = clip.get("path", "")
            folder = clip.get("folder_name", Path(path).parent.name if path else "")
            clip_sigs[i] = self.extract_clip_keywords(str(path), folder)

        results = []
        used_clips = set()

        for sentence in sentences:
            if len(sentence.strip()) < 4:
                continue

            # 提取句子的知识库关键词
            sent_kws = self.extract_copy_keywords(sentence)

            # 为每个未使用的素材打分
            scored = []
            for i, clip in enumerate(clip_pool):
                if i in used_clips:
                    continue
                score, method = self.match_score(sent_kws, clip_sigs[i])
                if score > 0.2:  # 阈值
                    scored.append((i, score, method))

            scored.sort(key=lambda x: -x[1])

            if scored:
                best_i, best_score, best_method = scored[0]
                clip = clip_pool[best_i].copy()
                clip["match_score"] = best_score
                clip["match_method"] = best_method
                results.append(clip)
                used_clips.add(best_i)
            elif clip_pool:
                # 无匹配:随机选一个
                available = [i for i in range(len(clip_pool)) if i not in used_clips]
                idx = available[0] if available else 0
                clip = clip_pool[idx].copy()
                clip["match_score"] = 0.0
                clip["match_method"] = "random_fallback"
                results.append(clip)
                used_clips.add(idx)

        return results

    def get_style_recommendation(self, style_name: str) -> Optional[Dict]:
        """获取风格推荐信息"""
        return STYLE_LIBRARY.get(style_name)

    def get_island_type_info(self, island_type: str) -> Optional[str]:
        """获取岛台类型描述"""
        return ISLAND_TYPES.get(island_type)

    def get_matching_styles(self, keywords: List[str]) -> List[str]:
        """根据关键词推荐匹配的风格"""
        scores = defaultdict(int)
        for kw in keywords:
            for style, data in STYLE_LIBRARY.items():
                if kw in data.get("colors", []) or kw in data.get("materials", []) or kw in data.get("features", []):
                    scores[style] += 1
                if kw in style:
                    scores[style] += 2
        return sorted(scores, key=scores.get, reverse=True)


# ═══════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════

_bridge_instance: Optional[KnowledgeBridge] = None


def get_bridge() -> KnowledgeBridge:
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = KnowledgeBridge()
    return _bridge_instance


# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    kb = KnowledgeBridge()

    # 测试文案关键词提取
    test_copy = ("岛台装修别踩坑了！岩板台面选潘多拉哑光系列，"
                 "配上意式中古风的南美柚木柜体，海棠角工艺精致到每个细节。"
                 "轨道插座随意移动，感应灯带自动亮起。北欧极简的设计太耐看了。")

    kws = kb.extract_copy_keywords(test_copy)
    print("文案关键词提取:")
    for cat, items in kws.items():
        if items:
            print(f"  {cat}: {items}")

    # 测试素材匹配
    test_clips = [
        {"path": "【潘多拉哑光+南美柚木】岛台海棠角展示.mp4", "folder_name": "卖点展示"},
        {"path": "【纯白岩板】轨道插座演示.mp4", "folder_name": "效果展示"},
        {"path": "【洞石+橡木】北欧极简岛台.mp4", "folder_name": "效果展示"},
    ]

    clip_kws = [kb.extract_clip_keywords(c["path"], c["folder_name"]) for c in test_clips]
    sent_kws = kb.extract_copy_keywords(test_copy)

    print("\n素材-文案匹配分数:")
    for i, (clip, ck) in enumerate(zip(test_clips, clip_kws)):
        score, method = kb.match_score(sent_kws, ck)
        print(f"  [{i+1}] {clip['path'][:50]}... -> {score:.2f} ({method})")

    # 风格推荐
    recos = kb.get_matching_styles(["潘多拉", "南美柚木", "海棠角"])
    print(f"\n风格推荐: {recos}")
