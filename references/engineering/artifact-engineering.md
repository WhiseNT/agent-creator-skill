# Artifact Engineering 细粒度工程设计
> 本文定义 Agent Harness 中 Artifact 的完整工程语义。它沿用本地参考文档中的
`ArtifactRef`、`ArtifactStore`、`ContentPart`、`ContextPlan`、`SessionEntry`、`Snapshot`、`Patch`、`ToolResult`、`Checkpoint`、`Projection`、`Sensitivity`、`RetentionPolicy`、durable/ephemeral event 和 egress policy 术语。
>

>
Artifact 不是把大文本简单丢到磁盘。它是带内容身份、版本、范围、权限、敏感度、生命周期、传输、预览、审计和恢复语义的独立资源系统。本文只使用当前目录已有参考架构、Agent Harness 以及 Prompt、Context、Tool、State/Memory、Permission/Sandbox、Subagent、Event/Observability、Evaluation 文档中的本地调研结论，不依赖 README，不新增网络搜索结论。
## 目录
1. [设计目标与非目标](#设计目标与非目标) 2. [Artifact 的定义与分类](#artifact-的定义与分类) 3. [职责边界](#职责边界) 4.

[总体架构与包布局](#总体架构与包布局) 5. [核心数据模型与 TypeScript 接口](#核心数据模型与-typescript-接口) 6. [ArtifactRef 与引用语义](#artifactref-与引用语义) 7. [ArtifactStore 与后端端口](#artifactstore-与后端端口) 8. [内容寻址、版本与去重](#内容寻址版本与去重) 9. [大小、分片与 Token Budget](#大小分片与-token-budget) 10. [Model-facing、User-facing 与 Durable](#model-facinguser-facing-与-durable) 11. [范围、权限、租户与敏感度](#范围权限租户与敏感度) 12. [TTL、Retention 与垃圾回收](#ttlretention-与垃圾回收) 13. [上传、下载与流式传输](#上传下载与流式传输) 14. [Range、断点续传与校验](#range断点续传与校验) 15. [MIME、预览与内容检测](#mime预览与内容检测) 16. [安全扫描、脱敏与外发](#安全扫描脱敏与外发) 17. [Snapshot、Patch、Merge 与 Revert](#snapshotpatchmerge-与-revert) 18. [Artifact 生命周期与状态机](#artifact-生命周期与状态机) 19. [跨 Session、Subagent 与 Provider](#跨-sessionsubagent-与-provider) 20. [与 Context、Prompt、Tool、State、Policy、Harness 集成](#与-contextprompttoolstatepolicyharness-集成) 21. [事件、审计与可观测性](#事件审计与可观测性) 22. [故障恢复](#故障恢复) 23. [测试策略](#测试策略) 24. [反模式](#反模式) 25. [实施清单](#实施清单) 26. [五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与非目标
### 目标
Artifact 子系统必须能够： 表达 text、diff、log、image、binary、structured 等不同内容类型； 为大工具输出、命令日志、代码 patch、快照、测试报告和交付物提供统一引用； 使用内容 hash、版本、大小、MIME、来源和作用域保证可验证身份； 将模型可见摘要、用户可见预览、durable 原始内容和诊断副本分离； 在 context/token budget 之外保留大内容，并按需要选择片段、摘要或 range； 强制租户、session、run、subagent、provider 和 host 的访问边界； 支持流式上传、下载、range、断点续传和完整性校验； 对文件、图片、二进制、压缩包和结构化数据执行 MIME sniff、安全扫描和脱敏； 支持 snapshot、patch、merge、revert 的 base hash 和冲突语义； 在跨 session、subagent、provider 复用时保留 owner、scope、expiry 和 egress 决策； 通过 artifact event、audit、trace、retention 和垃圾回收实现可运营治理； 在上传失败、扫描失败、provider 断线、worker 崩溃和引用失效时安全恢复。

### 非目标
Artifact 不负责： 取代 `SessionRepository` 保存语义 transcript； 取代 `ContextCompiler` 选择所有上下文； 把 artifact URI 当作用户拥有的永久公共 URL； 只用文件名或路径作为身份； 以 prompt 文字代替访问控制、敏感度和 egress policy； 将 secret、完整 reasoning 或所有工具输出默认持久化； 让 provider 直接读本地磁盘； 把 snapshot/patch 当作任意外部副作用的回滚保证； 允许 child session 自动继承父 artifact bucket； 只因为 MIME 名称可信就跳过内容检测。
### 核心判断
```text

Artifact = content identity + typed metadata + access scope + sensitivity/egress + version/retention + transport and range + preview/projection + audit/recovery
```
Artifact 不等于“把大文本写到磁盘”。磁盘只是某个 `StorageBackend`，不能代表引用、权限、版本或生命周期语义。
## Artifact 的定义与分类

### 六类基础分类
#### Text
源代码、文档、提示、摘要、自然语言报告、stdout/stderr 文本。 要求：编码、行/字符索引、语言、换行规范和脱敏状态可追踪。
#### Diff

unified diff、结构化编辑操作、三方合并结果、revert patch。 要求：base snapshot、affected paths、patch hash、apply status 和冲突信息。
#### Log
命令、测试、构建、lint、sandbox、MCP、provider 和审计诊断日志。 要求：时间、来源、退出状态、序列、截断标记和原始大小可追踪。
#### Image

截图、图表、OCR 输入、模型生成或工具产生的图片。 要求：MIME、像素、颜色空间、元数据、预览和恶意内容扫描。
#### Binary
压缩包、编译产物、数据库快照、音视频、模型文件或任意非文本 blob。 要求：大小上限、magic bytes、下载范围、病毒/恶意载荷扫描和 provider 能力检查。
#### Structured

JSON、JSONL、CSV、XML、SARIF、JUnit、coverage、评测结果、工具结构化输出。 要求：schema/version、编码、字段脱敏、可分页/可查询投影和校验。
### 类型不能只看扩展名
```text
filename extension + declared mediaType + magic bytes + decoder result + content policy -> canonical artifact classification

```
不一致时记录 diagnostic；高风险 binary、压缩包、脚本和可执行内容默认进入 quarantine 或 deny。
### 内容视图
同一 artifact 可拥有多个逻辑视图：

```text
raw content -> sanitized content -> structured projection -> model summary -> user preview -> range/chunk view
```
每个视图都必须有独立 hash/version 或明确声明派生关系。

## 职责边界
| 模块 | 负责 | 不负责 |
|---|---|---|
| `ArtifactRegistry` | ref、owner、scope、version、状态索引 | 保存实际 blob |

| `ArtifactStore` | put/get/range/delete/verify | 决定模型看到什么 |
| `ContentIngestor` | 流式接收、hash、大小、类型识别 | 绕过 quota |
| `Scanner` | MIME、恶意内容、secret/PII、压缩炸弹检测 | 授权跨租户访问 |
| `Redactor` | field/文本/图像脱敏和 redaction map | 反向泄露原文 |

| `Previewer` | 安全预览、缩略图、摘要、分页 | 修改原始 artifact |
| `ArtifactProjector` | session/run/tool/context 视图 | 创建事实内容 |
| `ReferenceAuthorizer` | tenant、scope、principal、egress 检查 | 生成 patch |
| `TransferManager` | upload/download/stream/range/resume | 修改 session truth |

| `SnapshotStore` | tree/resource 状态快照 | 自动执行回滚副作用 |
| `PatchStore` | patch、base hash、apply/reject/conflict | 代替业务 merge |
| `GarbageCollector` | TTL、引用计数、墓碑和清理 | 删除仍被 durable 引用的事实 |
| `AuditWriter` | 访问、导出、删除、扫描、权限变更记录 | 普通 debug log |

| `ContextCompiler` | 选择摘要/片段/ref 并分配 token | 强制持久化任意内容 |
| `Harness` | 生命周期、预算、恢复、事件和策略装配 | 变成 blob 数据库 |
强制边界：
```text

ArtifactRef identifies. ArtifactStore stores. Policy authorizes. Scanner classifies. Redactor transforms. ContextCompiler projects. State records semantic references. Harness supervises lifecycle.
```
## 总体架构与包布局
```text

Tool/Command/Provider/Host/Subagent | Artifact Ingest API | Type/Size/Hash/Scan/Redact | Artifact Registry + Metadata DB | Blob Storage / Local Store / Remote Store |          |             | Previewer   Transfer       GC/Retention | Context/Prompt/State/Event/Delivery Projections
```
推荐包布局：
```text

packages/artifact/ contracts.ts identity.ts registry.ts store.ts ingest.ts transfer.ts ranges.ts mime.ts scanner.ts redaction.ts preview.ts projections.ts retention.ts gc.ts snapshot.ts patch.ts merge.ts authorization.ts audit.ts providers/ backends/ testkit/
```
依赖方向：
```text

Context/Tool/State/Harness -> Artifact ports Artifact adapters -> filesystem/object store/provider file API
```
Kernel 只接收 `ArtifactRef`、摘要或 `ContentPart`，不导入对象存储 SDK、临时路径或数据库 schema。
## 核心数据模型与 TypeScript 接口

### 标识、类型与敏感度
```typescript
type ArtifactId = string; type ArtifactVersionId = string; type ArtifactViewId = string; type TransferId = string; type ScanId = string; type SnapshotId = string; type PatchId = string; type TenantId = string; type SessionId = string; type RunId = string; type SubagentRunId = string; type ArtifactKind = | "text" | "diff" | "log" | "image" | "binary" | "structured"; type Sensitivity = | "public" | "internal" | "confidential" | "secret" | "regulated";
```

### ArtifactRef
```typescript
interface ArtifactRef { id: ArtifactId; versionId: ArtifactVersionId; uri: string; kind: ArtifactKind; mediaType: string; charset?: string; size: number; contentHash: string; semanticHash?: string; summary?: string; sensitivity: Sensitivity; scope: ArtifactScope; owner: ArtifactOwner; status: ArtifactStatus; createdByRunId?: RunId; sourceRef?: SourceRef; retention: RetentionPolicy; expiresAt?: string; scan: ScanSummary; views: ArtifactViewRef[]; }
```

`id` 是逻辑对象身份，`versionId` 是不可变内容版本，`contentHash` 是原始或 canonical content 的 hash，不能混用。
### Scope 与 Owner
```typescript
interface ArtifactScope { tenantId: TenantId; visibility: "private" | "session" | "branch" | "run" | "subagent" | "workspace" | "organization" | "public"; sessionId?: SessionId; branchId?: string; runId?: RunId; subagentRunId?: SubagentRunId; workspaceId?: string; } interface ArtifactOwner { principalId: string; component: "user" | "agent" | "tool" | "subagent" | "system" | "provider"; createdBy: string; delegatedFrom?: string; }

```
### Artifact 状态
```typescript
type ArtifactStatus = | "uploading" | "pending_scan" | "available" | "restricted" | "quarantined" | "expired" | "deleting" | "deleted" | "corrupt";

```
### 来源与派生
```typescript
interface SourceRef { kind: "tool_result" | "command" | "file" | "message" | "snapshot" | "patch" | "provider" | "subagent" | "upload"; id: string; version?: string; contentHash?: string; } interface ArtifactDerivation { parent: ArtifactRef; operation: "summary" | "redaction" | "preview" | "thumbnail" | "structured_projection" | "compression" | "patch" | "merge"; toolVersion: string; parametersHash: string; derivedAt: string; }

```
### View
```typescript
interface ArtifactViewRef { id: ArtifactViewId; kind: "raw" | "sanitized" | "preview" | "summary" | "structured" | "thumbnail" | "range"; artifact: ArtifactRef; contentHash: string; mediaType: string; sensitivity: Sensitivity; tokenEstimate?: number; expiresAt?: string; }

```
## ArtifactRef 与引用语义
### URI 不是直接文件路径
`ArtifactRef.uri` 是可授权解析的逻辑 URI，不保证是公开 URL 或本地路径。

```text
artifact://tenant/<artifact-id>/versions/<version-id>
```
解析必须经过：

```text
authenticate principal -> authorize tenant/scope -> verify ref status/version/hash -> select permitted view/backend -> issue bounded read capability
```
### 引用不变量

ref 中的 tenant、owner、scope 不能被调用参数覆盖； expired/deleted/quarantined ref 不能假装 available； 逻辑 artifact 删除后，审计和 durable entry 可保留 tombstone； version 不可变；修改产生新 version； 视图不能提升敏感度或权限； 子 Agent 只能访问 assignment 授予的 ref/range； provider 只能收到 egress policy 允许的 view； user-facing 链接必须是短 TTL、授权和可撤销的。
### Ref 与 ContentPart
```typescript
type ContentPart = | { type: "text"; text: string } | { type: "artifact"; ref: ArtifactRef; presentation: "inline" | "link" | "model_summary" } | { type: "image"; ref: ArtifactRef; alt?: string } | { type: "structured"; ref: ArtifactRef; schema?: string };

```
模型拿到 artifact ref 时，prompt/context 必须说明：它看到的是摘要、预览、range 还是完整内容。
## ArtifactStore 与后端端口
### 基础端口

```typescript
interface ArtifactStore { begin(input: ArtifactInput): Promise<UploadSession>; put(input: ArtifactInput): Promise<ArtifactRef>; get(ref: ArtifactRef, options?: ReadOptions): Promise<ArtifactChunk | ArtifactStream>; stat(ref: ArtifactRef): Promise<ArtifactMetadata>; list(query: ArtifactQuery): Promise<ArtifactRef[]>; verify(ref: ArtifactRef): Promise<VerificationReceipt>; delete(ref: ArtifactRef, reason: string): Promise<void>; }
```
### 输入与读取

```typescript
interface ArtifactInput { kind: ArtifactKind; mediaType: string; source: ArtifactSource; scope: ArtifactScope; owner: ArtifactOwner; sensitivity: Sensitivity; retention: RetentionPolicy; expectedHash?: string; expectedSize?: number; metadata?: Record<string, string>; } type ArtifactSource = | { type: "bytes"; value: Uint8Array } | { type: "stream"; value: AsyncIterable<Uint8Array> } | { type: "file"; path: string } | { type: "remote"; uri: string; headersRef?: string }; interface ReadOptions { range?: ByteRange; view?: "raw" | "sanitized" | "preview" | "summary" | "structured"; acceptMediaTypes?: string[]; maxBytes?: number; signal?: AbortSignal; }
```
### Backend 类型

```typescript
interface ArtifactBackend { capabilities(): ArtifactBackendCapabilities; createUpload(input: UploadDescriptor): Promise<UploadSession>; uploadPart(session: UploadSession, part: UploadPart): Promise<PartReceipt>; completeUpload(session: UploadSession): Promise<BackendObjectRef>; read(ref: BackendObjectRef, range?: ByteRange): AsyncIterable<Uint8Array>; delete(ref: BackendObjectRef): Promise<void>; health(): Promise<BackendHealth>; }
```
后端可以是 local file、SQLite/blob、object store、remote worker 或 provider file API，但其差异必须在 adapter 内封装。

### Registry 与 Blob 分离
Registry 保存： ref、hash、version、scope、owner、状态和 retention； backend ref、扫描、预览、派生和审计引用； size、MIME、schema、来源和版本。 Blob backend 保存： 实际 bytes、分片、压缩和加密对象。 不能只在磁盘目录中推断 artifact 状态。
## 内容寻址、版本与去重
### Content Addressing

canonical hash 至少覆盖：
```text
content bytes + canonical encoding rule + media type policy + optional schema version
```

建议使用带算法前缀的 hash：
```text
sha256:<digest>
```

算法升级产生新 hash 表示，不覆盖旧对象。
### 逻辑 ID 与内容 hash
同一内容可以有多个逻辑 artifact： 不同 session、owner、scope 或 retention； 同一 artifact 的不同版本； 同一原文的不同脱敏 view。 因此：
```text

contentHash != artifactId != versionId != semanticHash
```
### Version
```typescript

interface ArtifactVersion { artifactId: ArtifactId; versionId: ArtifactVersionId; parentVersionId?: ArtifactVersionId; contentHash: string; size: number; sourceHash?: string; schemaVersion?: string; createdAt: string; immutable: true; }
```
修改 artifact 必须创建新 version，并在 session/event 中记录 parent version。
### 去重策略

内容去重可以复用 blob，但不能合并权限： registry ref 仍按 tenant、scope、owner 隔离； 访问检查在 logical ref 层完成； secret、regulated 和高敏感内容默认不跨 owner dedupe； 删除一个 ref 不删除仍被其他 ref 引用的 blob； dedupe 命中、拒绝和清理由 audit/metric 记录。
## 大小、分片与 Token Budget
### 三种预算
```text

byte budget        storage/transport/scan limit token budget       model context projection limit resource budget    CPU/memory/disk/scan/preview limit
```
artifact size 不等于 token 数。二进制和图片可能没有直接 token 估算，需要 provider-specific projection。
### SizePolicy

```typescript
interface ArtifactSizePolicy { maxBytesByKind: Record<ArtifactKind, number>; maxParts: number; maxPartBytes: number; maxExpansionRatio: number; maxPreviewBytes: number; maxModelTokens: number; overflow: "reject" | "truncate" | "offload" | "quarantine"; }
```
### Token Projection

```typescript
interface ArtifactProjectionRequest { ref: ArtifactRef; target: "model" | "user" | "trace" | "audit"; tokenBudget?: number; byteBudget?: number; range?: ByteRange; summaryPolicy?: string; } interface ArtifactProjection { ref: ArtifactRef; view: ArtifactViewRef; content: ContentPart[]; truncated: boolean; originalSize: number; retainedRange?: ByteRange; diagnostics: Diagnostic[]; }
```
### 超预算降级顺序

```text
remove duplicate metadata -> choose existing summary/preview -> select relevant range/pages/items -> structured projection -> semantic summary -> artifact reference only -> deny if required content cannot be safely projected
```
不要从大文本尾部机械截断；不要切断 diff header、JSON object、日志错误上下文或 tool call/result 对。

## Model-facing、User-facing 与 Durable
### 三个面
#### Model-facing
模型需要最小、可行动的信息： summary、structured fields、错误 code、首个失败、相关 range； `ArtifactRef`、size、truncated、original size 和下一步读取建议； 不暴露 secret、无关原始日志、宿主路径和完整敏感参数。

#### User-facing
用户需要可审查和可交付内容： diff、报告、日志、图片预览、下载/打开动作； artifact 名称、大小、来源、敏感度和有效期； 测试退出码、时间、命令和关键诊断； 权限不足、扫描 quarantine 和下载失败的解释。
#### Durable
状态和审计需要： immutable ref/version/hash； source、owner、scope、retention； scan/redaction/projection lineage； session/run/tool/checkpoint/patch 引用； 删除、访问、导出和恢复事实。 三者可以引用同一 blob，但不得假设内容、权限和生命周期相同。

### ToolResult 分层
```typescript
interface ArtifactBackedToolResult { callId: string; summary: ContentPart[]; structured?: unknown; modelArtifacts: ArtifactRef[]; userArtifacts: ArtifactRef[]; diagnostics: ArtifactRef[]; truncation?: TruncationMetadata; }
```

## 范围、权限、租户与敏感度
### Scope 层级
```text
global organization user workspace directory session branch run subagent turn

```
Artifact scope 不能自动向上升级。父 scope 可把受限 range 授予 child，但不能授予整个 bucket。
### Authorization
```typescript

interface ArtifactAuthorizationRequest { principal: PrincipalRef; action: "stat" | "read" | "range" | "preview" | "download" | "share" | "derive" | "delete"; ref: ArtifactRef; purpose: "model" | "user" | "tool" | "subagent" | "audit" | "recovery"; targetProvider?: ModelRef; hostCapabilities?: HostCapabilities; } interface ArtifactAuthorizationDecision { decision: "allow" | "allow_view" | "allow_range" | "redact" | "deny"; decisionId: string; view?: ArtifactViewRef; obligations: Obligation[]; expiresAt?: string; }
```
### Tenant 隔离
所有 registry、blob、preview、event、audit、GC 和 query API 都必须带 tenant scope。 不能依赖调用方记得过滤，也不能用 artifact URI 中的 tenant 字符串代替认证。

### Sensitivity
```text
public internal confidential secret regulated
```

等级决定： 是否允许 provider egress； 是否可进入 model context； 是否可被 user host 下载； 是否可被 subagent 继承； 是否可写长期 session/memory； 是否写 trace、log、audit； TTL、加密、删除和人工审批。 secret 和 regulated 默认 `artifact_only` 或 `deny`，不自动进入模型。
## TTL、Retention 与垃圾回收
### Retention
```typescript

type RetentionPolicy = | { type: "until_run_end" } | { type: "until_session_end" } | { type: "until_task_end" } | { type: "ttl"; expiresAt: string } | { type: "until_referenced" } | { type: "legal_hold"; reason: string } | { type: "never_persist" };
```
### 引用关系
GC 需要区分： live logical ref； semantic session entry； checkpoint； patch/snapshot； child result； active transfer； preview/derived view； audit/legal hold。 删除不能只看文件 mtime。

### GC 流程
```text
scan expired candidates -> load durable references and holds -> mark deleting -> block new reads -> delete derived views -> delete backend object if unreferenced -> append tombstone/audit -> verify deletion
```

### GC 状态
```text
Available -> Expired -> Deleting -> Deleted Available -> LegalHold Deleting -> Quarantined | FailedCleanup
```

GC 失败不得把仍可读的 ref 标成 deleted；孤儿 blob 进入重试或隔离队列。
### 最小 tombstone
可因隐私删除原文，但保留最小 tombstone： artifact ID/version； deletedAt、reason、requestedBy； hash 或 keyed hash； 关联 session/event ID； 防止旧 URI 复活的否定记录。
## 上传、下载与流式传输

### Upload 生命周期
```text
Create upload session -> authorize scope/size -> stream bytes -> compute hash/size -> persist parts -> complete upload -> MIME/type detection -> scan/redact policy -> publish available ref
```

在扫描完成前不能向模型或外部 host 宣称 artifact available。
### UploadSession
```typescript
interface UploadSession { id: TransferId; artifactDraftId: string; expectedSize?: number; expectedHash?: string; partSize: number; receivedParts: number[]; expiresAt: string; status: "open" | "completed" | "aborted" | "expired"; }

```
### 流式接口
```typescript
interface ArtifactTransferManager { upload(input: ArtifactInput, signal?: AbortSignal): Promise<ArtifactRef>; resumeUpload(session: UploadSession, signal?: AbortSignal): Promise<ArtifactRef>; download(ref: ArtifactRef, options: ReadOptions, signal?: AbortSignal): AsyncIterable<Uint8Array>; resumeDownload(ref: ArtifactRef, cursor: TransferCursor, signal?: AbortSignal): AsyncIterable<Uint8Array>; }

```
### Backpressure
bounded in-memory buffers； provider、scanner、previewer 和 backend 使用流式管道； slow consumer 不阻塞 durable writer； 高频 progress 可 coalesce； bytes 超预算立即停止或转 quarantine； 每个 stage 暴露 queue depth、lag 和 dropped/coalesced 计数； cancellation 传播到 reader、scanner、backend 和 child process。
## Range、断点续传与校验

### ByteRange
```typescript
interface ByteRange { start: number; endExclusive: number; } interface TransferCursor { transferId: TransferId; versionId: ArtifactVersionId; nextOffset: number; prefixHash?: string; lastPartHash?: string; }
```

### Range 语义
range 必须在 artifact version 内； 返回实际 `content-range`、总 size、version 和 hash； 文本 range 需要声明 byte/line/character 语义； structured range 需要声明 item/page/cursor 语义； image/binary 不应把任意 byte range 当可预览内容； range 读仍要执行授权、敏感度和扫描状态检查。
### 断点续传
上传恢复要求： session 未过期； tenant、owner、draft 和 expected hash 一致； 已收 part hash 可验证； part 顺序和大小合法； complete 时全量 hash 与 expected hash 匹配。 下载恢复要求： version 未变化； cursor 未超 retention； 客户端重新认证； 断点前后 hash 可对账； 发现内容变化时拒绝拼接旧新 version。

## MIME、预览与内容检测
### 检测流程
```text
declared mediaType -> extension metadata -> magic bytes -> safe decoder -> canonical type -> preview policy

```
### Previewer
```typescript
interface Previewer { canPreview(ref: ArtifactRef): Promise<boolean>; preview(ref: ArtifactRef, options: PreviewOptions): Promise<ArtifactViewRef>; } interface PreviewOptions { maxBytes: number; maxTokens?: number; page?: number; lineRange?: [number, number]; redact: boolean; target: "model" | "user" | "trace"; }

```
### 文本预览
检查 UTF-8/编码； 记录行范围和原始 byte range； 保留错误上下文； 对 source code 标记 path/commit/snapshot； 不把注释中的指令提升为 authority。
### Diff 预览

校验 base snapshot； 展示 affected paths、添加/删除行和冲突； 大 diff 按文件/symbol/range 分页； 生成 user-facing 和 model-facing 两种视图； 不能把“预览成功”当作 patch 已应用。
### Image 预览
限制像素、解码时间和输出大小； 去除或策略化保留 EXIF/GPS/隐藏元数据； 生成缩略图派生 artifact； OCR 文本作为不可信数据； provider 不支持时返回 thumbnail、summary 或 ref。
### Structured 预览

schema/version 验证； 字段级 allowlist 和分页； 大数组按 item range； 无效 JSON 保存 raw diagnostic，但不生成可信 structured view； CSV/XML 需要解析资源上限。
## 安全扫描、脱敏与外发
### 扫描阶段
```text

size/decompression limits -> MIME/magic validation -> malware/executable scan -> secret/PII/regulated detection -> prompt injection markers as diagnostic -> schema validation -> policy classification -> available/restricted/quarantine
```
扫描结果是 artifact 状态事实，不能只写普通 log。
### ScanSummary

```typescript
interface ScanSummary { status: "pending" | "passed" | "failed" | "partial" | "skipped"; scannerVersion: string; findings: ScanFinding[]; completedAt?: string; contentHash: string; } interface ScanFinding { code: string; severity: "info" | "low" | "medium" | "high" | "critical"; range?: ByteRange; action: "allow" | "redact" | "restrict" | "quarantine" | "deny"; }
```
### Redaction

```typescript
interface RedactionPolicy { profile: string; fields: string[]; patterns: string[]; replacement: "placeholder" | "hash" | "drop"; preserveMap: boolean; reversibleInsideTrustedBoundary: boolean; } interface RedactionRecord { source: ArtifactRef; derived: ArtifactRef; policyVersion: string; findings: string[]; mapRef?: ArtifactRef; }
```
redaction map 只在可信边界保存；外发 artifact 不应携带可恢复原文的 map。

### Egress 决策
```text
resource sensitivity + destination/provider/host + tenant policy + purpose + retention -> full | redacted | summarized | ref_only | deny
```

Provider tool/file API 不能绕过本地 Artifact Authorization 和 egress policy。
### Prompt Injection
Artifact 中的代码注释、日志、文档、OCR、MCP 结果或测试失败文本只能作为数据： 不能注册工具； 不能修改 policy/sandbox； 不能创建 approval； 不能要求外发 secret； 不能改变 artifact owner/scope。
## Snapshot、Patch、Merge 与 Revert

### Snapshot
```typescript
interface SnapshotRecord { id: SnapshotId; workspaceId: string; repositoryId?: string; baseRef?: string; treeHash: string; files: SnapshotFileRef[]; generatedAt: string; artifact: ArtifactRef; }
```

snapshot 是某时刻状态，不等于当前 workspace。
### Patch
```typescript
interface PatchRecord { id: PatchId; baseSnapshotId: SnapshotId; targetSnapshotId?: SnapshotId; patchArtifact: ArtifactRef; affectedPaths: string[]; applyStatus: "prepared" | "applied" | "rejected" | "conflicted" | "reverted"; conflictRefs: ArtifactRef[]; verification: VerificationReport[]; }

```
### Apply 流程
```text
load patch/base snapshot -> authorize affected paths -> compare current tree hash -> acquire resource locks -> three-way apply -> verify affected file hashes -> run targeted checks -> append PatchAppliedEntry

```
base hash 不匹配时拒绝静默覆盖。
### Merge
合并前必须： 计算共同 ancestor； 比较 path、symbol 和文件 hash； 识别同一资源冲突； 对文本执行三方合并； 对 structured artifact 运行 schema-aware merge； 对 binary 默认拒绝自动 merge； 运行验证命令； 对副作用只返回 merge plan，不假设业务状态可合并。

### Revert
revert 产生新 patch/version 和 durable entry； 不能物理删除原 artifact； 已被后续 version 依赖时需要显式冲突； 外部消息、付款、部署、删除等只能依赖业务补偿动作； revert 结果仍需 scan、policy、audit 和 verification。
## Artifact 生命周期与状态机
### 生命周期

```text
Draft -> Uploading -> Uploaded -> PendingScan -> Scanned -> Available -> Projected/Shared/Referenced -> Expiring -> Deleted PendingScan -> Restricted | Quarantined Available -> Corrupt | Deleting Uploading -> Aborted | Expired
```
### 派生视图状态

```text
Requested -> Authorized -> ReadingSource -> Transforming -> ScanningDerived -> ViewAvailable -> ViewExpired | ViewDeleted
```
### 访问状态

```text
Requested -> Authorized -> Streaming -> Completed Requested -> Denied Streaming -> Cancelled | Failed | Resumable
```
### Durable 边界

至少写入： artifact draft/created； upload completed； scan result； redaction/derived view； artifact attached to tool/session/checkpoint； share/export/download for sensitive content； patch/snapshot apply/reject/revert； expiry/delete/quarantine； corruption/recovery/unknown transfer。 text delta、preview spinner、短期 progress 通常 ephemeral。
## 跨 Session、Subagent 与 Provider
### Cross-session
默认 artifact scope 是最窄范围。跨 session 需要： 明确 source session 和 target session； tenant/owner/retention 兼容； egress 和 user consent； 复制 ref 还是复制内容的明确语义； 新 scope 的 audit； 不因复用而延长原 TTL，除非 policy 明确。

### Subagent
child 只获取：
```text
inputArtifacts explicit refs/ranges + assignment objective/criteria + necessary parent state summary + child-owned output namespace

```
父 approval、parent artifact bucket、secret view 不自动继承。 child artifact 必须记录： parentRunId、childRunId、assignmentId； owner、scope、sensitivity； base snapshot/patch lineage； result schema、evidence 和 expiry。
### Provider
Provider adapter 只能接收： 经过 Context egress 的 view； provider capability 支持的 MIME/part； 明确 size/token budget； ref 与 summary 的对应关系； redacted content 或 provider-specific upload ref。 不同 provider 的文件持久化、生命周期和可见性不能假设相同。外部 provider ref 必须映射为本地 `ArtifactRef`，记录 provider、api family、remote ID、upload time、expiry 和删除状态。

### Provider failure
上传成功但模型请求失败时： remote artifact 是否可复用由 provider semantics 和 local policy 决定； 不盲目重复上传敏感内容； 记录 remote ref 和本地 ref 的关联； provider 不支持删除时缩短本地 egress/retention 并产生 diagnostic； retry/fallback 时重新检查 capability、jurisdiction 和 token/byte budget。
## 与 Context、Prompt、Tool、State、Policy、Harness 集成
### Context 集成

`ContextCompiler` 决定： 大工具输出是 summary、structured、range 还是 ref-only； 哪些 artifact 必须保留； 哪些视图可以进入 model context； token/byte budget 和 overflow 顺序； stale、quarantined、expired 和 untrusted 内容如何标记； citation、source hash、version 和 range 如何保留。 Context 不应把 artifact raw blob 当成 prompt 字符串。
### Prompt 集成
Prompt 只解释： 当前 artifact 是完整、摘要、预览还是截断； 如何通过 ref/range 读取； 不可信内容的 authority 限制； 下载、分享、外发和敏感内容需要的审批； 大输出不会自动全部进入 context。 Prompt 不实现： authorization； token/byte quota； scan/quarantine； retention/delete； secret redaction； provider upload。
### Tool 集成

ToolSpec 声明：
```typescript
interface ArtifactPolicy { maxInputBytes: number; maxOutputBytes: number; allowedKinds: ArtifactKind[]; modelProjection: "full" | "summary" | "structured" | "artifact_ref"; userProjection: "preview" | "download" | "none"; offloadThresholdBytes: number; sensitivityCeiling: Sensitivity; }
```

ToolResult 必须区分 raw、structured、model、user 和 diagnostic 视图。
### State 集成
Session semantic entries 只保存 ref 和语义事实： `ArtifactCreatedEntry`； `ArtifactScannedEntry`； `ArtifactAttachedEntry`； `ArtifactViewCreatedEntry`； `SnapshotEntry`； `PatchPreparedEntry`； `PatchAppliedEntry`； `ArtifactSharedEntry`； `ArtifactExpiredEntry`； `ArtifactDeletedEntry`； `ArtifactQuarantinedEntry`。 不把大 blob 内嵌到 transcript。Projection 可以把 ref 解析为 preview，但事实来源仍是 registry/blob。
### Policy/Sandbox 集成

Artifact egress 不是工具执行成功后的自动步骤：
```text
artifact source -> sensitivity classification -> principal/scope authorization -> destination/provider/host policy -> redaction/preview obligation -> transfer/backend selection -> audit
```

sandbox 中的临时文件、stdout、coverage、截图和构建输出离开 sandbox 前都需要 scan、ownership 和 egress 决策。
### Harness 集成
Harness 负责： 为 run、turn、tool、subagent 创建 artifact namespace； 注入 ArtifactStore、Scanner、Redactor、Previewer、TransferManager； 记录 artifact budget、引用和 retention； 在 checkpoint/terminal 前 flush durable artifact metadata； 处理 provider/host disconnect 和 resumable transfer； 监督 GC、orphan cleanup、quarantine 和 audit sink； 将 artifact event 路由到 Context、State、Trace、Host 和 Evaluation。
## 事件、审计与可观测性

### Artifact Event
```typescript
type ArtifactEvent = | "artifact.created" | "artifact.upload.started" | "artifact.upload.part_received" | "artifact.upload.completed" | "artifact.scan.started" | "artifact.scan.completed" | "artifact.quarantined" | "artifact.view.created" | "artifact.read.started" | "artifact.read.completed" | "artifact.read.denied" | "artifact.shared" | "artifact.attached" | "artifact.patch.applied" | "artifact.patch.conflicted" | "artifact.expired" | "artifact.deleted" | "artifact.recovery.required";
```

每个事件携带：
```text
artifactId/versionId/contentHash tenant/session/run/subagent/turn owner/principal/purpose kind/mediaType/size/sensitivity source/parent/derived refs scan/redaction/preview version transfer/range/queue latency policy/approval/egress decision trace/correlation/causation
```

### Durable 与 Ephemeral
Durable：创建、完成上传、扫描、quarantine、attach、share、patch apply、delete、unknown transfer。 Ephemeral：上传进度、缩略图生成进度、UI preview delta、吞吐 heartbeat。
### Audit
Audit 必须回答： 谁创建、读取、导出、分享、派生或删除了 artifact； 访问了哪个 version/view/range； 基于哪个 tenant、scope、policy、approval 和 egress； artifact 是否经过 scan/redaction； provider、host、subagent 是否收到内容； patch/snapshot 是否应用、冲突、回滚； GC 是否删除、是否有 legal hold 或失败。 普通 debug log 只记录 hash、size、状态和 ID；完整敏感内容进入受控 artifact/audit store。

### Trace 与指标
Trace 层级：
```text
run -> tool/command -> artifact ingest -> scan -> preview/redaction -> transfer/read -> egress

```
指标包括： put/get/range latency； upload resume success； scan queue、扫描失败和 quarantine rate； preview/cache hit； model token saved by offload； truncation/offload rate； provider upload failure； bytes stored/read/egressed； tenant quota、GC lag、orphan count； cross-session/subagent share deny； artifact corruption、hash mismatch； sensitive egress、redaction hit、audit sink failure。 高基数 artifact ID、path、完整 URI 不作为 metric label。
### Diagnostic Snapshot
```typescript

interface ArtifactDiagnosticSnapshot { artifactId: ArtifactId; versionId: ArtifactVersionId; status: ArtifactStatus; size: number; hashes: { content: string; semantic?: string }; scope: ArtifactScope; owner: ArtifactOwner; scan: ScanSummary; views: ArtifactViewRef[]; activeTransfers: TransferSummary[]; references: ReferenceSummary[]; retention: RetentionPolicy; backend: string; recentErrors: Diagnostic[]; redactionState: string; }
```
默认 metadata-only、短 TTL、重新授权并审计读取。
## 故障恢复

### 错误分类
```text
artifact_input size_limit mime_mismatch encoding scan_failed quarantine redaction_failed backend_unavailable upload_timeout upload_expired hash_mismatch range_invalid version_changed permission_denied scope_mismatch egress_denied provider_upload_failed provider_delete_unknown artifact_corrupt retention_conflict gc_failed projection_failed host_disconnect
```

### 上传恢复
```text
load upload session -> verify owner/tenant/expiry -> verify received part hashes -> resume missing parts -> complete and recompute full hash -> scan again if source changed -> publish ref only after durable metadata commit
```

### 下载恢复
断点基于同一 version； 重新授权和检查 view/sensitivity； range 读取失败可从最后确认 offset 重试； hash mismatch 标记 corrupt，不继续拼接； provider/host 断线时 transfer 可 suspended/resumable； sensitive download 失败不自动切换到 unrestricted backend。
### 扫描/派生恢复
scan worker crash 后由 lease 接管； source hash/version 不匹配时丢弃旧 preview/summary； redaction 失败时禁止向低信任 sink 发送 raw； preview 失败不等于 raw 可直接展示； quarantine 不自动降级为 available。

### GC 恢复
`deleting` 对象重启后重新检查 refs/holds； backend delete 成功但 registry 未提交时通过 hash/remote ref 对账； registry tombstone 存在但 blob 仍在时继续清理； active upload、checkpoint、patch 或 legal hold 阻止删除； cleanup 失败进入有限重试和告警，不无限阻塞全部 GC。
### Cross-provider 恢复
provider 上传状态未知时：

1. 查询 remote file/status； 2. 依据 remote ID、hash、size 和 expiry 对账； 3. 已成功则补写 remote
binding； 4. 已失败才重传； 5. 无法确认则标记 `provider_upload_unknown`，不重复外发敏感内容； 6. 迁移或 fallback 前重新执行 egress、capability 和 retention 检查。
## 测试策略
### Testkit

```text
InMemoryArtifactRegistry FakeArtifactBackend ChunkedUploadSimulator ResumeTransferHarness HashVerifier MimeSniffer FakeScanner Secret/PII RedactionScanner PreviewerFixtures RangeReader FakePolicy/Egress FakeProviderFileAdapter FakeHostDownload GarbageCollectorHarness Snapshot/Patch/Merge Store DeterministicClock/IDs EventRecorder CrashInjector
```
### 单元测试

覆盖： ArtifactRef、version、contentHash、semanticHash 分离； MIME、magic bytes、charset 和 schema； size/part/token budget 与 overflow； scope、tenant、owner、sensitivity 和 view 授权； content dedupe 不越权； range、line/page/item projection； redaction map、派生 lineage 和不可逆脱敏； scan/quarantine/restricted 状态； retention、legal hold、tombstone 和 GC； snapshot、patch base hash、三方 merge 和 revert； provider/host/subagent sharing； event schema、audit 和 diagnostic snapshot。
### 传输测试
至少包括：
1. 单块上传成功； 2. 多块上传顺序变化； 3. 中途断线后 resume； 4. part 重复和 part hash 错误； 5. expected size/hash

不一致； 6. 上传过期或 owner 不匹配； 7. 下载 range、断点和 version 变化； 8. slow consumer/backpressure； 9. cancellation 释放 reader/scanner/backend； 10. 大于 quota 的流式拒绝； 11. backend 中途失败； 12. hash mismatch 标记 corrupt。
### 安全测试
跨 tenant/session/subagent ref 访问； expired/deleted/quarantined ref 读取； URI/path traversal 和本地路径泄露； MIME spoof、polyglot、恶意压缩包和 zip-slip； decompression bomb、像素炸弹和大 JSON； secret/PII/regulated 数据外发； redaction bypass、编码/压缩/嵌套 URL 绕过； provider remote file 权限和 expiry； prompt injection 不能改变 policy、tool、scope 或 egress； child 不能读取父未授予 artifact； GC 不能删除 legal hold 或 durable reference； audit sink fail-closed 场景。
### 集成测试

至少包括：
1. ToolResult 大日志 offload 后模型只收到摘要+ref； 2. command/test artifact 在 session/checkpoint
中可恢复； 3. ContextCompiler 选择相关 range 而不是全文； 4. Prompt 标记 truncation 和 untrusted 内容； 5. snapshot/patch 应用前 base hash mismatch； 6. child 共享 artifact range 并正确计费； 7. provider 不支持 MIME 时 fallback 到 preview/ref； 8. host 下载短 TTL link； 9. scan pending 时模型和用户看到 restricted 状态； 10. upload crash 后 worker resume； 11. provider upload unknown 不重复敏感外发； 12. artifact GC 不影响 session replay； 13. replay 不重新下载或执行真实副作用； 14. quarantine artifact 被 policy deny； 15. session 删除触发 artifact retention/GC 审计。
### 故障注入

在以下 boundary 前后 crash： draft metadata 写入； upload part 写入； complete upload； full hash 计算； scan result durable commit； redaction output 写入； preview metadata 与 blob 之间； artifact attach entry； provider upload acknowledgement； range transfer checkpoint； patch apply 与 durable entry 之间； delete registry 与 backend blob 之间； GC mark 与 delete 之间； audit append 与 user delivery 之间。 断言：不重复外发，不丢 ref，不把 pending scan 当 available，不把 unknown provider upload 当失败后自动重传，不删除仍被引用对象。
### 评测与契约
每个 ArtifactStore、backend、scanner、previewer、redactor、provider adapter 和 host adapter 运行 conformance suite： hash/size/version 正确； tenant/scope 授权一致； range/stream/resume 一致； scan/redaction 状态可审计； durable refs 可 replay； error taxonomy 稳定； cancellation 可观察； retention/GC 不复活已删对象； artifact 视图与 sensitivity 不越权。
## 反模式

1. Artifact 只是把大文本写入 `/tmp` 后返回路径。 2. 用文件名、URL 或路径代替 immutable ref/hash。
3. 逻辑 artifact
ID、version ID 和 content hash 混用。
4. registry 和 blob 没有一致性或 tombstone。 5. 扫描前就向模型或

provider 提供 raw 内容。
6. MIME 只信扩展名或调用方声明。 7. 全部 artifact 原文默认进入 prompt、trace 和日志。
8. 不区分
model-facing、user-facing、durable 和 diagnostic。

9. 大日志无 size/token budget，直接回传模型。
10. 截断没有 original size、range 和 `truncated` 标记。 11. range 下载不重新授权或不绑定 version。 12. 断点续传拼接不同版本内容。 13. dedupe 直接共享权限，导致跨 tenant 泄露。 14. child 自动继承父 artifact bucket。 15. provider remote file ID 当作本地 ArtifactRef。 16. provider 失败后盲目重复上传敏感内容。 17. preview 生成失败就回退到 unrestricted raw download。 18. redaction map 随 artifact 一起外发。 19. snapshot 没有 tree hash，patch 可覆盖新状态。 20. binary 或同一行文本无条件自动 merge。 21. revert 删除旧 artifact 或 session entry。 22. TTL 只看文件 mtime，不看 durable refs、hold 和 scope。 23. GC 删除仍被 checkpoint、patch 或审计引用的对象。 24. GC 失败却标记 deleted，导致数据事实不一致。 25. transfer buffer 无界，slow consumer 拖垮进程。 26. cancel 只停止 UI，不停止上传、扫描和 backend。 27. audit 只记录成功，不记录 deny、quarantine、delete 和 unknown。 28. secret 进入 artifact summary、filename、preview 或 metrics label。 29. prompt injection 通过 artifact content 修改工具或审批。 30. replay 重新执行 provider upload、Webhook、命令或外部交付。 31. 只测试 `put/get`，不测试扫描、权限、range、恢复和 GC。 32. 把 artifact 数量或存储大小当作系统质量指标。
## 实施清单
### V1：统一引用与本地存储

[ ] 定义 ArtifactId、VersionId、ArtifactRef、ArtifactKind、Sensitivity、Scope、Owner。；；[ ] 实现
ArtifactRegistry 与 `ArtifactStore` 端口。；
[ ] 实现 local/in-memory backend。；
[ ]

contentHash、size、MIME、status、retention 和 source ref 可验证。；
[ ] ToolResult 支持
summary、structured、user artifact、diagnostic。；
[ ] 大输出支持截断、artifact ref 和 token budget。

### V2：流式、扫描与视图
[ ] UploadSession、分片、hash、expected size 和 resume。；；[ ] Range read、line/page/item
projection。；
[ ] MIME/magic/charset/schema 检测。；；[ ] scanner、quarantine、restricted 状态机。；

[ ]
preview、thumbnail、summary 和 structured view。；
[ ] redaction policy、derived lineage 和
egress view。

### V3：权限、状态与跨边界
[ ] tenant/session/run/subagent/workspace scope。；；[ ] ReferenceAuthorizer、view/range 权限和短
TTL share。；
[ ] State semantic entries、checkpoint、projector 和 replay。；

[ ]
Context/Prompt/Tool/Harness 集成。；
[ ] provider file adapter、host download、subagent
assignment。；

[ ] sensitive artifact audit 和 access log。
### V4：Snapshot、Patch 与恢复
[ ] SnapshotRecord、PatchRecord、base hash 和 affected paths。；；[ ] 三方 merge、binary
conflict、revert 和 verification。；

[ ] provider upload unknown、artifact
corrupt、scan/preview crash recovery。；
[ ] durable transfer cursor 和 checkpoint。；
[ ]

orphan、quarantine、legal hold 和 GC recovery。；
[ ] 外部副作用与 artifact 事实分离。
### V5：规模化治理
[ ] object/remote backend、backend capability 和 health。；；[ ] 跨 session/subagent/provider

复制、引用、TTL 和 consent。；
[ ] quota、cost、egress、cache、dedupe 和容量规划。；；[ ] audit
integrity、retention/delete/export review。；
[ ]

scanner/previewer/redactor/provider/backend conformance suite。；
[ ] chaos、load、large
binary、slow client 和 multi-tenant isolation 评测。；
[ ] dashboard、diagnostic snapshot、SLO

和告警。
## 五个参考项目的启发来源
### Pi
tool result、artifact/resource loader、session tree 和 compaction 的分层方向，启发大输出 offload、引用而非全文、durable ref 和可恢复视图； headless runtime、EventStream 与 CLI/TUI/RPC 共用 runtime，启发 ArtifactStore 独立于 Host，model-facing 与 user-facing projection 分离； steering/follow-up 和资源加载来源，启发 artifact scope、source provenance 和运行中引用更新。

### Grok Build
工具/MCP 输出限制、token 估算、图片压缩和上下文修剪，启发 bytes/token/resource 三种 budget、summary/preview/range 选择； Session/ChatState/Sampler actor 和路径级锁，启发 artifact attach、snapshot/patch、并发读写和状态所有权； permission、folder trust、sandbox，启发 artifact scan、egress、provider 上传和 sandbox 临时文件的边界。
### OpenCode
message/part、session/server/event/projector，启发 ArtifactRef 作为语义状态引用、durable artifact entry、多客户端 replay 和 Host delivery； snapshot/patch/revert，直接启发 `SnapshotRecord`、`PatchRecord`、base hash、三方合并和可审计回滚； tool、permission、MCP/LSP 集成，启发外部工具结果和 remote artifact 的本地 wrapper、版本与政策快照。

### Claude Code
skills、memory、subagents、hooks、permission modes 和计划任务，启发 artifact 在 task、session、subagent scope 中的最小继承； 项目规则与长期 memory 方向，启发 source/provenance、retention、sensitivity 和 durable artifact reference； 公开能力和安全语义以现有本地文档中标注的官方资料为准，辅助源码不作为规范。
### OpenClaw
AgentHarness registry、agent-core、Gateway/channel 和 provider runtime，启发 artifact backend/provider/host adapter 分层； tool、sandbox、elevated 分离，启发 artifact egress、secret view、remote worker 和高权限传输边界； 后台运行、memory flush 和事务化插件注册，启发 resumable transfer、后台扫描/GC、注册回滚和跨渠道交付； 多渠道 session key，启发 tenant/identity/session scope 与 artifact ownership。 本设计的实现审查应回到当前目录已有参考文档及其已记录源码范围。若新增对象存储、provider 文件 API、恶意内容扫描器、法规 retention 或跨地域数据策略，应另行补充一手证据、迁移约束和契约测试。

