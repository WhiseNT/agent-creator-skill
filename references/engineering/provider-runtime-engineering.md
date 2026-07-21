# Provider Runtime Engineering 细粒度工程设计
> 本文把 Provider Runtime 设计为独立于 Agent Kernel 的模型调用基础设施。
>
> 依据仅来自当前目录已有的参考架构、Agent API 通用模式、API 选型矩阵、Harness/Tool/State/Policy/Event/Evaluation 文档，以及五个参考项目的本地源码调研归纳；不把 README 当作规范，不新增网络调研结论。
## 目录
- [设计目标与非目标](#设计目标与非目标)；[术语与核心原则](#术语与核心原则)；[职责边界](#职责边界)
- [总体分层](#总体分层)；[模块与包布局](#模块与包布局)；[核心数据模型](#核心数据模型)
- [TypeScript 契约](#typescript-契约)；[Provider/Model/Deployment 分层](#providermodeldeployment-分层)；[Capability 分层](#capability-分层)
- [Transport 与 Adapter 分层](#transport-与-adapter-分层)；[Provider-neutral Contract](#provider-neutral-contract)；[Model Catalog](#model-catalog)
- [Credential 与 Tenant Routing](#credential-与-tenant-routing)；[请求编译总流程](#请求编译总流程)；[消息与多模态编译](#消息与多模态编译)
- [Tool Calling 编译](#tool-calling-编译)；[Structured Output 编译](#structured-output-编译)；[请求预算与上下文检查](#请求预算与上下文检查)
- [发送与 Transport 生命周期](#发送与-transport-生命周期)；[Stream Event 归一化](#stream-event-归一化)；[Tool Call 增量组装](#tool-call-增量组装)
- [响应归一化](#响应归一化)；[Finish Reason 与拒答](#finish-reason-与拒答)；[Usage、Cost 与计费归因](#usagecost-与计费归因)
- [Rate Limit 与 Retry](#rate-limit-与-retry)；[Fallback 与 Model Routing](#fallback-与-model-routing)；[Context Overflow](#context-overflow)
- [Health 与 Circuit Breaker](#health-与-circuit-breaker)；[Provider 差异隔离](#provider-差异隔离)；[OpenAI 适配边界](#openai-适配边界)
- [Anthropic 适配边界](#anthropic-适配边界)；[Gemini 适配边界](#gemini-适配边界)；[Bedrock 适配边界](#bedrock-适配边界)
- [Azure 适配边界](#azure-适配边界)；[Vertex 适配边界](#vertex-适配边界)；[Conformance 契约测试](#conformance-契约测试)
- [与 Model/Prompt/Context 集成](#与-modelpromptcontext-集成)；[与 Tool/State/Policy 集成](#与-toolstatepolicy-集成)；[与 Harness/Event 集成](#与-harnessevent-集成)
- [生命周期与状态机](#生命周期与状态机)；[恢复与未知结果](#恢复与未知结果)；[安全、隐私与数据外发](#安全隐私与数据外发)
- [可观测性](#可观测性)；[测试策略](#测试策略)；[反模式](#反模式)
- [实施清单](#实施清单)；[五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与非目标
### 目标
Provider Runtime 必须：
- 为 Kernel 提供稳定的 `ModelPort`，不暴露 SDK 类型。；把 Provider、API family、Model、Deployment、Capability、Transport、Adapter 分层。；将 provider 原始 request/response/event 映射到 provider-neutral contract。
- 处理同步、流式、工具调用、结构化输出和多模态输入。；保留 reasoning、citation、grounding、safety、trace 和原始 metadata。；支持 credentials、tenant routing、region/location 与 deployment 解析。
- 区分 transport retry、agent retry、fallback 和 tool retry。；识别 context overflow 并交给 Context/Harness 处理。；对 rate limit、容量、网络、认证和能力错误分类。
- 聚合 usage/cost，并把 retry、fallback、compaction 等隐式调用归因。；通过 health、circuit breaker 和 model catalog 防止故障扩散。；为每个 provider/API family 提供独立 conformance suite。
- 在 provider SDK、HTTP、云签名和原始事件变化时局部演进。
### 非目标
本文不负责：
- Agent Kernel 的 while loop、终止条件和工具执行。；Prompt 文案、Context 选择、Memory 写入和 Compaction 规划。；工具业务授权、Approval、Sandbox 和 OS 级隔离。
- 直接决定租户配额、预算和数据驻留政策。；把所有 provider 降为最低公分母。；在 adapter 内偷偷切换租户、模型或 fallback。
- 用 provider safety filter 替代本地 Policy。；把原始 provider message 当作唯一 session 数据库模型。
### 质量公式
```text
Provider Reliability
  = Contract Correctness
  × Capability Accuracy
  × Stream Integrity
  × Retry Safety
  × Usage Attribution
  × Isolation of Provider Differences
```
任一项接近零，跨 provider 迁移就会在真实任务中失效。
## 术语与核心原则
### 稳定术语
- `Provider`：提供模型服务的产品或云平台边界。；`ApiFamily`：同一 Provider 内的协议族，例如 Responses、Messages、Converse、GenerateContent。；`Model`：能力和版本语义上的基础模型引用。
- `Deployment`：具体可调用资源，可能是 deployment name、endpoint、profile、ARN 或 publisher resource。；`ModelRef`：调用方选择模型的 provider-neutral 引用。；`ResolvedModel`：经过 catalog、deployment、region 和 capability 解析后的可调用模型。
- `Capability`：模型/部署对模态、工具、结构化输出、stream、reasoning 等能力的声明。；`Transport`：HTTP、SDK、SSE、WebSocket、云签名和连接生命周期。；`Adapter`：理解具体 API family 语义的 request/response/event 转换器。
- `Normalizer`：将 adapter 输出归一化为 Kernel 可消费的事件和响应。；`Attempt`：一次 provider/model 下的采样尝试；fallback 必须创建新 Attempt。
### 核心原则
- 先解析 `api_family`，再构造请求。；`OpenAI-compatible` 只表示部分 request shape 兼容。；Provider adapter 不能承载租户策略、配额策略或业务授权。
- 所有模型输出都视为不可信输入。；Stream 是事件流，不是 `AsyncIterable<string>`。；Tool call 只有在完成边界后才可解析和执行。
- Structured output 仍需应用端 schema 与业务校验。；原始 provider metadata 需要保留但不能污染 Kernel contract。；Unknown event 不静默丢弃。
- 失败恢复不能盲目重放可能成功的写请求。
## 职责边界
### Provider Runtime 负责
- provider registry 与 API family registry。；Model Catalog、ModelRef 解析和 Capability snapshot。；credentials provider、endpoint、region 和 deployment 解析。
- provider-neutral request 编译和原始 request 记录。；transport framing、超时、取消、连接复用和安全网络重试。；provider stream 解码、事件归一化和 response 聚合。
- tool schema projection、structured output projection 和多模态 projection。；provider error taxonomy、usage 解析、cost 估算和 metadata 保留。；health、readiness、circuit breaker 和 catalog freshness。
### Provider Runtime 不负责
- 租户是否允许使用某模型、预算和跨租户策略。；Prompt/Context 哪些资源可以发送给 provider。；Tool call 的业务参数是否合法或是否需要审批。
- Tool 是否实际执行、执行在哪里、是否有 sandbox。；Session transcript、Checkpoint、Compaction 和 Memory。；UI、SSE client、channel delivery 和审批界面。
### 明确的反越权边界
```text
Tenant Policy -> 选择允许的 provider/model/deployment/egress
Provider Runtime -> 按已解析配置调用 provider
Adapter -> 只做协议映射，不读取租户策略
Harness -> 注入已冻结的 tenant-aware config
```
Adapter 可以接收 `TenantRoutingSnapshot` 作为只读输入以选择 endpoint，但不能自己决定该 snapshot 的内容。
## 总体分层
```text
Tenant/Harness Routing
  -> Model Selection
  -> Model Catalog
  -> Credential Provider
  -> Provider/ApiFamily Adapter
  -> Request Compiler
  -> Transport
  -> Raw Frame Decoder
  -> Provider Event Decoder
  -> Stream Normalizer
  -> Provider-neutral ModelEvent
  -> Kernel ModelPort
```
### 控制面
控制面包括：
- provider、api family、model、deployment 注册。；capability、pricing、region、health 和 circuit state。；credential metadata、rotation status 和 routing policy 输入。
- adapter/transport/config snapshot。；conformance 结果和 catalog version。
### 数据面
数据面包括：
- provider request body 与 headers。；stream frames、content parts、tool arguments。；normalized event、usage 和 response metadata。
- error、retry、fallback 和 terminal result。
控制面错误不应通过 prompt 或模型输出掩盖；数据面高频事件不应阻塞控制面持久化。
## 模块与包布局
推荐包边界：
```text
packages/protocol/
  model.ts
  message.ts
  event.ts
  usage.ts
  error.ts
packages/model-runtime/
  contracts.ts
  provider-registry.ts
  api-family-registry.ts
  model-catalog.ts
  capability.ts
  request-compiler.ts
  response-normalizer.ts
  usage-ledger.ts
  routing-port.ts
  health.ts
  circuit-breaker.ts
packages/model-runtime/transport/
  transport.ts
  http-transport.ts
  stream-decoder.ts
  retry.ts
  cancellation.ts
packages/model-runtime/adapters/
  openai-responses.ts
  anthropic-messages.ts
  gemini-generate-content.ts
  bedrock-converse.ts
  azure-responses.ts
  vertex-generate-content.ts
packages/model-runtime/projection/
  message-projector.ts
  tool-projector.ts
  schema-projector.ts
  modality-projector.ts
packages/model-runtime/conformance/
  fixtures.ts
  suite.ts
  replay.ts
  providers/
packages/model-runtime/testkit/
  fake-provider.ts
  scripted-stream.ts
  fake-credentials.ts
  deterministic-clock.ts
```
依赖方向：
```text
Kernel -> ModelPort -> model-runtime contracts
Adapters -> protocol + transport contracts
Harness -> routing/credential/policy ports
Infrastructure -> concrete SDK/HTTP/cloud signer
```
Kernel 不导入 OpenAI、Anthropic、AWS、Azure 或 Google SDK 类型。
## 核心数据模型
### ProviderRef
```typescript
interface ProviderRef {
  id: string;
  kind: "first_party" | "cloud_hosted" | "gateway" | "custom";
  displayName: string;
  enabled: boolean;
  version: string;
}
```
### ApiFamilyRef
```typescript
interface ApiFamilyRef {
  id: string;
  providerId: string;
  protocol: "responses" | "messages" | "generate_content" | "converse"
    | "invoke_model" | "realtime" | "openai_compatible" | "custom";
  version: string;
  streaming: "sse" | "websocket" | "chunked" | "sdk_iterator" | "none";
}
```
### ModelRef
```typescript
interface ModelRef {
  provider?: string;
  apiFamily?: string;
  kind: "model" | "deployment" | "endpoint" | "profile" | "arn" | "publisher_model";
  value: string;
  regionOrLocation?: string;
  projectOrAccount?: string;
  deployment?: string;
}
```
`value` 不能被解释为“总是基础模型名”。Azure 可能是 deployment name；Bedrock 可能是 model/profile/ARN；Vertex 可能是 publisher model 或 endpoint resource。
### ResolvedModel
```typescript
interface ResolvedModel {
  ref: ModelRef;
  provider: ProviderRef;
  apiFamily: ApiFamilyRef;
  deployment: DeploymentRef;
  capabilities: ModelCapabilities;
  limits: ModelLimits;
  pricing?: PricingProfile;
  catalogVersion: string;
  resolutionDiagnostics: Diagnostic[];
}
```
### DeploymentRef
```typescript
interface DeploymentRef {
  id: string;
  kind: "direct_model" | "deployment" | "inference_profile" | "endpoint" | "publisher_model" | "custom";
  value: string;
  regionOrLocation?: string;
  projectOrAccount?: string;
  endpoint?: string;
  apiVersion?: string;
}
```
### ModelCapabilities
```typescript
interface ModelCapabilities {
  textInput: boolean;
  textOutput: boolean;
  imageInput: boolean;
  audioInput: boolean;
  audioOutput: boolean;
  videoInput: boolean;
  documentInput: boolean;
  streaming: boolean;
  toolCalling: boolean;
  parallelToolCalls: boolean;
  structuredOutput: boolean;
  strictStructuredOutput: boolean;
  reasoningEvents: boolean;
  citations: boolean;
  grounding: boolean;
  safetyEvents: boolean;
  promptCaching: boolean;
  serverSideConversation: boolean;
  batch: boolean;
}
```
### ModelLimits
```typescript
interface ModelLimits {
  contextWindowTokens?: number;
  maxOutputTokens?: number;
  maxTools?: number;
  maxToolArgumentBytes?: number;
  maxInputBytes?: number;
  maxParts?: number;
  maxImageBytes?: number;
}
```
### Usage
```typescript
interface Usage {
  inputTokens?: number;
  outputTokens?: number;
  reasoningTokens?: number;
  cachedInputTokens?: number;
  cacheWriteTokens?: number;
  toolTokens?: number;
  totalTokens?: number;
  source: "provider" | "estimated" | "reconciled";
  raw?: Record<string, unknown>;
}
```
### Money 与 Cost
```typescript
interface Money {
  currency: string;
  micros: number;
}
interface CostBreakdown {
  model: Money;
  input: Money;
  output: Money;
  cache: Money;
  transport: Money;
  total: Money;
  pricingVersion?: string;
  estimated: boolean;
}
```
## TypeScript 契约
### ModelPort
```typescript
interface ModelPort {
  stream(request: ModelRequest, signal: AbortSignal): AsyncIterable<ModelEvent>;
  generate(request: ModelRequest, signal: AbortSignal): Promise<ModelResponse>;
  resolveModel(ref: ModelRef, context: ModelResolutionContext): Promise<ResolvedModel>;
  capabilities(ref: ModelRef, context: ModelResolutionContext): Promise<ModelCapabilities>;
}
```
### ModelRequest
```typescript
interface ModelRequest {
  requestId: string;
  attemptId: string;
  model: ResolvedModel;
  messages: Message[];
  tools?: ProjectedToolDefinition[];
  output?: StructuredOutputRequest;
  generation: GenerationConfig;
  routing: RoutingSnapshot;
  egress: ModelEgressSnapshot;
  metadata?: Record<string, unknown>;
}
```
### ModelResponse
```typescript
interface ModelResponse {
  requestId: string;
  attemptId: string;
  items: ModelResponseItem[];
  finish: FinishState;
  usage?: Usage;
  cost?: CostBreakdown;
  providerMetadata: ProviderMetadata;
  raw?: RawResponseRef;
}
```
### ModelEvent
```typescript
type ModelEvent =
  | { type: "attempt_started"; requestId: string; attemptId: string }
  | { type: "content_start"; itemId: string; partId: string; kind: string }
  | { type: "text_delta"; itemId: string; partId: string; delta: string }
  | { type: "reasoning_delta"; itemId: string; partId: string; delta?: string; summary?: string }
  | { type: "tool_call_start"; itemKey: string; callId?: string; name?: string }
  | { type: "tool_call_name_delta"; itemKey: string; delta: string }
  | { type: "tool_call_arguments_delta"; itemKey: string; delta: string }
  | { type: "tool_call_complete"; itemKey: string; callId?: string }
  | { type: "citation"; citation: CitationPart }
  | { type: "grounding"; grounding: GroundingPart }
  | { type: "safety_update"; safety: SafetyUpdate }
  | { type: "usage_update"; usage: Usage; isFinal: boolean }
  | { type: "provider_event"; event: ProviderEventEnvelope }
  | { type: "attempt_completed"; finish: FinishState; usage?: Usage }
  | { type: "error"; error: NormalizedModelError };
```
### ModelProvider Adapter
```typescript
interface ModelProviderAdapter {
  provider: ProviderRef;
  apiFamily: ApiFamilyRef;
  resolveModel(ref: ModelRef, ctx: AdapterContext): Promise<ResolvedModel>;
  compileRequest(request: ModelRequest, ctx: AdapterContext): Promise<RawRequest>;
  decode(raw: RawFrame): ProviderEventBatch;
  normalize(batch: ProviderEventBatch, state: NormalizerState): NormalizedEventBatch;
  compileToolResult(result: ToolResultPart, ctx: AdapterContext): ProviderMessagePart;
  compileStructuredOutput(output: StructuredOutputRequest, caps: ModelCapabilities): ProjectedOutput;
  classifyError(error: unknown): NormalizedModelError;
}
```
Adapter 没有 `authorizeTenant`、`chooseFallback` 或 `executeTool` 方法。
### Transport
```typescript
interface ModelTransport {
  request(input: RawRequest, signal: AbortSignal): Promise<RawResponse>;
  stream(input: RawRequest, signal: AbortSignal): AsyncIterable<RawFrame>;
  health(input: HealthRequest, signal: AbortSignal): Promise<HealthResult>;
  close(): Promise<void>;
}
```
### Credentials
```typescript
interface CredentialProvider {
  resolve(ref: CredentialRef, context: CredentialContext): Promise<CredentialLease>;
  refresh(lease: CredentialLease, signal?: AbortSignal): Promise<CredentialLease>;
  revoke(leaseId: string): Promise<void>;
}
interface CredentialRef {
  kind: "static_api_key" | "bearer" | "azure_credential" | "aws_role"
    | "google_auth" | "custom_signer";
  secretRef: string;
  tenantBinding?: string;
}
```
## Provider/Model/Deployment 分层
### Provider 层
Provider 层保存：
- provider 身份和产品边界。；API family 列表。；credential 类型。
- region/location 和 account/project 语义。；默认错误分类和健康探针。；原始 metadata 命名空间。
Provider 层不保存某个租户的允许模型列表。
### Model 层
Model 层描述：
- 模型能力集合。；上下文和输出限制。；支持的模态组合。
- tool calling 和 structured output 子集。；reasoning、citation、safety 语义。；版本、生命周期和 catalog freshness。
### Deployment 层
Deployment 层描述：
- 实际可访问 resource ID。；endpoint、region/location、project/account。；API version 和协议头。
- deployment-specific capacity、health 和 quota signal。；允许的 credential strategy。
### 解析原则
```text
ModelRef
  -> provider/api family disambiguation
  -> deployment resolution
  -> catalog capability lookup
  -> credential compatibility
  -> routing snapshot
  -> ResolvedModel
```
如果同一 `value` 在多个 API family 有含义，必须要求调用方显式指定 `provider` 或 `apiFamily`，不能猜。
## Capability 分层
### 静态能力
静态能力来自 catalog 和版本：
- 模态输入输出。；是否支持 stream。；tool calling 类型。
- structured output 严格程度。；context window 与 max output。
### 动态能力
动态能力来自运行环境：
- 当前 region/deployment 是否 ready。；credentials 是否可用。；租户 policy 是否允许。
- host 是否支持流式/多模态 delivery。；当前 sandbox/egress 是否允许发送数据。；当前 provider quota 是否足够。
### 能力合取
```text
effective capability
  = catalog capability
  ∩ deployment capability
  ∩ credential capability
  ∩ tenant policy
  ∩ host capability
  ∩ egress policy
```
Provider Runtime 只计算前两项，并消费 Harness 注入的后续快照；不得自行扩大 capability。
### 能力不匹配
- 在请求编译前发现：返回 `provider_capability`。；在 provider 返回后发现：记录 adapter diagnostic 和失败 attempt。；不把不支持的能力静默降级为“看起来成功”。
- 明确记录被删除或降级的 schema constraint。
## Transport 与 Adapter 分层
### Transport 负责
- URL、DNS、TLS、代理、连接池。；HTTP method、headers、body framing。；SSE、chunked、WebSocket 或 SDK iterator 解包。
- deadline、AbortSignal、socket close。；安全的 transport retry。；response headers 和 request ID 采集。
### Adapter 负责
- API family 的 request shape。；provider message/content block 语义。；provider tool schema 和 output schema projection。
- provider event 类型和完成边界。；provider finish reason、安全和 usage 字段。；provider error body 到 normalized error 的映射。
### Normalizer 负责
- 生成通用 `ModelEvent`。；维护 open item、tool call、usage 和 metadata 状态。；检测 sequence gap、异常 EOF、截断和未知事件。
- 只在安全边界 emit `tool_call_complete`。
### 禁止混淆
- Transport 不解析 tool call 语义。；Adapter 不执行 retry policy 之外的业务 fallback。；Normalizer 不决定租户 egress。
- Provider metadata 不直接成为 UI 文案。
## Provider-neutral Contract
### Message 与 Part
```typescript
interface Message {
  id: string;
  role: "system" | "developer" | "user" | "assistant" | "tool";
  parts: ContentPart[];
  provenance?: Provenance;
  metadata?: Record<string, unknown>;
}
type ContentPart =
  | TextPart
  | ImagePart
  | AudioPart
  | VideoPart
  | DocumentPart
  | ToolCallPart
  | ToolResultPart
  | ReasoningPart
  | CitationPart
  | ProviderPart;
```
### ProviderPart
```typescript
interface ProviderPart {
  type: "provider_part";
  provider: string;
  apiFamily: string;
  kind: string;
  payload: unknown;
  sensitivity: Sensitivity;
}
```
ProviderPart 用于保留不可统一的事实，不应让 Kernel 根据任意 payload 做业务决策。
### ProviderMetadata
```typescript
interface ProviderMetadata {
  provider: string;
  apiFamily: string;
  requestId?: string;
  responseId?: string;
  rawEventKinds?: string[];
  safety?: SafetyMetadata;
  citations?: CitationPart[];
  grounding?: GroundingPart[];
  extensions?: Record<string, unknown>;
}
```
### Error
```typescript
interface NormalizedModelError {
  category:
    | "provider_transport"
    | "provider_authentication"
    | "provider_permission"
    | "provider_rate_limit"
    | "provider_capacity"
    | "provider_context_overflow"
    | "provider_capability"
    | "provider_safety"
    | "provider_invalid_request"
    | "provider_server"
    | "model_output_invalid"
    | "cancelled";
  code: string;
  message: string;
  retryable: boolean;
  outcomeKnown: boolean;
  retryAfterMs?: number;
  providerCode?: string;
  details?: Record<string, unknown>;
}
```
## Model Catalog
### Catalog 职责
Model Catalog 是解析和 conformance 的控制面，不是简单的模型名称数组。它保存：
- provider/API family/deployment identity。；model capabilities 和 limits。；region/location 可用性。
- pricing profile 版本。；preview/beta 标记和 adapter version。；last verified、source provenance 和 freshness。
- conformance status。
### Catalog 接口
```typescript
interface ModelCatalog {
  resolve(ref: ModelRef): Promise<CatalogModelRecord>;
  list(filter: CatalogFilter): Promise<CatalogModelRecord[]>;
  capabilities(ref: ModelRef): Promise<ModelCapabilities>;
  refresh(scope?: CatalogRefreshScope): Promise<CatalogRefreshResult>;
  snapshot(): CatalogSnapshot;
}
```
### Catalog 过期
- 过期 catalog 可用于提示诊断，不应保证能力。；`strictStructuredOutput`、工具和模态能力未知时，默认不可用。；pricing 过期时使用 estimated cost 并标记版本未知。
- deployment 健康异常不等于模型永久不可用。
## Credential 与 Tenant Routing
### 路由输入
```typescript
interface TenantRoutingSnapshot {
  tenantId: string;
  allowedProviders: string[];
  allowedModelRefs: ModelRef[];
  preferredRegions?: string[];
  requiredApiFamilies?: string[];
  credentialRef: CredentialRef;
  egressProfile: string;
  policyVersion: string;
}
```
### 路由流程
```text
authenticated principal
  -> tenant policy snapshot
  -> candidate ModelRefs
  -> catalog/capability filter
  -> region/deployment filter
  -> credential compatibility
  -> health/circuit filter
  -> deterministic selection
```
Provider adapter 只能使用已经解析好的 `ResolvedModel` 和 credential lease。
### Credential 生命周期
- Bootstrap 解析 secret reference，不读取明文到 model context。；Request 前获得短期 `CredentialLease`。；Transport 注入 API key、bearer、签名或云 SDK credential。
- 401/expired token 只按 credential provider 规则刷新一次。；失败记录 credential category，不记录 secret 值。；Run settlement 后释放 lease；长期 token 不进入 cache。
### 租户策略禁止放进 adapter
错误设计：
```text
OpenAIAdapter.stream() 内部判断 tenantId == specialTenant
```
正确设计：
```text
Tenant Router -> ResolvedModel + CredentialLease + EgressSnapshot
OpenAIAdapter -> 编译并发送已决策请求
```
## 请求编译总流程
```text
ModelRequest received
  -> validate ResolvedModel snapshot
  -> validate effective capabilities
  -> egress preflight
  -> message/part projection
  -> tool schema projection
  -> structured output projection
  -> generation parameter projection
  -> token/byte budget check
  -> credential lease
  -> raw request compile
  -> request hash and metadata
  -> transport send/stream
```
### 编译器接口
```typescript
interface RequestCompiler {
  compile(input: CompileInput): Promise<CompiledRequest>;
}
interface CompileInput {
  request: ModelRequest;
  capabilities: ModelCapabilities;
  adapter: ModelProviderAdapter;
  credential: CredentialLease;
  egress: ModelEgressSnapshot;
}
interface CompiledRequest {
  raw: RawRequest;
  requestHash: string;
  droppedFeatures: Diagnostic[];
  projectionHash: string;
}
```
### 编译失败分类
- `invalid_model_ref`：ModelRef 不能解析。；`capability_mismatch`：请求需要模型不支持的能力。；`schema_projection_unsafe`：不能安全投影 schema。
- `egress_denied`：数据不能发送到该 deployment。；`context_budget_exceeded`：需要 Context/Harness 先压缩。；`credential_unavailable`：凭据无法获得。
## 消息与多模态编译
### 文本
- 保持 role 顺序和 message/part 顺序。；不把 tool result 自由拼成 assistant 文本。；provider 不支持 developer role 时使用 adapter 的显式转换并记录诊断。
- system、developer、user、tool 的 authority 不可因 provider shape 改写。
### 图片、音频、视频、文档
```typescript
interface ImagePart {
  type: "image";
  source: { kind: "url" | "base64" | "artifact"; value: string };
  mediaType?: string;
  detail?: "low" | "high" | "auto";
}
```
编译前必须检查：
- sensitivity 和 egress policy。；media type 是否被 catalog 宣称支持。；URL 是否允许 provider 访问。
- artifact 是否可跨 provider 读取。；byte、像素、时长和 part 数量限制。；base64 是否需要脱敏或改为受控上传。
### 多模态降级
- 不支持某模态时返回 typed capability error。；允许摘要降级时由 Context Runtime 生成摘要，不由 adapter 自行 OCR 或编造内容。；不将远程 URL 直接发给不允许访问该域的 provider。
- 原始 artifact 只保留引用，模型收到的内容要记录 projection。
## Tool Calling 编译
### 工具 schema 投影
```typescript
interface ProjectedToolDefinition {
  name: string;
  description: string;
  inputSchema: JsonSchema;
  providerName?: string;
  projectionHash: string;
  droppedConstraints: string[];
}
```
### 规则
- canonical schema 保留在 Tool Runtime。；adapter 只投影 provider 支持的 schema 子集。；不可安全降级的 `oneOf`、约束或 required 语义应拒绝暴露。
- provider 名称冲突使用可逆映射。；tool definition hash 进入 request snapshot。；provider 支持 parallel tool calls 时仍由 Tool Scheduler 决定是否并行。
### Tool result 回传
- 保留 `callId`、tool name、结果顺序和 status。；provider 要求特定 content block 顺序时由 adapter 编译。；`unknown`、`denied`、`cancelled` 不伪装成成功文本。
- 大结果使用 artifact reference + summary。；tool result 不能携带新的权限或 secret。
## Structured Output 编译
### 接口
```typescript
interface StructuredOutputRequest {
  schema: JsonSchema;
  name?: string;
  strict: boolean;
  validationVersion: string;
}
interface ProjectedOutput {
  mode: "native_strict" | "native_relaxed" | "prompt_only" | "unsupported";
  schema?: unknown;
  projectionHash: string;
  diagnostics: Diagnostic[];
}
```
### 决策流程
```text
canonical schema
  -> provider supported subset check
  -> strict projection if safe
  -> compile provider request
  -> finish/safety check
  -> JSON parse
  -> local schema validation
  -> business validation
```
### 失败语义
- provider refusal/safety：typed refusal，不当作 JSON 错误。；length truncation：结果不完整，不能自动接受。；JSON parse failure：有限 `retry_modified`，不无限自修复。
- local schema failure：交给 Harness/Agent retry policy。；business validation failure：不由 adapter 猜测修复。
## 请求预算与上下文检查
### 预算公式
```text
usable input
  = model context window
  - expected output reserve
  - reasoning reserve
  - tool-call/result reserve
  - safety margin
```
### Provider Runtime 检查
- 估算 input tokens 和 bytes。；检查 max output 与 tool reserve。；检查最大 part、工具、参数和附件限制。
- 生成 `context_budget` diagnostic 并返回预计缺口。；不在 adapter 中删除历史消息。
### Context Overflow 处理边界
```text
Provider Runtime detects overflow
  -> classify provider_context_overflow
  -> emit diagnostic with limits
  -> Harness asks Context Runtime to compact
  -> new Attempt with changed context hash
```
如果 provider 只返回 400 而无明确 code，adapter 使用保守映射并保留 raw error reference。
## 发送与 Transport 生命周期
### Attempt 生命周期
```text
Created
  -> CredentialResolving
  -> Compiling
  -> Connecting
  -> Streaming | AwaitingResponse
  -> Completed | Failed | Cancelled
  -> Settled
```
### Cancellation
- AbortSignal 必须传到 transport、SDK iterator 和 response body reader。；取消后停止读取新 frame，关闭连接或 iterator。；不把用户取消当 provider success。
- 远程请求已发出但结果未知时，记录 `outcomeKnown: false`。；不因为 abort 自动重放有副作用的 provider-side operation。
### Timeout
分离：
- queue wait timeout。；credential resolve timeout。；connect timeout。
- first event timeout。；total stream timeout。；settlement timeout。
每个 timeout 使用不同 error code 和指标。
## Stream Event 归一化
### 原始流分层
```text
raw bytes/frame
  -> frame decoder
  -> provider event
  -> semantic adapter
  -> normalizer state machine
  -> ModelEvent
```
### NormalizerState
```typescript
interface NormalizerState {
  attemptId: string;
  responseId?: string;
  openItems: Map<string, OpenItemState>;
  openToolCalls: Map<string, ToolCallAssemblyState>;
  lastProviderSequence?: number;
  finish?: FinishState;
  usage?: Usage;
  unknownEventKinds: string[];
  diagnostics: Diagnostic[];
}
```
### 顺序要求
- provider sequence gap 触发 diagnostic。；text delta 仅在同一 item/part 内保持顺序。；tool arguments delta 不能跨 call key 混合。
- usage 可增量到达，最终 reconcile。；safety、citation、grounding 可与文本交错。；terminal 后禁止继续接受业务 delta。
### Durable 与 Ephemeral
Provider Runtime 发出的：
- `text_delta`、`reasoning_delta`、progress：默认 ephemeral。；`tool_call_complete`、final usage、finish、error：进入 Harness durable boundary。；unknown event：至少进入 diagnostic 或 raw artifact。
## Tool Call 增量组装
### 组装状态
```typescript
interface ToolCallAssemblyState {
  itemKey: string;
  callId?: string;
  nameBuffer: string;
  argumentsBuffer: string;
  phase: "started" | "streaming" | "complete" | "invalid";
  byteCount: number;
  eventCount: number;
  providerMetadata: Record<string, unknown>;
}
```
### 算法
- `tool_call_start` 创建状态。；name delta 追加到 name buffer。；arguments delta 按 provider sequence 追加原始片段。
- 检查 bytes、events、存活时间和调用总数上限。；只有 complete boundary 才 parse JSON。；校验 call ID、name、finish reason 和 sequence gap。
- 生成 `tool_call_complete` 或 typed invalid event。；response complete 时确认不存在未完成调用。
### 必测边界
- 多工具交错 delta。；call ID 在 start 或 complete 才出现。；JSON escape 和 Unicode 跨 frame。
- duplicate frame 和 complete 后 delta。；length、safety、cancel、EOF 截断。；provider unknown event 插入。
不完整调用不得进入 Tool Runtime、Policy 或 Executor。
## 响应归一化
### ModelResponseItem
```typescript
interface ModelResponseItem {
  id: string;
  parts: ContentPart[];
  status: "complete" | "incomplete" | "refused" | "error";
  providerMetadata?: ProviderMetadata;
}
```
### 归一化步骤
```text
provider response
  -> decode items/blocks
  -> preserve original order
  -> map content parts
  -> attach provider metadata
  -> map finish/safety/refusal
  -> reconcile usage
  -> compute cost
  -> emit ModelResponse
```
### 保留原始事实
- 原始 response/request ID。；provider event kind/version。；reasoning、citation、grounding 和 safety metadata。
- unknown fields 的安全摘要或 artifact reference。；projection diagnostics 和 dropped constraints。
## Finish Reason 与拒答
### FinishState
```typescript
interface FinishState {
  reason:
    | "stop"
    | "tool_calls"
    | "length"
    | "context_overflow"
    | "safety"
    | "refusal"
    | "cancelled"
    | "error"
    | "unknown";
  providerReason?: string;
  incomplete: boolean;
  safety?: SafetyMetadata;
}
```
### 决策表
| provider 结果 | normalized 状态 | 是否执行 tool call |
|---|---|---:|
| 正常文本完成 | complete | 否 |
| 工具调用完成 | complete/tool_calls | 仅完整调用 |
| length 截断 | incomplete | 否 |
| context overflow | error | 否 |
| safety/refusal | refused | 否 |
| transport EOF 无 terminal | failed | 否 |
| cancel | cancelled/incomplete | 否 |
不要把 safety refusal 当空文本成功。
## Usage、Cost 与计费归因
### Usage 处理
- provider usage 优先于估算。；缺失 usage 时生成 estimated 并注明 tokenizer/版本。；retry、fallback、compaction、memory extraction、embedding、rerank、subagent 分开记录。
- 失败 attempt 的 usage 不能丢弃。；增量 usage 与最终 reconciled usage 不能重复计费。
### UsageLedger
```typescript
interface UsageLedger {
  append(entry: UsageLedgerEntry): Promise<void>;
  summarize(scope: "attempt" | "run" | "session" | "tenant"): Promise<UsageSummary>;
  reconcile(receipt: BillingReceipt): Promise<void>;
}
```
### Cost 估算
```text
cost
  = input tokens × input rate
  + output tokens × output rate
  + cached tokens × cache rate
  + provider-specific surcharge
```
Pricing profile 必须带版本；未知价格不写确定金额。
### 预算交接
Provider Runtime 返回 `usage/cost`，Harness 的 `BudgetTracker` 决定是否继续；adapter 不能绕过预算。
## Rate Limit 与 Retry
### 错误分类
- 429 或明确 rate limit：`provider_rate_limit`。；临时容量：`provider_capacity`。；网络连接和安全 5xx：`provider_transport`/`provider_server`。
- 400 schema：`provider_invalid_request`。；401/403：`provider_authentication`/`provider_permission`。；模型不存在：`provider_capability` 或 routing error。
- context overflow：`provider_context_overflow`。
### Transport Retry
仅对同一安全请求：
- 使用 `Retry-After` 或服务端提示。；指数退避 + jitter。；最大次数和总时限。
- 仅在未观察到不可重放副作用时使用。；每次 retry 保留同一 Attempt 下的 transport attempt ID。
### Agent Retry
- 修改 context、generation 或 structured output。；由 Harness 创建新 Attempt 或 turn。；不复用原 provider request ID。
### 不可直接重试
- schema 400。；401/403。；模型不存在。
- 已可能成功的非幂等 provider-side 写操作。；context overflow 但没有缩减输入。
## Fallback 与 Model Routing
### Fallback 在 Harness
```text
primary attempt
  -> classify error
  -> check tenant fallback policy
  -> check capability compatibility
  -> check data egress/region
  -> freeze model change
  -> create new Attempt
  -> emit FallbackSelected
```
Adapter 不得在内部收到 429 就偷偷换模型。
### Fallback 兼容性检查
- 工具 calling 是否仍可用。；structured output 是否仍满足 strict 要求。；输入模态是否支持。
- context window 是否足够。；region/data egress 是否合规。；pricing 和 tenant budget 是否允许。
- safety/metadata 是否满足产品要求。
### Model Router 接口
```typescript
interface ModelRouter {
  select(input: RoutingInput): Promise<RoutingDecision>;
  fallback(input: FallbackInput): Promise<RoutingDecision | undefined>;
}
interface RoutingDecision {
  model: ResolvedModel;
  reasonCodes: string[];
  policyVersion: string;
}
```
## Context Overflow
### 检测来源
- 本地 token estimator 超预算。；provider 明确 context error。；response 因 length 截断且工具 call 未完成。
- model catalog limit 变化。；fallback 到更小窗口模型。
### 恢复流程
```text
detect overflow
  -> persist AttemptFailed(context_overflow)
  -> preserve usage and request hash
  -> Context Runtime builds CompactionPlan
  -> verify tool call/result pairs
  -> render new ModelRequest
  -> create new Attempt
```
### 禁止行为
- adapter 随机删除旧消息。；只保留最后字符串片段。；切断 assistant tool call/result pair。
- 用更小模型静默覆盖用户选择。；继续执行被截断的工具参数。
## Health 与 Circuit Breaker
### Health 维度
区分：
- liveness：进程和 adapter 可用。；readiness：transport、credential、catalog 和 endpoint 可调用。；capability readiness：目标模型支持所需能力。
- quota health：rate limit、容量和预算信号。；stream health：first event、EOF、sequence gap。；settlement health：usage、durable event 和 close 是否完成。
### Health 接口
```typescript
interface ProviderHealth {
  check(input: HealthCheckInput): Promise<HealthResult>;
  snapshot(): HealthSnapshot;
}
```
### Circuit 状态
```text
Closed
  -> Open on threshold failures
  -> HalfOpen after cooldown
  -> Closed on healthy probes
  -> Open on probe failure
```
### Circuit key
至少按：
```text
provider + apiFamily + deployment + region + credential class
```
不要把所有租户共用一个粗粒度 circuit，也不要把 tenant ID 作为高基数 metric label。
### 熔断策略
- 只熔断对应 provider/deployment 路由。；认证错误不应快速重试。；context/schema 错误不能作为 provider health failure。
- 记录 open reason、cooldown、probe result。；Fallback 前重新检查 capability 和 egress。
## Provider 差异隔离
### OpenAI 与其他 API family
不要用统一 `messages + delta` 类型覆盖所有协议。每个 adapter 自己定义 raw request、raw event 和 block state，再输出 canonical contract。
### 差异隔离原则
- provider-specific headers 在 Transport/Adapter 内。；provider-specific model ID 在 DeploymentRef 内。；provider-specific content block 在 ProviderPart 内。
- provider-specific finish/safety 在 normalized metadata 内。；provider-specific schema subset 在 projection layer 内。；provider-specific auth 在 CredentialProvider 内。
- provider-specific retry hint 在 ErrorClassifier 内。
### 不可隔离的差异
如果某能力无法表示为 canonical contract：
- 用 capability flag 表示。；保留 ProviderPart/ProviderMetadata。；对不支持该能力的调用显式报错。
- 不伪造等价行为。
## OpenAI 适配边界
- 优先以 Responses API 的 item/event 语义建 adapter。；不把 Responses item 当 Chat message delta。；保留 response/item/content/tool event 的层级和 ID。
- 结构化输出、tool call、reasoning、citation 等由 projection 处理。；Chat Completions 作为独立 API family，不与 Responses 共用 raw event parser。；Realtime/WebSocket 作为独立 Transport/API family。
- model ref 使用原厂 model ID；兼容端点需记录实际平台和支持子集。
## Anthropic 适配边界
- Messages API 的 content block 是一等结构。；tool use/tool result 保持 block 顺序和关联 ID。；thinking/reasoning block 不应被降级成普通文本。
- tool schema、usage、stop reason 和 refusal 由 Messages adapter 解析。；云平台托管时使用独立 Bedrock/Vertex API family，不在 Anthropic 原生 adapter 内混入云认证。；未完成 block 不得变成 ready tool call。
## Gemini 适配边界
- 原生 `Content/Part` 作为 Gemini family 的 canonical raw shape。；不以 OpenAI-compatible 层覆盖原生 multimodal 和 grounding 能力。；`generateContent` 与 `streamGenerateContent` 使用同一语义 adapter、不同 transport mode。
- function calling、structured output、safety、citation/grounding metadata 保持 provider metadata。；Developer API 和 Vertex 的认证、project/location/resource 解析分离。
## Bedrock 适配边界
- Converse/ConverseStream 是独立 API family。；`modelId` 可能是 model、profile、deployment 或 ARN，必须映射到 DeploymentRef。；AWS credential、region、SigV4 由 AWS transport/credential 实现。
- 特有模型参数使用 provider extension，不强塞到通用 generation config。；InvokeModel 与 Converse 使用不同 request/response adapter。；profile/ARN routing 由 Harness/Tenant Router 冻结，adapter 只执行。
## Azure 适配边界
- Azure OpenAI/Foundry 使用独立 Azure family。；`model` 常为 deployment name，不应被解释为基础模型名。；endpoint、api version、deployment path 和 credential 由 Azure transport 处理。
- `/openai/v1/responses` 与日期版旧 API 分离。；Foundry 项目型 Responses 资源引用不能冒充原厂 OpenAI deployment。；region/data residency 和 tenant egress 必须在 routing snapshot 中决定。
## Vertex 适配边界
- Vertex 使用独立 Google Gen AI/Generate Content family。；publisher model ID、endpoint resource、project/location 不混用。；Google auth、project 和 location 由 credential/deployment 解析。
- MaaS 合作伙伴模型可保留厂商 native adapter，不强行套 Gemini adapter。；OpenAI-compatible endpoint 仅作为迁移兼容 family，能力另行 conformance。；配额、认证和资源引用不能与 Gemini Developer API 混用。
## Conformance 契约测试
### Suite 接口
```typescript
interface ProviderConformanceSuite {
  provider: string;
  apiFamily: string;
  modelFixture: ModelFixture;
  cases: ProviderConformanceCase[];
}
interface ProviderConformanceCase {
  id: string;
  request: ModelRequestFixture;
  rawFrames?: unknown[];
  expectedEvents: EventExpectation[];
  expectedResponse?: ResponseExpectation;
  expectedError?: ErrorExpectation;
}
```
### 必测用例
- 普通文本、空 delta、Unicode 跨 frame。；单工具和多工具。；arguments 任意分片、交错和终止。
- call ID、item ID、block ID 映射。；tool result 回传形状和顺序。；structured output strict/relaxed/unsupported。
- image/audio/video/document projection。；usage 增量、最终值和缺失估算。；safety/refusal/length/context overflow。
- 429、5xx、EOF、abort、timeout。；unknown event、unknown field、版本变化。；capability mismatch 早失败。
- credential refresh 和 region/deployment resolution。
### Conformance 断言
- `Provider Event -> ModelEvent` 映射稳定。；不完整 tool call 不产生 ready。；provider metadata 不丢失。
- retry/fallback 不复用 Attempt ID。；cancel 释放 transport 和 reader。；raw fixture 脱敏并可 replay。
同一厂商不同 API family 必须使用独立 profile；“兼容”不能免测。
## 与 Model/Prompt/Context 集成
### Model Harness
Model Harness 调用：
- Model Catalog 解析。；credential provider。；request compiler。
- stream normalizer。；usage ledger。；health/circuit。
### Prompt 集成
Prompt Compiler 只接收 effective capabilities：
- 有 reasoning channel 才加入对应说明。；有 structured output 才加入 schema 约束。；有 tool calling 才描述工具协议。
- 没有某模态就删除相关指令。
Prompt 不负责声明 provider 已经批准请求。
### Context 集成
Context Compiler 在 Provider Runtime 之前完成：
- sensitivity/tenant egress 过滤。；token budget 和 ContextPlan。；artifact offload 与 redaction。
- provider-specific render target。
Provider Runtime 只能报告实际 limit 和 projection diagnostics。
## 与 Tool/State/Policy 集成
### Tool 集成
```text
ActiveToolset
  -> provider schema projection
  -> ModelRequest
  -> normalized ToolCall
  -> Tool Runtime
  -> ToolResult
  -> provider tool-result projection
```
Provider adapter 不校验业务权限、不执行工具、不生成 approval。
### State 集成
State Harness 至少持久化：
- ModelChangeEntry。；AttemptStarted/Completed/Failed。；provider/model/api family/deployment snapshot。
- request hash、toolset hash、context hash。；usage/cost、retry/fallback。；unknown outcome 和 recovery diagnostic。
### Policy 集成
Policy 在请求前决定：
- provider/model/deployment 是否允许。；data egress 是否允许。；credential scope。
- region/location 和 fallback。
Provider Runtime 只消费 immutable `RoutingSnapshot`、`EgressSnapshot` 和 `PolicySnapshot`。
## 与 Harness/Event 集成
### Harness 装配顺序
```text
resolve tenant/identity
  -> load policy
  -> resolve model routing
  -> catalog/capabilities
  -> credential lease
  -> build toolset/context
  -> create ModelRuntime
  -> freeze config snapshot
  -> start Kernel
```
### Event 层级
```text
Provider Event -> Kernel Event -> Harness Event -> Host Event
```
Provider Runtime 产生：
- `model.attempt.started`。；`content.text.delta`。；`tool.call.ready`。
- `usage.updated`。；`model.attempt.failed`。；`model.attempt.completed`。
- `provider.event` diagnostic。
### Durable 边界
- Attempt start。；完整 assistant item。；Tool call ready。
- final usage。；finish/error。；retry/fallback/model change。
Token delta 默认 ephemeral；高安全 provider event 保存 metadata/hash，不默认保存原文。
## 生命周期与状态机
### Request 状态机
```text
Received
  -> ModelResolved
  -> CapabilityChecked
  -> EgressChecked
  -> Compiled
  -> CredentialBound
  -> Sent
  -> Streaming | AwaitingResponse
  -> Normalizing
  -> Completed | Failed | Cancelled
  -> Settled
```
### Attempt 状态机
```text
Created
  -> Requesting
  -> Streaming
  -> ToolCallsReady | FinalContent
  -> Completed
Created -> Failed
Created -> Cancelled
```
### Circuit 状态机
```text
Closed -> Open -> HalfOpen -> Closed
                    -> Open
```
### 状态不变量
- Attempt terminal 后不能有新 delta。；Fallback 必须新 Attempt。；Tool call/result 关联不能重复或缺失。
- usage 最终值只能 reconcile 一次。；terminal durable commit 前不能报告 run success。
## 恢复与未知结果
### 进程崩溃恢复
```text
load checkpoint
  -> inspect open attempt
  -> inspect request/response receipt
  -> query provider-side status if available
  -> classify completed/failed/unknown
  -> preserve usage
  -> continue, fallback, or require manual action
```
### 状态未知
- 无副作用的模型采样：可按安全 retry policy 重试。；provider-side batch/file/job：优先 query status。；可能触发外部副作用的 hosted tool：不得盲目重放。
- unknown outcome 必须 durable 记录。
### 重新编译
恢复 run 时重新验证：
- catalog version 和 capability。；credential 是否仍有效。；tenant policy 和 egress 是否变化。
- context/toolset hash 是否兼容。；model/deployment 是否仍可用。
## 安全、隐私与数据外发
### Provider Egress
调用模型前评估：
```text
tenant policy
  + resource sensitivity
  + provider jurisdiction
  + deployment/region
  + redaction profile
  + retention requirement
  -> allow | redact | summarize | artifact_only | deny
```
### Secret
- secret 不进入 prompt、ModelRequest、tool arguments、stream event 或普通日志。；credential 只通过 `CredentialLease`、broker 或签名 transport 使用。；provider response 的 secret-like 内容进入 redaction pipeline。
- raw request/response 只存受控 artifact reference。
### 日志
默认记录：
- provider/api family/model/deployment hash。；request/response ID。；usage、latency、retry、finish code。
- schema/projection/context hash。；redaction state 和 sensitivity。
不默认记录：
- 完整 prompt。；hidden reasoning。；原始工具参数。
- bearer token、API key、cookie。；regulated 原文。
### 多租户交接
Provider Runtime 的每个 request 都带可信的 tenant routing snapshot，但 provider adapter 不能自行查询其他租户数据或修改 tenant ID。
## 可观测性
### Trace 层级
```text
session span
  -> run span
    -> attempt span
      -> model request span
        -> transport span
        -> stream normalize span
      -> retry/fallback event
      -> usage settlement span
```
### 必备字段
```text
trace_id
session_id
run_id
attempt_id
request_id
provider
api_family
model_ref hash
deployment hash
region/location
catalog_version
adapter_version
transport_version
context_hash
prompt_hash
toolset_hash
usage/cost
latency breakdown
retry/fallback
finish reason
error category
redaction state
```
### 指标
- model request success/failure。；TTFE、TTFT、first tool call latency。；connect、stream、settlement latency。
- 429、5xx、auth、capability、overflow 比例。；retry/fallback rate 和 retry amplification。；circuit open duration。
- usage reconciliation drift。；cost per run、cost per successful task。；unknown event、sequence gap、incomplete tool call。
高基数 tenant/user/request ID 不作为普通 metric label；需要时使用受控 trace 或分区聚合。
## 测试策略
### 单元测试
- ModelRef/DeploymentRef 解析。；capability intersection 和 projection。；schema projection 安全拒绝。
- message/part 多模态编译。；structured output projection。；error taxonomy 和 retry hints。
- tool-call assembler。；usage reconciliation 和 cost calculation。；circuit breaker transitions。
### Component 测试
- fake transport + adapter request shape。；raw frame decoder + normalizer。；credential refresh、cancel、timeout。
- catalog stale、health degraded。；egress deny、redaction、artifact-only。
### Contract 测试
每个 Provider/API family 运行同一 conformance suite，但允许声明 capability profile。
### 集成测试
- 真实低成本模型、无副作用工具。；单调用、多工具、structured output、图片/文档。；认证、stream、usage、finish reason。
- 环境变量可关闭，禁止依赖生产凭据。
### 故障注入
- 429、5xx、连接断开、半帧、重复帧。；provider EOF 无 terminal。；tool arguments 截断。
- context overflow。；usage 延迟或缺失。；credential refresh 失败。
- circuit open。；raw response 大小超限。；durable commit 前进程崩溃。
### 安全测试
- secret 出现在 prompt、headers、events、logs、artifact。；cross-tenant routing 误用。；URL/attachment egress 绕过。
- provider metadata 注入 UI 或 policy。；unknown event 触发错误执行。
### Evaluation 集成
Evaluation Harness 使用：
```text
FakeModelProvider
ScriptedModelStream
RecordedRawFrameFixture
DeterministicClock
DeterministicIdGenerator
EventRecorder
UsageLedgerRecorder
```
必须同时断言请求、事件、tool call/result、usage、cost、错误、状态和恢复，不能只断言最终文本。
## 反模式
- Kernel 直接 import provider SDK。；所有 provider 共享一个 ChatMessage/字符串流 parser。；把 `OpenAI-compatible` 当完全兼容。
- Adapter 内部偷偷 fallback 或修改 tenant routing。；Provider adapter 承载租户策略、预算或业务权限。；`AsyncIterable<string>` 丢弃 tool delta、usage 和 safety。
- Tool arguments 未完成就解析执行。；provider finish 为 length/safety 时仍执行半个调用。；structured output 只依赖 prompt 要求 JSON。
- 不保留 provider metadata。；Azure deployment name 被当成基础模型名。；Bedrock ARN/profile 被当成普通 model ID。
- Vertex 与 Gemini Developer API 混用认证和资源 ID。；Anthropic block 顺序被转换成任意消息数组。；多模态 URL 未经过 egress policy。
- retry 重复可能成功的 provider-side 写操作。；fallback 不写 ModelChange/Attempt entry。；只统计成功 attempt 的 usage/cost。
- catalog 过期仍把未知能力当作支持。；circuit key 过粗导致所有租户雪崩。；raw response 直接写普通日志。
- provider safety filter 被当作本地 Policy。；context overflow 时 adapter 随机截断历史。；测试只 mock final text。
- conformance 只测同步 happy path，不测 stream/abort/unknown event。
## 实施清单
### 契约与分层
- [ ] 定义 ProviderRef、ApiFamilyRef、ModelRef、DeploymentRef。；[ ] 定义 ResolvedModel、ModelCapabilities、ModelLimits。；[ ] 定义 ModelPort、ModelProviderAdapter、ModelTransport。
- [ ] 明确 Adapter 不执行工具、不承载租户策略。；[ ] 统一 Message、ContentPart、ModelEvent、Usage、Error。；[ ] ProviderPart 保留不可统一 metadata。
### Catalog 与路由
- [ ] 建立 Provider/API family registry。；[ ] 建立 Model Catalog、版本、freshness 和 conformance 状态。；[ ] 实现 deployment/region/project/account 解析。
- [ ] 实现 credential lease、refresh、revoke。；[ ] 实现 tenant routing snapshot 输入。；[ ] 实现 capability intersection 和 deterministic routing。
### 请求编译
- [ ] 实现 message/part projection。；[ ] 实现多模态 egress、大小和 capability 检查。；[ ] 实现 tool schema projection 和 hash。
- [ ] 实现 structured output strict/relaxed/unsupported。；[ ] 实现 generation parameter projection。；[ ] 实现 token/byte/tool/attachment budget。
- [ ] 生成 request hash 和 config snapshot。
### Stream 与响应
- [ ] 分离 transport、decoder、adapter、normalizer。；[ ] 支持 text/reasoning/tool/citation/safety/usage/error/completion。；[ ] 支持交错多 tool call 和任意参数分片。
- [ ] 截断、gap、EOF、未知事件不执行不完整调用。；[ ] 保留 provider metadata 和 raw reference。；[ ] 完成 response/finish/refusal 归一化。
### 可靠性与运营
- [ ] 分类 rate limit、capacity、transport、auth、capability、overflow。；[ ] 分离 transport retry、agent retry、fallback。；[ ] 实现 circuit breaker 和 health/readiness。
- [ ] 实现 usage ledger、pricing version 和 reconciliation。；[ ] 实现 Attempt/ModelChange durable entries。；[ ] 实现 crash recovery 和 unknown outcome。
### Conformance 与安全
- [ ] 为六类 provider/API family 建独立 fixture profile。；[ ] 覆盖同步、stream、tool、structured output、多模态和错误。；[ ] 覆盖 credential、region/deployment、cancel、retry、fallback。
- [ ] 覆盖 egress、redaction、secret、cross-tenant routing。；[ ] 记录 adapter/transport/catalog/projection 版本。；[ ] 在 CI 中执行 replay、fault injection 和 provider contract tests。
## 五个参考项目的启发来源
### Pi
- headless agent loop 和统一 EventStream 启发 ModelPort 与 Kernel 解耦。；provider event 归一化启发 stream 不是字符串。；session tree、Attempt、compaction usage 启发 usage、model change 和恢复边界。
- CLI/TUI/RPC 共用 runtime 启发 Host 不应读取 provider raw event。
### Grok Build
- HTTP、协议转换、采样器和 actor 的分层启发 Transport/Adapter/Normalizer 分离。；sampler 多层结构启发 Attempt、retry/fallback 和 usage 归因。；工具参数流、输出预算和并行执行启发增量组装与 event backpressure。
- 独立 trace 和状态 actor 启发 health、恢复和单写者顺序。
### OpenCode
- provider、session、message/part 和 server 分离启发 provider-neutral contract。；durable event/projector 启发 Attempt、Usage、ModelChange 的持久化投影。；client/server 与多客户端事件启发 stream resume 和 delivery 解耦。
- permission/tool/provider 模块分离启发 adapter 不承担授权。
### Claude Code
- permission modes、skills、hooks、subagents 和 memory 的产品 harness 启发 capability/context/policy 交接。；模式化工具可见性启发 effective capabilities 参与 Prompt 编译。；长任务和后台工作流启发 provider usage、fallback、checkpoint 必须可解释。
- 公开能力和安全语义以现有本地文档中标注的 Anthropic 官方资料为准。
### OpenClaw
- AgentHarness registry 与独立 agent-core 启发 provider registry、runtime factory 和 Host 解耦。；provider runtime、tool、sandbox、elevated 分层启发 routing、adapter、policy、execution 边界。；Gateway/channel 与后台运行启发 stream event、delivery、background run 的分离。
- 插件事务化注册启发 adapter/catalog 注册和失败回滚。
本设计的实现审查应回到已有本地参考文档和其列出的源码范围；若新增 provider、API family、区域策略、价格或合规要求，应另行补充一手证据、版本和迁移约束。
