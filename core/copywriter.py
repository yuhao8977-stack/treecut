"""
╔══════════════════════════════════════════════════════════════╗
║  ✍  video_editor.copywriter — DeepSeek AI 文案生成        ║
╚══════════════════════════════════════════════════════════════╝
"""
import re
import random
from typing import Optional, List

from core.config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    CTA_KEYWORDS, CTA_TEMPLATES, TTS_CHARS_PER_SEC, DEFAULT_COPY_DURATION,
)
from utils.text_filter import filter_redbook_text, contains_forbidden_word


# ═══════════════════════════════════════════════════════════════
# DeepSeek 系统提示词
# ═══════════════════════════════════════════════════════════════

DEEPSEEK_SYSTEM_PROMPT = """你是「坤宝岛台」品牌的口播文案专家,专为28秒竖版短视频写配音脚本.

# ★ 强制三段式结构(缺一不可)

## 第一段:钩子开头(0-3秒,约15字)
制造悬念或直击痛点,五选一,每次换一种:
- "90%的人选岛台都踩坑,装完才后悔！"(数据冲击)
- "你敢信吗？这个岛台居然自带XXX！"(反常识)
- "从普通厨房到高级感,只差岛台这一步！"(场景反差)
- "知道这个是什么吗？这是我们家的XXX岛台！"(悬念提问)
- "我把普通岛台换成这个,整个厨房都高级了！"(改造对比)

## 第二段:核心卖点展开(3-24秒,约55-65字)
依次介绍3-4个不同的核心功能,每个卖点1-2句:
- 每句12-18字,口语化短句,适合配音朗读
- 给每个卖点起具体名字:XX风+XX款+XX材质
- 细节画面感:材质厚度,工艺,使用场景
- 关键词:呢,吧,哇,你看,就是,这样的,太

## 第三段:★ 结尾CTA行动引导(24-28秒,约15-20字)★
**[这是全文最重要的部分,绝对不能省略！]**
必须包含明确的行动引导:
- "想要同款岛台的朋友,评论区扣1发你详细方案"
- "喜欢这种设计的话点个关注,每天分享更多岛台案例"
- "有任何问题私信我,免费给你设计专属岛台"

# ★ 铁律(违反以下任何一条都是不合格)
1. !! 三段式结构必须完整:钩子->卖点->CTA,缺一不可
2. !! 最后一句话必须是CTA行动引导,绝不能是功能描述
3. !! 每个卖点对应一句文案,材质颜色必须与画面一致
4. !! 禁止相邻句子结构雷同；禁止连续"你看...再看..."
5. !! 禁止编号,禁止[],禁止书面词,禁止编造颜色
6. !! 总字数80-90字,不能截断,不能超出

# 参考范文
"岛台装修别人装出高级感,你装的平平无奇！差距就在岛台功能上.上层薄抽一拉开,零食收纳超顺手.内嵌烤箱精准开孔,烘焙聚餐一步到位.轨道插座随意移动,小家电想放哪就放哪.喜欢这种全能岛台吗？评论区扣1发你详细方案." """


# ═══════════════════════════════════════════════════════════════
# 画面描述提取
# ═══════════════════════════════════════════════════════════════

# ── 画面描述提取 — 预编译关键词正则 ──
_MATERIAL_KW_RE = re.compile(
    r'岩板|木纹|奶油|黑色|白色|纯黑|纯白|深灰|浅棕|深棕|橡木|胡桃|'
    r'樱桃|奢石|洞石|潘多拉|宝格丽|维多利亚|翡翠|水泥|微水泥|哑光|亮光'
)

# ★ v12.3: 家居行业30+细分标签库 — 支撑文案关键词提取和素材智能匹配
HOME_TAGS = {
    "材质":  ["岩板", "原木", "实木", "颗粒板", "多层板", "石英石", "不锈钢", "玻璃", "亚克力"],
    "品类":  ["岛台", "餐桌", "橱柜", "衣柜", "鞋柜", "电视柜", "玄关柜", "酒柜", "餐边柜"],
    "风格":  ["极简", "轻奢", "北欧", "新中式", "日式", "工业风", "奶油风", "原木风", "现代风"],
    "功能":  ["定制", "防水", "耐磨", "收纳", "伸缩", "折叠", "灯带", "插座", "内嵌", "轨道"],
    "场景":  ["厨房", "客厅", "卧室", "玄关", "阳台", "小户型", "大平层", "别墅"],
    "品牌":  ["坤宝", "定制家", "全屋定制", "高端定制"],
}

def extract_home_tags(text: str) -> dict:
    """★ v12.3: 按家居行业标签库提取分类关键词"""
    results = {}
    for category, tags in HOME_TAGS.items():
        matched = [tag for tag in tags if tag in text]
        if matched:
            results[category] = matched
    return results

def extract_all_keywords(text: str) -> list:
    """★ v12.3: 从文案中提取全部家居标签(去重)"""
    tags = extract_home_tags(text)
    seen = set()
    flat = []
    for vals in tags.values():
        for v in vals:
            if v not in seen:
                seen.add(v)
                flat.append(v)
    return flat

def calculate_match_score(material_tags: list, script_keywords: list) -> float:
    """★ v12.3: 计算素材标签与文案关键词的匹配度(0-1)"""
    if not script_keywords:
        return 0.5
    hit = len(set(material_tags) & set(script_keywords))
    return round(hit / len(script_keywords), 2)

def extract_video_descriptions(clips: List[dict]) -> List[str]:
    """从视频文件名精确提取画面内容描述 (v2 — 预编译正则)"""
    descs = []
    for c in clips:
        fname = c["path"].stem
        tags = re.findall(r'\[([^\]]+)\]', fname)
        material = ""
        for t in tags:
            if '+' in t and len(t) > 4 and not t[0].isdigit():
                material = t; break
        if not material:
            for t in tags:
                if _MATERIAL_KW_RE.search(t):
                    material = t; break
        feature = ""
        for t in reversed(tags):
            if len(t) >= 4 and not t[0].isdigit() and t != material:
                feature = t; break
        kw = c.get("keyword", "")
        if material and feature:
            desc = f"画面: {material}色岛台,{feature}"
        elif material:
            desc = f"画面: {material}色岛台,展示{kw}设计"
        elif feature:
            desc = f"画面: 展示{feature}"
        else:
            desc = f"画面: 展示{kw}相关设计"
        descs.append(desc)
    return descs


# ═══════════════════════════════════════════════════════════════
# CTA 检测与追加
# ═══════════════════════════════════════════════════════════════

def check_cta_present(text: str) -> bool:
    """检测文案结尾是否包含CTA行动引导"""
    tail = text[-40:] if len(text) > 40 else text
    return any(kw in tail for kw in CTA_KEYWORDS)


def append_cta_if_missing(text: str) -> str:
    """如果文案没有CTA,自动在末尾追加"""
    cta = random.choice(CTA_TEMPLATES)
    if text and text[-1] not in ".！？~":
        text += "."
    return text + cta


# ═══════════════════════════════════════════════════════════════
# 备用文案（API不可用时）
# ═══════════════════════════════════════════════════════════════

def generate_fallback_copy(keyword: str) -> str:
    """API失败时的模板备用文案"""
    templates = [
        lambda kw: (
            f"90%的人选岛台都踩坑了！装完才后悔没做{kw}."
            f"坤宝岛台把{kw}做到极致,严丝合缝的细节看得见."
            f"收纳翻倍,台面永远干净,小户型也有大厨房."
            f"喜欢这个设计吗？评论区告诉我,免费拿方案！"
        ),
        lambda kw: (
            f"你敢信吗？这个岛台居然自带{kw}！"
            f"自从装了坤宝岛台,厨房动线顺了不止一倍呢."
            f"{kw}设计太贴心了,每天做饭都是一种享受."
            f"姐妹们心动了吗💕 私信我解锁你的岛台方案～"
        ),
        lambda kw: (
            f"岛台装修别再踩坑了！{kw}才是正确打开方式."
            f"坤宝岛台的{kw}设计,简单高级又好打理."
            f"12mm岩板一体成型,手感温润,越用越喜欢."
            f"想抄作业的评论区扣1✨我来安排！"
        ),
    ]
    return filter_redbook_text(random.choice(templates)(keyword))[0]


# ═══════════════════════════════════════════════════════════════
# DeepSeek 文案生成
# ═══════════════════════════════════════════════════════════════

def generate_copy(keyword: str, num_clips: int, total_duration: float,
                  clips: List[dict] = None) -> str:
    """调用DeepSeek生成小红书风格文案"""
    if not DEEPSEEK_API_KEY:
        print("   !! 未配置 DEEPSEEK_API_KEY")
        return generate_fallback_copy(keyword)

    try:
        from openai import OpenAI
    except ImportError:
        print("   !! openai 库未安装")
        return generate_fallback_copy(keyword)

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    selling_points_shown = [keyword]
    if clips:
        for c in clips:
            parent = c["path"].parent.name
            clean = re.sub(r'^\d+', '', parent)
            if clean and clean not in selling_points_shown:
                selling_points_shown.append(clean)
    selling_points_str = ",".join(selling_points_shown[:5])

    scene_lines = []
    if clips:
        descs = extract_video_descriptions(clips)
        for i, desc in enumerate(descs):
            scene_lines.append(f"  片段{i+1}: {desc}")
    scene_desc = "\n".join(scene_lines) if scene_lines else f"  (关于{keyword}的展示画面)"

    HOOK_SEC = 3.0
    CTA_SEC = 6.0
    features_sec = max(10.0, total_duration - HOOK_SEC - CTA_SEC)
    max_chars = int(total_duration * 3.2)
    features_chars = int(features_sec * 3.2)
    cta_chars = int(CTA_SEC * 3.2)

    user_prompt = f"""请为「坤宝岛台」生成口播配音脚本,视频总时长{total_duration:.0f}秒.

当前视频展示的卖点:{selling_points_str}

画面内容依次为:
{scene_desc}

# ★ 强制遵守的三段式结构

## 第一段[钩子开头 0-3秒, 约15字]
从系统提示给出的5种钩子中选一种(不要原文照抄),直击厨房岛台的痛点或制造悬念.

## 第二段[核心卖点 3-{3+features_sec:.0f}秒, 约{features_chars}字]
依次介绍视频中展示的3-4个不同功能,每句对应一个卖点:
- 共{num_clips-1 if num_clips > 2 else num_clips}句功能描述
- 每句12-18字,口语化
- 材质颜色与画面严格一致

## 第三段[★ CTA行动引导 {total_duration-CTA_SEC:.0f}-{total_duration:.0f}秒, 约{cta_chars}字]★
**[这是全文最重要的1句,绝对不能省略！]**
从以下三个方向选一个:
- 引导评论
- 引导关注
- 引导私信

# 铁律
- !! 全文必须包含钩子+卖点+CTA三段
- !! 最后一句话必须是CTA行动引导
- !! 总字数80-90字,不要编号
- !! 每句材质颜色与画面一致"""

    print(f"   🤖 正在调用 DeepSeek 生成三段式文案...")
    print(f"   📐 时长预算: 钩子{HOOK_SEC:.0f}s + 卖点{features_sec:.0f}s + CTA{CTA_SEC:.0f}s = {total_duration:.0f}s")

    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.9,
            max_tokens=600,
        )
        copy_text = response.choices[0].message.content.strip()
        # ── 敏感词过滤 (v11.1 新增) ──
        has_forbidden, matched = contains_forbidden_word(copy_text)
        if has_forbidden:
            print(f"   ⚠️ 检测到违禁词: {matched}，正在自动过滤...")
            copy_text, filtered_count = filter_redbook_text(copy_text)
            print(f"   ✅ 已完成 {filtered_count} 处违禁词处理")
        has_cta = check_cta_present(copy_text)
        print(f"   ✅ 文案生成成功({len(copy_text)}字)")
        if has_cta:
            print(f"   ✅ CTA检查: 结尾包含行动引导")
        else:
            print(f"   !! CTA检查: 未检测到明确行动引导,已自动追加")
            copy_text = append_cta_if_missing(copy_text)
        return copy_text
    except Exception as e:
        print(f"   ❌ DeepSeek API 调用失败: {e}")
        print(f"   !! 将使用默认文案")
        return generate_fallback_copy(keyword)
