"""
树剪 TreeCut v13.0 — FastAPI REST 服务层
=========================================
统一入口: `python api_server.py`
浏览器: http://localhost:8000/docs

端点:
  POST /api/v1/task/submit     — 提交视频生成任务
  GET  /api/v1/task/{id}       — 查询任务状态/结果
  GET  /api/v1/task/list       — 用户任务列表
  GET  /api/v1/material/search — 按标签搜索素材
  GET  /api/v1/user/quota      — 查询配额
  GET  /api/v1/status          — 系统状态
"""
import sys, os, time, json, uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List

# ── 请求/响应模型 ──────────────────────────────────
class TaskSubmitRequest(BaseModel):
    keyword: str = Field(..., min_length=2, description="卖点关键词")
    script: Optional[str] = Field(None, description="自定义文案(可选)")
    num_clips: Optional[int] = Field(None, ge=2, le=20)
    auto_bgm: bool = Field(True)
    generate_tts: bool = Field(True)

class ApiResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: Optional[dict] = None

# ── FastAPI 应用 ───────────────────────────────────
app = FastAPI(
    title="树剪 TreeCut v13.0 API",
    version="13.0",
    description="家居岛台品牌 AI 视频半自动剪辑服务",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


# ═══════════════ 权限中间件 ═══════════════
def _check_auth(x_api_key: str = Header(...)) -> dict:
    if not x_api_key or len(x_api_key) < 6:
        raise HTTPException(403, "缺少有效 API Key")
    try:
        from core.auth_middleware import get_auth
        auth = get_auth()
        ok, msg, info = auth.verify(x_api_key)
        if not ok:
            raise HTTPException(403, msg)
        return info
    except ImportError:
        return {"user_id": "dev", "role": "admin"}


# ═══════════════ 任务提交 ═══════════════
@app.post("/api/v1/task/submit", response_model=ApiResponse)
def submit_task(req: TaskSubmitRequest, x_api_key: str = Header(...)):
    user = _check_auth(x_api_key)
    start = time.time()

    try:
        # 配额检查
        try:
            from core.auth_middleware import get_auth
            auth = get_auth()
            ok, qmsg, _ = auth.check_quota(user["user_id"], user.get("role"))
            if not ok:
                raise HTTPException(429, qmsg)
        except ImportError:
            pass

        task_id = uuid.uuid4().hex[:12]

        # 提交到调度中心
        try:
            from core.smart_orchestrator import get_orchestrator
            orch = get_orchestrator()
            # 异步启动(后台线程)
            import threading
            t = threading.Thread(
                target=orch.execute,
                args=(req.keyword,),
                kwargs={"keyword": req.keyword, "max_retry": 2},
                daemon=True,
            )
            t.start()
        except ImportError:
            pass

        # 记录任务
        try:
            from core.database import db
            db.insert_task_record(
                demand=req.keyword, keyword=req.keyword, status="已提交",
                retry_times=0,
            )
        except Exception:
            pass

        cost = round(time.time() - start, 3)
        return ApiResponse(data={
            "task_id": task_id, "keyword": req.keyword,
            "status": "submitted", "cost_sec": cost,
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"提交失败: {e}")


# ═══════════════ 任务查询 ═══════════════
@app.get("/api/v1/task/{task_id}", response_model=ApiResponse)
def get_task(task_id: str, x_api_key: str = Header(...)):
    _check_auth(x_api_key)
    try:
        from core.database import db
        records = db.get_task_records(limit=200)
        for r in records:
            if r.get("keyword", "") == task_id or str(r.get("id")) == task_id:
                return ApiResponse(data=r)
        raise HTTPException(404, f"任务不存在: {task_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════ 任务列表 ═══════════════
@app.get("/api/v1/task/list", response_model=ApiResponse)
def list_tasks(page: int = Query(1, ge=1), page_size: int = Query(20, le=100),
               x_api_key: str = Header(...)):
    _check_auth(x_api_key)
    try:
        from core.database import db
        records = db.get_task_records(limit=500)
        start = (page - 1) * page_size
        page_data = records[start:start + page_size]
        return ApiResponse(data={
            "total": len(records), "page": page, "page_size": page_size,
            "list": page_data,
        })
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════ 素材搜索 ═══════════════
@app.get("/api/v1/material/search", response_model=ApiResponse)
def search_materials(tags: str = Query(..., description="逗号分隔标签"),
                     x_api_key: str = Header(...)):
    _check_auth(x_api_key)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    try:
        from core.database import db
        with db.get_connection() as conn:
            results = []
            for tag in tag_list:
                rows = conn.execute(
                    """SELECT video_path, tags, objects, style, duration, confidence
                       FROM materials WHERE tags LIKE ? AND analyzed=1
                       LIMIT 10""",
                    (f"%{tag}%",)
                ).fetchall()
                for r in rows:
                    results.append({
                        "path": r[0], "tags": r[1], "objects": r[2],
                        "style": r[3], "duration": r[4], "confidence": r[5],
                    })
            return ApiResponse(data={"tag": tags, "total": len(results), "list": results})
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════ 用户配额 ═══════════════
@app.get("/api/v1/user/quota", response_model=ApiResponse)
def get_quota(x_api_key: str = Header(...)):
    user = _check_auth(x_api_key)
    try:
        from core.auth_middleware import get_auth
        auth = get_auth()
        quota = auth.get_quota(user["user_id"])
        return ApiResponse(data=quota)
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════ 系统状态 ═══════════════
@app.get("/api/v1/status", response_model=ApiResponse)
def get_status():
    import platform, time as _t
    info = {
        "version": "13.0",
        "python": platform.python_version(),
        "platform": platform.system(),
        "uptime": _t.time() - _t.time(),  # 占位
    }
    try:
        from core.database import db
        stats = db.get_task_stats()
        info["db_stats"] = stats
    except Exception:
        pass
    try:
        from core.review_queue import get_review_queue
        rq = get_review_queue()
        info["pending_reviews"] = rq.pending_count()
    except Exception:
        pass
    return ApiResponse(data=info)


# ═══════════════ 启动 ═══════════════
@app.on_event("startup")
async def startup():
    print("=" * 50)
    print("  TreeCut v13.0 API Server")
    print(f"  Swagger: http://localhost:8000/docs")
    print("=" * 50)
    # 初始化系统
    try:
        from core.event_bus import get_bus; get_bus()
    except Exception: pass
    try:
        from utils.logging import setup_eventbus; setup_eventbus()
    except Exception: pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
