"""
╔══════════════════════════════════════════════════════════════╗
║  🛡️  安全加固模块                                        ║
║                                                            ║
║  - API Key 防护（脱敏/检测泄漏/安全加载）                  ║
║  - 敏感字段过滤                                           ║
║  - 配置文件安全读写                                       ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import re
import json
from pathlib import Path
from typing import Optional, Dict, Any, List


# ═══════════════════════════════════════════════════════════════
# 敏感字段检测
# ═══════════════════════════════════════════════════════════════

SENSITIVE_PATTERNS = [
    r'sk-[a-zA-Z0-9]{20,}',              # OpenAI/DeepSeek API Key
    r'api[_-]?key["\s:=]+([a-zA-Z0-9_-]{20,})',  # API Key 赋值
    r'Bearer\s+[a-zA-Z0-9_-]{20,}',      # Bearer Token
    r'[a-zA-Z0-9]{32,}',                 # 长随机字符串（可能是Key）
]

REDACT_PLACEHOLDER = "***REDACTED***"


def redact_sensitive(text: str) -> str:
    """脱敏文本中的敏感信息"""
    for pattern in SENSITIVE_PATTERNS:
        text = re.sub(pattern, REDACT_PLACEHOLDER, text)
    return text


def detect_secret_leak(text: str) -> List[str]:
    """检测文本中是否包含疑似泄露的密钥，返回匹配的片段"""
    leaks = []
    for pattern in SENSITIVE_PATTERNS:
        matches = re.findall(pattern, text)
        for m in matches:
            if len(m) > 15:  # 过滤短匹配
                leaks.append(m[:8] + "..." + m[-4:])
    return leaks


def is_sensitive_key(key: str) -> bool:
    """判断配置键名是否为敏感字段"""
    key_lower = key.lower().replace("-", "_").replace(" ", "_")
    sensitive = [
        "api_key", "apikey", "api_secret", "secret", "password",
        "token", "credential", "private_key", "authorization",
    ]
    return any(s in key_lower for s in sensitive)


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """递归过滤字典中的敏感字段"""
    if not isinstance(data, dict):
        return data
    result = {}
    for k, v in data.items():
        if is_sensitive_key(k):
            if v and isinstance(v, str):
                result[k] = v[:4] + "****" + v[-4:] if len(v) > 8 else "****"
            else:
                result[k] = "****"
        elif isinstance(v, dict):
            result[k] = sanitize_dict(v)
        elif isinstance(v, list):
            result[k] = [
                sanitize_dict(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            result[k] = v
    return result


# ═══════════════════════════════════════════════════════════════
# 安全文件读写
# ═══════════════════════════════════════════════════════════════

def safe_read_json(filepath: Path) -> Optional[Dict]:
    """安全读取 JSON 文件（即使损坏也不会崩溃）"""
    try:
        if not filepath.exists():
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, IOError, UnicodeDecodeError):
        return None


def safe_write_json(filepath: Path, data: Dict, ensure_ascii: bool = False,
                    sanitize: bool = False):
    """
    安全写入 JSON 文件（原子写入：先写临时文件再重命名）。
    v12.0 修复: sanitize 参数默认 False — 调用者须显式选择脱敏，避免静默数据丢失。
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp = filepath.with_suffix(filepath.suffix + ".tmp")

    # 显式选择时才过滤敏感字段
    safe_data = sanitize_dict(data) if sanitize else data

    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(safe_data, f, ensure_ascii=ensure_ascii, indent=2)
        tmp.replace(filepath)  # 原子操作
    except Exception:
        # 直接写入（非原子，但尽力而为）
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(safe_data, f, ensure_ascii=ensure_ascii, indent=2)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def safe_read_env(env_path: Path) -> Dict[str, str]:
    """安全读取 .env 文件，返回键值对字典"""
    result = {}
    if not env_path.exists():
        return result
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    result[key] = value
    except Exception:
        pass
    return result


# ═══════════════════════════════════════════════════════════════
# API Key 安全加载（优先环境变量 → .env → 询问用户）
# ═══════════════════════════════════════════════════════════════

def load_api_key(key_name: str, env_var: str = None, required: bool = True) -> Optional[str]:
    """
    安全加载 API Key。
    优先级：系统环境变量 > .env 文件 > None

    参数:
      key_name: 人类可读的名称（用于日志）
      env_var:  环境变量名，默认与 key_name 大写+下划线
      required: 是否必需，若为 True 且找不到则打印警告
    """
    if env_var is None:
        env_var = key_name.upper().replace(" ", "_") + "_API_KEY"

    # 1. 系统环境变量
    value = os.environ.get(env_var)
    if value:
        return value

    # 2. .env 文件
    from core.config import _PROJECT_ROOT
    env_file = Path(_PROJECT_ROOT) / ".env"
    env_data = safe_read_env(env_file)
    value = env_data.get(env_var)
    if value and value not in ("your_api_key_here", "your_deepseek_api_key_here", ""):
        return value

    # 3. 未找到
    if required:
        print(f"   ⚠ {key_name} API Key 未配置 ({env_var})")
        print(f"   💡 请设置环境变量或在 {env_file} 中配置")

    return None


# ═══════════════════════════════════════════════════════════════
# 自检
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 50)
    print("  安全模块自检")
    print("=" * 50)

    # 测试脱敏
    test_text = "DEEPSEEK_API_KEY=sk-abc123def456ghi789jkl"
    print(f"  脱敏测试: {redact_sensitive(test_text)}")
    print(f"  泄漏检测: {detect_secret_leak(test_text)}")

    # 测试敏感键判断
    for k in ["deepseek_api_key", "user_name", "password", "bgm_path"]:
        print(f"  敏感键 '{k}': {is_sensitive_key(k)}")
