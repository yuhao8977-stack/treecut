"""
小红书敏感词与违规词自动过滤 (Text Filter)
================================================================
三层防护: 系统提示词约束 + 输出后强制过滤 + 备用文案过滤

用法:
  from utils.text_filter import filter_redbook_text, contains_forbidden_word
  has_forbidden, matched = contains_forbidden_word(text)
  clean_text, changes = filter_redbook_text(text)
"""
import re
from typing import Tuple, List

# ── 直接匹配词库 ──
FORBIDDEN_WORDS = {
    # 导流类
    "评论区扣1": "", "评论区扣一": "", "私信我": "", "加微信": "", "加V": "",
    "加VX": "", "加我微信": "", "看主页": "", "私藏": "",
    # 绝对化/极限词 → 弱化替换
    "最": "很", "第一": "值得推荐", "唯一": "不可多得", "顶级": "高品质",
    "极致": "非常", "绝对": "很", "永久": "长期", "万能": "多功能",
    "全网最佳": "口碑优选",
    # 功效夸大
    "治疗": "改善", "消炎": "舒缓", "杀菌": "洁净", "减肥": "管理体重",
    "祛斑": "淡化", "除皱": "平滑", "逆龄": "更显年轻", "零甲醛": "",
    "食品级": "安全环保", "永不褪色": "持久耐用", "终身保修": "完善售后",
    # 虚假承诺
    "100%": "高", "绝对安全": "很安全", "无毒无害": "环保材质",
    "无效退款": "", "包教包会": "", "保过": "",
    # 刺激消费
    "秒杀": "限时优惠", "抢爆": "热门", "再不抢就没了": "",
    "错过就没机会了": "", "万人疯抢": "受欢迎",
    # 封建迷信
    "招财进宝": "", "旺财": "", "带来好运": "", "护身": "",
    # 更多敏感词
    "免费拿": "", "免费送": "", "0元购": "", "出厂价": "优惠价",
    "批发价": "优惠价", "包安装": "", "包上楼": "",
}

# ── 正则变体模式 ──
PATTERNS = [
    (r'[薇微]信|[vV][xX]|[vV]我?', ""),
    (r'看[主頁主页]|首[页葉]', ""),
    (r'最{1,3}', "很"),
    (r'第?[1一]|N[Oo].?[1一]', "值得推荐"),
    (r'\d{2,3}%[\s]*纯棉|十成棉', "高含棉量"),
    (r'免[费廢]\s*拿|免[费廢]\s*送|0[元圆]\s*购', ""),
    (r'出[厂厰]\s*价|批[发發]\s*价', "优惠价"),
    (r'包[安按]\s*装|包[上]\s*楼', ""),
    (r'领[取]\s*免', "获得"),
]


def contains_forbidden_word(text: str) -> Tuple[bool, str]:
    """检查文本是否包含违禁词。返回 (是否违禁, 匹配到的词列表)。"""
    matched = set()
    for word in FORBIDDEN_WORDS:
        if word in text:
            matched.add(word)
    for pattern, _ in PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            matched.add(f"匹配: {pattern}")
    if matched:
        return True, ", ".join(sorted(matched)[:8])
    return False, ""


def filter_redbook_text(text: str) -> Tuple[str, int]:
    """
    过滤文本中的敏感词。
    返回 (过滤后文本, 修改次数)。
    规则: 有替换词则替换，无替换词则删除。
    """
    changes = 0
    # 1. 直接词替换
    for word, replacement in FORBIDDEN_WORDS.items():
        count = text.count(word)
        if count > 0:
            if replacement:
                text = text.replace(word, replacement)
            else:
                text = text.replace(word, "")
            changes += count

    # 2. 正则模式替换
    for pattern, replacement in PATTERNS:
        new_text, count = re.subn(pattern, replacement, text, flags=re.IGNORECASE)
        if count > 0:
            changes += count
            text = new_text

    # 3. 清理多余标点和空白
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'，{2,}', '，', text)
    text = re.sub(r'。{2,}', '。', text)
    text = re.sub(r'！{2,}', '！', text)

    return text, changes


def append_compliance_note(text: str) -> str:
    """在文案末尾追加合规声明（如果还不存在）"""
    note = "以上展示效果因个体差异可能不同，请以实物为准。"
    if note not in text and len(text) > 20:
        text = text.rstrip("。！？.!?") + "。" + note
    return text
