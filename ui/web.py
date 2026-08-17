#!/usr/bin/env python3
"""
TreeCut Control Panel - Web UI
Run: python tree_cut_ui.py
Open: http://localhost:7860
"""
import sys, os, json, time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

_ve = None
_gr = None


def _get_ve():
    global _ve
    if _ve is None:
        import core as _ve
    return _ve


def _get_gr():
    global _gr
    if _gr is None:
        import gradio as _gr
    return _gr


def _is_ve_loaded():
    try:
        _get_ve()
        return True
    except Exception:
        return False


# ============================================================
# Tab 1: Quick Generate
# ============================================================
def get_selling_points():
    try:
        ve = _get_ve()
        pts = ve.list_available_selling_points()
        return [p.get("original_name", p.get("name", "")) for p in pts]
    except Exception:
        return []


def generate_single(keyword, copy_text, use_tts, use_bgm, use_bgroup, folders=None, progress=None):
    logs = []
    def add(msg): logs.append(msg); return msg
    try:
        ve = _get_ve()
        add(f"[Start] keyword={keyword}")
        if progress is None:
            try: progress = _gr.Progress()
            except Exception: progress = None
        def _prog(step, total, msg):
            if progress: progress(step/total, desc=msg)
        result = ve.run(
            keyword=keyword,
            copy_text_override=copy_text.strip() if copy_text and copy_text.strip() else None,
            progress_callback=_prog,
            generate_tts=use_tts,
            auto_bgm=use_bgm,
        )
        thumb = None
        if result and isinstance(result, dict) and "draft_dir" in result:
            tp = Path(result["draft_dir"]) / "thumbnail.jpg"
            if tp.exists(): thumb = str(tp)
            add(f"[Done] {result['draft_dir']}")
        return "\n".join(logs), thumb
    except Exception as e:
        add(f"[ERROR] {e}")
        return "\n".join(logs), None


# ============================================================
# Tab 2: Batch Production
# ============================================================
def generate_batch(script_file, count, use_tts, use_bgm, progress=None):
    if progress is None:
        class _P:
            def tqdm(self, iterable, desc=""):
                for i, item in enumerate(iterable): yield item
        progress = _P()
    results = []
    ve = _get_ve()
    script_path = script_file.name if script_file else None
    for i in progress.tqdm(range(1, count + 1), desc="Batch"):
        try:
            copy_text = None
            if script_path:
                row = ve.get_script_row(script_path, row_num=i + 1)
                if row:
                    copy_text = row.get("copy", row.get("copy_text", ""))
            ve.run(keyword="batch", copy_text_override=copy_text,
                   generate_tts=use_tts, auto_bgm=use_bgm)
            results.append([i, "OK", (copy_text or "AI generated")[:30]])
        except Exception as e:
            results.append([i, f"FAIL: {str(e)[:40]}", ""])
        time.sleep(0.5)
    return results


# ============================================================
# Tab 3: Material Library
# ============================================================
def refresh_material_stats():
    try:
        ve = _get_ve()
        pts = ve.list_available_selling_points(use_cache=False)
        table = [[p.get("original_name", p.get("name", "")), p.get("mp4_count", p.get("count", 0))]
                 for p in pts[:30]]
        return f"Scanned: {len(pts)} folders, {sum(r[1] for r in table)} clips", table
    except Exception as e:
        return f"ERROR: {e}", []


def clear_cache():
    try:
        ve = _get_ve()
        ve.MaterialCacheManager.invalidate()
        return "Cache cleared"
    except Exception as e:
        return f"ERROR: {e}"


def show_usage_stats():
    try:
        ve = _get_ve()
        ve.MaterialUsageTracker.print_stats(top_n=20)
        return "Stats printed to console"
    except Exception as e:
        return f"ERROR: {e}"


# ============================================================
# Tab 4: History
# ============================================================
def load_history():
    rows = []
    output_dirs = [
        Path(os.environ.get("TREECUT_DRAFT_DIR", str(Path.home() / "Desktop" / "视频工作流" / "03_粗剪输出"))),
        Path(os.environ.get("LOCALAPPDATA", "")) / r"JianyingPro\User Data\Projects\com.lveditor.draft"
    ]
    for output_dir in output_dirs:
        if not output_dir.exists():
            continue
        for d in sorted(output_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
            if not d.is_dir():
                continue
            mtime = datetime.fromtimestamp(d.stat().st_mtime).strftime("%m-%d %H:%M")
            thumb = str(d / "thumbnail.jpg") if (d / "thumbnail.jpg").exists() else ""
            rows.append([mtime, d.name[:40], str(d), thumb])
    return rows if rows else [["", "No history found", "", ""]]


# ============================================================
# UI Build
# ============================================================
def build_ui():
    gr = _get_gr()
    selling_points = get_selling_points()

    with gr.Blocks(title="TreeCut Control Panel", theme=gr.themes.Soft()) as app:
        gr.Markdown("# TreeCut AI Video Editor - Web Console v10.0")
        gr.Markdown(f"Status: Ready | Port: 7860")

        with gr.Tabs():
            with gr.Tab("Quick Generate"):
                with gr.Row():
                    with gr.Column(scale=1):
                        kw = gr.Dropdown(label="Keyword", choices=selling_points,
                                         value=selling_points[0] if selling_points else "",
                                         allow_custom_value=True)
                        folders = gr.Dropdown(label="Material Folders (multi-select)",
                                             choices=selling_points, multiselect=True,
                                             info="留空=使用全部文件夹")
                        tts = gr.Checkbox(label="AI Voiceover (TTS)", value=True)
                        bgm = gr.Checkbox(label="Auto BGM", value=True)
                        bgrp = gr.Checkbox(label="B-Group Mix", value=True)
                    with gr.Column(scale=2):
                        copy_txt = gr.Textbox(label="Direct Copy Text (optional)", lines=5,
                                              placeholder="Paste copy text, or leave empty for AI")

                gen_btn = gr.Button("Generate Video Draft", variant="primary", size="lg")
                with gr.Row():
                    log_out = gr.Textbox(label="Log", lines=14, interactive=False, max_lines=20)
                    thumb_out = gr.Image(label="Thumbnail Preview", height=320)

                gen_btn.click(generate_single,
                    inputs=[kw, copy_txt, tts, bgm, bgrp, folders],
                    outputs=[log_out, thumb_out])

            with gr.Tab("Batch Production"):
                with gr.Row():
                    script_up = gr.File(label="Excel Script (optional)", file_types=[".xlsx"])
                    batch_n = gr.Slider(1, 30, value=3, step=1, label="Count")
                with gr.Row():
                    bt_tts = gr.Checkbox(label="TTS", value=True)
                    bt_bgm = gr.Checkbox(label="BGM", value=True)
                batch_btn = gr.Button("Start Batch", variant="primary")
                batch_table = gr.Dataframe(
                    headers=["#", "Status", "Copy Preview"],
                    interactive=False, row_count=10
                )
                batch_btn.click(generate_batch,
                    inputs=[script_up, batch_n, bt_tts, bt_bgm],
                    outputs=batch_table)

            with gr.Tab("Material Library"):
                with gr.Row():
                    refresh_btn = gr.Button("Refresh Scan", variant="secondary")
                    clear_cache_btn = gr.Button("Clear Cache", variant="stop")
                    usage_btn = gr.Button("Usage Stats", variant="secondary")
                status_txt = gr.Textbox(label="Status", interactive=False)
                mat_table = gr.Dataframe(
                    headers=["Selling Point", "Clip Count"],
                    interactive=False, row_count=15
                )
                refresh_btn.click(refresh_material_stats, outputs=[status_txt, mat_table])
                clear_cache_btn.click(clear_cache, outputs=status_txt)
                usage_btn.click(show_usage_stats, outputs=status_txt)

            with gr.Tab("素材库管理 / Library Management"):
                gr.Markdown("### AI素材库索引管理")
                lib_status = gr.Textbox(label="状态", interactive=False)
                rebuild_btn = gr.Button("全量重建FAISS索引", variant="primary")
                lib_stats = gr.Dataframe(headers=["指标","数值"], interactive=False, row_count=5)

                def rebuild_index():
                    try:
                        from core.library_builder import LibraryBuilder
                        import io, sys as _sys
                        old = _sys.stdout; buf = io.StringIO(); _sys.stdout = buf
                        LibraryBuilder().build_faiss_index()
                        _sys.stdout = old
                        return f"✅ {buf.getvalue()}", [["总片段","-"],["索引状态","已重建"]]
                    except Exception as e:
                        return f"❌ {e}", []

                def get_lib_stats():
                    try:
                        from core.library_builder import LibraryBuilder
                        s = LibraryBuilder().get_stats()
                        return [[k,str(v)] for k,v in s.items()]
                    except Exception: return []

                rebuild_btn.click(rebuild_index, outputs=[lib_status, lib_stats])

            with gr.Tab("History"):
                hist_btn = gr.Button("Load History")
                hist_table = gr.Dataframe(
                    headers=["Time", "Draft Name", "Path", "Thumbnail"],
                    interactive=False, row_count=15
                )
                hist_btn.click(load_history, outputs=hist_table)

        gr.Markdown("---\n*TreeCut v10.0 | Web Console*")

    return app


if __name__ == "__main__":
    # 简单Token认证（从环境变量读取，未设置时跳过）
    import os as _os
    AUTH_TOKEN = _os.environ.get("TREECUT_WEB_TOKEN", "")
    AUTH_MSG = "请输入访问令牌 / Enter access token"

    app = build_ui()
    launch_kwargs = {
        "server_name": "127.0.0.1",
        "server_port": int(_os.environ.get("TREECUT_WEB_PORT", "7860")),
        "inbrowser": False,
        "show_error": True,
        "share": False,
    }
    if AUTH_TOKEN:
        launch_kwargs["auth"] = ("admin", AUTH_TOKEN)
        launch_kwargs["auth_message"] = AUTH_MSG
        print(f"   🔒 Web UI 已启用认证 (admin / token)")
    else:
        print(f"   ⚠ Web UI 未启用认证，设置 TREECUT_WEB_TOKEN 环境变量以保护访问")

    app.launch(**launch_kwargs)
