# Provider Schema Evolution Engineering 细粒度工程设计
> 本文定义 Agent 平台中 Provider Schema Evolution 的工程边界、数据模型、兼容性、迁移、验证、发布和恢复方法。
>
> 本设计只使用当前目录已有参考架构、Agent API 模式、能力矩阵、Harness、Prompt、Context、Tool、State/Memory、Permission/Sandbox、Event/Observability、Evaluation、Provider Runtime、Provider Routing、Provider Runtime Conformance、Session Replay、Artifact、Multi-tenant、Host Adapter、Workspace Isolation 和 Production Operations 文档中已经记录的源码调研结论。
## 目录
1. [设计目标与非目标](#设计目标与非目标)
2. [核心判断与术语](#核心判断与术语)
3. [职责边界](#职责边界)
4. [总体架构与包布局](#总体架构与包布局)
5. [Canonical Schema 原则](#canonical-schema-原则)
6. [Schema 分类与生命周期](#schema-分类与生命周期)
7. [核心 TypeScript 数据模型](#核心-typescript-数据模型)
8. [Request Schema](#request-schema)
9. [Response Schema](#response-schema)
10. [Stream/Event Schema](#streamevent-schema)
11. [Tool Schema](#tool-schema)
12. [Structured Output Schema](#structured-output-schema)
13. [Multimodal Schema](#multimodal-schema)
14. [Provider Projection](#provider-projection)
15. [版本策略与 Compatibility Levels](#版本策略与-compatibility-levels)
16. [Additive 与 Breaking Change](#additive-与-breaking-change)
17. [Capability Negotiation](#capability-negotiation)
18. [Schema Registry](#schema-registry)
19. [Validation 与 Unknown Fields](#validation-与-unknown-fields)
20. [Provider Drift](#provider-drift)
21. [Migration、Dual-read 与 Dual-write](#migrationdual-read-与-dual-write)
22. [Persisted Session/Event/Artifact Migration](#persisted-sessioneventartifact-migration)
23. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
24. [决策流程](#决策流程)
25. [生命周期与状态机](#生命周期与状态机)
26. [Rollout、Canary 与 Rollback](#rolloutcanary-与-rollback)
27. [安全、隐私与 Redaction](#安全隐私与-redaction)
28. [故障恢复与 Unknown Outcome](#故障恢复与-unknown-outcome)
29. [可观测性、Audit 与 SLO](#可观测性audit-与-slo)
30. [测试策略](#测试策略)
31. [CI、Release Gates 与运维](#cirelease-gates-与运维)
32. [反模式](#反模式)
33. [实施清单](#实施清单)
34. [五个参考项目的启发来源](#五个参考项目的启发来源)
35. [Definition of Done](#definition-of-done)
## 设计目标与非目标
### 目标
Provider Schema Evolution 必须使系统能够：
- 在 provider-neutral contract 中保存稳定语义，而不是把某家 SDK 类型当数据库模型。 - 同时处理 request、response、stream、tool、structured output 和 multimodal schema。 - 将 canonical schema 与 provider projection 明确分离。 - 对每次 schema 变更给出兼容级别、影响面、迁移计划和回滚窗口。 - 在能力协商阶段发现不能安全投影的 schema，而不是发出请求后才失败。 - 允许 provider 特有字段存在，并保留 provider metadata、raw receipt 和 projection diagnostics。 - 对未知字段和未知事件采取可诊断、可回放、可安全忽略的策略。 - 将 schema drift 转化为 fixture、golden、contract、conformance、canary 和 release evidence。 - 迁移已持久化的 session、semantic entry、event、checkpoint、memory、artifact metadata 和 usage ledger。 - 在双读、双写、shadow、canary 和 rollback 中保持 tenant、policy、egress、redaction 和审计边界。 - 在进程崩溃、provider 断流、schema 校验失败和迁移半完成时保持 durable truth 可恢复。 - 让每次模型行为差异都能由 schema、capability、projection、版本和配置快照解释。
### 明确边界判断
```text
Schema Evolution != 简单改 JSON 字段 Schema Evolution = 语义契约 + 版本 + 投影 + 能力 + 持久化迁移 + 验证 + 发布控制 + 恢复
```
修改一个字段可能影响：
- provider request shape； - provider response parser； - stream normalizer； - tool call/result 配对； - structured output validator； - ContextPlan token/egress； - PromptCompiler capability instructions； - State/Session projector； - ArtifactRef view 和 retention； - Policy/Approval action hash； - Event replay 和 Host projection； - UsageLedger、Evaluation fixture 与 CI gate。
### 非目标
本文不负责：
- 选择 primary/fallback provider；选择属于 Provider Routing。 - 执行工具或决定业务授权；执行属于 Tool Runtime、Policy 和 Sandbox。 - 优化 prompt 措辞；Prompt 只解释 schema 能力与限制。 - 让所有 provider 产生相同文本、token 或事件粒度。 - 把 provider-specific 能力强行压成最低公分母。 - 用 JSON 能解析证明迁移成功。 - 用当前 provider response 覆盖原始历史事实。 - 用 telemetry、UI transcript 或 cache 替代 State/Event Store。 - 通过 migration 绕过 tenant、egress、retention 或 redaction policy。
## 核心判断与术语
### Canonical Schema
Canonical Schema 是 Agent Kernel、Harness、Tool Runtime、State 和 Evaluation 之间的稳定内部契约。
它表达：
- 语义身份； - 角色和顺序； - content parts； - tool call/result 关联； - structured validation 状态； - stream 完成边界； - usage、error、safety 和 provider metadata； - scope、sensitivity、provenance 和版本。
Canonical Schema 不等于某个 provider 的原始 JSON。
### Provider Projection
Provider Projection 是将 canonical request、tool definitions、structured output 和 multimodal parts 转换为目标 provider/API family 可接受的子集。
Projection 必须记录：
- provider、api family、deployment； - adapter version； - capability snapshot； - dropped constraints； - degraded fields； - projection hash； - egress/redaction profile； - raw request reference。
### Schema Version
Schema Version 是契约演进的身份，不是数据库 migration 的替代品。
至少分开记录：
- `contractVersion`； - `canonicalSchemaVersion`； - `providerApiVersion`； - `adapterVersion`； - `capabilityVersion`； - `projectionVersion`； - `eventSchemaVersion`； - `toolSchemaVersion`； - `structuredValidationVersion`； - `artifactManifestVersion`； - `pricingVersion`。
### Compatibility Level
兼容级别描述“旧消费者、旧数据、旧 provider adapter 和旧 replay 能否安全工作”，而不是只描述 TypeScript 是否能编译。
建议级别：
```text
L0: byte-compatible L1: parse-compatible L2: semantic-compatible L3: projection-compatible L4: replay-compatible L5: operationally-compatible L6: breaking
```
### Provider Drift
Provider Drift 是外部 provider、SDK、API family、model alias、deployment 或服务端行为相对已记录 contract 的变化。
drift 可能表现为：
- 新增/删除字段； - null、empty、missing 语义变化； - 事件顺序变化； - tool call 完成边界变化； - structured schema 子集变化； - usage 字段或计费口径变化； - finish reason、safety/refusal 或 error code 变化； - 多模态 MIME、artifact 生命周期或 URL 访问规则变化。
## 职责边界
### Schema Evolution Service 负责
- 定义 canonical schema 和版本元数据。 - 维护 Schema Registry、Compatibility Matrix 和 Projection Registry。 - 编译、验证、diff、分类和发布 schema 变更。 - 维护 upcaster、downcaster、adapter parser 和 projection rules。 - 生成 schema hash、projection hash、request hash 和 migration evidence。 - 管理 dual-read、dual-write、shadow validation 和 rollout gate。 - 向 Provider Runtime、Tool Runtime、State/Event Store 提供契约检查。 - 对未知字段、未知事件和 drift 生成 diagnostic 与告警。 - 为 session/event/artifact migration 提供 dry-run、copy、verify 和 rollback。
### Provider Runtime 负责
- 使用冻结的 canonical request、ResolvedModel、capability 和 projection。 - 发送 provider request、解析 response/stream、生成 normalized events。 - 保存 raw receipt、provider metadata、unknown event reference 和 usage evidence。 - 按 adapter contract 提供 capability mismatch、schema error 和 protocol error。
### Provider Routing 负责
- 在 policy、egress、capability 和 quota 边界内选择 provider/model/deployment。 - 根据 projection compatibility 排除不可安全投影的候选。 - Fallback 时重新执行能力、区域、数据驻留和 schema 兼容检查。
### Tool Runtime 负责
- 保留 canonical input/output schema。 - 在 provider projection 之外重新做本地 schema 和业务校验。 - 将 schema 变更与 tool semantic version、effect、idempotency、approval 绑定。 - 防止 provider strict schema 被误当作本地授权或业务正确性。
### State/Event/Session 负责
- 保存 schemaVersion、payloadHash、sourceEventId、scope 和 sensitivity。 - 以 append-only 事实记录 migration、upcast、projection rebuild 和 recovery。 - 维护 projector compatibility、checkpoint validity 和 replay evidence。
### Harness 负责
- 冻结 run config、model、toolset、policy、context、schema、projection 和 sandbox snapshot。 - 在 request 前执行 capability、egress、budget、validation preflight。 - 监督迁移、重试、fallback、approval、checkpoint、delivery 和 terminal settlement。 - 在失败时区分 retryable、migration_required、unknown outcome 和 manual action。
### 强制边界
```text
Canonical Schema -> Validation -> Capability Negotiation -> Provider Projection -> Transport/Adapter -> Normalized Event -> Tool/State/Harness
```
```text
Provider projection 不能替代 canonical validation。 Provider strict mode 不能替代本地业务校验。 Migration 不能重写 immutable audit fact。
```
## 总体架构与包布局
```text
packages/schema-evolution/ contracts.ts schema-registry.ts schema-diff.ts compatibility.ts validators.ts unknown-fields.ts projection-registry.ts capability-negotiation.ts migration-plan.ts upcasters.ts downcasters.ts dual-read.ts dual-write.ts drift-detector.ts golden.ts rollout.ts redaction.ts audit.ts testkit/
```
```text
packages/provider-runtime/ request-compiler.ts response-parser.ts stream-normalizer.ts tool-projector.ts structured-output.ts multimodal.ts
```
```text
packages/state/ entry-upcaster.ts checkpoint-migration.ts projection-rebuilder.ts replay-compatibility.ts
```
依赖方向：
```text
Harness -> Schema Evolution contracts Provider Runtime -> Projection/Validation ports Tool Runtime -> Canonical Schema/Business Validator State/Event -> Versioned Entry/Upcaster contracts Evaluation -> Fixtures/Golden/Conformance contracts Infrastructure -> Registry/Store/Migration adapters
```
Kernel 不导入 provider SDK、数据库 ORM、具体 object store 或 UI schema。
## Canonical Schema 原则
### 语义优先
Canonical Schema 先表达“发生了什么”，再表达“provider 如何编码”。
例如 ToolCall 至少包含：
- `callId`； - canonical tool name； - validated arguments； - arguments hash； - source attempt； - call ordinal； - provider metadata； - completeness state。
不能只保存 provider 的一个 JSON 字符串。
### 稳定身份与展示字段分离
以下身份必须分开：
```text
providerRequestId != attemptId != responseId callId != toolExecutionId != businessIdempotencyKey artifactId != artifactVersionId != contentHash sessionId != runId != turnId
```
展示名称可以被投影或脱敏；稳定 ID 不应随 provider 别名变化。
### 顺序是语义
Canonical Schema 必须保留：
- message order； - part order； - tool call ordinal； - provider sequence； - event stream sequence； - causation/correlation。
并行工具的完成时间不等于模型反馈顺序。
### 未知字段不是垃圾
未知字段应按 sensitivity 和影响分类：
- 可安全忽略的 optional field； - 需要诊断的 provider extension； - 可能改变完整性的 unknown event； - 不能安全解析的 required field； - 受控 raw artifact reference。
## Schema 分类与生命周期
### Schema 分类
至少维护以下 schema family：
```text
CanonicalMessageSchema CanonicalPartSchema ModelRequestSchema ModelResponseSchema ModelStreamEventSchema ToolDefinitionSchema ToolCallSchema ToolResultSchema StructuredOutputSchema MultimodalPartSchema UsageSchema ErrorSchema PolicySnapshotSchema ContextPlanSchema SessionEntrySchema CheckpointSchema ArtifactMetadataSchema
```
### Schema 生命周期
```text
Draft -> Reviewed -> Registered -> CompatibleChecked -> FixtureBacked -> CanaryReady -> Active -> Deprecated -> Retired
```
### 注册前必须具备
- schema ID 和版本； - owner、reviewer、source provenance； - compatibility report； - migration/upcaster plan； - fixture/golden； - redaction policy； - supported consumer range； - rollback window； - deprecation date 或条件； - conformance status。
## 核心 TypeScript 数据模型
```typescript
type SchemaId = string; type SchemaVersion = `${number}.${number}.${number}`; type SchemaHash = string; type ProjectionHash = string; type CapabilityVersion = string; type CompatibilityLevel = | "byte_compatible" | "parse_compatible" | "semantic_compatible" | "projection_compatible" | "replay_compatible" | "operationally_compatible" | "breaking"; type ChangeKind = | "add_optional" | "add_required" | "remove_field" | "rename_field" | "change_type" | "change_enum" | "change_default" | "change_semantics" | "change_order" | "change_limit" | "change_security";
```
```typescript
interface SchemaDescriptor { id: SchemaId; version: SchemaVersion; family: string; canonical: boolean; jsonSchema: JsonSchema; hash: SchemaHash; owner: string; source: ResourceSource; status: "draft" | "active" | "deprecated" | "retired"; compatibility: CompatibilityLevel; supportedReaders: string[]; supportedWriters: string[]; sensitivity: Sensitivity; createdAt: string; deprecatedAt?: string; retiredAt?: string; }
```
```typescript
interface SchemaChange { id: string; schemaId: SchemaId; from: SchemaVersion; to: SchemaVersion; changes: SchemaFieldChange[]; compatibility: CompatibilityLevel; migrationRequired: boolean; projectionImpact: "none" | "warning" | "required" | "unsafe"; persistedDataImpact: "none" | "read_only" | "backfill" | "dual_write" | "new_stream"; securityImpact: "none" | "review" | "redaction_change" | "egress_change"; evidenceRefs: EvidenceRef[]; }
```
```typescript
interface SchemaFieldChange { path: string; kind: ChangeKind; oldType?: string; newType?: string; requiredBefore?: boolean; requiredAfter?: boolean; semanticNote: string; safeForUnknownReader: boolean; }
```
```typescript
interface ProviderProjection { provider: string; apiFamily: string; deploymentClass?: string; canonicalSchemaId: SchemaId; canonicalSchemaVersion: SchemaVersion; projectionVersion: string; projectedSchema: unknown; projectionHash: ProjectionHash; droppedConstraints: string[]; warnings: Diagnostic[]; mode: "native_strict" | "native_relaxed" | "emulated" | "prompt_only" | "unsupported"; capabilitySnapshotId: string; redactionProfile: string; }
```
```typescript
interface SchemaRegistry { register(descriptor: SchemaDescriptor): Promise<RegistrationReceipt>; resolve(id: SchemaId, version?: SchemaVersion): Promise<SchemaDescriptor>; diff(from: SchemaRef, to: SchemaRef): Promise<SchemaChange>; compatibility(from: SchemaRef, to: SchemaRef): Promise<CompatibilityReport>; list(query: SchemaQuery): Promise<SchemaDescriptor[]>; }
```
```typescript
interface CompatibilityReport { from: SchemaRef; to: SchemaRef; level: CompatibilityLevel; readerResults: CompatibilityCheck[]; writerResults: CompatibilityCheck[]; projectionResults: ProjectionCompatibilityCheck[]; replayResults: ReplayCompatibilityCheck[]; failures: Diagnostic[]; generatedAt: string; }
```
## Request Schema
### Canonical ModelRequest
```typescript
interface ModelRequest { requestId: string; attemptId: string; contractVersion: SchemaVersion; model: ResolvedModel; messages: Message[]; tools?: ToolDefinition[]; responseFormat?: StructuredOutputRequest; modalities?: ModalityRequest; sampling?: SamplingOptions; contextPlan: ContextPlan; toolsetHash?: string; policySnapshotId: string; egressSnapshotId: string; timeoutMs: number; metadata?: ProviderNeutralRequestMetadata; }
```
### Request 演进规则
- 增加 optional metadata 通常是 additive。 - 增加 required message part、tool field 或 output requirement 通常是 breaking。 - 改变 role、part 顺序、tool result 配对和 approval 语义是 breaking。 - 改变默认 sampling 可能是 semantic change，即使 JSON shape 不变。 - 改变 `maxOutputTokens` 解释、单位或预算归属必须升级语义版本。 - 改变 `ArtifactRef` 的 view 语义必须触发 egress 与 replay 检查。
### Request Hash
Request hash 应覆盖：
```text
canonical request payload + schema version/hash + model/deployment snapshot + contextPlan hash + toolset hash + policy/egress snapshot hash + projection hash
```
不应把短期 credential 值、随机 trace ID 或 UI cursor 放入 request hash。
## Response Schema
### Canonical ModelResponse
```typescript
interface ModelResponse { responseId: string; attemptId: string; status: "complete" | "incomplete" | "refused" | "error"; items: ModelResponseItem[]; toolCalls: CanonicalToolCall[]; structured?: StructuredResult; finish: FinishState; usage?: Usage; providerMetadata?: ProviderMetadata; warnings: Diagnostic[]; rawReceipt?: RawResponseReceipt; }
```
### Response 兼容检查
必须分别检查：
- message/part 是否完整； - tool call 是否全部保留； - finish reason 是否可区分 stop、tool_calls、length、safety、refusal、cancelled； - structured result 是否经过 parse、schema、business validation； - usage 是否 observed、estimated 或 reconciled； - provider metadata 是否被保留； - unknown event 或 field 是否进入 diagnostic； - raw receipt 是否可访问但不越过 redaction。
### 不允许的降级
以下不可静默转换为成功：
- safety/refusal -> 空文本； - length truncation -> 完整 tool call； - JSON parse success -> schema valid； - tool call parsed -> tool executed； - stream EOF -> completed； - provider unknown outcome -> failed without evidence； - missing usage -> exact cost。
## Stream/Event Schema
### Canonical ModelEvent
```typescript
type ModelEvent = | ModelAttemptStarted | ContentPartStarted | TextDelta | ReasoningDelta | ToolCallStarted | ToolArgumentsDelta | ToolCallReady | CitationEvent | SafetyUpdate | UsageUpdated | ModelAttemptCompleted | ModelAttemptFailed | ModelAttemptCancelled | ProviderUnknownEvent;
```
```typescript
interface CanonicalEvent<T = unknown> { eventId: string; schemaVersion: SchemaVersion; kind: string; layer: "provider" | "kernel" | "harness" | "host"; durability: "durable" | "ephemeral"; attemptId: string; sequence: EventSequence; correlation: EventCorrelation; source: EventSource; security: EventSecurity; payload: T; extensions?: Record<string, unknown>; }
```
### Stream 版本规则
- 新增 optional event payload 字段通常为 minor。 - 新增可安全忽略的 event kind 需要 unknown 分支和监控。 - 改变 event 顺序、完成边界、call/result 配对或 terminal 语义是 major。 - terminal event 必须唯一且可查询。 - provider sequence gap 必须显式标记。 - delta coalescing 不能改变 canonical sequence 或最终内容 hash。
### Unknown Event 处理
```text
unknown optional field -> preserve metadata or ignore with diagnostic unknown event kind -> provider.event.unknown + rawRef unknown critical terminal -> fail/suspend attempt unknown schema major -> stop consumer and retain original event
```
## Tool Schema
### Canonical ToolDefinition
```typescript
interface ToolDefinition { identity: ToolIdentity; description: string; inputSchema: JsonSchema; outputSchema?: JsonSchema; semantics: ToolSemantics; execution: ToolExecutionSpec; result: ToolResultSpec; schemaVersion: SchemaVersion; provenance: ToolProvenance; }
```
### 工具 schema 演进
以下通常 backward compatible：
- 增加 optional input field，且执行器默认行为明确； - 扩展非安全敏感的 output metadata； - 增加可忽略的 provider projection hint。
以下通常 breaking 或需要新语义版本：
- 增加 required input； - 缩小 enum； - 改变字段含义或单位； - 改变 effect、repeatability、idempotency； - 改变 output status 或错误 code； - rename tool name； - 改变默认 target、路径或资源作用域。
### 双重校验
Provider 端 strict tool schema 只约束模型输出形状。
执行前仍必须：
```text
parse -> canonicalize -> schema validate -> business validate -> hook transform -> revalidate -> policy -> approval -> sandbox -> execute
```
### Tool Projection
```typescript
interface ToolSchemaProjector { project( spec: ToolDefinition, capabilities: ModelCapabilities, ): Promise<ProviderProjection>; }
```
不能安全降级的 `oneOf`、required、范围、enum、嵌套限制必须拒绝投影，而不是删除约束后继续执行。
## Structured Output Schema
### Canonical 请求
```typescript
interface StructuredOutputRequest { schemaId: SchemaId; schemaVersion: SchemaVersion; schema: JsonSchema; strict: boolean; name?: string; validationVersion: string; onFailure: "stop" | "retry_modified" | "fallback"; }
```
### 处理顺序
```text
canonical schema -> provider subset analysis -> native strict/relaxed/emulated decision -> request projection -> provider finish/safety check -> JSON parse -> local schema validation -> business validation -> durable structured result
```
### 兼容性规则
- strict -> relaxed 是降级，不是等价兼容。 - native -> prompt_only 必须改变 capability、warning 和验收标准。 - 修改 required、enum、additionalProperties、数组边界通常是 breaking。 - 增加 optional output field 对宽松 reader 可兼容，但对 exact golden 可能是 semantic diff。 - schema parse 失败和 provider refusal 必须使用不同错误类别。
## Multimodal Schema
### Canonical Part
```typescript
interface MultimodalPart { type: "image" | "audio" | "video" | "document" | "file"; source: { kind: "inline" | "artifact" | "url"; ref: string; }; mediaType: string; sizeBytes?: number; contentHash?: string; sensitivity: Sensitivity; egressView: "raw" | "sanitized" | "preview" | "summary" | "ref_only"; sourceVersion?: string; }
```
### 多模态演进注意
- MIME、尺寸、part 顺序和 source kind 是契约事实。 - URL 不能绕过 SSRF、redirect 和 provider egress policy。 - ArtifactRef 的 remote provider ID 不能替代本地 ArtifactRef。 - provider 不支持某 MIME 时返回 typed capability error。 - summary/thumbnail/ref-only 是显式 projection，不是“同一输入”。 - provider upload 成功但 model request 失败时，remote artifact 状态必须单独对账。 - 多模态 output 需要记录 part type、artifact hash、retention、delivery view。
## Provider Projection
### Projection 流程
```text
canonical request -> resolve capabilities -> validate egress/sensitivity -> project messages/parts -> project tool schemas -> project structured output -> project multimodal refs -> project generation parameters -> enforce provider limits -> compute projection hash -> compile raw request
```
### Projection 结果
必须包含：
- `projectedSchema`； - `projectionHash`； - `droppedConstraints`； - `warnings`； - `mode`； - `capabilitySnapshotId`； - `redactionProfile`； - `provider/apiFamily`； - `rawRequestRef` 或安全摘要。
### Projection 不变量
- canonical schema 永远保留。 - provider projection 不改变原始 semantic meaning；若无法保持则拒绝或显式 degrade。 - projection 结果被冻结到 Attempt。 - Run 中间 provider registry 变化不影响已有 Attempt。 - fallback 必须重新生成 projection，不复用不兼容 projection。 - provider-specific metadata 进入受控 ProviderPart 或 ProviderMetadata。
### API family 隔离
以下必须使用独立 adapter/profile：
- OpenAI Responses、Chat Completions、Realtime； - Anthropic Messages； - Gemini generateContent/streamGenerateContent； - Bedrock Converse/ConverseStream、InvokeModel； - Azure OpenAI/Foundry； - Vertex Generate Content； - OpenAI-compatible 托管端点。
“兼容”只表示部分 request shape 相似，不表示工具、流、错误、文件、usage、安全和 metadata 完全一致。
## 版本策略与 Compatibility Levels
### 版本维度
```text
canonical schema version provider projection version provider API version adapter version capability registry version event schema version session entry version checkpoint version artifact metadata version validator version pricing version
```
### L0 Byte-compatible
- 序列化字节相同； - 仅允许不影响内容的 metadata 外部存储变化； - 不应把字段顺序变化误判为业务兼容。
### L1 Parse-compatible
- 旧 reader 可解析新 payload； - 新 optional field 可被忽略； - unknown field 有上限和敏感度规则。
### L2 Semantic-compatible
- 旧 reader 忽略新字段后仍保持相同语义； - 默认值不改变行为； - status、effect、顺序、单位和错误语义未改变。
### L3 Projection-compatible
- 所有目标 provider projection 仍安全； - capability matrix 不需要降低 required capability； - dropped constraints 不增加安全风险。
### L4 Replay-compatible
- 旧 session/event/checkpoint 可读取； - projector 可重建； - tool call/result pair、branch head、usage 和 terminal state 不丢失。
### L5 Operationally-compatible
- dual-read/dual-write 可运行； - rollout 可暂停； - rollback reader 仍能读取新数据； - 指标、审计、redaction、quota、SLO 和 DR 不退化。
### L6 Breaking
- 需要新 stream、离线迁移、新 API family 或明确停机窗口； - 旧数据不能直接执行； - 旧 consumer 不能安全解释新语义； - 需要人工确认或长期兼容层。
## Additive 与 Breaking Change
### Additive 变更清单
可考虑 additive，但仍需验证：
- optional request field； - optional response metadata； - new provider extension field； - new unknown-safe event extension； - new output artifact reference； - new diagnostic reason code； - output object 增加非必需字段。
必须检查：
- unknown field budget； - redaction 是否覆盖； - structured validator 是否允许； - exact golden 是否需要更新； - provider projection 是否会误把 optional 变 required。
### Breaking 变更清单
- required field 增加； - 字段 rename/remove； - type 或单位改变； - enum 收窄； - nullable 改为 non-null； - default 改变行为； - finish/terminal 语义改变； - tool call/result pairing 改变； - event sequence 改变； - policy/approval/action hash 输入改变； - sensitivity、retention、egress 变宽或变窄； - ArtifactRef 逻辑身份或 version 语义改变； - unknown outcome 被重新解释为 success/failed。
### 变更审查问题
每项 change 必须回答：
1. 旧 reader 读到什么？
2. 新 writer 写什么？
3. 旧 provider projection 是否仍安全？
4. replay 是否仍能恢复？
5. unknown field 是否可能携带指令或 secret？
6. 是否改变 policy、approval 或 action hash？
7. 是否需要 dual-read/dual-write？
8. 是否需要迁移已有 artifact 或 checkpoint？
9. rollback 后旧版本能否读取新数据？
10. 失败时如何暂停、补偿和人工处置？
## Capability Negotiation
### 能力模型
```typescript
interface ModelCapabilities { textInput: boolean; textOutput: boolean; streaming: CapabilityLevel; tools: CapabilityLevel; parallelToolCalls: CapabilityLevel; structuredOutput: StructuredOutputCapability; multimodalInput: ModalityCapability[]; multimodalOutput: ModalityCapability[]; reasoningEvents: CapabilityLevel; usage: UsageCapability; cancellation: CapabilityLevel; maxContextTokens?: number; maxOutputTokens?: number; providerLimits: Record<string, unknown>; capabilityVersion: string; }
```
### 有效能力合取
```text
effective capability = catalog ∩ deployment ∩ credential ∩ tenant policy ∩ workspace policy ∩ host capability ∩ egress policy ∩ current quota/health
```
### 协商决策
```text
required feature -> canonical schema check -> provider projection check -> capability level check -> limit check -> egress check -> host delivery check -> accept | degrade with warning | reject
```
### 不能安全降级
以下必须 reject：
- strict structured output 变成 prompt-only，但产品要求 strict； - required tool constraint 被 provider 删除； - multimodal artifact 无法满足 data residency； - provider 无法表达 denied/cancelled/unknown tool result； - stream 无法识别 tool completion boundary； - context window 不足且 Context Runtime 无法安全压缩； - host 无法展示 required approval 或安全事件。
## Schema Registry
### Registry 记录
Registry 至少保存：
- descriptor、version、hash； - family、owner、source、provenance； - reader/writer ranges； - compatibility report； - projection profiles； - migration/upcaster references； - deprecation and expiry； - conformance status； - security review； - tenant visibility； - rollout assignment。
### 注册事务
```text
begin registry transaction -> load previous snapshot -> register candidate schemas -> compile validators -> run compatibility checks -> validate projection profiles -> validate policy/redaction hooks -> validate fixtures/goldens -> commit new snapshot failure -> dispose candidate handles -> restore previous snapshot
```
### Registry Snapshot
```typescript
interface SchemaRegistrySnapshot { id: string; version: string; schemas: SchemaDescriptor[]; projections: ProviderProjection[]; validators: ValidatorDescriptor[]; migrationPlans: MigrationPlanRef[]; hash: string; createdAt: string; }
```
Run 保存 snapshot ID/hash；运行中注册表变化只影响新 run 或显式 schema change entry。
## Validation 与 Unknown Fields
### Validation 分层
```text
wire decode -> envelope/schema validation -> canonical shape validation -> semantic validation -> capability/projection validation -> policy/egress validation -> business validation
```
### Validator 接口
```typescript
interface SchemaValidator<T = unknown> { validate(input: unknown, descriptor: SchemaDescriptor): ValidationResult<T>; validateUnknownFields(input: unknown, policy: UnknownFieldPolicy): UnknownFieldReport; }
```
### UnknownFieldPolicy
```typescript
interface UnknownFieldPolicy { mode: "reject" | "ignore" | "preserve_metadata" | "preserve_raw_ref"; maxFields: number; maxBytes: number; allowedPrefixes?: string[]; sensitivityCeiling: Sensitivity; criticalPaths: string[]; }
```
### 默认规则
- canonical request 的安全关键字段未知时 reject。 - provider response 的 optional unknown field 可 metadata-only 保存。 - unknown provider event 必须保留 kind、version、hash 和 rawRef。 - unknown enum 必须进入 `unknown` 分支，不能默认为第一个值。 - unknown field 不能自动进入 Prompt system section。 - unknown field 不能创建工具、approval、secret binding 或 policy exception。 - 深度、字段数、单字段 bytes 和总 payload bytes 必须有上限。 - unknown field 处理结果必须进入 diagnostics 和 conformance evidence。
### 语义校验
JSON parse、JSON Schema 和业务校验是三个不同层次：
```text
parse success != schema valid schema valid != capability compatible capability compatible != policy allowed policy allowed != side effect succeeded
```
## Provider Drift
### Drift Detection 输入
- raw response/stream fixture； - provider request/response schema； - finish reason； - event order； - usage shape； - tool call boundary； - structured output validation； - multimodal MIME/size； - error category； - provider API/SDK/model/deployment version。
### Drift Detector
```typescript
interface DriftDetector { compare(observed: ProviderObservation, baseline: ProviderBaseline): Promise<DriftReport>; classify(report: DriftReport): DriftClassification; openIncident(report: DriftReport): Promise<void>; }
```
### Drift 级别
```text
D0: metadata-only D1: additive optional field D2: warning/degradation D3: capability mismatch D4: protocol integrity failure D5: security/egress regression
```
### Drift 处理
- D0/D1：记录并进入 scheduled review。 - D2：降级、告警、保留旧 projection。 - D3：停止 affected capability，等待 adapter 更新。 - D4：暂停 attempt、保留 raw evidence、禁止执行不完整 tool call。 - D5：立即 fail-closed、暂停 rollout、创建 security incident。
### 不应做
- 不因一个未知字段立刻修改全局 canonical schema。 - 不因一个 429 将 schema drift 误判为协议 drift。 - 不用 golden 更新掩盖 event loss、usage loss 或 redaction regression。 - 不把 provider alias 的变化当成同一个 model snapshot。
## Migration、Dual-read 与 Dual-write
### Migration 类型
```text
read-time upcast offline copy migration online dual-read online dual-write backfill with verification new stream migration projection rebuild artifact view migration
```
### Upcaster
```typescript
interface Upcaster<T = unknown> { id: string; from: SchemaVersion; to: SchemaVersion; canHandle(input: unknown): boolean; upcast(input: T): T; verify(before: T, after: T): MigrationVerification; }
```
### Downcaster
Downcaster 只允许在：
- 目标旧 reader 明确支持； - 语义不会丢失； - 被删除字段不含安全关键事实； - projection diagnostics 能说明缺失； - 旧 provider 不会误执行； - 版本和用途明确。
不能将 breaking schema 任意 downcast 成旧 JSON。
### Dual-read
```text
read old + new -> normalize to canonical -> compare semantic hash -> record diff -> prefer new only after threshold
```
dual-read 期间必须记录：
- old parse outcome； - new parse outcome； - semantic diff； - missing/unknown fields； - redaction diff； - projection diff； - latency and error delta。
### Dual-write
```text
canonical input -> write old representation -> write new representation -> verify both hashes/semantic state -> commit one durable receipt
```
双写不是两个独立成功就算成功。
需要：
- 相同 idempotency key； - correlation/causation； - atomic outbox 或可补偿 transaction； - partial write recovery； - old/new write status； - replayable reconciliation。
### 双写失败
- old success/new failure：保留 old fact，标记 migration pending，加入补偿队列。 - new success/old failure：若旧 reader 仍必须支持，暂停新 writer 或回滚新 commit。 - 两者结果 semantic diff：停止 promotion，保留两份 evidence。 - 不允许把“至少写了一份”伪装成完整成功。
## Persisted Session/Event/Artifact Migration
### 迁移对象
必须盘点：
- SessionRecord、BranchRecord、RunRecord、TurnRecord、AttemptRecord； - User/Assistant/Tool semantic entries； - CanonicalEvent 与 ProviderEvent rawRef； - Checkpoint、CompactionEntry、WorkingState； - ContextPlan、PromptCompiled evidence、ToolsetSnapshot； - PolicySnapshot、Approval、SandboxAttestation； - ArtifactRef、ArtifactView、Snapshot、Patch； - UsageLedger、CostReceipt、DeliveryCursor； - MemoryRecord、embeddingVersion、forget tombstone； - Audit、Forensic Bundle、Evaluation fixture。
### 迁移顺序
```text
freeze migration scope -> snapshot source -> validate counts/hashes/ownership -> dry-run upcasters -> compare projections before/after -> migrate immutable copy or transactional partition -> verify replay/invariants/redaction -> dual-read -> switch writer -> monitor -> retain rollback window -> deprecate old reader
```
### Session/Event 约束
- 原始 event 不覆盖、不删除、不改 hash。 - migration 生成新 canonical view 或新版本 event。 - tool call/result pairing 必须保持。 - branch ancestor、head、sequence 和 CAS 版本必须保持。 - terminal uniqueness、unknown outcome、usage 和 cost 不得丢失。 - checkpoint 只有在 reducer/projector 兼容时才能直接使用。 - projector 失败时从旧 source event 重建，而不是手工修 projection。
### Artifact 约束
- artifact version immutable；修改生成新 version。 - raw、sanitized、summary、structured、preview view 必须分别迁移和验证。 - contentHash、artifactId、versionId、semanticHash 不混用。 - scan、redaction、retention、ACL、owner、tenant 和 expiry 迁移后复核。 - provider remote file ID 不能直接复用为本地 ArtifactRef。 - provider upload 状态未知时先 query/status，不盲目重传敏感内容。
### Memory 约束
- provenance、confidence、TTL、scope、sensitivity 和 consent 保留。 - semantic contradiction 不因格式迁移被静默覆盖。 - forgotten/tombstone 不得因 backfill 复活。 - embedding 需要记录版本和是否重算。
## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成
### Model Runtime
Model Runtime 使用：
- ResolvedModel； - ModelCapabilities； - SchemaRegistrySnapshot； - ProviderProjection； - CredentialLease； - EgressSnapshot； - Retry/Fallback policy。
Model Runtime 不自行修改 canonical schema，不在 adapter 内偷偷 fallback。
### Prompt
PromptCompiler 只描述 effective capability：
- provider 是否支持 tools； - structured output 是 native strict、relaxed、emulated 还是 unsupported； - reasoning、citation、grounding、safety 是否可见； - 多模态输入是完整、摘要、预览还是 ref-only； - 未知 provider field 被视为 metadata/data，而非 instruction。
Prompt 不负责：
- schema validation； - permission； - approval； - idempotency； - egress； - migration correctness。
### Context
ContextCompiler 负责：
- 根据 target model capability 选择资源； - 维护 tool call/result pair； - 计算 token/byte budget； - 生成 modality projection； - 处理 artifact summary/range/ref； - 执行 sensitivity、tenant 和 egress 过滤； - 在 context window 变化时产生 CompactionPlan 和新 context hash。
Schema Evolution 负责确保 `ContextPlan` 在不同 provider projection 中的字段语义可解释。
### Tool
Tool Runtime 使用 canonical tool schema；provider projection 只面向模型输入。
流程：
```text
ToolDefinition canonical -> active toolset snapshot -> provider projection -> model ToolCall -> local assembler -> canonical validation -> business validation -> policy/approval/sandbox -> execution/result
```
schema 变更若影响 effect、idempotency、risk、approval 或 output meaning，必须升级 Tool semantic version，并检查旧 transcript 恢复。
### State/Memory
State 必须保存：
- schema/version/hash； - request/projection/context/toolset hash； - attempt/model/provider/api family； - raw receipt、unknown fields 和 diagnostics； - migration/upcast/replay status； - dual-read/dual-write outcome； - terminal、usage、artifact 和 approval facts。
Memory 只作为 Context 候选，不能决定 schema、授权或 provider egress。
### Policy/Sandbox
Schema change 可能改变：
- action hash； - material parameters； - resource keys； - sensitivity； - approval scope； - sandbox profile； - result egress。
因此 policy 必须参与 compatibility review。
### Harness
Harness 装配顺序：
```text
resolve tenant/identity -> load policy/egress -> resolve model/routing -> load schema registry snapshot -> build active toolset -> compile ContextPlan/Prompt -> project provider request -> freeze run config -> start Kernel
```
运行中 schema registry 变化不影响当前 run，除非写入显式 `SchemaChangeEntry` 并重新 prepare/revalidate。
### Event/Observability
事件至少保留：
- schema ID/version/hash； - projection version/hash； - adapter/capability version； - old/new semantic hash； - unknown fields count/bytes； - drift class； - migration plan/run ID； - redaction state； - tenant/session/run/attempt IDs。
## 决策流程
### 新 schema 发布
1. 规范化变更目标和受影响 schema family。
2. 读取当前 schema、consumer range 和 provider projection。
3. 生成 field-level diff。
4. 判断 additive、semantic 或 breaking。
5. 运行 reader、writer、projection、replay 和 security compatibility。
6. 生成 migration、dual-read/dual-write 和 rollback plan。
7. 创建 fixtures、goldens、contract cases 和 conformance cases。
8. 通过 schema registry transaction 注册候选版本。
9. 进行 offline replay 和 shadow comparison。
10. 选择 canary scope、tenant、provider、model 和 host。
11. 观察错误、drift、schema invalid、unknown event、cost 和 latency。
12. 扩大 rollout 或暂停并回滚。
13. 进入 deprecation window。
14. 关闭旧 writer，保留旧 reader 与 forensic 读取能力。
15. 退休旧版本前完成 retention、replay 和 DR 验证。
### 请求前决策
```text
load frozen schema snapshot -> validate canonical request -> resolve model capabilities -> check provider projection -> check egress/redaction -> check policy/host/tool requirements -> choose strict/degraded/reject -> persist request/projection hashes
```
### provider 返回后决策
```text
decode raw frame -> validate event envelope -> detect unknown/drift -> normalize response/stream -> validate tool/structured/multimodal result -> reconcile usage -> classify error/finish -> commit durable result or unknown outcome
```
### 恢复时决策
```text
load checkpoint and schema snapshot -> verify registry compatibility -> verify policy/tenant/egress -> identify in-flight request/result -> query receipt/status -> upcast or mark migration_required -> resume safe boundary or manual review
```
## 生命周期与状态机
### Schema 生命周期
```text
Draft -> Validating -> Reviewed -> Registered -> Shadowing -> Canarying -> Active -> Deprecated -> Retired
```
### Migration 生命周期
```text
Planned -> Snapshotted -> DryRun -> DualRead -> DualWrite -> Backfill -> Verified -> Promoted -> RollbackWindow -> Completed -> Deprecated
```
### Projection 生命周期
```text
Requested -> CapabilityChecked -> EgressChecked -> Projected -> Validated -> Frozen -> Sent -> Normalized -> Reconciled -> Committed
```
### Drift 生命周期
```text
Observed -> Classified -> Diagnosed -> Mitigating -> AdapterPatched -> Replayed -> CanaryVerified -> Resolved
```
### 关键不变量
- 已发送 Attempt 的 schema/projection hash 不变。 - 不完整 tool call 不进入 Tool Runtime。 - terminal event 后不再接受业务 delta。 - unknown outcome 不自动转换为 success。 - migration 失败保留旧读路径。 - rollback 不删除已产生的新版本事实。 - 旧数据不能被新 projector 静默解释成不同语义。
## Rollout、Canary 与 Rollback
### Rollout 单位
可以单独 rollout：
- canonical schema； - provider adapter； - projection version； - validator； - event schema； - session projector； - artifact metadata； - tool schema； - structured output validator； - model capability catalog。
不要把所有变更绑定成一个不可拆分的大版本。
### Canary 条件
- 选择低风险 tenant/workspace/session； - 使用明确 provider/model/deployment allowlist； - 保持相同或更严格 policy/sandbox/egress； - Shadow 使用脱敏输入、fake/dry-run tool； - 记录 old/new semantic diff； - hard gate 监控未授权副作用、schema invalid、unknown outcome、redaction breach 和 event loss； - 可按 provider/API family/model/host 分桶。
### 自动暂停条件
- canonical event 无法被当前 projector 读取； - tool call/result pairing 下降； - structured output invalid rate 超阈值； - provider projection unsafe 增加； - unknown event 或 sequence gap 增加； - redaction 或 egress 失败； - usage/cost ledger 非幂等； - session migration projection mismatch； - unknown side effect 增加； - 多租户 scope 或 artifact ACL 违规。
### Rollback
Rollback 顺序：
```text
stop new writer/canary -> preserve durable evidence -> keep reader compatibility -> drain safe in-flight attempts -> classify unknown outcomes -> switch route/adapter/projection -> rebuild affected projections -> reconcile dual-write/backfill -> validate old reader -> reopen bounded traffic
```
Rollback 不等于删除新 event、artifact version、audit 或 usage。
### Rollback 前提
- 旧 reader 能读取新 payload，或 upcaster 已部署； - checkpoint 可从旧 reducer 重建； - provider projection 可切回旧版本； - dual-write 的新写入可补偿； - 已执行副作用有 status query 或 receipt； - artifact remote binding 有清理/过期策略； - operator runbook 与 owner 明确。
## 安全、隐私与 Redaction
### Schema 是数据边界
Schema field 必须声明：
- sensitivity； - purpose； - retention； - egress allowed view； - audit requirement； - provider visibility； - subagent inheritance； - log policy。
### Redaction 流程
```text
classify field -> tenant/scope check -> secret/PII/regulated detection -> field allowlist -> redact/tokenize/drop -> validate forbidden-field absence -> record redaction profile/hash -> route to sink
```
### 禁止内容
不得把以下内容写入普通 schema fixture、golden、trace 或日志：
- API key、bearer token、cookie； - 明文 secret binding； - 完整受监管内容； - 未脱敏 prompt、tool args、artifact 原文； - 可重放的生产 webhook、支付、部署参数； - 其他 tenant 的 resource ref； - 能改变 policy、approval、sandbox 的不可信内容。
### Unknown Field 安全
未知字段不能：
- 注册工具； - 创建 approval； - 扩大 tenant/session/workspace scope； - 改变 provider routing； - 选择 secret； - 关闭 sandbox 或 egress； - 覆盖 schema version； - 让 artifact 从 ref-only 变成 raw。
### Multi-tenant
Schema Registry、fixture、golden、projection cache、migration job、artifact、event、checkpoint、audit 和 report 都必须带 tenant/scope。
跨 tenant 复用 canonical schema 定义可以，但不能复用敏感 payload、缓存、approval、artifact view 或 provider prompt cache。
## 故障恢复与 Unknown Outcome
### 故障分类
```text
schema_parse_error schema_validation_error schema_compatibility_error projection_unsafe capability_mismatch unknown_field_overflow provider_schema_drift provider_protocol_error migration_required migration_failed dual_write_partial projection_rebuild_failed artifact_metadata_mismatch redaction_failed policy_version_conflict checkpoint_incompatible unknown_outcome
```
### Provider stream 故障
- 保存已接收 provider sequence； - 标记 open item/tool call； - 不执行未完成调用； - 保留 raw frame reference； - 记录 usage observed/estimated； - 按安全 retry policy 创建新 Attempt； - 若请求可能触发 provider-side job，先查询状态。
### Migration 故障
- 停止 promotion； - 保留 source snapshot； - 保留 old reader； - 标记 affected partition 为 migration_required； - 不删除半迁移新数据； - 使用 reconciliation job 比较 counts/hashes/semantic state； - 对不可恢复差异创建人工处置任务。
### Dual-write 崩溃窗口
最危险窗口：
```text
old write committed new write not committed
```
或：
```text
new write committed outbox/receipt not committed
```
恢复流程：
1. 查询 idempotency key；
2. 查询 old/new record；
3. 比较 semantic hash；
4. 补写缺失副本；
5. 写 migration recovery entry；
6. 若存在语义冲突，停止自动修复；
7. 不把 partial write 当 completed。
### Unknown outcome
- 不确定 provider 是否接受请求时，不能直接重发同一副作用请求。 - 不确定 artifact upload 是否完成时，按 remote ID/hash/size/expiry 查询。 - 不确定 tool result 是否持久化时，先读取 ExecutionRecord 和 durable event。 - 不确定 checkpoint 是否完整时，从上一可靠 cursor 重建。 - 不确定 migration 是否完成时，以 source/new snapshot 和 hash 对账。
## 可观测性、Audit 与 SLO
### Trace 层级
```text
session -> run -> schema.resolve -> compatibility.check -> projection.compile -> provider.attempt -> stream.normalize -> tool/structured/multimodal.validate -> migration -> replay/projector -> rollout/canary
```
### 必备字段
```text
tenant_id_hash session_id run_id turn_id attempt_id schema_id/version/hash change_id projection_version/hash provider/api_family/model/deployment adapter_version capability_version context_plan_hash toolset_hash policy_version egress/redaction profile unknown_field_count/bytes drift_class migration_id old/new semantic hash usage/cost latency error category rollback/canary id
```
### 指标
- schema validation success/failure； - compatibility pass/fail/skipped； - projection safe/degraded/unsupported； - unknown field count/bytes； - unknown event rate； - provider drift D0–D5； - tool call incomplete/invalid rate； - structured output invalid/refusal rate； - multimodal unsupported rate； - migration throughput/failure/lag； - dual-read semantic diff rate； - dual-write partial rate； - projection rebuild lag； - replay mismatch； - canary rollback count； - usage reconciliation drift； - artifact metadata/hash mismatch； - redaction failure和egress deny； - unknown outcome count。
### SLO
建议分别定义：
- canonical schema validation latency； - provider projection latency； - durable schema event append success； - migration recovery time； - projection rebuild completeness； - unknown field preservation rate； - conformance pass rate； - terminal event queryability； - cross-tenant schema artifact isolation； - redaction breach target 为零； - 未授权副作用 target 为零。
### Audit 必须回答
- 哪个 schema、版本和 projection 被使用？ - 哪个 provider/API family/model/deployment 接收了什么 view？ - 哪些 constraints 被删除或降级？ - 哪个 policy、egress、redaction 和 tenant snapshot 生效？ - 哪次 migration/upcast/dual-write 产生了什么结果？ - 谁批准了 breaking rollout？ - 哪些 session/event/artifact 被迁移、跳过或 quarantine？ - 是否出现 provider drift、unknown event 或 unknown outcome？
## 测试策略
### Testkit
必须提供：
```text
SchemaRegistryTestkit SchemaDiffEngine CompatibilityOracle FakeProviderAdapter RecordedRawFrameFixture ScriptedModelStream ProjectionHarness UnknownFieldFuzzer MigrationRunnerTestkit DualReadComparator DualWriteReconciler InMemoryEventStore CheckpointStore ArtifactMetadataStore DeterministicClock DeterministicIds CrashInjector RedactionScanner SideEffectRecorder ReplayRunner
```
### 单元测试
- schema descriptor、hash、version、registry transaction； - field diff、compatibility level、required/optional 变化； - unknown field policy、深度、字节和敏感度限制； - request/response/event validation； - tool call assembler 和完整性； - structured output strict/relaxed/emulated； - multimodal MIME、size、artifact view、egress； - projection dropped constraints 和 unsafe rejection； - capability intersection； - upcaster/downcaster invariants； - action hash 和 approval invalidation； - semantic hash、content hash、projection hash 区分。
### Provider Contract Tests
每个 provider/API family 必须覆盖：
1. 最小文本 request/response。
2. system/user/assistant/tool role 顺序。
3. 多 content parts。
4. 单工具、多工具、交错 delta。
5. arguments 任意分片、Unicode、转义和截断。
6. structured output native strict/relaxed/unsupported。
7. 图片、音频、视频、文档和 artifact ref。
8. usage 增量、最终、缺失和 reconciliation。
9. safety/refusal/length/context overflow。
10. 429、5xx、EOF、abort、timeout。
11. unknown field、unknown event、future version。
12. provider metadata、citation、grounding、reasoning 和 rawRef。
13. capability mismatch 早失败。
14. ToolResult status 和顺序。
15. tenant/egress/redaction 不泄漏。
### Migration Tests
- additive field 的旧 reader； - required field 的 breaking gate； - rename/type/default/enum/semantic change； - upcast idempotency； - dual-read equal/diff/missing/unknown； - dual-write partial commit； - old/new projection compare； - event replay before/after migration； - checkpoint source hash mismatch； - artifact view migration； - memory tombstone 不复活； - rollback reader 读取新写入； - migration pause/resume； - migration crash recovery。
### Security Tests
- unknown field 中的 prompt injection； - schema bomb、深层递归 JSON、超大数组和字段洪泛； - secret 出现在 schema example、golden、raw artifact、error、trace； - provider field 伪造 tenant、approval、policy 或 sandbox； - cross-tenant registry、fixture、artifact、cache、replay； - egress/redaction bypass； - provider URL、redirect、attachment 和 remote file 越权； - migration 复制受限数据到更宽 scope； - rollback 恢复旧 adapter 后执行不兼容 tool call。
### Fault Injection
在以下 boundary 注入 crash：
- schema registry commit 前后； - projection compile 后发送前； - provider accepted 后 response 前； - ToolCallReady durable commit 前后； - structured result validation 前后； - dual-write 第一副本/第二副本之后； - migration snapshot、backfill、verify、switch writer 之后； - checkpoint blob 和 reference 之间； - artifact metadata 与 blob 之间； - terminal event 和 usage settlement 之间； - canary promotion 和 rollback 之间。
断言：不丢 durable fact、不重复不可逆副作用、不把 unknown 当 success、不降低 redaction、不跨 tenant。
### Evaluation 集成
Evaluation 必须同时断言：
- request schema； - normalized events； - projection hash； - tool call/result； - structured validation； - multimodal view； - state/projector； - usage/cost； - migration/replay； - side-effect count； - security negative path。
LLM judge 只能评价开放式语义，不得判断 schema、权限、event order、真实副作用或迁移完整性。
## CI、Release Gates 与运维
### CI 层次
```text
lint/typecheck -> schema parse/compile -> compatibility diff -> validator/property tests -> provider fixture/golden -> contract/conformance -> migration replay -> security/fault injection -> cross-provider comparison -> canary smoke
```
### Hard Gates
以下必须阻断 merge/release：
- canonical schema 编译失败； - breaking change 未声明； - required projection constraint 被静默删除； - provider capability 声明与行为不一致； - 未完成 tool call 被执行； - event projector 无法读取新版本； - migration 丢 entry、usage、artifact ACL、terminal 或 approval； - dual-write 不可恢复； - redaction 或 tenant isolation 失败； - unknown outcome 被盲目重放； - conformance required case 失败； - rollback reader 无法读取 canary 数据。
### Soft Gates
可以作为 warning/review：
- optional provider capability 缺失； - event 粒度变化但语义保持； - latency/cost 基线轻微变化； - provider-specific metadata 增加； - golden 中可解释的非关键字段变化。
每个 soft gate 必须有 owner、reason、expiry 和用户可见 degradation。
### Release Evidence
发布包至少包括：
- schema registry snapshot； - compatibility report； - projection matrix； - conformance report； - migration dry-run report； - golden/fixture manifest； - security/redaction report； - canary result； - rollback test； - operator runbook； - known gaps 和 expiry。
### 运维动作
运维应能执行：
- 暂停新 writer； - 停止受影响 provider capability； - 切回旧 projection/adapter； - 重建 projector； - 重跑 migration reconciliation； - 查询 unknown outcome； - 导出最小 forensic bundle； - 暂停高风险 tool； - 只读恢复 session； - 逐租户回滚 canary； - 验证 artifact、usage、audit 和 tenant boundary。
不要通过手工改数据库 payload 解决 schema 漂移。
## 反模式
1. 把 Schema Evolution 当成给 JSON 增加字段。
2. 把 provider request JSON 直接保存为 session truth。
3. 只维护一个全局 schemaVersion，混淆 event、adapter、projection、model 和 pricing。
4. 只检查 JSON parse，不检查语义、能力、业务和安全。
5. Provider strict schema 成功后跳过本地 validation。
6. Tool schema 改 required 字段却不升级 tool semantic version。
7. Unknown event 静默丢弃。
8. Unknown field 无上限地进入 prompt、日志或 artifact。
9. Provider projection 删除约束后不记录 droppedConstraints。
10. 把 OpenAI-compatible 当作完整协议兼容。
11. 把不同 API family 共用同一个 raw parser。
12. 让 adapter 私自 fallback 或修改 tenant routing。
13. 迁移只验证 JSON 可解析。
14. 迁移直接覆盖 immutable event、audit 或 artifact version。
15. 双写两个独立提交，没有 outbox、idempotency 和 reconciliation。
16. migration 失败后删除旧读路径。
17. 旧 reader 不能读取新数据却直接扩大 canary。
18. Rollback 删除新事实，而不是切换 writer/reader。
19. 只测最终文本，不测事件、state、usage、artifact 和副作用。
20. Golden 更新用于掩盖 provider drift。
21. 把 schema downgrade 当作无害兼容。
22. 用当前 model alias 重放旧 session。
23. 迁移 artifact 时忽略 scan、redaction、retention 和 ACL。
24. 把 memory 内容当 schema authority。
25. 让 unknown provider field 创建 approval 或 secret binding。
26. 在 schema migration 中绕过 tenant、egress 或 sandbox。
27. 失败后重发可能已被 provider 接受的副作用请求。
28. 把 provider safety/refusal 当 JSON 校验失败重试。
29. 让 Host/UI 缓存决定 schema 真相。
30. 只依赖实时 provider smoke，不保留 deterministic fixture。
31. 用高基数 prompt、path、artifact URI 作为 metric label。
32. 没有 deprecation、owner、expiry 和迁移回滚窗口。
## 实施清单
### P0：Canonical Contract
- [ ] 定义 Message、Part、ModelRequest、ModelResponse、ModelEvent。 - [ ] 定义 ToolDefinition、ToolCall、ToolResult。 - [ ] 定义 StructuredOutputRequest、MultimodalPart、Usage、Error。 - [ ] 定义 schema ID/version/hash 和 registry snapshot。 - [ ] 区分 canonical schema、provider projection 和 raw payload。 - [ ] 区分 request/response/stream/tool/structured/multimodal family。 - [ ] 定义 unknown field/event policy 和大小上限。
### P1：Compatibility 与 Projection
- [ ] 实现 field-level diff 和 compatibility levels。 - [ ] 实现 reader/writer/projection/replay/security checks。 - [ ] 实现 ProviderProjection、droppedConstraints 和 projection hash。 - [ ] 为每个 API family 建独立 projection profile。 - [ ] 实现 capability negotiation 和 effective capability intersection。 - [ ] 将 provider-specific metadata 保留为 ProviderPart/ProviderMetadata。 - [ ] 建立 tool/structured/multimodal conformance。
### P2：Migration 与 Persisted State
- [ ] 实现 upcaster/downcaster registry。 - [ ] 实现 dual-read semantic comparator。 - [ ] 实现 dual-write outbox、idempotency 和 reconciliation。 - [ ] 迁移 Session/Event/Checkpoint/Artifact/Memory/Usage metadata。 - [ ] 维护 old reader、new writer 和 rollback window。 - [ ] 验证 replay、projector、branch、tool pair、terminal 和 usage。 - [ ] 维护 artifact scan/redaction/retention/ACL lineage。
### P3：Drift、Rollout 与安全
- [ ] 建立 provider drift detector 和 D0–D5 分类。 - [ ] 建立 fixture、golden、recorded replay 和 raw reference。 - [ ] 建立 shadow、canary、pause、rollback 和 incident runbook。 - [ ] 将 schema、projection、adapter、capability 版本接入 trace/audit。 - [ ] 建立 secret、PII、tenant、egress 和 redaction 测试。 - [ ] 在 provider outage、unknown outcome、migration crash 时 fail-closed。
### P4：CI 与运营
- [ ] 配置 presubmit、merge、scheduled、release gates。 - [ ] 维护 conformance report、known gaps、owner、expiry。 - [ ] 建立 migration dashboard、projection lag、drift、unknown event 告警。 - [ ] 建立 rollback reader 验证和 DR/restore replay。 - [ ] 建立最小 forensic bundle 和 operator diagnostic snapshot。 - [ ] 将生产反馈脱敏、最小化后加入 regression dataset。
## 五个参考项目的启发来源
### Pi
- headless agent loop 与统一 provider event 启发 canonical contract 和 provider projection 分离。 - session tree、Attempt、compaction entry 启发 persisted event、replay-compatible migration 和 durable checkpoint。 - CLI/TUI/RPC 共用 runtime 启发 Host 不应读取 provider raw schema。 - tool result 与 artifact offload 启发大型 response、日志和 raw payload 采用引用化保存。
### Grok Build
- HTTP、协议转换、sampler、actor 分层启发 transport、adapter、normalizer 和状态 owner 分离。 - permission decision、folder trust、sandbox 启发 schema capability 不等于 authorization。 - 并行工具、路径级锁和输出限制启发 tool schema、资源锁、预算和 unknown outcome 设计。 - 多阶段 compaction 和工具结果修剪启发 projection/summary 变化必须可观察、可验证。
### OpenCode
- provider、session、message/part、server/client 分离启发 canonical message/part 和 durable event/projector。 - durable event/projector 启发旧 schema 保留、projection rebuild 和 replay compatibility。 - snapshot/patch/revert 启发 artifact、workspace、checkpoint 和 schema migration 保留 base hash。 - MCP/LSP 与权限模块分离启发 adapter 不承担 policy、approval 和执行。
### Claude Code
- permission modes、hooks、skills、subagents、memory 和任务工作流启发 capability、context、policy、schema 和 scope 的联合装配。 - 项目规则与 auto memory 方向启发 provenance、trust、retention、deprecation 和最小上下文继承。 - 计划与验证工作流启发 acceptance criteria、fixture、evidence、CI gate 和 rollout review。 - 公开能力和安全语义以现有本地文档中标注的官方资料为准，辅助源码不作为规范。
### OpenClaw
- AgentHarness registry、agent-core、provider runtime 和 Gateway/channel 分层启发 schema registry、runtime factory 和 Host 解耦。 - tool、sandbox、elevated 分层启发 schema projection 不得覆盖执行安全边界。 - 后台运行、memory flush 和长生命周期任务启发 migration worker、lease、checkpoint 和恢复设计。 - 事务化插件注册启发 registry transaction、candidate snapshot、失败回滚和 provenance。
## Definition of Done
一份 Provider Schema Evolution 实现只有在以下条件同时满足时才算完成：
- canonical schema 与 provider projection 清晰分离； - request/response/stream/tool/structured/multimodal 均有版本和接口； - compatibility level 可由自动化报告证明； - unknown field/event 有安全策略和诊断； - capability negotiation 在请求前阻止 unsafe projection； - provider drift 有 fixture、golden、conformance 和告警路径； - session/event/checkpoint/artifact/memory/usage migration 可 dry-run、暂停、恢复和回滚； - dual-read/dual-write 不丢 durable fact、不重复副作用； - redaction、tenant、egress、policy、approval 和 sandbox 不被迁移绕过； - canary、rollback、CI release gate 和 on-call runbook 可执行； - 测试覆盖正常、边界、故障、恢复、未知事件和安全负向路径； - 任何“模型说成功”的结论都不能替代 schema、event、state、artifact、receipt 和 side-effect evidence。
