"""
Island Counter Industry Knowledge Base V1.0
4-level tag system + auto-correction for VL model outputs
"""
import json
from pathlib import Path

KB_FILE = Path(__file__).parent / "island_kb.json"

# Full industry taxonomy
INDUSTRY_KB = {
    "product": {
        "岛台": ["island", "kitchen island", "中岛", "island counter"],
        "餐边柜": ["sideboard", "buffet", "side cabinet"],
        "吧台": ["bar counter", "bar table", "breakfast bar"],
        "中岛柜": ["center island cabinet", "central island"],
        "悬浮岛台": ["floating island", "suspended island"],
        "落地岛台": ["floor-standing island", "full-height island"],
        "岛台餐桌一体": ["island dining table combo", "integrated island table"],
    },
    "material": {
        "岩板": ["sintered stone", "slab", "rock panel", "stone slab"],
        "通体岩板": ["full-body sintered stone", "through-body slab"],
        "连纹岩板": ["continuous vein slab", "book-matched slab"],
        "大理石": ["marble", "natural stone"],
        "石英石": ["quartz", "engineered quartz"],
        "洞石": ["travertine", "travertine stone"],
        "微水泥": ["micro cement", "microcement", "cement finish"],
        "不锈钢": ["stainless steel", "metal surface"],
        "实木": ["solid wood", "natural wood", "timber"],
        "人造石": ["engineered stone", "artificial stone", "acrylic solid surface"],
    },
    "craft": {
        "海棠角": ["beveled edge", "chamfered corner"],
        "水磨边": ["water-polished edge", "smooth edge"],
        "圆弧倒角": ["rounded corner", "radius edge", "filleted edge"],
        "无缝台面": ["seamless countertop", "joint-free surface"],
        "六面防潮": ["6-sided moisture proof", "full moisture barrier"],
        "悬浮底座": ["floating base", "suspended foundation"],
        "腰线设计": ["waistline design", "belt-line detail"],
    },
    "hardware": {
        "公牛轨道插座": ["track socket", "rail socket", "movable outlet"],
        "隐藏式插座": ["hidden socket", "concealed outlet", "pop-up socket"],
        "软关门铰链": ["soft-close hinge", "damped hinge"],
        "全推拉抽屉": ["full-extension drawer", "push-pull drawer"],
        "感应灯带": ["sensor light strip", "motion LED strip"],
        "无拉手设计": ["handleless design", "push-to-open"],
        "嵌入式蒸烤": ["built-in steam oven", "integrated oven"],
        "集成水槽": ["integrated sink", "built-in sink"],
    },
    "style": {
        "意式中古风": ["Italian mid-century", "Italian vintage"],
        "法式奶油风": ["French cream style", "French pastoral"],
        "侘寂风": ["wabi-sabi", "Japanese zen", "imperfect beauty"],
        "极简风": ["minimalist", "ultra-minimal", "clean line"],
        "轻奢风": ["light luxury", "affordable luxury"],
        "原木风": ["natural wood style", "organic wood"],
        "包豪斯": ["Bauhaus", "form follows function"],
        "新中式": ["neo-Chinese", "modern oriental"],
        "工业风": ["industrial style", "loft style"],
    },
    "scene": {
        "备餐": ["food prep", "meal preparation"],
        "下厨": ["cooking", "kitchen work"],
        "就餐": ["dining", "eating", "meal time"],
        "展示": ["display", "showcase", "presentation"],
        "收纳展示": ["storage display", "organized storage"],
        "开放厨房": ["open kitchen", "open-plan kitchen"],
        "动线设计": ["workflow design", "kitchen triangle"],
    },
    "sense": {
        "温润": ["warm and smooth", "gentle texture"],
        "细腻": ["fine grain", "delicate", "refined"],
        "哑光": ["matte", "non-glossy", "soft finish"],
        "通透": ["transparent", "airy", "open feel"],
        "大气": ["grand", "spacious", "magnificent"],
        "沉稳": ["steady", "grounded", "solid presence"],
    },
}

# VL correction mapping (generic -> industry-specific)
VL_CORRECTION = {
    "table": "岛台",
    "desk": "岛台",
    "cabinet": "餐边柜",
    "stone": "岩板",
    "rock": "岩板",
    "wood": "实木",
    "metal": "不锈钢",
    "drawer": "抽屉",
    "shelf": "收纳层",
    "kitchen": "厨房空间",
    "modern": "现代简约",
    "simple": "极简风",
    "luxury": "轻奢风",
    "vintage": "中古风",
    "white": "白色系",
    "black": "黑色系",
    "brown": "木纹色系",
    "grey": "灰色系",
}


def query_kb(category=None, keyword=None):
    """Query industry knowledge base"""
    if category and category in INDUSTRY_KB:
        return INDUSTRY_KB[category]
    if keyword:
        results = []
        for cat, items in INDUSTRY_KB.items():
            for k, aliases in items.items():
                if keyword in k or any(keyword in a for a in aliases):
                    results.append({"category": cat, "keyword": k, "aliases": aliases})
        return results
    return INDUSTRY_KB


def correct_vl_output(vl_tag):
    """Correct generic VL model output to industry-specific terms"""
    vl_lower = vl_tag.lower().strip()
    if vl_lower in VL_CORRECTION:
        return VL_CORRECTION[vl_lower]
    for cat, items in INDUSTRY_KB.items():
        for keyword, aliases in items.items():
            if vl_lower in [a.lower() for a in aliases] or vl_lower == keyword.lower():
                return keyword
    return vl_tag


def save_kb():
    KB_FILE.write_text(json.dumps(INDUSTRY_KB, ensure_ascii=False, indent=2), encoding="utf-8")


def load_kb():
    if KB_FILE.exists():
        return json.loads(KB_FILE.read_text(encoding="utf-8"))
    return INDUSTRY_KB
