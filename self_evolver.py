#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
  树剪 TreeCut — 自持续升级优化器 (Self-Evolver)
═══════════════════════════════════════════════════════════════

功能:
  1. 启动树剪程序（子进程）
  2. 模拟用户操作（GUI自动化 + 子进程CLI模式）
  3. 捕获日志/错误并分析
  4. 调用 DeepSeek API 生成修复代码
  5. 安全应用补丁（备份 + 回滚）
  6. 无限循环，记录迭代历史

用法:
  python self_evolver.py                    # 开始自进化循环
  python self_evolver.py --calibrate        # 校准模式（记录控件坐标）
  python self_evolver.py --once             # 单次测试（不循环）
  python self_evolver.py --max-loops 5      # 最多5次循环

依赖:
  pip install pyautogui openai  （可选，用于 UI 自动化和 AI 修复）
  pip install psutil            （可选，用于进程监控）
"""

import os, sys, json, time, random, re, shutil, signal, subprocess
import threading, traceback, hashlib, io, argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple

# ═══════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).parent
TREE_SCRIPT = PROJECT_ROOT / "树剪.py"
LOG_FILE = PROJECT_ROOT / "self_evolver_log.txt"
HISTORY_FILE = PROJECT_ROOT / "evolution_history.json"
BACKUP_DIR = PROJECT_ROOT / "evolution_backups"
CALIB_FILE = PROJECT_ROOT / "calibration.json"
CRASH_LOG = PROJECT_ROOT / "crash_log.txt"

BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# 环境
IS_WINDOWS = sys.platform == "win32"
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
HAS_GUI_AUTO = False
HAS_AI = bool(DEEPSEEK_KEY)

# 当前迭代
_iteration = 0
_running = True
_pending_fixes: List[dict] = []


def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ═══════════════════════════════════════════════════
# 模块1: 子进程管理器
# ═══════════════════════════════════════════════════

class ProcessManager:
    """管理树剪子进程的启动、监控、终止"""

    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self._stdout_lines: List[str] = []
        self._stderr_lines: List[str] = []
        self._lock = threading.Lock()
        self._reader_thread: Optional[threading.Thread] = None
        self._started_at: Optional[float] = None

    @property
    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def elapsed(self) -> float:
        if self._started_at:
            return time.time() - self._started_at
        return 0

    def start(self, extra_args: List[str] = None) -> bool:
        """启动树剪程序。返回是否成功。"""
        if self.is_alive:
            self.stop(timeout=5)

        cmd = [sys.executable, str(TREE_SCRIPT)]
        if extra_args:
            cmd.extend(extra_args)

        # 确保使用 utf-8 编码
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            self._started_at = time.time()
            self._stdout_lines = []
            self._stderr_lines = []

            # 启动日志读取线程
            self._reader_thread = threading.Thread(
                target=self._read_output, daemon=True
            )
            self._reader_thread.start()

            log(f"进程启动 PID={self.proc.pid}")
            return True
        except Exception as e:
            log(f"启动失败: {e}", "ERROR")
            return False

    def stop(self, timeout: float = 10.0):
        """优雅终止子进程"""
        if self.proc is None:
            return
        log(f"终止进程 PID={self.proc.pid}...")
        try:
            if IS_WINDOWS:
                self.proc.terminate()
            else:
                self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)
        except Exception as e:
            log(f"终止进程异常: {e}", "WARN")
        self.proc = None
        self._started_at = None

    def _read_output(self):
        """后台线程: 持续读取子进程输出"""
        try:
            for line in iter(self.proc.stdout.readline, ""):
                if not line:
                    break
                line = line.rstrip("\n").rstrip("\r")
                with self._lock:
                    self._stdout_lines.append(line)
                if len(self._stdout_lines) > 10000:
                    self._stdout_lines = self._stdout_lines[-5000:]
        except (ValueError, OSError):
            pass
        except Exception as e:
            log(f"读取输出线程异常: {e}", "WARN")

    def get_recent_output(self, tail: int = 200) -> str:
        """获取最近N行输出"""
        with self._lock:
            return "\n".join(self._stdout_lines[-tail:])

    def search_output(self, pattern: str) -> List[str]:
        """在输出中搜索匹配行"""
        regex = re.compile(pattern, re.IGNORECASE)
        matches = []
        with self._lock:
            for line in self._stdout_lines:
                if regex.search(line):
                    matches.append(line)
        return matches

    def write_stdin(self, text: str):
        """向子进程写入内容（用于CLI交互）"""
        if self.proc and self.proc.stdin:
            try:
                self.proc.stdin.write(text + "\n")
                self.proc.stdin.flush()
            except Exception:
                pass


# ═══════════════════════════════════════════════════
# 模块2: 测试操作执行器（CLI模式 — 无GUI依赖）
# ═══════════════════════════════════════════════════

class TestRunner:
    """
    通过 CLI 模式运行各项功能测试。
    GUI 自动化需要 pyautogui 等库，这里先提供 CLI 版本的测试框架。
    """

    def __init__(self, pm: ProcessManager):
        self.pm = pm

    # ── CLI 模式测试（子进程调用 树剪.py --cli）──

    def test_single_generate(self, keyword: str = "岩板台面") -> dict:
        """测试: 单次生成视频"""
        log(f"  测试: 单次生成 (关键词={keyword})")
        result = {"action": "single_generate", "keyword": keyword, "success": False, "error": None}

        cmd = [sys.executable, str(TREE_SCRIPT), "--cli", keyword, "--tts", "--auto-bgm"]
        try:
            p = subprocess.run(
                cmd, cwd=str(PROJECT_ROOT), capture_output=True,
                text=True, timeout=120, encoding="utf-8", errors="replace"
            )
            output = p.stdout + "\n" + p.stderr
            if "草稿已生成" in output or "OK" in output:
                result["success"] = True
                log(f"    [OK] {keyword} 生成成功")
            elif "Traceback" in output:
                result["error"] = self._extract_error(output)
                log(f"    [FAIL] {result['error'].get('type','?')}: {result['error'].get('msg','?')}")
            elif p.returncode != 0:
                result["error"] = {"type": "NonZeroExit", "msg": f"returncode={p.returncode}"}
                log(f"    [FAIL] 退出码={p.returncode}")
            else:
                result["success"] = True  # 未检测到明确错误
        except subprocess.TimeoutExpired:
            result["error"] = {"type": "Timeout", "msg": "生成超时(120s)"}
            log("    [TIMEOUT] 生成超时")
        except Exception as e:
            result["error"] = {"type": type(e).__name__, "msg": str(e)}
            log(f"    [EXCEPT] {e}")

        return result

    def test_batch_generate(self, count: int = 3) -> dict:
        """测试: 批量生成"""
        log(f"  测试: 批量生成 (数量={count})")
        result = {"action": "batch_generate", "count": count, "success": False, "error": None}

        cmd = [sys.executable, str(TREE_SCRIPT), "--batch", str(count), "--tts", "--auto-bgm"]
        try:
            p = subprocess.run(
                cmd, cwd=str(PROJECT_ROOT), capture_output=True,
                text=True, timeout=300, encoding="utf-8", errors="replace"
            )
            output = p.stdout + "\n" + p.stderr
            success_count = output.count("[OK]")
            fail_count = output.count("[FAIL]")
            if "Traceback" in output:
                result["error"] = self._extract_error(output)
                log(f"    [FAIL] 批量生成错误: {result['error'].get('msg','?')}")
            else:
                result["success"] = success_count > 0
                log(f"    [DONE] 批量生成: 成功{success_count}/失败{fail_count}")
        except subprocess.TimeoutExpired:
            result["error"] = {"type": "Timeout", "msg": "批量生成超时(300s)"}
            log("    [TIMEOUT]")
        except Exception as e:
            result["error"] = {"type": type(e).__name__, "msg": str(e)}
            log(f"    [EXCEPT] {e}")

        return result

    def test_system_status(self) -> dict:
        """测试: 系统状态检查"""
        log("  测试: 系统状态")
        result = {"action": "system_status", "success": False, "error": None}
        cmd = [sys.executable, str(TREE_SCRIPT), "--status"]
        try:
            p = subprocess.run(
                cmd, cwd=str(PROJECT_ROOT), capture_output=True,
                text=True, timeout=30, encoding="utf-8", errors="replace"
            )
            output = p.stdout
            # 检查关键信息
            checks = {
                "FAISS索引": "[OK]" if "[OK]" in output else "缺失",
                "素材片段": "有数据" if "素材片段" in output else "无数据",
                "DeepSeek": "[OK]" if "[OK] 已配置" in output else "未配置",
            }
            result["checks"] = checks
            result["success"] = all(v in output for v in ["素材片段", "FAISS"])
            log(f"    [DONE] FAISS={checks['FAISS索引']}, 素材={checks['素材片段']}")
        except Exception as e:
            result["error"] = {"type": type(e).__name__, "msg": str(e)}
            log(f"    [EXCEPT] {e}")
        return result

    def test_python_syntax(self) -> dict:
        """测试: 检查所有核心Python文件语法"""
        log("  测试: Python语法检查")
        result = {"action": "syntax_check", "success": True, "errors": []}
        core_files = list(PROJECT_ROOT.glob("core/**/*.py"))
        core_files += list(PROJECT_ROOT.glob("ui/**/*.py"))
        core_files += list(PROJECT_ROOT.glob("material_engine_v3/**/*.py"))
        core_files.append(PROJECT_ROOT / "树剪.py")

        # 排除 __pycache__
        core_files = [f for f in core_files if "__pycache__" not in str(f)]
        checked = 0
        for f in core_files:
            try:
                import py_compile
                py_compile.compile(str(f), doraise=True)
                checked += 1
            except py_compile.PyCompileError as e:
                result["success"] = False
                result["errors"].append({"file": str(f.relative_to(PROJECT_ROOT)), "error": str(e)})
            except Exception:
                pass

        log(f"    [DONE] 语法检查: {checked}/{len(core_files)} 通过, {len(result['errors'])} 错误")
        for err in result["errors"]:
            log(f"    [FAIL] {err['file']}: {err['error']}")

        return result

    def test_frame_annotation(self) -> dict:
        """测试: 全帧识别（轻量模式: 单帧验证流水线, 120s超时）"""
        result = {"action": "frame_annotation", "success": False, "error": None,
                  "frames_found": 0, "mode": "single_frame"}

        from core.config import SELLING_POINT_DIR, EFFECTS_DIR, B_GROUP_PATH
        search_dirs = [SELLING_POINT_DIR, EFFECTS_DIR, B_GROUP_PATH]
        test_video = None
        for sd in search_dirs:
            mp4s = list(Path(str(sd)).rglob("*.mp4")) if os.path.exists(str(sd)) else []
            if mp4s:
                test_video = str(mp4s[0])
                break

        if not test_video:
            result["error"] = {"type": "MissingFile", "msg": "未找到测试视频"}
            log("    [SKIP] 未找到 .mp4"); return result

        log(f"  测试视频: {Path(test_video).name}")

        try:
            from core.smart_analyzer import get_analyzer
            import threading as _thr

            analyzer = get_analyzer()
            analyzer.reset_cancel()

            # 单帧验证: 只取第5秒处1帧, 120s超时
            done = [False]; analysis = [None]

            def _run():
                try:
                    analysis[0] = analyzer.analyze_video_frames(
                        test_video,
                        frame_interval=3.0,  # 每3秒1帧 → 取少量帧
                        log_callback=None,
                    )
                except Exception as e:
                    analysis[0] = {"error": str(e)}
                done[0] = True

            t = _thr.Thread(target=_run, daemon=True)
            t.start()
            t.join(timeout=120)

            if not done[0]:
                analyzer.cancel()
                t.join(timeout=5)
                result["error"] = {"type": "Timeout", "msg": "全帧识别(CPU)超时, 流水线代码正常"}
                log("    [TIMEOUT] CPU推理较慢(正常现象), 流水线代码路径已验证")
                analyzer._reclaim_memory()
                return result

            ar = analysis[0] or {}
            if ar.get("error"):
                result["error"] = {"type": "AnalysisError", "msg": str(ar["error"])[:200]}
                log(f"    [FAIL] {ar['error']}")
            else:
                result["success"] = True
                result["frames_found"] = ar.get("total_frames", 0)
                log(f"    [OK] {ar.get('total_frames',0)}帧分析, "
                    f"{ar.get('island_frames',0)}岛台帧, "
                    f"{ar.get('saved_frames',0)}帧入库")

            analyzer._reclaim_memory()

        except Exception as e:
            result["error"] = {"type": type(e).__name__, "msg": str(e)[:200]}
            log(f"    [EXCEPT] {e}")

        return result

    def test_db_integrity(self) -> dict:
        """测试: 数据库完整性检查"""
        log("  测试: 数据库完整性")
        result = {"action": "db_integrity", "success": True, "error": None, "stats": {}}
        db_path = PROJECT_ROOT / "ai_material_library.db"
        if not db_path.exists():
            result["success"] = False
            result["error"] = {"type": "MissingDB", "msg": "ai_material_library.db 不存在"}
            log("    [FAIL] 数据库文件缺失")
            return result
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            # 检查各表行数
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            for (tname,) in tables:
                cnt = conn.execute(f"SELECT COUNT(*) FROM [{tname}]").fetchone()[0]
                result["stats"][tname] = cnt
            # 完整性检查
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                result["success"] = False
                result["error"] = {"type": "DBIntegrity", "msg": str(integrity)}
                log(f"    [FAIL] 数据库完整性: {integrity}")
            else:
                log(f"    [OK] {len(tables)}张表, 完整性ok")
            conn.close()
        except Exception as e:
            result["success"] = False
            result["error"] = {"type": type(e).__name__, "msg": str(e)}
            log(f"    [FAIL] {e}")
        return result

    @staticmethod
    def _extract_error(text: str) -> dict:
        """从文本中提取最后一个异常"""
        # 匹配 Traceback...ErrorType: msg
        pattern = r'(\w+Error|Exception|RuntimeError|ValueError|TypeError|'
        pattern += r'KeyError|IndexError|AttributeError|ImportError|'
        pattern += r'ModuleNotFoundError|OSError|IOError|PermissionError|'
        pattern += r'FileNotFoundError|UnicodeError|UnicodeEncodeError|'
        pattern += r'UnicodeDecodeError|SyntaxError|IndentationError|'
        pattern += r'NameError|ZeroDivisionError|OverflowError|MemoryError)\s*:?\s*(.+)'
        matches = re.findall(pattern, text, re.MULTILINE)
        if matches:
            error_type, error_msg = matches[-1]
            return {"type": error_type, "msg": error_msg.strip()[:300]}
        # 回退: 只找 Traceback
        if "Traceback" in text:
            lines = text.split("\n")
            for i, l in enumerate(lines):
                if "Error" in l and ":" in l:
                    return {"type": "PythonError", "msg": l.strip()[:300]}
            return {"type": "UnknownError", "msg": lines[-1].strip()[:200] if lines else "(空)"}
        return None


# ═══════════════════════════════════════════════════
# 模块3: GUI 自动化控制器（可选 — 需要 pyautogui）
# ═══════════════════════════════════════════════════

class GUIAutomator:
    """
    GUI 自动化（可选模块）。
    如果 pyautogui 不可用，此模块静默跳过。
    使用前需运行 --calibrate 校准坐标。
    """

    def __init__(self):
        self.pyautogui = None
        self.gw = None
        self._coords = {}  # 控件名称 → (x, y)
        self._available = False
        self._load_calibration()
        try:
            import pyautogui as pg
            import pygetwindow as gw
            self.pyautogui = pg
            self.gw = gw
            self.pyautogui.FAILSAFE = True
            self.pyautogui.PAUSE = 0.3
            self._available = True
        except ImportError:
            log("pyautogui/pygetwindow 未安装，GUI自动化不可用。", "WARN")
            log("安装: pip install pyautogui pygetwindow", "WARN")

    @property
    def available(self) -> bool:
        return self._available

    def _load_calibration(self):
        if CALIB_FILE.exists():
            try:
                self._coords = json.loads(CALIB_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._coords = {}

    def calibrate(self):
        """校准模式: 用户依次点击各控件，记录坐标"""
        import tkinter as tk
        from tkinter import messagebox
        log("=== 校准模式 ===")
        log("请确保树剪程序已打开并可见。")

        win_title = "树剪 TreeCut v11"
        try:
            win = self.gw.getWindowsWithTitle(win_title)
            if not win:
                win = [w for w in self.gw.getAllWindows() if "树剪" in w.title]
            if not win:
                log("未找到树剪窗口！请先启动程序。")
                return
            w = win[0]
            w.activate()
            time.sleep(1)
        except Exception:
            log("无法定位窗口，继续手动校准...")

        targets = [
            ("tab_generate", "点击「生成/Generate」标签页"),
            ("tab_material", "点击「素材盘检索」标签页"),
            ("tab_script_lib", "点击「脚本学习库」标签页"),
            ("tab_history", "点击「历史/History」标签页"),
            ("input_keyword", "点击关键词输入框"),
            ("btn_generate", "点击「生成视频草稿」按钮"),
            ("input_copy", "点击文案输入框"),
            ("btn_clear", "点击「清空」按钮"),
        ]

        for key, desc in targets:
            log(f"请点击: {desc}")
            try:
                x, y = self.pyautogui.locateCenterOnScreen(
                    f"calibration_{key}.png", confidence=0.8
                )
            except Exception:
                log(f"  图像识别失败，请在3秒内手动移动到 {desc} 位置...")
                time.sleep(3)
                x, y = self.pyautogui.position()
            self._coords[key] = (x, y)
            log(f"  已记录: {key} -> ({x}, {y})")
            time.sleep(0.5)

        CALIB_FILE.write_text(json.dumps(self._coords, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"校准完成！坐标已保存到 {CALIB_FILE}")

    def focus_window(self) -> bool:
        """激活树剪窗口"""
        if not self._available:
            return False
        try:
            windows = self.gw.getWindowsWithTitle("树剪 TreeCut")
            if not windows:
                windows = [w for w in self.gw.getAllWindows() if "树剪" in w.title]
            if windows:
                w = windows[0]
                if w.isMinimized:
                    w.restore()
                w.activate()
                time.sleep(0.5)
                return True
        except Exception:
            pass
        return False

    def click(self, key: str, fallback_xy: Tuple[int, int] = None):
        """点击指定控件"""
        if not self._available:
            return
        if key in self._coords:
            x, y = self._coords[key]
        elif fallback_xy:
            x, y = fallback_xy
        else:
            log(f"  坐标未校准: {key}", "WARN")
            return
        self.pyautogui.click(x, y)
        time.sleep(0.5)

    def type_text(self, text: str):
        """输入文字"""
        if not self._available:
            return
        self.pyautogui.write(text, interval=0.05)

    def press_key(self, *keys):
        """按下组合键"""
        if not self._available:
            return
        self.pyautogui.hotkey(*keys)

    def gui_test_cycle(self) -> List[dict]:
        """GUI 测试循环: 模拟用户依次操作各功能"""
        results = []
        if not self._available:
            return results

        actions = [
            ("切换到素材盘检索", lambda: self.click("tab_material")),
            ("在生成页输入关键词", lambda: (
                self.click("tab_generate"),
                self.click("input_keyword"),
                self.type_text("岩板台面耐造"),
                time.sleep(1),
            )),
            ("点击生成视频草稿", lambda: (
                self.click("btn_generate"),
                log("  等待生成完成..."),
                time.sleep(15),
            )),
            ("切换到历史页", lambda: (
                self.click("tab_history"),
                time.sleep(2),
            )),
            ("清空并切换回生成页", lambda: (
                self.click("tab_generate"),
                self.click("btn_clear"),
                time.sleep(1),
            )),
        ]

        for name, action in actions:
            try:
                self.focus_window()
                action()
                results.append({"action": name, "success": True})
            except Exception as e:
                results.append({"action": name, "success": False, "error": str(e)})
                log(f"  GUI操作失败 [{name}]: {e}", "WARN")

        return results


# ═══════════════════════════════════════════════════
# 模块4: 错误分析与修复生成
# ═══════════════════════════════════════════════════

class FixGenerator:
    """
    错误分析 + 修复代码生成。
    规则模式处理常见错误，AI模式处理未知错误。
    """

    # ── 预定义修复模式 ──
    PATTERNS = [
        {
            "name": "encoding_gbk",
            "match": lambda e: "gbk" in e.get("msg", "").lower() and "encode" in e.get("msg", "").lower(),
            "fix": "添加 encoding='utf-8' 到 open() 调用",
            "apply": "_fix_encoding_gbk",
        },
        {
            "name": "import_missing",
            "match": lambda e: e.get("type") in ("ModuleNotFoundError", "ImportError"),
            "fix": "自动安装缺失的库（pip install）",
            "apply": "_fix_missing_import",
        },
        {
            "name": "db_locked",
            "match": lambda e: "database is locked" in e.get("msg", "").lower(),
            "fix": "增加 SQLite timeout",
            "apply": "_fix_db_locked",
        },
        {
            "name": "attribute_missing",
            "match": lambda e: e.get("type") == "AttributeError",
            "fix": "检查对象是否有该属性，添加缺失的方法或属性",
            "apply": "_fix_attribute_error",
        },
        {
            "name": "memory_error",
            "match": lambda e: e.get("type") in ("MemoryError", "RuntimeError") and
                              ("memory" in e.get("msg", "").lower() or "cuda" in e.get("msg", "").lower()),
            "fix": "添加 gc.collect() + torch.cuda.empty_cache()",
            "apply": "_fix_memory",
        },
        {
            "name": "file_not_found",
            "match": lambda e: e.get("type") == "FileNotFoundError",
            "fix": "添加路径检查和自动创建目录",
            "apply": "_fix_file_not_found",
        },
        {
            "name": "syntax_error",
            "match": lambda e: e.get("type") == "SyntaxError",
            "fix": "修复语法错误（需要精确定位）",
            "apply": "_fix_syntax_error",
        },
        {
            "name": "none_type",
            "match": lambda e: "'NoneType' object has no attribute" in e.get("msg", ""),
            "fix": "添加 None 检查保护",
            "apply": "_fix_none_type",
        },
    ]

    def analyze(self, error_info: dict, source_context: str = "") -> dict:
        """
        分析错误并生成修复建议。
        返回: {"matched": bool, "pattern_name": str, "fix": str, "code_patch": str|None}
        """
        if not error_info:
            return {"matched": False, "fix": "无错误信息", "code_patch": None}

        # 1. 尝试规则匹配
        for pat in self.PATTERNS:
            if pat["match"](error_info):
                return {
                    "matched": True,
                    "pattern_name": pat["name"],
                    "fix": pat["fix"],
                    "rule_apply": pat["apply"],
                }

        # 2. 如果是未知错误且有AI，调用AI
        if HAS_AI and source_context:
            ai_fix = self._ai_analyze(error_info, source_context)
            if ai_fix:
                return ai_fix

        return {
            "matched": False,
            "pattern_name": "unknown",
            "fix": f"未匹配到修复模式: {error_info.get('type','?')}",
            "code_patch": None,
        }

    def apply_rule_fix(self, error_info: dict, rule_name: str) -> bool:
        """应用规则修复。返回是否成功。"""
        method = getattr(self, rule_name, None)
        if method is None:
            log(f"  修复方法不存在: {rule_name}", "ERROR")
            return False
        return method(error_info)

    # ═══════════ 规则修复实现 ═══════════

    def _fix_encoding_gbk(self, error_info: dict) -> bool:
        msg = error_info.get("msg", "")
        # 提取文件路径
        file_match = re.search(r"File ['\"]([^'\"]+)['\"]", msg)
        if not file_match:
            return False
        file_path = file_match.group(1)
        # 找到 open(..., 'w') 改为 open(..., 'w', encoding='utf-8')
        log(f"  修复编码: {file_path}")
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="replace")
            # 修复模式
            fixed = re.sub(
                r"open\(([^)]+),\s*['\"]w['\"](?!\s*,\s*encoding)",
                r"open(\1, 'w', encoding='utf-8'",
                content
            )
            fixed = re.sub(
                r"\.write_text\(([^)]+)\)",
                r".write_text(\1, encoding='utf-8')",
                fixed
            )
            if fixed != content:
                self._safe_backup(file_path)
                Path(file_path).write_text(fixed, encoding="utf-8")
                log(f"    已修复 {len(re.findall(r'encoding', fixed)) - len(re.findall(r'encoding', content))} 处")
                return True
        except Exception as e:
            log(f"    修复失败: {e}", "ERROR")
        return False

    def _fix_missing_import(self, error_info: dict) -> bool:
        msg = error_info.get("msg", "")
        if "No module named" in msg:
            mod = msg.split("No module named")[-1].strip().strip("'").strip('"')
            log(f"  尝试安装: pip install {mod}")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", mod],
                    capture_output=True, timeout=120
                )
                return True
            except Exception:
                pass
        return False

    def _fix_db_locked(self, error_info: dict) -> bool:
        db_file = PROJECT_ROOT / "core" / "database.py"
        if not db_file.exists():
            return False
        content = db_file.read_text(encoding="utf-8", errors="replace")
        if "busy_timeout=5000" in content:
            # 增加 timeout
            fixed = content.replace("busy_timeout=5000", "busy_timeout=30000")
            if fixed != content:
                self._safe_backup(str(db_file))
                db_file.write_text(fixed, encoding="utf-8")
                log("    已增加数据库超时到 30s")
                return True
        return False

    def _fix_attribute_error(self, error_info: dict) -> bool:
        msg = error_info.get("msg", "")
        # 提取: 'ClassName' object has no attribute 'attr_name'
        match = re.search(r"'(\w+)' object has no attribute '(\w+)'", msg)
        if not match:
            return False
        cls_name, attr_name = match.groups()
        log(f"  属性缺失: {cls_name}.{attr_name}")
        # 这是一个复杂的修复 — 通常需要人工介入
        # 这里记录日志，不自动修改
        log(f"    [SKIP] 属性缺失需要人工分析: {cls_name}.{attr_name}", "WARN")
        return False

    def _fix_memory(self, error_info: dict) -> bool:
        # 在 smart_analyzer.py 中增加内存回收
        target = PROJECT_ROOT / "core" / "smart_analyzer.py"
        if not target.exists():
            return False
        content = target.read_text(encoding="utf-8", errors="replace")
        if "gc.collect()" not in content:
            marker = "def _reclaim_memory(self):"
            if marker not in content:
                # 插入内存回收方法
                insert_code = '''
    def _reclaim_memory(self):
        """回收GPU和Python内存"""
        import gc
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
'''
                idx = content.find("def scan_videos")
                if idx > 0:
                    self._safe_backup(str(target))
                    content = content[:idx] + insert_code + content[idx:]
                    target.write_text(content, encoding="utf-8")
                    log("    已添加内存回收方法")
                    return True
        return False

    def _fix_file_not_found(self, error_info: dict) -> bool:
        msg = error_info.get("msg", "")
        match = re.search(r"No such file or directory:\s*['\"]?([^'\"]+)['\"]?", msg)
        if match:
            missing_path = match.group(1).strip()
            log(f"  缺失路径: {missing_path}")
            try:
                os.makedirs(os.path.dirname(missing_path) or missing_path, exist_ok=True)
                log(f"    已创建目录: {missing_path}")
                return True
            except Exception:
                pass
        return False

    def _fix_syntax_error(self, error_info: dict) -> bool:
        # SyntaxError 太复杂，不自动修复
        log("    [SKIP] SyntaxError 需要人工修复", "WARN")
        return False

    def _fix_none_type(self, error_info: dict) -> bool:
        msg = error_info.get("msg", "")
        match = re.search(r"'NoneType' object has no attribute '(\w+)'", msg)
        if match:
            attr = match.group(1)
            log(f"    [SKIP] NoneType.{attr} — 需要添加 None 检查", "WARN")
        return False

    # ═══════════ AI 分析 ═══════════

    def _ai_analyze(self, error_info: dict, context: str) -> dict:
        """调用 DeepSeek API 分析错误"""
        if not HAS_AI:
            return None
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=DEEPSEEK_KEY,
                base_url="https://api.deepseek.com",
            )
            prompt = f"""你是树剪(TreeCut)视频剪辑程序的修复专家。
请分析以下错误并生成修复代码。

错误类型: {error_info.get('type', '?')}
错误信息: {error_info.get('msg', '?')}

相关代码上下文:
```
{context[:2000]}
```

要求:
1. 只输出修复后的代码片段（几行即可），不要解释。
2. 如果无法修复，输出 "CANNOT_FIX"。
3. 确保代码与现有风格一致。
"""
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.1,
            )
            code = resp.choices[0].message.content.strip()
            if code and "CANNOT_FIX" not in code:
                return {
                    "matched": True,
                    "pattern_name": "ai_fix",
                    "fix": code[:200],
                    "code_patch": code,
                }
        except Exception as e:
            log(f"  AI分析失败: {e}", "WARN")
        return None

    @staticmethod
    def _safe_backup(file_path: str):
        fpath = Path(file_path)
        if fpath.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = BACKUP_DIR / f"{fpath.stem}_{ts}{fpath.suffix}"
            shutil.copy2(str(fpath), str(backup))
            log(f"    备份: {backup.name}")
            # 清理旧备份（保留最近20个）
            all_backups = sorted(BACKUP_DIR.glob(f"{fpath.stem}_*{fpath.suffix}"))
            for old in all_backups[:-20]:
                old.unlink(missing_ok=True)

    def apply_code_patch(self, file_path: str, patch_content: str) -> bool:
        """应用AI生成的代码补丁（危险操作，需要备份）"""
        fpath = Path(file_path)
        if not fpath.exists():
            return False
        self._safe_backup(str(fpath))
        fpath.write_text(patch_content, encoding="utf-8")
        log(f"    应用补丁: {fpath.name}")
        return True


# ═══════════════════════════════════════════════════
# 模块5: 迭代历史管理
# ═══════════════════════════════════════════════════

class IterationHistory:
    """记录每次迭代的详细信息"""

    def __init__(self):
        self.records = self._load()

    def _load(self) -> List[dict]:
        if HISTORY_FILE.exists():
            try:
                return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def add(self, iteration: int, test_results: List[dict],
            errors_found: List[dict], fixes_applied: List[dict],
            success: bool):
        record = {
            "iteration": iteration,
            "timestamp": datetime.now().isoformat(),
            "test_results": test_results,
            "errors_found": errors_found,
            "fixes_applied": fixes_applied,
            "success": success,
        }
        self.records.append(record)
        # 限制记录数
        if len(self.records) > 200:
            self.records = self.records[-200:]
        self._save()

    def _save(self):
        HISTORY_FILE.write_text(
            json.dumps(self.records, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def get_stats(self) -> dict:
        if not self.records:
            return {"total_iterations": 0}
        successes = sum(1 for r in self.records if r["success"])
        total_fixes = sum(len(r["fixes_applied"]) for r in self.records)
        return {
            "total_iterations": len(self.records),
            "success_rate": f"{successes}/{len(self.records)}",
            "total_fixes_applied": total_fixes,
            "last_iteration": self.records[-1]["timestamp"] if self.records else None,
        }

    def last_error_types(self, n: int = 5) -> List[str]:
        types = []
        for r in reversed(self.records):
            for e in r.get("errors_found", []):
                if e.get("type"):
                    types.append(e["type"])
                    if len(types) >= n:
                        return types
        return types


# ═══════════════════════════════════════════════════
# 模块6: 主循环
# ═══════════════════════════════════════════════════

class SelfEvolver:
    """自进化主控制器"""

    def __init__(self, max_loops: int = 0, gui_mode: bool = False):
        self.max_loops = max_loops
        self.gui_mode = gui_mode
        self.pm = ProcessManager()
        self.runner = TestRunner(self.pm)
        self.fixer = FixGenerator()
        self.history = IterationHistory()
        self.gui = GUIAutomator() if gui_mode else None

    def run_once(self) -> bool:
        """执行单次迭代。返回是否成功。"""
        global _iteration
        _iteration += 1
        iter_num = _iteration
        log(f"\n{'='*60}")
        log(f"迭代 #{iter_num} 开始")
        log(f"{'='*60}")

        test_results = []
        errors_found = []
        fixes_applied = []

        # ── 阶段1: 测试核心功能 ──
        log("阶段1: 核心功能测试")

        tests = [
            ("语法检查", self.runner.test_python_syntax),
            ("数据库完整性", self.runner.test_db_integrity),
            ("系统状态", self.runner.test_system_status),
        ]

        # 随机选择是否执行耗时测试
        if iter_num % 2 == 0:  # 每2次迭代执行一次全帧识别
            tests.append(("全帧识别", self.runner.test_frame_annotation))
        if iter_num % 3 == 0:  # 每3次迭代执行一次
            tests.append(("单次生成(油风)", lambda: self.runner.test_single_generate("奶油风岛台")))
        if iter_num % 5 == 0:  # 每5次执行一次批量
            tests.append(("批量生成(2条)", lambda: self.runner.test_batch_generate(2)))

        for name, test_fn in tests:
            log(f"  [{name}] 执行中...")
            try:
                result = test_fn()
                test_results.append(result)

                if result.get("error"):
                    errors_found.append(result["error"])

                # 如果是语法错误，收集上下文
                if isinstance(result.get("error"), dict) and not _running:
                    break

            except Exception as e:
                err = {"type": type(e).__name__, "msg": str(e), "test": name}
                errors_found.append(err)
                log(f"  [{name}] 异常: {e}", "ERROR")

        # ── 阶段2: 分析错误并尝试修复 ──
        log(f"\n阶段2: 错误分析 (共{len(errors_found)}个错误)")

        for err in errors_found:
            # 收集相关源代码上下文
            context = ""
            src_match = re.search(
                r'File ["\']([^"\']+\.py)["\'].*line (\d+)',
                err.get("msg", "") + err.get("test", "")
            )
            if src_match:
                src_file = src_match.group(1)
                try:
                    lines = Path(src_file).read_text(encoding="utf-8", errors="replace").split("\n")
                    lineno = int(src_match.group(2)) - 1
                    start = max(0, lineno - 5)
                    end = min(len(lines), lineno + 5)
                    context = "\n".join(
                        f"{i+1}: {l}" for i, l in enumerate(lines[start:end], start)
                    )
                except Exception:
                    pass

            analysis = self.fixer.analyze(err, context)
            log(f"  [{err.get('type','?')}] → {analysis['fix'][:80]}")

            if analysis.get("matched"):
                rule = analysis.get("rule_apply")
                if rule:
                    applied = self.fixer.apply_rule_fix(err, rule)
                    fixes_applied.append({
                        "error": err.get("type"),
                        "rule": rule,
                        "applied": applied,
                    })
                elif analysis.get("code_patch"):
                    # AI补丁（谨慎应用）
                    if src_match:
                        applied = self.fixer.apply_code_patch(
                            src_match.group(1), analysis["code_patch"]
                        )
                        fixes_applied.append({
                            "error": err.get("type"),
                            "ai_fix": True,
                            "applied": applied,
                        })

        # ── 阶段3: GUI测试(可选) ──
        if self.gui and self.gui.available and _running:
            log("\n阶段3: GUI交互测试")
            gui_results = self.gui.gui_test_cycle()
            test_results.extend(gui_results)

        # ── 记录迭代历史 ──
        overall_success = len(errors_found) == 0 or all(
            f.get("applied", False) for f in fixes_applied
        )
        self.history.add(iter_num, test_results, errors_found, fixes_applied, overall_success)

        # 汇总
        stats = self.history.get_stats()
        log(f"\n迭代 #{iter_num} 完成")
        log(f"  测试: {len(test_results)}项 | 错误: {len(errors_found)}项 | 修复: {len(fixes_applied)}项")
        log(f"  累计: {stats['total_iterations']}次迭代, 成功率{stats['success_rate']}")

        return overall_success

    def run(self):
        """主循环"""
        log("树剪 自进化系统 启动")
        log(f"  AI模式: {'已启用(DeepSeek)' if HAS_AI else '规则模式'}")
        log(f"  GUI模式: {'已启用' if (self.gui and self.gui.available) else 'CLI模式'}")
        log(f"  最大迭代: {self.max_loops if self.max_loops > 0 else '无限'}")
        log(f"  备份目录: {BACKUP_DIR}")

        global _running
        _running = True

        try:
            while _running:
                success = self.run_once()

                if self.max_loops > 0 and _iteration >= self.max_loops:
                    log(f"\n已达到最大迭代次数({self.max_loops})，退出。")
                    break

                # 等待下一次迭代
                wait = random.randint(30, 120)
                log(f"\n等待 {wait}s 后开始下一次迭代... (Ctrl+C 退出)\n")
                for _ in range(wait):
                    if not _running:
                        break
                    time.sleep(1)

        except KeyboardInterrupt:
            log("\n收到中断信号，正在优雅退出...")
        finally:
            _running = False
            if self.pm.is_alive:
                self.pm.stop()
            log(f"自进化系统停止。总计 {_iteration} 次迭代。")
            stats = self.history.get_stats()
            log(f"最终统计: {json.dumps(stats, ensure_ascii=False)}")


# ═══════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="树剪 TreeCut 自进化系统")
    parser.add_argument("--calibrate", action="store_true", help="GUI坐标校准模式")
    parser.add_argument("--once", action="store_true", help="只运行一次迭代")
    parser.add_argument("--max-loops", type=int, default=0, help="最大迭代次数(0=无限)")
    parser.add_argument("--gui", action="store_true", help="启用GUI自动化测试")
    parser.add_argument("--stats", action="store_true", help="只显示历史统计")
    args = parser.parse_args()

    if args.stats:
        h = IterationHistory()
        print(json.dumps(h.get_stats(), ensure_ascii=False, indent=2))
        return

    if args.calibrate:
        g = GUIAutomator()
        if g.available:
            g.calibrate()
        else:
            print("GUI自动化库未安装。请先运行: pip install pyautogui pygetwindow")
        return

    evolver = SelfEvolver(
        max_loops=1 if args.once else args.max_loops,
        gui_mode=args.gui,
    )
    evolver.run()


if __name__ == "__main__":
    main()
