# Google Gemini API 协议完整参考

> 基线：2026-07-21。本文包含 Interactions API、GenerateContent API、Live API 的完整细节。实现前请核对 ai.google.dev 最新变更。

---

## 目录

1. [Interactions API（推荐主线）](#1-interactions-api推荐主线)
2. [GenerateContent API](#2-generatecontent-api)
3. [Live API（WebSocket 实时）](#3-live-apiwebsocket-实时)
4. [Content 和 Part 完整定义](#4-content-和-part-完整定义)
5. [Tool 定义格式](#5-tool-定义格式)
6. [认证与错误处理](#6-认证与错误处理)
7. [Gemini 特有格式参考](#7-gemini-特有格式参考)

---

## 1. Interactions API（推荐主线）

**端点**：`POST https://generativelanguage.googleapis.com/v1beta/interactions`
**流式**：`POST https://generativelanguage.googleapis.com/v1beta/interactions?alt=sse`

### 1.1 请求完整字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | `string` | 见说明 | 模型 ID，如 `gemini-3.5-flash`。与 `agent` 二选一必填 |
| `agent` | `string` | 见说明 | 代理 ID，如 `deep-research-preview-04-2026`。与 `model` 二选一必填 |
| `input` | `string \| Step[]` | **是** | 简化输入用字符串，完整输入用 Step 数组 |
| `system_instruction` | `string` | 否 | 系统指令 |
| `tools` | `Tool[]` | 否 | 工具声明 |
| `generation_config` | `GenerationConfig` | 否 | 生成参数 |
| `response_format` | `ResponseFormat` | 否 | 响应格式约束 |
| `response_mime_type` | `string` | 否 | MIME 类型，与 `response_format` 配合 |
| `stream` | `boolean` | 否 | 是否流式 |
| `store` | `boolean` | 否 | 默认 `true` |
| `background` | `boolean` | 否 | 后台异步执行 |
| `previous_interaction_id` | `string` | 否 | 上一轮 interaction ID |
| `response_modalities` | `string[]` | 否 | `["TEXT"]` \| `["IMAGE"]` \| `["AUDIO"]` |
| `service_tier` | `string` | 否 | `"flex"` \| `"standard"` \| `"priority"` |
| `webhook_config` | `{ uris: string[], user_metadata?: object }` | 否 | 后台任务完成通知 |

#### `input` 格式

```json
// 简化输入（字符串）
{ "input": "What is the capital of France?" }

// 完整输入（Step 数组）
{
  "input": [
    { "type": "user_input", "content": [
        { "type": "text", "text": "Tell me about" },
        { "type": "image", "uri": "https://...", "mime_type": "image/jpeg" }
    ]},
    { "type": "model_output", "content": [{ "type": "text", "text": "Previous model response" }] }
  ]
}
```

Step 的 `type` 枚举：

| type 值 | 说明 |
|---------|------|
| `"user_input"` | 用户输入 |
| `"thought"` | 模型思考过程 |
| `"function_call"` | 模型发出的函数调用 |
| `"function_result"` | 函数执行结果 |
| `"model_output"` | 模型文本输出 |
| `"tool_call"` | 服务端工具调用 |
| `"tool_response"` | 服务端工具响应 |
| `"code_execution"` | 代码执行 |
| `"image"` | 图片生成 |
| `"audio"` | 音频生成 |

### 1.2 响应 Schema

```json
{
  "id": "v1_ChdPU0F4YWFtNk...",
  "model": "gemini-3.5-flash",
  "object": "interaction",
  "status": "COMPLETED",
  "steps": [
    {
      "type": "model_output",
      "id": "step_001",
      "content": [{ "type": "text", "text": "Paris is the capital of France." }]
    }
  ],
  "output_text": "Paris is the capital of France.",
  "usage": {
    "prompt_token_count": 10,
    "response_token_count": 8,
    "total_token_count": 18,
    "thoughts_token_count": 0
  },
  "create_time": "2025-11-26T12:22:47Z",
  "update_time": "2025-11-26T12:22:47Z"
}
```

`status` 枚举：`COMPLETED` | `RUNNING` | `FAILED`

### 1.3 流式 SSE 事件

```text
data: {"event_type": "step.delta", "delta": {"type": "text", "text": "Paris"}}
data: {"event_type": "step.complete", "step": { "type": "model_output", ... }}
data: {"event_type": "interaction.complete", "interaction": { ... }}
```

| event_type | 说明 |
|-----------|------|
| `"step.delta"` | 增量内容块 |
| `"step.complete"` | 单个步骤完成 |
| `"interaction.complete"` | 整个 Interaction 完成 |

---

## 2. GenerateContent API

**端点**：`POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
**流式**：`POST https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent`

### 2.1 请求

```json
{
  "system_instruction": { "parts": [{"text": "You are a helpful assistant."}] },
  "contents": [
    { "role": "user", "parts": [{"text": "Hello"}] }
  ],
  "tools": [
    { "function_declarations": [{ "name": "get_weather", "description": "...", "parameters": {...} }] },
    { "google_search": {} },
    { "code_execution": {} }
  ],
  "tool_config": {
    "function_calling_config": { "mode": "AUTO", "allowed_function_names": ["get_weather"] }
  },
  "safety_settings": [
    { "category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH" }
  ],
  "generation_config": {
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "stop_sequences": ["\n"],
    "response_mime_type": "application/json"
  }
}
```

### 2.2 响应

```json
{
  "candidates": [{
    "content": { "parts": [{"text": "Hello! How can I help?"}], "role": "model" },
    "finish_reason": "STOP",
    "safety_ratings": [
      { "category": "HARM_CATEGORY_HARASSMENT", "probability": "NEGLIGIBLE" }
    ]
  }],
  "usage_metadata": {
    "prompt_token_count": 5,
    "candidates_token_count": 10,
    "total_token_count": 15
  }
}
```

`finish_reason` 枚举：`STOP` | `MAX_TOKENS` | `SAFETY` | `RECITATION` | `OTHER`

---

## 3. Live API（WebSocket 实时）

**端点**：`wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent`

**认证**：`?key=YOUR_API_KEY` 或 `Authorization: Bearer ACCESS_TOKEN`

### 3.1 客户端消息格式

每条消息必须恰好包含一个顶层字段：

```json
{
  // 其中之一：
  "setup": BidiGenerateContentSetup,
  "clientContent": BidiGenerateContentClientContent,
  "realtimeInput": BidiGenerateContentRealtimeInput,
  "toolResponse": BidiGenerateContentToolResponse
}
```

#### `setup`（第一条消息，必填）

```json
{
  "model": "models/gemini-3.5-flash",
  "generationConfig": {
    "candidateCount": 1,
    "maxOutputTokens": 8192,
    "temperature": 1.0,
    "topP": 0.95,
    "topK": 40,
    "responseModalities": ["TEXT"],
    "speechConfig": {},
    "mediaResolution": {}
  },
  "systemInstruction": { "parts": [{"text": "You are..."}] },
  "tools": [Tool, ...],
  "realtimeInputConfig": {
    "automaticActivityDetection": {},
    "activityHandling": "START_OF_ACTIVITY_INTERRUPTS"
  },
  "inputAudioTranscription": {},
  "outputAudioTranscription": {},
  "sessionResumption": { "handle": "..." },
  "contextWindowCompression": { "slidingWindow": { "targetTokens": 32000 }, "triggerTokens": 64000 }
}
```

**不支持**（setup 中无效）：`responseLogprobs`、`responseMimeType`、`logprobs`、`responseSchema`、`stopSequence`

#### `clientContent`

```json
{
  "turns": [{ "role": "user", "parts": [{"text": "Hello"}] }],
  "turnComplete": true
}
```

#### `realtimeInput`

```json
{
  "audio": { "mimeType": "audio/pcm;rate=16000", "data": "base64..." },
  "text": "string",
  "activityStart": {},
  "activityEnd": {}
}
```

#### `toolResponse`

```json
{
  "functionResponses": [{ "id": "call_xxx", "name": "get_weather", "response": {"temp": 22} }]
}
```

### 3.2 服务端消息

```json
{
  // 其中之一：
  "setupComplete": {},
  "serverContent": BidiGenerateContentServerContent,
  "toolCall": { "functionCalls": [FunctionCall, ...] },
  "toolCallCancellation": { "ids": ["call_xxx"] },
  "goAway": { "timeLeft": "30s" },
  "sessionResumptionUpdate": { "newHandle": "...", "resumable": true },
  "usageMetadata": { UsageMetadata }
}
```

#### `serverContent`

```json
{
  "modelTurn": { "parts": [{"text": "Hello"}], "role": "model" },
  "groundingMetadata": {},
  "inputTranscription": { "text": "..." },
  "outputTranscription": { "text": "..." },
  "generationComplete": true,
  "turnComplete": true,
  "interrupted": false
}
```

---

## 4. Content 和 Part 完整定义

### Content

```json
{
  "parts": [Part, ...],
  "role": "user" | "model"
}
```

### Part（联合类型，一次只能填充一种数据字段）

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | `string` | 纯文本 |
| `inlineData` | `Blob` | 内嵌媒体（base64） |
| `functionCall` | `FunctionCall` | 模型发出的函数调用 |
| `functionResponse` | `FunctionResponse` | 函数执行结果 |
| `fileData` | `FileData` | 文件 URI 引用 |
| `executableCode` | `ExecutableCode` | 生成的代码 |
| `codeExecutionResult` | `CodeExecutionResult` | 代码执行结果 |
| `toolCall` | `ToolCall` | 服务端工具调用 |
| `toolResponse` | `ToolResponse` | 服务端工具响应 |
| `thought` | `boolean` | 是否是思考部分 |
| `thoughtSignature` | `string` (base64) | 思维签名 |
| `partMetadata` | `object` | 自定义元数据 |
| `videoMetadata` | `VideoMetadata` | 视频元数据 |

#### Blob

```json
{
  "mimeType": "image/jpeg",     // 图片/音频/视频/文档 MIME
  "data": "base64-encoded..."
}
```

#### FunctionCall

```json
{
  "id": "call_abc123",           // 唯一调用 ID
  "name": "get_weather",
  "args": { "location": "Paris" }
}
```

#### FunctionResponse

```json
{
  "id": "call_abc123",           // 对应 FunctionCall.id
  "name": "get_weather",
  "response": { "response": { "temperature": 22 } }   // 必须包在 response 键中
}
```

#### FileData

```json
{
  "mimeType": "image/jpeg",
  "fileUri": "https://generativelanguage.googleapis.com/v1beta/files/..."
}
```

#### ExecutableCode

```json
{
  "language": "PYTHON",    // 仅 PYTHON
  "code": "print('hello')"
}
```

#### CodeExecutionResult

```json
{
  "outcome": "OUTCOME_OK",    // OUTCOME_OK | OUTCOME_FAILED | OUTCOME_DEADLINE_EXCEEDED
  "output": "hello\n"
}
```

---

## 5. Tool 定义格式

### Tool 基本结构

```json
{
  "function_declarations": [FunctionDeclaration, ...],
  "google_search": {},
  "code_execution": {},
  "google_maps": {},
  "url_context": {},
  "file_search": {},
  "computer_use": { "environment": "WEB_BROWSER" },
  "google_search_retrieval": {
    "dynamic_retrieval_config": { "mode": "MODE_DYNAMIC", "dynamic_threshold": 0.5 }
  }
}
```

### FunctionDeclaration

```json
{
  "name": "get_weather",
  "description": "Get weather for a location",
  "parameters": {
    "type": "object",
    "properties": { "location": { "type": "string", "description": "City name" } },
    "required": ["location"]
  },
  "response": {                      // 可选，结构化输出 schema
    "type": "object",
    "properties": { ... }
  }
}
```

SDK 中使用略有不同的格式：

```json
{
  "type": "function",
  "name": "get_weather",
  "description": "...",
  "parameters": { "type": "object", "properties": {...}, "required": [...] }
}
```

### Schema 支持

- 类型：`string` / `number` / `integer` / `boolean` / `array` / `object`
- 格式：`int32` / `float` / `double` / `enum`
- 高级：`anyOf` / `oneOf`、`$ref` / `$defs`、`minItems` / `maxItems`

### ToolConfig（GenerateContent 中控制函数调用）

```json
{
  "function_calling_config": {
    "mode": "AUTO",        // AUTO | ANY | NONE
    "allowed_function_names": ["func1", "func2"]
  }
}
```

---

## 6. 认证与错误处理

### 6.1 认证

```http
# API Key（开发者 API）
x-goog-api-key: AIzaSy...

# OAuth 2.0（Vertex AI 场景）
Authorization: Bearer ya29...
```

### 6.2 错误格式

Gemini API 使用标准 Google JSON 错误格式：

```json
{
  "error": {
    "code": 400,
    "message": "Invalid request",
    "status": "INVALID_ARGUMENT"
  }
}
```

| HTTP | 状态 | 说明 |
|------|------|------|
| 400 | `INVALID_ARGUMENT` | 请求参数错误 |
| 401 | `UNAUTHENTICATED` | API 密钥无效 |
| 403 | `PERMISSION_DENIED` | 权限不足 |
| 404 | `NOT_FOUND` | 资源不存在 |
| 429 | `RESOURCE_EXHAUSTED` | 配额/速率限制 |
| 500 | `INTERNAL` | 服务器错误 |
| 503 | `UNAVAILABLE` | 服务暂不可用 |

---

## 7. Gemini 特有格式参考

### GenerationConfig 完整字段

```json
{
  "stop_sequences": ["\n"],
  "response_mime_type": "text/plain",      // text/plain | application/json | text/x.enum
  "response_schema": { Schema },
  "candidate_count": 1,
  "max_output_tokens": 8192,
  "temperature": 1.0,                       // 0.0–2.0
  "top_p": 0.95,
  "top_k": 40,
  "seed": null,
  "presence_penalty": 0.0,
  "frequency_penalty": 0.0,
  "thinking_config": {
    "include_thoughts": true,
    "thinking_budget": 1024,
    "thinking_level": "MEDIUM"              // UNSPECIFIED | MINIMAL | LOW | MEDIUM | HIGH
  },
  "speech_config": { "voice_config": { "prebuilt_voice_config": { "voice_name": "..." } } },
  "image_config": { "aspect_ratio": "1:1", "image_size": "1K" },
  "media_resolution": "MEDIA_RESOLUTION_MEDIUM",
  "response_format": {
    "text": { "mime_type": "APPLICATION_JSON", "schema": {} },
    "audio": { "mime_type": "AUDIO_MP3", "delivery": "INLINE", "sample_rate": 24000 },
    "image": { "mime_type": "IMAGE_JPEG", "delivery": "INLINE", "aspect_ratio": "1:1" }
  }
}
```

### 枚举常量

```typescript
type ServiceTier = "flex" | "standard" | "priority";
type ThinkingLevel = "UNSPECIFIED" | "MINIMAL" | "LOW" | "MEDIUM" | "HIGH";
type HarmCategory = "HARM_CATEGORY_HARASSMENT" | "HARM_CATEGORY_HATE_SPEECH" | "HARM_CATEGORY_SEXUALLY_EXPLICIT" | "HARM_CATEGORY_DANGEROUS_CONTENT";
type HarmBlockThreshold = "BLOCK_ONLY_HIGH" | "BLOCK_MEDIUM_AND_ABOVE" | "BLOCK_LOW_AND_ABOVE" | "BLOCK_NONE";
type FinishReason = "STOP" | "MAX_TOKENS" | "SAFETY" | "RECITATION" | "OTHER";
type ResponseModality = "TEXT" | "IMAGE" | "AUDIO";
type LiveClientEvent = "setup" | "clientContent" | "realtimeInput" | "toolResponse";
type LiveServerEvent = "setupComplete" | "serverContent" | "toolCall" | "toolCallCancellation" | "goAway" | "sessionResumptionUpdate";
```

### 支持的数据类型 MIME

| 类型 | 支持 MIME |
|------|-----------|
| 图片 | `image/png`, `image/jpeg`, `image/webp`, `image/heic`, `image/gif`, `image/avif` |
| 音频 | `audio/wav`, `audio/mp3`, `audio/mpeg`, `audio/ogg`, `audio/aac` |
| 视频 | `video/mp4`, `video/mov`, `video/webm` |
| 文档 | `application/pdf`, `text/csv`, `text/plain`, `application/json` |
