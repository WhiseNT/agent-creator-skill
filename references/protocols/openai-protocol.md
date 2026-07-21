# OpenAI API 协议完整参考

> 基线：2026-07-21。本文包含 Responses API、Chat Completions API、Codex、Realtime API 的全部协议细节，经官方文档验证。实现前请核对 developers.openai.com 最新变更。

---

## 目录

1. [Responses API](#1-responses-api)
2. [Chat Completions API](#2-chat-completions-api)
3. [Codex](#3-codex)
4. [Realtime API（WebSocket）](#4-realtime-apiwebsocket)
5. [认证与错误处理](#5-认证与错误处理)
6. [OpenAI 特有格式参考](#6-openai-特有格式参考)

---

## 1. Responses API

**端点**：`POST https://api.openai.com/v1/responses`

**状态**：推荐主线。Chat Completions 仍然可用，但新项目应使用 Responses。

### 1.1 请求完整字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | `string` | **是** | 模型 ID，如 `gpt-5.6`、`gpt-5.5`、`gpt-4o`、`o3-mini` |
| `input` | `string \| InputItem[]` | **是** | 用户输入。字符串或输入项数组 |
| `instructions` | `string \| null` | 否 | 系统指令，插在对话顶部，默认 `null` |
| `max_output_tokens` | `integer \| null` | 否 | 输出 token 上限，默认无限制 |
| `metadata` | `object \| null` | 否 | 最多 16 个键值对，键最长 64 字符、值最长 512 字符 |
| `parallel_tool_calls` | `boolean` | 否 | 是否允许并行工具调用，默认 `true` |
| `previous_response_id` | `string \| null` | 否 | 上一轮 response ID，维护服务端状态 |
| `reasoning` | `object \| null` | 否 | `{ "effort": "low" \| "medium" \| "high" }` |
| `store` | `boolean` | 否 | 是否存储输出，默认 `true` |
| `stream` | `boolean \| null` | 否 | 是否 SSE 流式，默认 `false` |
| `temperature` | `number \| null` | 否 | 0–2，默认 `1` |
| `tool_choice` | `string \| object \| null` | 否 | `"none"` / `"auto"` / `"required"` / `{"type":"function","name":"..."}` |
| `tools` | `Tool[]` | 否 | 工具定义数组 |
| `top_p` | `number \| null` | 否 | 0–1，默认 `1` |
| `truncation` | `string \| null` | 否 | `"auto"`（默认）或 `"disabled"` |
| `user` | `string` | 否 | 终端用户标识 |
| `text` | `object \| null` | 否 | 文本输出格式，含 `text.format` |

#### `text.format` 结构化输出格式

```typescript
// 纯文本（默认）
{ "format": { "type": "text" } }

// JSON 模式
{ "format": { "type": "json_object" } }

// JSON Schema 约束
{
  "format": {
    "type": "json_schema",
    "name": "response_schema",
    "strict": true,       // 可选，默认 false
    "schema": {
      "type": "object",
      "properties": { ... },
      "required": [...],
      "additionalProperties": false
    }
  }
}
```

`json_schema` 约束：
- 根 `type` 必须为 `"object"`
- `additionalProperties` 必须为 `false`
- 所有属性必须在 `required` 中
- 最大嵌套深度 5 层
- 支持：`string`、`number`、`integer`、`boolean`、`array`、`object`、`null`、`enum`、`anyOf`

### 1.2 Input Item 类型

#### Message Item

```json
{
  "type": "message",
  "role": "user",            // "user" | "assistant"
  "status": "completed",
  "content": [               // 内容部件数组
    { "type": "input_text", "text": "Hello" },
    { "type": "input_image", "image_url": "https://...", "detail": "auto" }
  ]
}
```

- `input_text`：`{ "type": "input_text", "text": "..." }`
- `input_image`：`{ "type": "input_image", "image_url": "..." \| "data:image/...;base64,...", "detail": "auto" \| "low" \| "high" }`

#### File Item

```json
{ "type": "file", "file_id": "file_xxx", "tools": [{"type": "file_search"}] }
```

#### function_call_output Item（工具结果回传）

```json
{ "type": "function_call_output", "call_id": "call_xxx", "output": "..." }
```

#### computer_call_output Item

```json
{
  "type": "computer_call_output",
  "call_id": "call_xxx",
  "output": {
    "type": "computer_screenshot",
    "image_url": "data:image/png;base64,..."
  }
}
```

### 1.3 响应完整 Schema

```json
{
  "id": "resp_68af4030592c81938ec0a5fbab4a3e9f05438e46b5f69a3b",
  "object": "response",
  "created_at": 1756315696,
  "status": "completed",
  "model": "gpt-5.5",
  "error": null | { "code": "...", "message": "..." },
  "incomplete_details": null | { "reason": "max_output_tokens" },
  "instructions": null | "系统指令",
  "metadata": {},
  "output": [ /* OutputItem[] */ ],
  "parallel_tool_calls": true,
  "previous_response_id": null | "resp_xxx",
  "temperature": 1.0,
  "tool_choice": "auto",
  "tools": [],
  "top_p": 1.0,
  "truncation": "auto",
  "usage": {
    "input_tokens": 10,
    "output_tokens": 100,
    "total_tokens": 110,
    "output_tokens_details": { "reasoning_tokens": 30 }
  }
}
```

`status` 枚举：`"completed"` | `"failed"` | `"in_progress"` | `"incomplete"` | `"cancelled"`

### 1.4 Output Item 类型

`output` 数组包含以下类型：

#### `message`

```json
{
  "id": "msg_xxx",
  "type": "message",
  "status": "completed",
  "role": "assistant",
  "content": [
    { "type": "output_text", "text": "...", "annotations": [] },
    { "type": "refusal", "refusal": "I cannot answer..." }
  ]
}
```

#### `reasoning`

```json
{
  "id": "rs_xxx",
  "type": "reasoning",
  "content": [],
  "summary": [
    { "text": "推理总结文本" }
  ]
}
```

#### `function_call`

```json
{
  "id": "fc_xxx",
  "type": "function_call",
  "call_id": "call_xxx",
  "name": "get_weather",
  "arguments": "{\"location\": \"San Francisco\"}",   // JSON 字符串
  "status": "completed"
}
```

#### `function_call_output`

```json
{
  "type": "function_call_output",
  "call_id": "call_xxx",
  "output": "result string"
}
```

#### `web_search_call`

```json
{
  "id": "ws_xxx",
  "type": "web_search_call",
  "status": "completed",
  "results": [{"title": "...", "url": "...", "description": "..."}]
}
```

#### `file_search_call`

```json
{
  "id": "fs_xxx",
  "type": "file_search_call",
  "status": "completed",
  "queries": ["用户搜索词"],
  "results": [{"file_id": "...", "file_name": "...", "score": 0.95, "content": [...]}]
}
```

#### `computer_call`

```json
{
  "id": "comp_xxx",
  "type": "computer_call",
  "call_id": "call_xxx",
  "action": {
    "type": "click",                                    // click | double_click | drag | keypress | type | wait | move | scroll | screenshot
    "button": "left",                                    // click/double_click 时
    "x": 500, "y": 300,                                  // 坐标
    "keys": ["ctrl", "c"]                                // keypress 时
  },
  "pending_safety_checks": []
}
```

#### `code_interpreter_call`

```json
{
  "id": "ci_xxx",
  "type": "code_interpreter_call",
  "status": "completed",
  "input": "print('hello')",
  "outputs": [
    { "type": "code", "output": "hello\n" },
    { "type": "file", "file_id": "file_xyz", "filename": "chart.png" }
  ]
}
```

### 1.5 Tool 定义格式

#### Function Tool

```json
{
  "type": "function",
  "name": "get_weather",
  "description": "获取天气信息",
  "strict": true,                                   // optional, default false
  "parameters": {
    "type": "object",
    "properties": {
      "location": { "type": "string", "description": "城市" }
    },
    "required": ["location"],
    "additionalProperties": false
  }
}
```

注意：Responses 中 function 定义是**内部标记**（`name` 在顶层），Chat Completions 是**外部标记**（`name` 在 `function.name` 内）。

#### Web Search Tool

```json
{
  "type": "web_search",
  "user_location": {
    "type": "approximate",
    "city": "San Francisco", "country": "US",
    "region": "California", "timezone": "America/Los_Angeles"
  },
  "search_context_size": "medium"    // "low" | "medium" | "high"
}
```

#### File Search Tool

```json
{ "type": "file_search", "vector_store_ids": ["vs_xxx"], "max_num_results": 5 }
```

#### Computer Use Tool

```json
{
  "type": "computer_use_preview",
  "display_width": 1024,
  "display_height": 768,
  "environment": "mac"    // "mac" | "windows" | "ubuntu" | "browser"
}
```

#### Code Interpreter Tool

```json
{ "type": "code_interpreter" }
```

### 1.6 SSE 流式事件

设置 `stream: true` 后，SSE 事件格式为 `event: <type>\ndata: <json>\n\n`

| 事件名 | 时机 | 关键 payload |
|--------|------|--------------|
| `response.created` | Response 创建 | `response.id`, `response.status: "in_progress"` |
| `response.in_progress` | 变为 in_progress | `response.id`, `response.status` |
| `response.output_item.added` | 新 output item | `item.type`, `item.id`, `output_index` |
| `response.output_item.done` | item 完成 | `item`（完整） |
| `response.content_part.added` | 内容部件添加 | `part.type`, `item_id` |
| `response.content_part.done` | 内容部件完成 | `part`（完整） |
| `response.output_text.delta` | 文本增量 | `delta`（字符串）, `item_id` |
| `response.output_text.done` | 文本完成 | `text`（完整字符串） |
| `response.function_call_arguments.delta` | 参数增量 | `delta`（JSON 片段） |
| `response.function_call_arguments.done` | 参数完成 | `arguments`（完整 JSON） |
| `response.code_interpreter.delta` | 代码输出增量 | `delta` |
| `response.code_interpreter.done` | 代码执行完成 | `output` |
| `response.completed` | 完全完成 | `response.status: "completed"`, `response.usage` |
| `response.failed` | 失败 | `response.error` |
| `response.incomplete` | 不完整 | `reason: "max_output_tokens"` |
| `response.cancelled` | 取消 | `response.status: "cancelled"` |
| `error` | 流错误 | `error.type`, `error.message` |

### 1.7 多轮交互

```python
# 方式 A：previous_response_id（推荐）
resp1 = client.responses.create(model="gpt-5.6", input="Hello")
resp2 = client.responses.create(model="gpt-5.6", input="What did I say?",
                                previous_response_id=resp1.id)

# 方式 B：手动回传 output items
resp1_items = resp1.output
resp2 = client.responses.create(model="gpt-5.6",
                                input=["Hello", *resp1_items, "What did I say?"])

# 方式 C：Conversations API（持久性对话）
```

**注意**：`previous_response_id` 不传递 `instructions`，所以每次请求要重新发送 `instructions`。

---

## 2. Chat Completions API

**端点**：`POST https://api.openai.com/v1/chat/completions`

**状态**：稳定。新项目推荐迁移到 Responses API。

### 2.1 请求字段

| 字段 | 类型 | 必填 |
|------|------|------|
| `model` | `string` | **是** |
| `messages` | `Message[]` | **是** |
| `temperature` | `number` | 否，默认 `1` |
| `top_p` | `number` | 否，默认 `1` |
| `n` | `integer` | 否，默认 `1` |
| `stream` | `boolean` | 否，默认 `false` |
| `stream_options` | `object` | 否，如 `{"include_usage": true}` |
| `stop` | `string \| string[]` | 否，最多 4 个 |
| `max_tokens` | `integer` | 否 |
| `presence_penalty` | `number` | 否，-2.0~2.0 |
| `frequency_penalty` | `number` | 否，-2.0~2.0 |
| `logit_bias` | `map` | 否 |
| `logprobs` | `boolean` | 否 |
| `top_logprobs` | `integer` | 否，0~20 |
| `response_format` | `object` | 否，`{"type": "json_schema", "json_schema": {...}}` |
| `seed` | `integer` | 否 |
| `service_tier` | `string` | 否，`"auto"` \| `"default"` |
| `tools` | `Tool[]` | 否 |
| `tool_choice` | `string\|object` | 否，`"none"` \| `"auto"` \| `"required"` |
| `parallel_tool_calls` | `boolean` | 否，默认 `true` |
| `user` | `string` | 否 |
| `store` | `boolean` | 否，默认 `true` |
| `metadata` | `object` | 否 |

#### `messages[]` 的 role 和格式

| role | 说明 | content 格式 |
|------|------|--------------|
| `"system"` | 系统指令 | `string` 或 `ContentPart[]` |
| `"developer"` | 开发者指令（新） | `string` 或 `ContentPart[]` |
| `"user"` | 用户消息 | `string` 或 `ContentPart[]` |
| `"assistant"` | 模型回复 | `string \| null`（当有 `tool_calls` 时可为 null） |
| `"tool"` | 工具结果 | `string`，需 `tool_call_id` 字段 |

#### `response_format` 结构化输出

```json
// JSON Schema
{ "type": "json_schema", "json_schema": { "name": "schema", "strict": true, "schema": {...} } }

// JSON Object
{ "type": "json_object" }

// 文本（默认）
{ "type": "text" }
```

### 2.2 响应 Schema

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "gpt-4o-mini",
  "system_fingerprint": "fp_44709d6fcb",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "\n\nHello!",
        "tool_calls": [
          { "id": "call_xxx", "type": "function",
            "function": { "name": "get_weather", "arguments": "{\"loc\":\"SF\"}" } }
        ] | null
      },
      "logprobs": null,
      "finish_reason": "stop"     // "stop" | "length" | "content_filter" | "tool_calls"
    }
  ],
  "usage": {
    "prompt_tokens": 9,
    "completion_tokens": 12,
    "total_tokens": 21,
    "completion_tokens_details": { "reasoning_tokens": 0 }
  }
}
```

### 2.3 Streaming Chunks

```json
// 第一个 chunk
{ "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}}] }

// 中间 chunk（文本）
{ "choices": [{"index": 0, "delta": {"content": "Hello"}}] }

// 中间 chunk（tool call）
{
  "choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "id": "call_xxx", "function": {"name": "get_weather", "arguments": "{\"loc\""}}]}}]
}

// 拒绝时
{ "choices": [{"index": 0, "delta": {"refusal": "I cannot..."}}] }

// 最终 chunk
{ "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}] }
```

流结束时发送 `data: [DONE]`。

---

## 3. Codex

### 3.1 定位

Codex 不是独立的 API 端点，而是**基于 Responses API 的编程 Agent 平台**。Codex 使用专用模型 `gpt-5.3-codex` / `gpt-5.2-codex` / `codex-mini-latest`。

### 3.2 Codex 模型参数

| 模型 | 上下文 | max_output | 输入价格 | 输出价格 |
|------|--------|------------|----------|----------|
| `gpt-5.3-codex` | 400K | 128K | $1.25/1M | $10/1M |
| `codex-mini-latest` | — | — | $1.50/1M | — |

### 3.3 集成方式

```python
# Responses API 直接使用 Codex 模型
response = client.responses.create(model="gpt-5.3-codex", input="Write a Python script to ...")

# Codex SDK
from openai import codex
await codex.run(task="Refactor this function")

# Codex CLI（终端使用）
codex "Add error handling to main.py"

# Codex MCP Server（嵌入其他工具链）
```

---

## 4. Realtime API（WebSocket）

**端点**：`wss://api.openai.com/v1/realtime`

**认证**：`?token=YOUR_API_KEY` 查询参数，或 WebSocket 握手时 `Authorization: Bearer` 头

### 4.1 Client Events

| 事件类型 | 关键字段 |
|----------|----------|
| `session.update` | `session.modalities`, `session.instructions`, `session.voice`, `session.turn_detection`, `session.tools`, `session.temperature`, `session.max_response_output_tokens` |
| `conversation.item.create` | `item.type`（"message"/"function_call"/"function_call_output"）, `item.role`, `item.content` |
| `response.create` | `response.modalities`, `response.instructions`, `response.tools` |
| `input_audio_buffer.append` | `audio`（base64） |
| `input_audio_buffer.commit` | — |
| `input_audio_buffer.clear` | — |
| `cancel` | — |

### 4.2 Server Events

| 事件类型 | 关键字段 |
|----------|----------|
| `session.created` | `session.id`, `session.model`, `session.modalities` |
| `session.updated` | 同上 |
| `conversation.created` | `conversation.id` |
| `conversation.item.created` | `item.id`, `item.type`, `item.status`, `item.content` |
| `input_audio_buffer.speech_started` | `audio_start_ms`, `item_id` |
| `input_audio_buffer.speech_stopped` | `audio_end_ms`, `item_id` |
| `response.created` | `response.id`, `response.status: "in_progress"` |
| `response.done` | `response.status`, `response.output[]`, `response.usage` |
| `response.text.delta` | `delta`（字符串） |
| `response.text.done` | `text`（完整） |
| `response.audio.delta` | `delta`（base64 音频） |
| `response.audio.done` | — |
| `response.audio_transcript.delta` | `delta`（文本转录增量） |
| `response.audio_transcript.done` | `transcript`（完整转录） |
| `response.function_call_arguments.delta` | `call_id`, `delta`（JSON 片段） |
| `response.function_call_arguments.done` | `call_id`, `arguments`（完整 JSON） |
| `rate_limits.updated` | `rate_limits[]` |
| `error` | `error.type`, `error.code`, `error.message` |

### 4.3 `session.update` 的 session 对象

```json
{
  "modalities": ["text", "audio"],
  "instructions": "You are a helpful assistant.",
  "voice": "alloy",                          // alloy | ash | ballad | coral | echo | sage | shimmer | verse
  "input_audio_format": "pcm16",
  "output_audio_format": "pcm16",
  "input_audio_transcription": { "enabled": true, "model": "whisper-1" },
  "turn_detection": {
    "type": "server_vad",
    "threshold": 0.5,
    "prefix_padding_ms": 300,
    "silence_duration_ms": 500
  },
  "tools": [],
  "tool_choice": "auto",
  "temperature": 0.8,
  "max_response_output_tokens": 4096
}
```

---

## 5. 认证与错误处理

### 5.1 认证

所有 API（除了 WebSocket 用查询参数或握手头）：
```http
Authorization: Bearer sk-xxxxxxxxxxxxxxxxxxxxxxxx
Content-Type: application/json
```

### 5.2 错误响应格式

```json
{
  "error": {
    "message": "人类可读的错误描述",
    "type": "invalid_request_error",      // 见下表
    "param": null,                          // 导致错误的字段
    "code": "model_not_found"               // 可选，机器可读的代码
  }
}
```

| HTTP | error.type | 说明 |
|------|-----------|------|
| 400 | `invalid_request_error` | 请求格式/内容问题 |
| 401 | `authentication_error` | API 密钥无效 |
| 403 | `permission_error` | 权限不足 |
| 404 | `not_found` | 资源不存在 |
| 409 | `conflict_error` | 资源冲突 |
| 429 | `rate_limit_error` | 速率限制（带 `Retry-After` 头） |
| 500 | `server_error` | 服务器错误 |
| 503 | `server_error` | 服务不可用 |

---

## 6. OpenAI 特有格式参考

### 工具调用格式：Responses vs Chat Completions

```typescript
// Chat Completions —— 外部标记
{
  "type": "function",
  "function": {                        // 外部 function 对象
    "name": "get_weather",
    "description": "...",
    "strict": true,
    "parameters": { ... }
  }
}

// Responses API —— 内部标记
{
  "type": "function",
  "name": "get_weather",               // name 在顶层
  "description": "...",
  "strict": true,
  "parameters": { ... }
}
```

### Item 类型常量

```typescript
type InputItemType = "message" | "file" | "function_call_output" | "computer_call_output";
type InputContentPartType = "input_text" | "input_image";
type OutputItemType = "message" | "reasoning" | "function_call" | "function_call_output"
                    | "web_search_call" | "file_search_call" | "computer_call" | "code_interpreter_call";
type OutputContentPartType = "output_text" | "refusal";
```

### SSE 事件常量

```typescript
type ResponseStreamEvent =
  | "response.created" | "response.in_progress" | "response.completed"
  | "response.failed" | "response.incomplete" | "response.cancelled"
  | "response.output_item.added" | "response.output_item.done"
  | "response.content_part.added" | "response.content_part.done"
  | "response.output_text.delta" | "response.output_text.done"
  | "response.function_call_arguments.delta" | "response.function_call_arguments.done"
  | "response.function_call_arguments.awaiting_confirmation"
  | "response.code_interpreter.delta" | "response.code_interpreter.done"
  | "response.file_search_call.delta" | "response.file_search_call.done"
  | "response.web_search.delta" | "response.web_search.done"
  | "response.rate_limited" | "response.refusal" | "error";
```
