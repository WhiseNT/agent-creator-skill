# Anthropic / Claude API 协议完整参考

> 基线：2026-07-21。本文包含 Messages API、Message Batches、Claude Agent SDK、MCP 协议的完整细节。实现前请核对 platform.claude.com/docs 最新变更。

---

## 目录

1. [Messages API](#1-messages-api)
2. [Message Batches API](#2-message-batches-api)
3. [Claude Agent SDK](#3-claude-agent-sdk)
4. [MCP 协议（Model Context Protocol）](#4-mcp-协议model-context-protocol)
5. [认证与错误处理](#5-认证与错误处理)
6. [Anthropic 特有格式参考](#6-anthropic-特有格式参考)

---

## 1. Messages API

**端点**：`POST https://api.anthropic.com/v1/messages`
**Token 计数**：`POST https://api.anthropic.com/v1/messages/count_tokens`

### 1.1 请求完整字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `model` | `string` | **是** | 模型 ID，如 `claude-opus-4-8`、`claude-sonnet-5` |
| `max_tokens` | `integer` | **是** | 最大输出 token 数（>= 1） |
| `messages` | `Message[]` | **是** | 对话消息数组 |
| `system` | `string \| SystemBlock[]` | 否 | 系统提示词 |
| `tools` | `ToolDefinition[]` | 否 | 工具定义 |
| `tool_choice` | `ToolChoice` | 否 | 工具选择策略 |
| `metadata` | `{ user_id?: string }` | 否 | 用户标识 |
| `stop_sequences` | `string[]` | 否 | 最多可达模型上限的停止序列 |
| `temperature` | `number` | 否 | Opus 4.7+ 不支持 |
| `top_p` | `number` | 否 | Opus 4.7+ 不支持 |
| `top_k` | `number` | 否 | Opus 4.7+ 不支持 |
| `stream` | `boolean` | 否 | 默认 `false` |
| `thinking` | `ThinkingConfig` | 否 | 扩展思维 |
| `output_config` | `OutputConfig` | 否 | 结构化输出 |
| `cache_control` | `CacheControl` | 否 | 上下文缓存控制 |
| `betas` | `string[]` | 否 | 启用的 beta 功能列表 |

#### `messages[]` 格式

```json
{
  "role": "user",          // "user" | "assistant"
  "content": "Hello"       // 字符串，等价于 [{"type": "text", "text": "Hello"}]
}
// 或
{
  "role": "user",
  "content": [
    { "type": "text", "text": "Describe this image" },
    { "type": "image", "source": { "type": "base64", "media_type": "image/jpeg", "data": "..." } },
    { "type": "document", "source": { "type": "base64", "media_type": "application/pdf", "data": "..." } }
  ]
}
```

#### Content Block 完整类型

**`text`**（user/assistant）：
```json
{ "type": "text", "text": "Hello world" }
```

**`image`**（user only）：
```json
{
  "type": "image",
  "source": {
    "type": "base64",
    "media_type": "image/jpeg",     // image/jpeg | image/png | image/gif | image/webp
    "data": "base64EncodedData"
  }
}
```

**`tool_use`**（assistant only）：
```json
{
  "type": "tool_use",
  "id": "toolu_01ABC...",
  "name": "get_weather",
  "input": { "location": "San Francisco" },
  "caller": {                      // 可选，程序化工具调用时出现
    "type": "direct" | "code_execution_20260120",
    "tool_id": "srvtoolu_..."
  }
}
```

**`tool_result`**（user only）：
```json
{
  "type": "tool_result",
  "tool_use_id": "toolu_01ABC...",
  "content": "15 degrees",                  // 字符串或 ContentBlock[]
  "is_error": false
}
```

> **规则**：`tool_result` 必须在 user 消息 content 数组的**最前面**；文本放在所有 `tool_result` 之后。

**`thinking`**（assistant only）：
```json
{
  "type": "thinking",
  "thinking": "Let me analyze step by step...",
  "signature": "WaUjzkypQ2mUEVM36O2TxuC06KN8xyfbJ..."
}
```

#### `system` 参数

```json
// 字符串
"system": "You are a helpful assistant."

// 数组（支持 cache_control）
"system": [
  { "type": "text", "text": "You are a helpful assistant.", "cache_control": { "type": "ephemeral" } }
]
```

#### `tools[]` 定义

```json
{
  "name": "get_weather",                                    // 必填，^[a-zA-Z0-9_-]{1,64}$
  "description": "Get current weather for a location.",     // 强烈推荐
  "input_schema": {                                        // 必填，JSON Schema
    "type": "object",
    "properties": { "location": { "type": "string", "description": "City" } },
    "required": ["location"]
  },
  "input_examples": [{ "location": "San Francisco" }],      // 可选
  "cache_control": { "type": "ephemeral" },                  // 可选
  "strict": true,                                            // 可选
  "allowed_callers": ["direct"]                               // 可选
}
```

**Anthropic 预置 Server Tools**（通过 tools 数组中的 `type` 字段引用）：

| 工具 | type 值 | 状态 |
|------|---------|------|
| 网页搜索 | `web_search_20260318` | GA |
| 网页抓取 | `web_fetch_20260318` | GA |
| 代码执行 | `code_execution_20260521` | GA |
| 工具搜索 | `tool_search_tool_regex_20251119` | GA |
| MCP 连接 | `"type": "mcp_toolset"` + `mcp_servers` 字段 | Beta |

#### `tool_choice` 策略

```json
// auto —— Claude 自主决定
{ "type": "auto", "disable_parallel_tool_use": false }

// any —— 必须调用某个工具
{ "type": "any", "disable_parallel_tool_use": false }

// tool —— 强制调用指定工具
{ "type": "tool", "name": "get_weather", "disable_parallel_tool_use": false }
```

#### `thinking` 扩展思维配置

```json
// 手动模式
{ "type": "enabled", "budget_tokens": 10000, "display": "summarized" }

// 自适应模式
{ "type": "adaptive" }
```

`display`：`"summarized"` | `"omitted"` — 控制响应中是否包含 thinking block 的完整文本。

#### `output_config` 结构化输出

```json
{
  "format": {
    "type": "json_schema",
    "schema": {
      "type": "object",
      "properties": { "name": { "type": "string" } },
      "required": ["name"],
      "additionalProperties": false
    }
  }
}
```

约束：根 `type` 必须为 `"object"`；必须设 `additionalProperties: false`；不支持 `$ref`、`definitions`、`if/then/else`、`not`。

### 1.2 响应完整 Schema

```json
{
  "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
  "type": "message",
  "role": "assistant",
  "content": [
    { "type": "thinking", "thinking": "...", "signature": "..." },
    { "type": "text", "text": "The answer is..." },
    { "type": "tool_use", "id": "toolu_...", "name": "get_weather", "input": {"location": "SF"} }
  ],
  "model": "claude-opus-4-8",
  "stop_reason": "end_turn",     // end_turn | max_tokens | stop_sequence | tool_use | refusal | pause_turn
  "stop_sequence": null,
  "stop_details": null,            // refusal 时非 null: { type: "refusal", category: "...", explanation: "..." }
  "usage": {
    "input_tokens": 12,
    "output_tokens": 6,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0
  }
}
```

### 1.3 流式 SSE 事件

设置 `"stream": true` 后的事件流：

```
message_start
  → content_block_start (index 0)
    → content_block_delta (xN)
    → content_block_stop
  → content_block_start (index 1)
    → content_block_delta (xN)
    → content_block_stop
  → ...
message_delta
message_stop
```

| 事件 | data 结构 | 说明 |
|------|-----------|------|
| `message_start` | `{ type: "message_start", message: Message }` | 初始 Message 对象，content 为空 |
| `content_block_start` | `{ type: "content_block_start", index, content_block }` | 内容块开始 |
| `content_block_delta` | `{ type: "content_block_delta", index, delta }` | 增量更新（见下方 3 种 delta） |
| `content_block_stop` | `{ type: "content_block_stop", index }` | 内容块结束 |
| `message_delta` | `{ type: "message_delta", delta: { stop_reason }, usage }` | 累计 usage |
| `message_stop` | `{ type: "message_stop" }` | 流结束 |
| `ping` | `{ type: "ping" }` | 保活 |
| `error` | `{ type: "error", error: { type, message } }` | 错误 |

#### 三种 delta 类型

```json
// text_delta
{ "type": "text_delta", "text": "Hello" }

// input_json_delta（工具参数增量）
{ "type": "input_json_delta", "partial_json": "{\"location\": \"San" }

// thinking_delta（思维增量）
{ "type": "thinking_delta", "thinking": "Let me analyze..." }

// signature_delta（签名增量）
{ "type": "signature_delta", "signature": "WaUjzky..." }
```

---

## 2. Message Batches API

**端点**：`POST https://api.anthropic.com/v1/messages/batches`

### 2.1 请求格式

```json
{
  "requests": [
    {
      "custom_id": "req-001",
      "params": {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 256,
        "messages": [{ "role": "user", "content": "Hello" }]
      }
    }
  ]
}
```

### 2.2 约束

| 限制项 | 值 |
|--------|-----|
| 最大请求数 | 100,000 |
| 最大总大小 | 256 MB |
| 处理时间 | 多数 < 1 小时 |
| 有效期 | 创建后 29 天 |
| 不支持参数 | `stream: true`、speed、`store`、`max_tokens: 0` |

### 2.3 批次状态

`processing` → `ended` | `canceled` | `expired`

### 2.4 结果格式（JSONL）

```json
{"custom_id":"req-001","result":{"type":"succeeded","message":{/* 完整 Message */}}}
{"custom_id":"req-002","result":{"type":"errored","error":{"type":"...","message":"..."}}}
```

---

## 3. Claude Agent SDK

### 3.1 架构

Claude Agent SDK 不是 API 端点，而是一个完整的 Agentic Runtime（Python/TypeScript），包含：

- **Agent Loop**：模型推理 → 工具执行 → 循环直到最终回答
- **Tool 执行引擎**：内置文件读写、命令执行、代码编辑
- **会话持久化层**：中断后恢复
- **权限系统**：`PermissionSet`，决定哪些操作允许
- **Hook 架构**：在工具调用前后注入自定义逻辑
- **多 Agent 协调协议**：subagent 委派与结果合并
- **Memory 栈**：跨会话持久记忆

### 3.2 核心使用模式

```python
from claude_agent_sdk import AgentSession

async with AgentSession.create() as session:
    # 完整 Agent 循环（Claude 自行调用工具）
    response = await session.query(
        prompt="Refactor main.py to use async/await",
        tools=["read", "write", "bash", "search"],
        permission_set=PermissionSet(allow_all=True)
    )

    # 流式结果
    async for msg in response:
        print(msg.text_delta, end="")
```

### 3.3 与 Messages API 的关系

Agent SDK 在底层使用 Messages API + `tool_use` content block + `thinking` content block。SDK 自动管理：
- 工具循环迭代
- 上下文窗口和压缩
- Prompt caching
- 流式事件解析
- 断线恢复

---

## 4. MCP 协议（Model Context Protocol）

### 4.1 架构

```
MCP Host (AI Application)
  └─ MCP Client
       └─ MCP Server (提供 tools / resources / prompts)
```

传输方式：Streamable HTTP 或 SSE。

### 4.2 底层协议：JSON-RPC 2.0

**初始化**（能力协商）：
```json
// Client → Server
{"jsonrpc": "2.0", "id": 1, "method": "initialize",
 "params": { "protocolVersion": "2025-06-18",
             "capabilities": {},
             "clientInfo": { "name": "my-client", "version": "1.0.0" } }}

// Server → Client
{"jsonrpc": "2.0", "id": 1,
 "result": { "protocolVersion": "2025-06-18",
             "capabilities": { "tools": { "listChanged": true } },
             "serverInfo": { "name": "my-server", "version": "1.0.0" } }}
```

**工具发现**：
```json
// Client → Server
{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}

// Server → Client
{"jsonrpc": "2.0", "id": 2,
 "result": { "tools": [{ "name": "get_weather", "description": "...",
                          "inputSchema": { "type": "object", "properties": {...}, "required": [...] } }] }}
```

**工具调用**：
```json
{"jsonrpc": "2.0", "id": 3, "method": "tools/call",
 "params": { "name": "get_weather", "arguments": { "location": "SF" } }}

// 响应
{"jsonrpc": "2.0", "id": 3,
 "result": { "content": [{ "type": "text", "text": "65°F" }], "isError": false }}
```

### 4.3 Anthropic Messages API 中的 MCP Connector

需 beta header：`anthropic-beta: mcp-client-2025-11-20`

```json
{
  "mcp_servers": [{
    "type": "url",
    "url": "https://example-server.mcp.io/sse",
    "name": "example-mcp",
    "authorization_token": "YOUR_TOKEN"
  }],
  "tools": [{
    "type": "mcp_toolset",
    "mcp_server_name": "example-mcp",
    "allowed_tools": ["tool1"],
    "denied_tools": ["tool2"]
  }]
}
```

---

## 5. 认证与错误处理

### 5.1 认证

```http
x-api-key: sk-ant-xxxxxxxxxxxxxxxx
anthropic-version: 2023-06-01
content-type: application/json
anthropic-beta: mcp-client-2025-11-20    # Beta 功能按需
```

### 5.2 错误格式

```json
{
  "type": "error",
  "error": { "type": "error_type_string", "message": "Human-readable description" }
}
```

| HTTP | error.type | 说明 |
|------|-----------|------|
| 400 | `invalid_request_error` | 请求格式问题 |
| 401 | `authentication_error` | API 密钥无效 |
| 402 | `billing_error` | 计费问题 |
| 403 | `permission_error` | 权限不足 |
| 404 | `not_found_error` | 资源不存在 |
| 409 | `conflict_error` | 资源冲突 |
| 413 | `request_too_large` | 请求过大 |
| 429 | `rate_limit_error` | 速率限制 |
| 500 | `api_error` | 服务器内部错误 |
| 504 | `timeout_error` | 超时 |
| 529 | `overloaded_error` | API 过载 |

### 5.3 Rate Limit 响应头

`retry-after`：重试前等待秒数。

---

## 6. Anthropic 特有格式参考

### 常用模型 ID

| 模型 | 标识符 | 上下文 | 备注 |
|------|--------|--------|------|
| Opus 4.8 | `claude-opus-4-8` | 1M | 不支持 temp/top_p/top_k |
| Opus 4.7 | `claude-opus-4-7` | 1M | 不支持 temp/top_p/top_k |
| Sonnet 5 | `claude-sonnet-5` | 1M | 当前最新 Sonnet |
| Sonnet 4.6 | `claude-sonnet-4-6` | 1M | |
| Sonnet 4.5 | `claude-sonnet-4-5` | 200K | |
| Haiku 4.5 | `claude-haiku-4-5` | 200K | |

### Content Block 类型常量

```typescript
type ContentBlock = TextBlock | ImageBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock | DocumentBlock;
type ContentBlockSource = { type: "base64" | "url" | "file"; media_type?: string; data?: string; url?: string; file_id?: string };
```

### `stop_reason` 枚举

```typescript
type StopReason = "end_turn" | "max_tokens" | "stop_sequence" | "tool_use" | "refusal" | "pause_turn" | "model_context_window_exceeded";
```

### usage 对象

```typescript
interface Usage {
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens?: number;
  cache_read_input_tokens?: number;
}
```

### SSE 事件类型常量

```typescript
type MessageStreamEvent =
  | "message_start" | "message_delta" | "message_stop"
  | "content_block_start" | "content_block_delta" | "content_block_stop"
  | "ping" | "error";
```

### 缓存控制

```json
// 5 分钟 TTL（默认）
{ "type": "ephemeral" }

// 1 小时 TTL（2x 价格）
{ "type": "ephemeral", "ttl": "1h" }

// 自动模式（仅顶层自动缓存可用）
{ "type": "ephemeral", "ttl": "auto" }
```
