# 心屿「数据埋点」规格说明书（analytics_spec.md）

> 目的：为 AI 产品经理求职（STAR / 简历 R 段）提供**可核对、可复现**的产品与性能数据。
> 实现：后端一个轻量 SDK（`backend/app/analytics.py`），追加写 NDJSON 到根目录日志
> `logs/analytics__events.log`。本轮只记录结构化元数据，**绝不落盘用户消息原文**（隐私红线）。

---

## 0. 名词与假设（先列假设再实现）

- **假设 A（目标岗位）**：以「AI 产品经理」为基准设计埋点，优先支撑「任务成功率 / 性能 / 降级兜底 / 模型路由分布 / RAG 可靠性 / 留存」叙事。
- **假设 B（无 JD）**：未提供完整 JD，仅用 AI PM 岗位高频关键词设计。
- **假设 C（多进程写入）**：当前为单进程 uvicorn；日志写入用进程内 `threading.Lock` 串行。若日后多进程部署，需改为「append 模式 + 原子尾部写」或引入消息队列（见 §6）。
- **假设 D（隐私替代）**：涉及用户内容的字段一律不写入埋点；需要关联时用 `user_id` 弱哈希片段（见 `analytics._anonymize`）。
- **假设 E（失败降级）**：所有 `track()` 异常被内部捕获，仅记 debug，**不影响任何业务主流程**。

---

## 1. 埋点总目标 → 支撑 STAR 哪一段

| 埋点事件簇 | 支撑概念 | STAR 段 |
|---|---|---|
| `chat_session_started` / `chat_message_sent` / `ai_reply_completed` | 产品有完整对话链路、可完成任务 | **S / A / R** |
| `crisis_triggered` / `diary_ai_fallback` | 有安全红线与降级兜底，AI 挂了产品仍可用 | **A / R** |
| `model_routed` / `lm_query_latency` | 有路由决策 + 性能可量化 | **A / R** |
| `rag_search` / `rag_no_hit_rejected` | 宁可拒答不编造，可靠性 | **R** |
| `diary_created` / `assessment_submitted` / `training_completed` / `achievement_unlocked` | 留存与活跃的可用事实 | **S / R** |

关键 R 段可提炼指标见 §5。

---

## 2. 事件清单表（event_name / 触发时机 / 关键字段 / 隐私注意）

> 公共字段（每条都有）：`event` · `event_ts`(UTC ISO8601 ms) · `app_version` · `user_id`(弱哈希片段)。

| event_name | 触发时机（代码位置） | 关键属性 | 隐私注意 |
|---|---|---|---|
| `chat_session_started` | 新建会话（`coordinator.process_message` 步骤1，`conversation_id is None`） | `conversation_id` `is_new` | 只存 id |
| `chat_message_sent` | 保存用户消息（步骤3之后） | `conversation_id` `round_count` `input_len` | 只存输入长度，不存原文 |
| `perception_result` | `perception_module.execute` 返回（步骤4） | `is_privacy` `is_complex` `intent` | intent 标签无内容 |
| `crisis_triggered` | 感知 `is_crisis`，进入危机分支（步骤5） | `model_used` `posted_hotline` | 只计数，不落危机原文 |
| `phase_transition` | `phase_manager.should_transition` 为真（步骤6） | `from_phase` `to_phase` `at_round` | — |
| `rag_search` | `hybrid_search` 返回（intent=knowledge 时，步骤6.5） | `hits_count` `no_hit` `search_type` | 只存命中数量 |
| `rag_no_hit_rejected` | `no_hit=True` 拒答（步骤6.5） | `conversation_id` `query_len` | 只存 query 长度 |
| `model_routed` | `get_model_name` 决策后（步骤7） | `model_used` `is_privacy` `is_complex` | 只存模型名 |
| `lm_query_latency` | `generate_with_prompt` 流式结束 | `elapsed_ms` `model_used` `reply_len` | — |
| `ai_reply_completed` | AI 响应生成完成 | `reply_len` `agent_type` `model_used` `phase` | — |
| `diary_created` | `POST /api/diary/create` 成功 | `diary_id` `word_count` `writing_duration_s` `template_used` `main_emotion` `emotion_valence` | 情绪标签可采，不落正文 |
| `diary_ai_fallback` | 日记 AI 反馈失败→`generate_simple_feedback` | `fallback` `reason` | — |
| `diary_create_failed_dup` | 当天重复提交 400 | `err_code` `reason` | — |
| `assessment_submitted` | `POST /api/assessments/submit` 成功 | `record_id` `scale_name` `score` `risk_level` | 只存总分/等级，不落逐题 |
| `training_completed` | `POST /api/training/complete` 成功 | `training_id` `training_type` `duration_s` `completion_status` | — |
| `achievement_unlocked` | `growth.check_achievements` 触发新成就 | `achievement_type` `name` `current_streak` `total_winged` `positive_ratio` | — |

---

## 3. 关键事件「定义」与字段说明

### 3.1 `chat_message_sent`
- 触发条件：用户在对话中成功发出一条消息（协调器步骤3保存 users 消息后）。
- 用途：对话活跃数、单会话轮次分布。
```json
{"event": "chat_message_sent", "event_ts": "2026-09-09T03:55:00.000Z", "app_version": "1.0.0", "user_id": "c2a9f08d", "conversation_id": 12, "round_count": 4, "input_len": 37}
```

### 3.2 `model_routed`
- 触发条件：协调器选择模型服务后。
- 字段 `model_used`：`remote-Qwen3-Next-80B` 或 `local-Qwen3-4B`（取决于路由）。
```json
{"event": "model_routed", "event_ts": "...", "app_version": "1.0.0", "user_id": "a1b2c3d4", "conversation_id": 12, "model_used": "remote-Qwen3-Next-80B", "is_privacy": false, "is_complex": true}
```

### 3.3 `crisis_triggered`
- 触发条件：感知判断 `is_crisis=True`；此时主流程立即返回热线卡片，不再走普通生成。
- 口径：`posted_hotline=true` 表示已输出 400-161-9995 热线。**该事件仅计数，不记录触发原文。**
```json
{"event": "crisis_triggered", "event_ts": "...", "app_version": "1.0.0", "user_id": "e5f60708", "conversation_id": 20, "model_used": "local", "posted_hotline": true}
```

### 3.4 `diary_ai_fallback`
- 触发条件：`generate_ai_feedback_with_ollama` 异常 → 回退 `generate_simple_feedback`。
- 口径：`fallback=true` 表示降级；`reason` 为异常类型名（如 `ollama._types.ResponseError`）。
```json
{"event": "diary_ai_fallback", "event_ts": "...", "app_version": "1.0.0", "user_id": "a1b2c3d4", "fallback": true, "reason": "ResponseError"}
```

### 3.5 `assessment_submitted`
- 触发条件：评估提交并保存记录成功。
- 字段：`scale_name`（PHQ-9/GAD-7/…）、`score`（官方总分）、`risk_level`（正常/轻度/中度/重度…）。
```json
{"event": "assessment_submitted", "event_ts": "...", "app_version": "1.0.0", "user_id": "a1b2c3d4", "record_id": 3, "scale_name": "PHQ-9", "score": 7, "risk_level": "轻度"}
```

---

## 4. 如何本地验证（手动触发 → 观察日志）

> 预期日志文件：`d:\xinyu\xinyu-main\logs\analytics__events.log`

### 前置：启服
在后端目录启动：
```bash
cd backend
.venv\Scripts\python.exe main.py
```

### 用例 1｜对话链路（普通消息）
```bash
curl -X POST http://localhost:8000/api/chat/send \
  -H "Authorization: Bearer <你的token>" -H "Content-Type: application/json" \
  -d '{"message": "我最近压力有点大"}'
```
**应在日志看到**：`chat_session_started`(若新会话) → `chat_message_sent` → `perception_result`(?intent) → `model_routed` → `lm_query_latency` → `ai_reply_completed`。

### 用例 2｜危机拦截（安全红线）
```bash
curl -X POST http://localhost:8000/api/chat/send \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"message": "我觉得活着没意思"}'
```
**应在日志看到**：`crisis_triggered` 且 `posted_hotline=true`；**不应出现** `model_routed` / `ai_reply_completed`（危机优先，主流程终止）。

### 用例 3｜日记创建
```bash
curl -X POST http://localhost:8000/api/diary/create \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"diary_date":"2026-09-09","content":"今天心情不错","emotions":[{"emotion":"快乐","intensity":8}], "life_dimensions":{}}'
```
**应在日志看到**：`diary_created`（含 `word_count`、`main_emotion=快乐`、`emotion_valence`）。若今天重复提交 → 看到 `diary_create_failed_dup`。

### 用例 4｜评估提交
```bash
curl -X POST http://localhost:8000/api/assessments/submit \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"template_id":1,"answers":[1,0,0,1,0,0,0,0,1]}'
```
**应在日志看到**：`assessment_submitted`（`scale_name`、`score`、`risk_level`）。

### 查看最新事件
```bash
Get-Content logs\analytics__events.log -Tail 20
```

---

## 5. 建议「简历可写指标」定义（含统计口径）

1. **对话任务成功率**
   口径：`ai_reply_completed / chat_message_sent`（每发一条且正常生成完成=成功）；危机/错误不计为失败，单独统计。
2. **AI 生成响应延迟 P95**
   口径：`lm_query_latency.elapsed_ms` 的分位数 P95（首 token 流式耗时）。
3. **降级兜底率**
   口径：`(diary_ai_fallback + 对话错误事件) / 总 AI 调用`，越低越好；证明"AI 偶发失败产品仍可用"。
4. **模型路由分布 + 缓存命中**
   口径：按 `model_routed.model_used` 计数占比；`remote` 场景可结合 `llm_service.record_llm_call` 的 `cached_tokens/total_tokens`。
5. **RAG 命中与拒答率**
   口径：knowledge 意图里 `rag_search.no_hit=false` 占比；`rag_no_hit_rejected / knowledge 查询数`。证明"拒答不编造"。
6. **留存探针**
   口径：周 N-1 有 `diary_created` 的用户中，周 N 仍有任一事件的比例。

---

## 6. 实现与部署注意事项

- **与现有 LLM 统计去重**：`record_llm_call`（`LlmCallStats` 表）已记录 token/缓存；`lm_query_latency` **只补延迟**，不重复记 usage。
- **低开销**：`track()` 是「单行追加+线程锁」，写入量小，不阻塞 SSE 流（埋点在生成**之后**一次性落）。
- **多进程并发警告**：单进程锁在多 worker 下不保证顺序；生产建议改消费队列或接受轻微乱序（NDJSON 按行仍不损坏）。
- **隐私/合规**：全表不带 `content` 原文字段；`user_id` 弱哈希化；危机只记"是否发生"。
- **可回放**：事件带 `conversation_id`，可按序还原单次会话成败，供面试讲"一次真实降级→恢复"的案例。

---

## 7. 变更文件清单（本次实现）

| 文件 | 内容 |
|---|---|
| `backend/app/analytics.py` | **新增** 轻量埋点 SDK（NDJSON 追加写入，失败静默） |
| `backend/app/coordinator.py` | 接入：chat_session_started / chat_message_sent / perception_result / crisis_triggered / phase_transition / rag_search / rag_no_hit_rejected / model_routed / lm_query_latency / ai_reply_completed |
| `backend/app/routers/diary.py` | 接入：diary_created / diary_ai_fallback / diary_create_failed_dup |
| `backend/app/routers/assessment.py` | 接入：assessment_submitted |
| `backend/app/routers/training.py` | 接入：training_completed |
| `backend/app/routers/growth.py` | 接入：achievement_unlocked |
| `logs/analytics__events.log` | **运行期产物**，NDJSON 追加 |