# 心屿 v2 升级说明（RAG + 长期记忆 + 效果度量）

本文件记录本次升级的内容与使用方法。代码为非破坏性升级：启动时自动备份数据库并补建表/列。

## 新增能力

1. **RAG 知识库问答**
   - 精选公开心理资料种子库（量表说明、情绪管理、危机资源等），启动时自动幂等导入；
   - 混合检索：向量（`Qwen/Qwen3-Embedding-0.6B`）+ SQLite FTS5 关键词 + RRF 合并；
   - 类型化分块：量表/危机类文档整篇单块，长文按标题分段（≤800 字，重叠 80）；
   - 相关性不足时明确拒答，回答带 `[来源：标题]` 引用；
   - 支持用户上传 txt/markdown 文档。
2. **长期记忆**
   - 对话/日记/量表提交后自动抽取事实（身份、偏好、事件、情绪模式、危机时刻）；
   - 同类高相似新事实取代旧事实（旧记录保留但失效）；
   - 检索排序 = 相似度 + 时效衰减 + 情绪峰值加权；
   - 超过 90 天未使用且非高情绪的记忆自动失效；高情绪/危机记忆不自动删除，仅用户可删。
3. **效果度量**
   - PHQ-9 / GAD-7 分数变化、风险等级迁移、日记情绪趋势（含斜率）；
   - 每次量表提交自动写周快照；
   - 数据分析页新增“效果概览”。仅供参考，不构成诊断。

## 新增 API

- `POST /api/knowledge/seed` 手动导入种子知识库（幂等）
- `GET /api/knowledge` / `POST /api/knowledge/upload` / `DELETE /api/knowledge/{id}`
- `GET /api/memory` / `DELETE /api/memory/{id}`
- `GET /api/analytics/outcome?days=28`

## 配置（backend/.env）

```env
MODELSCOPE_API_KEY=你的Key
MODELSCOPE_BASE_URL=https://api-inference.modelscope.cn/v1
CHAT_MODEL=Qwen/Qwen3-Next-80B-A3B-Instruct
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
RAG_TOP_K=3
RAG_MIN_SCORE=0.35
MEMORY_TOP_K=5
MEMORY_RECENCY_WEIGHT=0.3
MEMORY_EMOTION_WEIGHT=0.2
MEMORY_INACTIVE_DAYS=90
```

未配置 Key 时：页面可用，AI 相关能力（对话、RAG、记忆抽取）会优雅降级/跳过，不影响其余功能。

## 隐私说明

一期采用魔搭云端单平台：对话、向量化与记忆抽取经云端处理。记忆数据仍保存在本机 SQLite；
“敏感话题强制本地”的代码路径保留，需要时设置 `USE_LOCAL_MODEL=true` 并安装 Ollama 后恢复。
