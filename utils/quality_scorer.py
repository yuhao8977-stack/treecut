"""
素材质量评估与过滤模块 v2.0
功能：清晰度、稳定性、构图、时长适配、标签完整度、感知哈希去重、批量并发
"""
import os, re, subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import cv2, numpy as np
    _HAS_CV = True
except ImportError:
    _HAS_CV = False

TAG_KEYWORDS = {
    "materials": ["岩板","实木","石英石","大理石","不锈钢","亚克力","微水泥","洞石","奢石","潘多拉","宝格丽","胡桃","柚木","橡木","玻璃","多层板"],
    "colors": ["纯黑","纯白","奶油白","奶白","深灰","浅灰","深棕","浅棕","原木色","米色","哑光白","哑光黑","香奈白","奶油色"],
    "features": ["抽屉","烤箱","水槽","灯带","插座","酒柜","拉篮","吧台","薄抽","电磁炉","冰箱","餐桌","煮茶","烤炉","轨道插座"],
    "actions": ["展示","拉开","打开","关闭","旋转","伸缩","嵌入","收纳"],
}

@dataclass
class QualityReport:
    path: str = ""
    sharpness: float = 0.0
    stability: float = 0.0
    composition: float = 0.0
    duration_fit: float = 0.0
    tag_completeness: float = 0.0
    total_score: float = 0.0
    is_valid: bool = True
    phash: str = ""
    duration: float = 0.0
    WEIGHTS = {"sharpness":0.30,"stability":0.20,"composition":0.15,"duration_fit":0.20,"tag_completeness":0.15}

    def compute_total(self):
        self.total_score = round(
            self.sharpness*self.WEIGHTS["sharpness"]+self.stability*self.WEIGHTS["stability"]+
            self.composition*self.WEIGHTS["composition"]+self.duration_fit*self.WEIGHTS["duration_fit"]+
            self.tag_completeness*self.WEIGHTS["tag_completeness"], 3)
        self.is_valid = self.total_score >= 0.3


class QualityScorer:
    def __init__(self, use_cv=True):
        self.use_cv = use_cv and _HAS_CV

    def get_duration(self, vp):
        from core.frame_extractor import get_video_duration
        return get_video_duration(str(vp))

    def evaluate_sharpness(self, vp):
        if not self.use_cv: return 0.5
        cap = cv2.VideoCapture(str(vp))
        try:
            tf = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if tf <= 0: return 0.3
            scores = []
            for pos in [tf//4, tf//2, tf*3//4]:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos); ret, frame = cap.read()
                if not ret: continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                v = cv2.Laplacian(gray, cv2.CV_64F).var()
                scores.append(min(1.0, v/500.0))
            return round(sum(scores)/len(scores), 3) if scores else 0.3
        finally:
            cap.release()

    def evaluate_stability(self, vp):
        if not self.use_cv: return 0.7
        cap = cv2.VideoCapture(str(vp))
        try:
            tf = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if tf < 3: return 0.5
            mid = tf//2; flows = []; prev = None
            for pos in [mid-1, mid, mid+1]:
                cap.set(cv2.CAP_PROP_POS_FRAMES, pos); ret, frame = cap.read()
                if not ret: continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if prev is not None:
                    flow = cv2.calcOpticalFlowFarneback(prev, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                    flows.append(float(np.sqrt(flow[...,0]**2+flow[...,1]**2).mean()))
                prev = gray
            if not flows: return 0.5
            avg = sum(flows)/len(flows)
            return round(max(0.0, min(1.0, 1.0-(avg-0.5)/3.0)), 3)
        finally:
            cap.release()

    def evaluate_composition(self, vp):
        if not self.use_cv: return 0.5
        cap = cv2.VideoCapture(str(vp))
        try:
            tf = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.set(cv2.CAP_PROP_POS_FRAMES, tf//2); ret, frame = cap.read()
            if not ret: return 0.5
            h, w = frame.shape[:2]; gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY); edges = cv2.Canny(gray, 50, 150)
            th, tw = h//3, w//3
            regs = [edges[th:2*th, 0:tw], edges[th:2*th, 2*tw:w], edges[0:th, tw:2*tw], edges[2*th:h, tw:2*tw]]
            ds = [np.count_nonzero(r)/r.size for r in regs if r.size > 0]
            if not ds: return 0.5
            d = sum(ds)/len(ds)
            return round(max(0.2, min(1.0, 1.0-abs(d-0.08)/0.12 if 0.03 <= d <= 0.2 else 0.6)), 3)
        finally:
            cap.release()

    def evaluate_duration_fit(self, d):
        if 3.0<=d<=6.0: return 1.0
        elif 2.0<=d<3.0: return 0.8
        elif 6.0<d<=10.0: return 0.7
        elif 1.0<=d<2.0: return 0.5
        elif 10.0<d<=15.0: return 0.4
        return 0.2

    def evaluate_tag_completeness(self, fname, folder=""):
        s=fname+" "+folder; found=sum(1 for cat,kws in TAG_KEYWORDS.items() if any(kw in s for kw in kws))
        return found/len(TAG_KEYWORDS)

    def compute_phash(self, vp):
        if not self.use_cv: return ""
        cap = cv2.VideoCapture(str(vp))
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0); ret, frame = cap.read()
            if not ret: return ""
            small = cv2.resize(frame, (8, 8)); gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            avg = gray.mean(); bits = (gray > avg).flatten()
            return ''.join(str(int(b)) for b in bits)
        finally:
            cap.release()

    def evaluate(self, vp, folder=""):
        vp=str(vp); fname=Path(vp).name; dur=self.get_duration(vp)
        r=QualityReport(path=vp,duration=dur)
        r.sharpness=self.evaluate_sharpness(vp); r.stability=self.evaluate_stability(vp)
        r.composition=self.evaluate_composition(vp); r.duration_fit=self.evaluate_duration_fit(dur)
        r.tag_completeness=self.evaluate_tag_completeness(fname,folder)
        r.compute_total(); r.phash=self.compute_phash(vp); return r

    def batch_evaluate(self, videos, max_workers=4):
        results=[]
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            fs={ex.submit(self.evaluate,vp,f):(vp,f) for vp,f in videos}
            for fu in as_completed(fs):
                try: results.append(fu.result())
                except Exception: results.append(QualityReport(path=str(fs[fu][0]),total_score=0,is_valid=False))
        return results

    def filter_by_quality(self, clips, min_score=0.3):
        return [c for c in clips if c.get("quality_score", self.evaluate(str(c["path"]),c.get("folder_name","")).total_score) >= min_score]

    def deduplicate(self, clips, hamming_distance=5):
        """感知哈希去重 v2.0 — phash前缀分桶 O(n)"""
        if not self.use_cv: return clips
        for c in clips:
            if "phash" not in c: c["phash"]=self.compute_phash(str(c["path"]))
            if "quality_score" not in c: c["quality_score"]=c.get("quality_report",QualityReport()).total_score
        # 使用phash前8位分桶，大幅减少汉明距离比较次数
        buckets = {}
        for c in clips:
            ph = c.get("phash", "")
            qs = c.get("quality_score", 0)
            if not ph or len(ph) < 8:
                buckets.setdefault("_nophash", []).append(c)
                continue
            prefix = ph[:8]
            buckets.setdefault(prefix, []).append(c)
        uniq = {}
        for prefix, bucket in buckets.items():
            for c in bucket:
                ph = c.get("phash", "")
                qs = c.get("quality_score", 0)
                if not ph:
                    uniq[id(c)] = c
                    continue
                dup = False
                for ep, ec in list(uniq.items()):
                    if ep.startswith("_nophash_"):
                        continue
                    if self._hd(ph, ep) <= hamming_distance:
                        if qs > ec.get("quality_score", 0):
                            uniq[ep] = c
                        dup = True
                        break
                if not dup:
                    uniq[ph] = c
        return list(uniq.values())

    def _hd(self,s1,s2): return sum(c1!=c2 for c1,c2 in zip(s1,s2)) if len(s1)==len(s2) else 100

_scorer=None
_scorer_lock = __import__('threading').Lock()
def get_scorer():
    global _scorer
    if _scorer is None:
        with _scorer_lock:
            if _scorer is None:
                _scorer = QualityScorer()
    return _scorer
