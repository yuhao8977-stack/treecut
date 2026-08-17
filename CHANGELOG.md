# 🏝️ 岛台品牌 · 小红书视频半自动剪辑工具 — 优化日志

> 脚本: `video_editor.py` | 路径: `C:\Users\admin\Desktop\视频工作流\`
> 剪映版本: 专业版 5.9+ | 视频规格: 1080×1920 (9:16)
> 最后更新: 2026-06-07 19:35

---

## v8.0 — 2026-06-07 · SSML移除 + 原生TTS参数（致命BUG修复）

**修复**: Edge TTS不支持SSML，`<speak>` XML标签被当做文本朗读→前17秒是XML朗读
**方案**: 改用 `edge_tts.Communicate(text, voice, rate="-2%", pitch="+5Hz")` 原生参数
**效果**: 110字配音42.5s→25.5s，文件249KB→149KB，前20秒恢复正常正文播报

## v7.0 — 2026-06-07 · 全链路数字/符号过滤 + MULTILINE修复

**修复**: `_strip_leading_junk()` 只用`^`锚点→第2行起序号残留。改用`re.MULTILINE`
**新增**: `_global_strip_numbers()` 全局正则清除句中孤立数字
**新增**: 5层拦截链（字幕拆分→TTS拼接→清洗→配音前→配音后）

## v6.0 — 2026-06-07 · 保护词词库 + 配音断句保护

**新增**: `PROTECTED_WORDS` 110+产品词，强制TTS连贯朗读不拆分
**新增**: `_protect_text_for_tts()`, `_verify_word_integrity()` 校验机制

## v5.0 — 2026-06-07 · ★ 时长控制反转（架构改动）

**核心改动**: 先生成完整文案+配音，再根据配音时长选取素材
**旧流程**: 选素材→定时长→写文案→截断 | **新流程**: 写文案→配音→素材适配
**新增**: `FORCE_COMPLETE_SENTENCE=True`, 素材不足自动补充

## v4.0 — 2026-06-07 · 字幕无背景 + 句子级拆分

**修复**: `SUBTITLE_BACKGROUND_ENABLED=False` 永久关闭灰色背景
**修复**: 重写 `split_copy_to_subtitles()` — 按。！？拆分，逗号保留句内

## v3.0 — 2026-06-07 · 多卖点混合 + 三段式CTA

**新增**: `collect_multi_point_mp4s()` 强制≥3卖点源
**新增**: 三段式文案结构（钩子→卖点→CTA），`_check_cta_present()` CTA自动补全
**配置**: `MIN_SELLING_POINTS=3, MAX_CLIPS_PER_POINT=2`

---

## v2.0 — 2026-06-07 · 全功能稳定版

**所有模块集成完毕，2407行代码，45个函数，1个核心类。**

| 模块 | 状态 | 命令 |
|------|------|------|
| 单卖点 | ✅ | `python video_editor.py 内嵌烤箱 --auto-bgm --tts` |
| 多卖点混剪 | ✅ | `--multi "烤箱,灯带,水槽" --auto-bgm --tts` |
| 随机混剪 | ✅ | `--multi-random 6 --auto-bgm --tts` |
| BGM下载 | ✅ | `--download-bgm 10` |
| 交互模式 | ✅ | `-i` |

### 已固化功能清单

1. **剪映格式** — pyJianYingDraft 生成标准 draft_content.json + draft_meta_info.json + draft_settings
2. **字幕样式** — 暖白(#FFF8E7) + 黑色描边 + 阴影 + 半透明背景遮挡，size=9.0 统一
3. **配音字幕同步** — 同一数据源，TTS读什么字幕显示什么
4. **配音填满视频** — 自动插入过渡句，覆盖率≥90%
5. **时间轴对齐** — TTS时长检测 → 字幕按比例定位
6. **画面精确匹配** — 文件名材质颜色解析 → AI强制按画面写
7. **坤宝风格文案** — 学习103条陶联社稿 → "90%的人..."钩子
8. **视频原声静音** — volume=0.0，BGM 45%，配音100%
9. **变速节奏** — 0.85x~1.15x 画面变速
10. **BGM多样化** — Mixkit 9首曲目 + 批量下载
11. **Edge TTS** — 晓依音色，纯文本无乱码
12. **片段分组排列** — 同卖点不分散

---

## v1.13 — 2026-06-07 · 画面精确匹配

**问题**: 文案说的材质颜色和视频实际画面不符（画面白色原木风，文案却讲骑士黑）

**修复**:
- 重写 `_extract_video_descriptions()` — 从文件名精确解析材质颜色（识别`+`号连接的颜色标签如"微水泥奶油白+兰亭香樟木纹"）
- 更新 DEEPSEEK_SYSTEM_PROMPT — 新增"画面匹配"规则
- 更新 user prompt — 强制要求每句材质颜色严格对应画面
- 新增禁止项：禁止编造画面中没有的颜色和材质

---

## v1.12 — 2026-06-07 · 配音填满视频

**问题**: 视频25秒但配音只有18秒，留7秒空镜头只有BGM

**修复**:
- 新增 `_pad_subtitles_for_duration()` — 字幕不足93%覆盖率时自动插入过渡句
- 填充句库：12条自然岛台评价语句
- 新增 `_estimate_tts_duration()` — 中文4字/秒估算
- 新增 `TTS_CHARS_PER_SEC = 4.0` 配置

---

## v1.11 — 2026-06-07 · 配音时间轴同步

**问题**: 配音读完了字幕还在前面，字幕和配音对不上

**修复**:
- 新增 `get_audio_duration_seconds()` — pymediainfo检测TTS实际时长
- 新增 `build_tts_synced_timeline()` — 按字数比例分配字幕时长
- 字幕时间位置跟随TTS节奏而非视频片段边界
- 微秒级非重叠时间计算

---

## v1.10 — 2026-06-07 · 字幕单行显示

**问题**: 视频中字幕3-4行混乱，大小不统一，含异常字符

**修复**:
- 重写 `split_copy_to_subtitles()` — 强制 MAX_LEN=20，超出拆分
- 字幕样式统一 size=9.0
- 字幕和TTS使用完全相同文本（`tts_text = "。".join(subtitles)`）
- 清理emoji和异常Unicode字符

---

## v1.9 — 2026-06-06 · 坤宝风格文案

**问题**: 文案风格普通，不像小红书爆款

**修复**:
- 读取学习 `C:\Users\admin\Desktop\陶联社视频稿.xlsx` (103条洗稿文案)
- 重写 DEEPSEEK_SYSTEM_PROMPT — "90%的人..."钩子、"你敢信吗？"反转、"它叫XX风岛台"命名法
- 口语化表达：呢、吧、你看、就是、其实
- CTA模板："想要同款？评论区扣'岛台'发你方案！"

---

## v1.8 — 2026-06-06 · BGM多样化

**问题**: BGM总是同一首，太单一

**修复**:
- 新增 `download_bgm_batch()` — 从Mixkit多页面批量下载
- 多风格页面池：corporate/ambient/chill/motivational/cinematic
- 本地已有9首BGM随机轮换
- 新增 `--download-bgm N` 命令

---

## v1.7 — 2026-06-06 · 视频变速

**问题**: 视频节奏呆板，没有快慢变化

**修复**:
- `add_video_clip()` 增加 `speed` 参数（0.85x~1.15x）
- `collect_multi_selling_mp4s()` 自动分配变速节奏
- `select_clips()` 增加随机变速
- 变速后自动修正 target_timerange（从 segment 读取实际值）

---

## v1.6 — 2026-06-06 · 字幕样式升级

**问题**: 字幕纯白无样式，原视频字幕干扰

**修复**:
- TextBorder 黑色描边 (width=45)
- TextShadow 阴影增强立体感
- TextBackground 半透明暗底遮挡 (alpha=0.35)
- 字幕位置上移 y=-0.75 避开原视频底部文字
- 字体颜色改为暖白(1.0, 0.97, 0.90)

---

## v1.5 — 2026-06-06 · TTS配音

**问题**: 无配音，只有背景音乐

**修复**:
- 集成 Edge TTS (`edge-tts` 库)
- 晓依音色 (zh-CN-XiaoyiNeural)
- 纯文本模式（最初SSML导致乱码，已废弃）
- 独立配音轨道（在BGM之上）
- 新增 `--tts` 和 `--voice` 参数

---

## v1.4 — 2026-06-06 · 多卖点混剪

**问题**: 只能做单一卖点视频

**修复**:
- 新增 `run_multi()` 函数
- 新增 `--multi` 参数（逗号分隔卖点列表）
- 新增 `--multi-random N` 参数（随机选择N个卖点）
- 新增 `collect_multi_selling_mp4s()` — 从多文件夹各取片段
- 新增 `generate_multi_copy()` — 多卖点统一文案
- 片段按卖点分组排列（不分散）

---

## v1.3 — 2026-06-06 · 音频修复

**问题**: 原声干扰配音，BGM太小声

**修复**:
- VIDEO_VOLUME: 0.0（原声彻底静音）
- BGM_VOLUME: 0.45（提升到45%）
- SUBTITLE_FONT_SIZE: 9.0（约60-80px显示）

---

## v1.2 — 2026-06-06 · BGM自动获取

**功能新增**:
- `download_bgm_from_pixabay()` — Pixabay API下载
- `download_bgm_from_mixkit()` — Mixkit免费音乐
- `generate_ambient_bgm()` — Python纯算法合成（兜底）
- `auto_get_bgm()` — 三层获取策略

---

## v1.1 — 2026-06-06 · 格式修复

**问题**: 草稿在剪映中提示"草稿内容已损坏"

**修复**:
- 废弃手动构造的JSON格式
- 改用 pyJianYingDraft 库生成标准格式
- 修复 canvas_config、config、platform、segment等关键字段
- 新增 draft_settings 文件

---

## v1.0 — 2026-06-06 · 初始版本

**功能**:
- 关键词匹配卖点文件夹
- 智能选取5-8个片段
- DeepSeek生成小红书风格文案
- 剪映草稿文件生成
- BGM轨道、字幕轨道
