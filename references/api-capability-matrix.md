# LLM Agent API 选型矩阵

> 调研基线：2026-07-21。模型、区域、配额、价格和预览状态变化很快；实现前应再次核对官方文档。

## 先选 API family

| 平台 | 新 Agent 推荐主线 | 何时使用其他接口 | 关键陷阱 |
|---|---|---|---|
| OpenAI | Responses API | 兼容旧项目时使用 Chat Completions；实时音频使用 Realtime | 不要把 Responses item/event 当成 Chat message delta |
| Anthropic | Messages API | 使用云平台托管时遵循 Bedrock 或 Vertex 的认证和模型标识 | tool use/result 是 content block；thinking 与工具循环需保留 block 顺序 |
| Gemini Developer API | `generateContent` / `streamGenerateContent` | 已有 OpenAI SDK 代码可考虑兼容层 | 原生 `Content/Part` 能力多于兼容层 |
| Azure OpenAI / Foundry | OpenAI `/openai/v1/responses`；项目型 Agent 使用 Foundry 项目 Responses | 旧能力才使用日期版 Azure API | `model` 通常是部署名，不是基础模型名 |
| Amazon Bedrock | `Converse` / `ConverseStream` | 特有参数、专用生成模型使用 `InvokeModel`；已有代码可用 Mantle 兼容接口 | `modelId` 可能是模型、profile、deployment 或 ARN |
| Vertex AI | Google Gen AI SDK + Gemini `generateContent` | MaaS 合作伙伴模型可能使用厂商接口；已有 OpenAI 代码可用兼容端点 | Developer API 与 Vertex 的认证、资源 ID 和配额不可混用 |
| OpenAI-compatible 托管商 | 明确记录其兼容 endpoint 和支持子集 | 需要平台专有能力时使用原生 API | “兼容”不等于工具、流式、错误和模型参数完全兼容 |

## 选型问题

按顺序回答：

1. 模型由原厂直供、云平台托管，还是第三方推理平台托管？
2. 是否必须使用 IAM、托管身份、VPC、私网、数据驻留或企业审计？
3. 是否需要服务端工具、托管 RAG、代码执行、浏览器或长任务 runtime？
4. 是否需要原生多模态或实时双向音频？
5. 是否已有 OpenAI SDK 代码，迁移成本是否高于原生能力收益？
6. 是否依赖 provider-specific reasoning、citation、grounding 或 safety metadata？

## 不应被统一抹平的差异

### 模型引用

```text
OpenAI/原厂：model ID
Azure：deployment name
Bedrock：model/profile/deployment ID 或 ARN
Vertex：publisher model ID 或 endpoint resource
```

建议使用：

```json
{
  "provider": "aws-bedrock",
  "api_family": "aws-converse",
  "model_ref": {
    "kind": "inference-profile",
    "value": "..."
  }
}
```

### 消息内容

统一 `parts[]`，至少支持：

```text
TextPart
ImagePart
AudioPart
VideoPart
DocumentPart
ToolCallPart
ToolResultPart
ProviderPart
```

### 工具调用

统一内部形式：

```json
{
  "id": "provider-call-id",
  "name": "get_weather",
  "arguments": {"city": "Seattle"},
  "provider_metadata": {}
}
```

映射时保留原始 ID、block/item 顺序和 provider metadata。

### 流式

不要只返回 `AsyncIterator<string>`。至少应支持：

```text
text delta
reasoning delta
tool call start
arguments delta
tool call complete
citation/grounding
safety update
usage update
response complete
provider event
error
```

### 结构化输出

各平台支持的 JSON Schema/OpenAPI 子集不同。通用 schema 应先经过 provider-specific 转换和检查；应用端仍需验证最终结果。

## Provider adapter 最小接口

```typescript
interface ModelProvider {
  generate(request: GenerateRequest): Promise<GenerateResponse>;
  stream(request: GenerateRequest): AsyncIterable<StreamEvent>;
  capabilities(modelRef: ModelRef): Promise<ModelCapabilities>;
}
```

可选接口：

```typescript
interface BatchProvider {}
interface EmbeddingProvider {}
interface FileProvider {}
interface VectorStoreProvider {}
interface RealtimeProvider {}
interface HostedAgentProvider {}
```

不要强迫不支持某能力的平台实现伪功能；用 capability detection 或显式报错。

## 认证抽象

认证不应只有 `apiKey: string`：

```text
StaticApiKey
BearerTokenProvider
AzureCredential
AwsCredentialProvider
GoogleAuthCredential
CustomSigner
```

短期令牌必须支持刷新；AWS 请求通常由 SDK 执行 SigV4 签名。

## 完整协议参考文档

四份协议文档包含请求/响应 Schema、流式事件、工具调用、认证、错误处理等完整细节，可直接指导兼容代码生成：

- [OpenAI API 协议完整参考](protocols/openai-protocol.md) — Responses API、Chat Completions、Codex、Realtime
- [Anthropic API 协议完整参考](protocols/anthropic-protocol.md) — Messages API、Batches、Agent SDK、MCP
- [Gemini API 协议完整参考](protocols/gemini-protocol.md) — Interactions API、GenerateContent、Live API
- [xAI Grok API 协议完整参考](protocols/grok-protocol.md) — Responses/Chat Completions、Agent Tools、gRPC、Voice

## 当前主流 API 协议全景

截至 2026 年中，各厂商的 API 接口正在从"纯聊天补全"演进为统一 Agent/Responses/Interactions 范式。以下按厂商列出当前推荐的主线接口、兼容接口和特殊协议。

### OpenAI

| 接口 | 端点 | 状态 | 适用场景 |
|------|------|------|----------|
| **Responses API** | `POST /v1/responses` | **推荐主线** | 所有新项目；内置工具（web search、file search、code interpreter、computer use、MCP）；支持 stateful context、reasoning、结构化输出 |
| Chat Completions API | `POST /v1/chat/completions` | 稳定（将被取代） | 现有项目兼容；简单聊天补全 |
| Realtime API | `POST /v1/realtime` | 稳定 | 实时双向音频、WebSocket 流式对话 |
| Batch API | `POST /v1/batch` | 稳定 | 异步批量处理，50% 折扣 |
| Assistants API | `/v1/assistants` | 稳定（不推荐新项目） | 已有 assistant+thread 项目；新项目使用 Responses + Conversations |
| Completions API | `POST /v1/completions` | **已弃用** | 只用于遗留代码；最后更新于 2023-07 |
| **Codex** | Responses API 专用模型 | **稳定 GA** | 自主编程 Agent，使用 `gpt-5.3-codex` / `gpt-5.2-codex` 等模型；通过 Codex SDK、CLI 或 MCP Server 集成 |

**关键转变：** Responses API 使用 `Item` 数组（`message`、`reasoning`、`function_call`、`function_call_output`）取代 Chat Completions 的 `choices[].message`。支持 `previous_response_id` 链式状态，无需手动管理 transcript。Codex 模型仅在 Responses API 可用。

### Anthropic / Claude

| 接口 | 端点 | 状态 | 适用场景 |
|------|------|------|----------|
| **Messages API** | `POST /v1/messages` | **推荐主线** | 所有 Claude 项目；tool use、extended thinking、image/PDF 理解 |
| Message Batches | `POST /v1/messages/batches` | 稳定 | 异步批量请求，50% 折扣 |
| **Claude Agent SDK** | SDK 库（Python/TS） | **稳定** | 完整 Agentic Runtime；包含文件 R/W、命令执行、代码编辑、会话持久化、权限系统、subagent、MCP 集成；是 Claude Code 的引擎 |
| Completions API | `POST /v1/complete` | 遗留 | 只用于旧版文本补全 |
| **MCP**（Model Context Protocol） | 独立协议 | **开放标准** | 连接模型到外部工具的开放协议；支持本地和远程 MCP Server |

**关键转变：** Messages API 的 `content` 是 content block 数组（`text`、`tool_use`、`tool_result`、`thinking`、`source`）。Claude Agent SDK 不是一个简单的 API 包装，而是一个完整的 agent runtime：包含 subprocess 模型、tool 执行引擎、会话层、权限系统、hook 架构、多 Agent 协调协议和 memory 栈。

### Google / Gemini

| 接口 | 端点 | 状态 | 适用场景 |
|------|------|------|----------|
| **Interactions API** | `POST /v1beta/interactions` | **推荐主线**（实验性） | 所有 Gemini 模型；统一端点、server-side state、background 执行、工具组合、多模态生成 |
| GenerateContent | `POST /v1beta/models/{model}:generateContent` | 稳定 | 简单单轮生成 |
| Live API | WebSocket 实时 | 稳定 | 实时双向语音/视频对话 |
| Batch API | `POST /v1beta/batch` | 稳定 | 异步批量处理 |
| Context Cache | `POST /v1beta/cachedContents` | 稳定 | 缓存频繁使用的前缀 token 以节省成本 |

**关键转变：** Interactions API 是 Google 的最新统一推理端点，支持 `model` 或 `agent` 两个入口。使用 `agent` 时可调用预构建智能体（如 `deep-research-pro`）。支持 `previous_interaction_id`、`background` 异步执行和 `webhook_config`。

### xAI / Grok

| 接口 | 端点 | 状态 | 适用场景 |
|------|------|------|----------|
| **Chat Completions** | `POST /v1/chat/completions` | **推荐主线** | OpenAI 兼容接口；所有 Grok 模型（grok-4.5、grok-4.1-fast、grok-4.20 等） |
| **Responses API** | `POST /v1/responses` | **推荐主线** | OpenAI Responses 兼容接口；支持 `previous_response_id`、reasoning、tokens details、cost metrics |
| **Agent Tools API** | 内置 server-side 工具 | **稳定** | 在 xAI 基础设施上运行 web search、X search、code execution（sandbox）、MCP 工具；无需要管理 API key 或沙箱 |
| gRPC API | `api.x.ai`（Protobuf） | 稳定 | 高性能场景；Python SDK 原生使用 gRPC；支持 chat、image、video、batch、stored completion |
| Voice API | WebSocket | 稳定 | 实时语音对话 |
| Context Compaction | `POST /v1/responses/compact` | 稳定 | 将长对话压缩为加密紧凑块，继续后续对话 |

**关键转变：** xAI 同时支持和扩展了 OpenAI 的 Chat Completions 和 Responses API 协议，提供双端点兼容。gRPC 是其独特的性能通道。Agent Tools API 的 server-side 工具（web search、X search、code execution）全部运行在 xAI 自己的基础设施上。

### 接口趋势总结

```text
2023        2024            2025-2026
Completions → Chat Completions → Responses / Interactions
纯文本补全     多消息，工具调用     统一 Agent 接口，内置工具，
                                  stateful context，Agent loop
```

- OpenAI 已明确 Responses API 是未来，Chat Completions 将逐步退出。
- Anthropic 以 Messages API 为基础，通过 MCP 和 Agent SDK 向上构建 Agent 能力。
- Google 通过 Interactions API 把模型和 agent 统一到一个端点。
- xAI 选择兼容 OpenAI 协议 + 自研高性能 gRPC + server-side Agent Tools 的混合策略。

## 时效风险

以下信息每次实现都应重新核对：

- 推荐接口是否变化；
- SDK 包名和主要版本；
- 模型与区域可用性；
- structured output 和 tool calling 支持矩阵；
- preview/beta 请求头；
- 配额、限流和价格；
- 托管 Agent 产品的弃用与迁移时间表。
