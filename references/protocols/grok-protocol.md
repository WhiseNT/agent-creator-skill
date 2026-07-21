# xAI Grok API 协议完整参考

> 基线：2026-07-21。本文包含 Chat Completions API、Responses API、Agent Tools API、gRPC API、Voice/Image/Video API 的完整细节。实现前请核对 docs.x.ai 最新变更。

---

## 目录

1. [Chat Completions API](#1-chat-completions-api)
2. [Responses API（推荐主线）](#2-responses-api推荐主线)
3. [Agent Tools API](#3-agent-tools-api)
4. [gRPC API](#4-grpc-api)
5. [Voice API（WebSocket）](#5-voice-apiwebsocket)
6. [Image/Video API](#6-imagevideo-api)
7. [认证与错误处理](#7-认证与错误处理)
8. [Grok 特有格式参考](#8-grok-特有格式参考)

---

## 1. Chat Completions API

**端点**：`POST https://api.x.ai/v1/chat/completions`
**状态**：稳定，兼容 OpenAI Chat Completions 格式

### 1.1 请求完整字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | `string` | **是** | `grok-4.5`、`grok-4`、`grok-3.5-turbo` |
| `messages` | `Message[]` | **是** | 消息列表，role 顺序无限制 |
| `temperature` | `number` | 否，默认 `1.0` | 0–2 |
| `top_p` | `number` | 否，默认 `1.0` | 0–1 |
| `stream` | `boolean` | 否，默认 `false` | SSE 流式 |
| `stop` | `string \| string[]` | 否 | 最多 4 个，**不可与 reasoning 模型共用** |
| `max_tokens` | `integer` | 否 | 最大输出 token 数 |
| `presence_penalty` | `number` | 否，-2.0~2.0 | **不可与 reasoning 模型共用** |
| `frequency_penalty` | `number` | 否，-2.0~2.0 | **不可与 reasoning 模型共用** |
| `n` | `integer` | 否，默认 `1` | choice 数 |
| `response_format` | `object` | 否 | `{"type": "text"}` / `{"type": "json_object"}` / `{"type": "json_schema", "json_schema": {...}}` |
| `tools` | `Tool[]` | 否 | 最多 128 个 |
| `tool_choice` | `string\|object` | 否 | `"auto"` / `"required"` / `"none"` / `{"type":"function","function":{"name":"..."}}` |
| `parallel_tool_calls` | `boolean` | 否，默认 `true` |
| `user` | `string` | 否 | 终端用户标识 |
| `store` | `boolean` | 否，默认 `true` | 存储请求/响应到服务端 |
| `metadata` | `object` | 否 | 自定义元数据 |
| `service_tier` | `string` | 否 | `"default"` / `"priority"` |
| `include` | `string[]` | 否 | Grok 扩展：`["verbose_streaming"]`、`["reasoning.encrypted_content"]` |
| `logprobs` | `boolean` | 否 | grok-4.20+ 不支持，静默忽略 |
| `top_logprobs` | `integer` | 否 | 0~8，新模型不支持 |

### Grok 特有参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `reasoning_effort` | `"low"` \| `"medium"` \| `"high"` | 控制推理深度，仅 grok-4.5 支持。设为后不能与 `stop`、`presence_penalty`、`frequency_penalty` 共用 |

### 1.2 响应 Schema

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "grok-4.5",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello!",
        "tool_calls": [
          { "id": "call_xxx", "type": "function",
            "function": { "name": "get_weather", "arguments": "{\"location\":\"SF\"}" } }
        ] | null
      },
      "finish_reason": "stop",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 41,
    "completion_tokens": 1,
    "total_tokens": 42,
    "prompt_tokens_details": {
      "text_tokens": 41,
      "audio_tokens": 0,
      "image_tokens": 0,
      "cached_tokens": 0
    },
    "completion_tokens_details": {
      "reasoning_tokens": 0,
      "accepted_prediction_tokens": 0,
      "rejected_prediction_tokens": 0
    }
  },
  "system_fingerprint": "fp_xxxxxxxxxx"
}
```

**Grok 特有 usage 字段**：`prompt_tokens_details.text_tokens`、`prompt_tokens_details.cached_tokens`、`completion_tokens_details.reasoning_tokens`

### 1.3 Streaming Chunks

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":...,"model":"grok-4.5",
       "choices":[{"index":0,"delta":{"content":"Ah","role":"assistant"}}],
       "usage":{"prompt_tokens":41,"completion_tokens":1,...}}
data: [DONE]
```

Grok 特有：**每一个 chunk 都包含完整的 `usage` 字段**，而非仅在最后一个 chunk。

### 1.4 Function Calling 格式

完全兼容 OpenAI 格式。**`strict` 标志始终隐含为 true**——模型保证输出符合 schema。

```json
{
  "type": "function",
  "function": {
    "name": "get_temperature",
    "description": "Get current temperature",
    "parameters": {
      "type": "object",
      "properties": { "location": { "type": "string" } },
      "required": ["location"]
    }
  }
}
```

参数 schema 的根必须是 `"type": "object"` 或 `oneOf`/`anyOf`（所有分支都是 object）。

---

## 2. Responses API（推荐主线）

**端点**：`POST https://api.x.ai/v1/responses`
**状态**：推荐主线，支持 OpenAI Responses 兼容 + Grok 扩展

### 2.1 请求完整字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | `string` | **是** | 模型 ID |
| `input` | `string \| array` | **是** | 输入内容 |
| `instructions` | `string` | 否 | 系统指令 |
| `max_output_tokens` | `integer` | 否 | 输出 token 上限 |
| `temperature` | `number` | 否 | 0–2 |
| `top_p` | `number` | 否 | 0–1 |
| `store` | `boolean` | 否，默认 `true` | 存储到服务端 |
| `previous_response_id` | `string` | 否 | 继续对话 |
| `tools` | `array` | 否 | 工具（含内置工具和函数） |
| `tool_choice` | `string\|object` | 否 | `"auto"` / `"required"` / `"none"` / `{"type":"function","name":"..."}` |
| `parallel_tool_calls` | `boolean` | 否，默认 `true` |
| `include` | `string[]` | 否 | `["reasoning.encrypted_content"]` |
| `metadata` | `object` | 否 | 自定义元数据 |
| `truncation` | `string` | 否 | `"disabled"`（默认） |
| `top_logprobs` | `integer` | 否 | 0~8 |
| `service_tier` | `string` | 否 | `"default"` |
| `background` | `boolean` | 否 | 兼容字段 |
| `reasoning_effort` | `string` | 否 | `"low"` / `"medium"` / `"high"`（默认） |

**注意**：`frequency_penalty` 和 `presence_penalty` 在 Responses API 中不支持（兼容性接受但无效）。

### 2.2 响应 Schema

```json
{
  "id": "resp_xxx",
  "object": "response",
  "created_at": 1234567890,
  "completed_at": 1234567895,
  "model": "grok-4.5",
  "status": "completed",
  "output": [
    {
      "type": "message",
      "id": "msg_xxx",
      "role": "assistant",
      "status": "completed",
      "content": [{ "type": "output_text", "text": "Hello!", "annotations": [] }]
    }
  ],
  "usage": {
    "input_tokens": 41,
    "output_tokens": 100,
    "total_tokens": 141,
    "input_tokens_details": { "cached_tokens": 128 },
    "output_tokens_details": { "reasoning_tokens": 30 },
    "num_sources_used": 0,
    "num_server_side_tools_used": 0,
    "cost_in_usd_ticks": 37756000
  },
  "text": { "format": { "type": "text" } },
  "store": true,
  "service_tier": "default"
}
```

### 2.3 Grok 特有响应字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `usage.cost_in_usd_ticks` | `integer` | 每次请求的精确成本（1 tick = $0.00000001） |
| `usage.num_server_side_tools_used` | `integer` | 服务端工具使用次数 |
| `usage.input_tokens_details.cached_tokens` | `integer` | 缓存命中的输入 token 数 |
| `usage.output_tokens_details.reasoning_tokens` | `integer` | 推理 token 数 |
| `citations` | `array` | 搜索结果的引用来源 |
| `server_side_tool_usage` | `array` | 服务端工具使用记录 |
| `text.annotations` | `array` | 文本标注 |

### 2.4 Context Compaction

**端点**：`POST https://api.x.ai/v1/responses/compact`

将长对话压缩为加密紧凑块：

```json
// 请求
{ "model": "grok-4.5", "input": [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}] }

// 响应
{ "id": "cmp_<uuid>", "object": "response.compaction", "output": [{"type": "compaction", "content": {...}}] }
```

返回的 `output` 可直接作为下一个 `POST /v1/responses` 的 `input`。

### 2.5 其他 Responses 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `GET /v1/responses/{response_id}` | GET | 检索存储的 response |
| `DELETE /v1/responses/{response_id}` | DELETE | 删除存储的 response |
| `GET /v1/chat/deferred-completion/{request_id}` | GET | 轮询延迟完成结果（200 完成 / 202 处理中） |

---

## 3. Agent Tools API

### 3.1 Web Search

```json
// 工具定义
{ "type": "web_search",
  "allowed_domains": ["example.com"],        // 可选，最多 5 个
  "excluded_domains": ["bad.com"],           // 可选，与 allowed 互斥
  "enable_image_understanding": true,        // 可选
  "enable_image_search": true,               // 可选
  "location": { "country": "US", "city": "SF" }  // 可选
}
```

### 3.2 X Search

```json
{ "type": "x_search",
  "allowed_x_handles": ["@openai"],           // 可选，最多 20 个
  "excluded_x_handles": ["@spam"],            // 可选
  "from_date": "2025-01-01",                  // ISO 8601
  "to_date": "2025-12-31",
  "enable_image_understanding": true,
  "enable_video_understanding": true
}
```

### 3.3 Code Execution

```json
{ "type": "code_interpreter" }    // 或 SDK: code_execution()
```

在 xAI 沙箱 Python 环境中执行，预装 NumPy、Pandas、Matplotlib、SciPy 等。有执行时间和内存限制，无网络/文件系统访问。

### 3.4 工具组合规则

- 服务端工具（web_search / x_search / code_execution）在 xAI 服务器自动执行
- 自定义函数（function calling）暂停执行，返回给客户端处理
- 可以混合使用服务端工具和自定义函数
- 通过 `tool_choice` 控制选择行为
- 每个请求最多 128 个工具

---

## 4. gRPC API

**服务端点**：`api.x.ai`（TLS）
**认证**：`Authorization: Bearer <XAI_API_KEY>`（metadata header）
**Protobuf 定义**：`https://github.com/xai-org/xai-proto`

### 4.1 Chat Service

| RPC | 类型 | 说明 |
|-----|------|------|
| `GetCompletion` | Unary | 采样完整响应，阻塞直到完成 |
| `GetCompletionChunk` | Server Streaming | 采样并流式输出 token |
| `StartDeferredCompletion` | Unary | 启动后台采样，立即返回 request_id |
| `GetDeferredCompletion` | Unary | 用 request_id 轮询结果 |
| `GetStoredCompletion` | Unary | 用 response ID 检索存储的响应 |
| `DeleteStoredCompletion` | Unary | 删除存储的响应 |

### 4.2 Image / Video Service

| Service | RPC | 说明 |
|---------|-----|------|
| `Image` | `GenerateImage` | 基于文本提示生成图像 |
| `Video` | `GenerateVideo` | 异步生成视频，返回 request_id |
| `Video` | `ExtendVideo` | 扩展已有视频 |
| `Video` | `GetDeferredVideo` | 轮询视频生成结果 |

### 4.3 Other Services

| Service | 说明 |
|---------|------|
| `BatchMgmt` | 创建批次、添加请求、列出结果 |
| `Models` | 列出语言/图像/视频模型 |
| `Auth` | API key 信息校验 |
| `Tokenize` | 文本分词 |

---

## 5. Voice API（WebSocket）

### 5.1 Voice Agent（双向实时对话）

**端点**：`wss://api.x.ai/v1/realtime?model=grok-voice-latest`

**模型选项**：
- `grok-voice-latest` （当前 = `grok-voice-think-fast-1.0`）
- `grok-voice-think-fast-1.0`（旗舰语音模型）
- `grok-voice-fast-1.0`（旧版，已弃用）

**session.update 配置**：

```json
{
  "type": "session.update",
  "session": {
    "voice": "eve",
    "instructions": "You are a helpful assistant.",
    "reasoning": { "effort": "high" },
    "turn_detection": {
      "type": "server_vad",
      "threshold": 0.85,
      "silence_duration_ms": 500,
      "prefix_padding_ms": 333
    },
    "tools": [{ "type": "web_search" }],
    "audio": {
      "input": { "format": { "type": "audio/pcm", "rate": 24000 }, "transport": "json" },
      "output": { "format": { "type": "audio/pcm", "rate": 24000 }, "transport": "json" }
    },
    "resumption": { "enabled": false }
  }
}
```

**支持的音频格式**：`audio/pcm`（PCM16 LE，8000~48000 Hz）、`audio/pcmu`（µ-law，8000 Hz）、`audio/pcma`（A-law，8000 Hz）、`audio/opus`（24000 Hz）

**传输模式**：`"json"`（base64）、`"binary"`（原始字节）

**客户端事件**：`session.update`、`conversation.item.create`、`response.create`、`input_audio_buffer.append`、`input_audio_buffer.commit`、`input_audio_buffer.clear`

**服务端事件**：`session.updated`、`response.created`、`response.done`、`response.output_audio.delta`、`response.audio.delta`、`conversation.item.created`、`input_audio_buffer.speech_started/stopped`、`error`

### 5.2 TTS（Text-to-Speech）

**端点**：`POST https://api.x.ai/v1/tts`（Unary / Server-Streamed）
**WebSocket**：`wss://api.x.ai/v1/tts`（双向，无文本长度限制）

```json
{
  "text": "Hello world",              // 最多 15,000 字符（Unary）
  "voice_id": "eve",                   // 默认
  "language": "en-US",                 // BCP-47 或 "auto"
  "output_format": { "codec": "mp3", "sample_rate": 24000, "bit_rate": 128000 },
  "speed": 1.0,                        // 0.7~1.5
  "with_timestamps": false
}
```

### 5.3 STT（Speech-to-Text）

**Batch 端点**：`POST https://api.x.ai/v1/stt`（multipart/form-data，最大 500 MB）
**WebSocket**：`wss://api.x.ai/v1/stt?sample_rate=16000&encoding=pcm`

服务端事件：`transcript.created`、`transcript.partial`（含 `is_final`、`speech_final`）、`transcript.done`

---

## 6. Image/Video API

### 6.1 Image Generation

**端点**：`POST https://api.x.ai/v1/images/generations`

```json
{
  "model": "grok-imagine-image-quality",
  "prompt": "A serene lake at sunrise",
  "n": 1,
  "aspect_ratio": "16:9",
  "resolution": "1k",            // "1k" | "2k"
  "image_format": "url"           // "url" | "base64"
}
```

### 6.2 Video Generation

**端点**：`POST https://api.x.ai/v1/videos/generations`（异步，返回 `request_id`）
**轮询**：`GET https://api.x.ai/v1/videos/{request_id}`

```json
{
  "model": "grok-imagine-video",
  "prompt": "A serene lake at sunrise with mist",
  "duration": 5,                  // 1~15 秒
  "aspect_ratio": "16:9",
  "resolution": "720p"            // "480p"(默认) | "720p" | "1080p"
}
```

状态：`pending` → `done` | `expired` | `failed`

---

## 7. 认证与错误处理

### 7.1 认证

```http
Authorization: Bearer xai-xxxxxxxxxxxxxxxxxxxxxxxx
```

所有 REST 和 gRPC API 均使用相同的 Bearer Token。API Keys 在 https://console.x.ai 管理。

### 7.2 错误格式

```json
{
  "error": {
    "message": "错误描述",
    "type": "invalid_request_error",
    "param": null,
    "code": null
  }
}
```

| HTTP | error.type | 说明 |
|------|-----------|------|
| 400 | `invalid_request_error` | 请求格式错误 |
| 401 | `authentication_error` | API 密钥无效 |
| 403 | `permission_error` | 权限不足 |
| 404 | `not_found_error` | 资源不存在 |
| 409 | `conflict_error` | 资源冲突 |
| 429 | `rate_limit_error` | 速率限制 |
| 500 | `server_error` | 服务器错误 |
| 503 | `service_unavailable` | 服务不可用 |

---

## 8. Grok 特有格式参考

### 常用模型 ID

| 模型 | 标识符 | 说明 |
|------|--------|------|
| Grok 4.5 | `grok-4.5` | 最新旗舰，支持 reasoning |
| Grok 4.1 Fast Reasoning | `grok-4-1-fast-reasoning` | 优先推理深度 |
| Grok 4.1 Fast Non-Reasoning | `grok-4-1-fast-non-reasoning` | 即时响应 |
| Grok 4 | `grok-4` | 前代旗舰 |
| Grok 4.20 | `grok-4-20-0309-reasoning` | 特定快照 |

### 与 OpenAI 兼容性差异

| 特性 | OpenAI | Grok |
|------|--------|------|
| `reasoning_effort` | `reasoning.effort` 对象 | 顶层 `string` 参数 |
| `include` | 无 | `["verbose_streaming"]` / `["reasoning.encrypted_content"]` |
| `usage.completion_tokens_details.reasoning_tokens` | 有 | 有（+ 更多细节字段） |
| `usage.prompt_tokens_details` | 有 | 有（`text_tokens`、`cached_tokens`、`audio_tokens`、`image_tokens`） |
| `store` 默认值 | `false`（旧账号） | `true`（始终） |
| `logprobs` / `top_logprobs` | 支持 | grok-4.20+ 不支持（静默忽略） |
| `stop` / `presence_penalty` / `frequency_penalty` | 支持 | 与 reasoning 模型冲突 |
| `cost_in_usd_ticks` | 无 | 有 |
| `server_side_tool_usage` | 无 | 有 |
| `citations` | 无 | 有 |
| gRPC 原生 | 无 | 有（xai-proto） |
| Agent Tools（server-side） | 部分有 | web_search + x_search + code_execution |
| 消息 role 顺序 | 必须按序 | 任意顺序 |

### 响应状态枚举

```typescript
type ResponseStatus = "completed" | "in_progress" | "incomplete" | "failed";
type FinishReason = "stop" | "length" | "content_filter" | "tool_calls";
```

### Tool 类型常量

```typescript
type GrokToolType = "function" | "web_search" | "x_search" | "code_interpreter";
type GrokServerSideToolUsage = "SERVER_SIDE_TOOL_WEB_SEARCH" | "SERVER_SIDE_TOOL_X_SEARCH"
                             | "SERVER_SIDE_TOOL_CODE_EXECUTION" | "SERVER_SIDE_TOOL_VIEW_IMAGE"
                             | "SERVER_SIDE_TOOL_IMAGE_SEARCH";
```
