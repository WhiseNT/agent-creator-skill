# Agent State/Memory Engineering 细粒度工程设计
> 本文把 Agent 的状态与记忆设计为可审计、可分支、可恢复的 Harness 子系统。它沿用 `Session`、`Run`、`Turn`、`Attempt`、`Message/Part`、semantic entries、Projector、Checkpoint、Compaction、ArtifactRef 和 `ContextPlan` 等术语。
>
> 架构依据仅来自本目录已完成的五个参考项目源码归纳、现有参考架构、Agent Harness、Context Engineering 和 Harness Engineering 文档；不把 README 当作规范，也不新增网络调研结论。
## 目录
1. [设计目标与非目标](#设计目标与非目标)
2. [职责边界与包布局](#职责边界与包布局)
3. [核心概念：五种状态视图](#核心概念五种状态视图)
4. [数据模型与 TypeScript 接口](#数据模型与-typescript-接口)
5. [Message 与 Part 模型](#message-与-part-模型)
6. [Semantic Entry 事件模型](#semantic-entry-事件模型)
7. [Session 生命周期](#session-生命周期)
8. [Run/Turn/Attempt 状态机](#runturnattempt-状态机)
9. [Event Sourcing 与 Projector](#event-sourcing-与-projector)
10. [Branch、Fork 与 Revert](#branchfork-与-revert)
11. [乐观并发与冲突协调](#乐观并发与冲突协调)
12. [Checkpoint 与恢复游标](#checkpoint-与恢复游标)
13. [Compaction 设计](#compaction-设计)
14. [Artifact、Snapshot 与 Patch](#artifactsnapshot-与-patch)
15. [Memory 类型与记录模型](#memory-类型与记录模型)
16. [Provenance、Confidence、TTL 与 Scope](#provenanceconfidence-ttl-与-scope)
17. [Memory Write 流程](#memory-write-流程)
18. [Memory Recall 流程](#memory-recall-流程)
19. [Contradiction、Forget 与修订](#contradictionforget-与修订)
20. [Durability 与存储后端](#durability-与存储后端)
21. [迁移与版本兼容](#迁移与版本兼容)
22. [隐私、安全与数据外发](#隐私安全与数据外发)
23. [Crash Recovery 与未知副作用](#crash-recovery-与未知副作用)
24. [可观测性与诊断](#可观测性与诊断)
25. [测试策略](#测试策略)
26. [反模式与审查规则](#反模式与审查规则)
27. [实施清单与分阶段交付](#实施清单与分阶段交付)
28. [五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与非目标
### 目标
状态子系统必须使以下问题可回答：
- 当前会话有哪些分支，活跃分支是哪一个？
- 某次模型请求看到了哪些内容，哪些内容被摘要或卸载？
- 哪个 `ToolCall` 对应哪个 `ToolResult`，是否已经持久化？
- 崩溃发生时最后一个 durable boundary 是什么？
- 一个写操作是否已执行、未执行，还是结果未知？
- 某条 memory 来自哪里、何时验证、何时过期、谁可以删除？
- 多客户端同时写入时，哪个版本获胜，冲突如何呈现？
- 从旧 schema 恢复时，是否能保持语义而不是只保持 JSON 可解析？
### 非目标
本模块不负责：
- provider SDK 的原始协议转换；
- Prompt 的措辞优化；
- 工具授权和 sandbox 决策本身；
- 向量数据库或全文检索实现细节；
- UI transcript 的具体渲染；
- 自动把全部对话写入长期 memory；
- 以自然语言摘要替代结构化任务状态。
原则保持简单：
```text
Transcript 保存语义历史。 Model Context 是 Transcript 的一次投影。 Memory 是可治理的跨任务资源。 Artifact 保存大内容和可交付物。 Event 是事实；Projection 是视图。
```
## 职责边界与包布局
推荐包边界：
```text
packages/protocol/ Message, Part, Entry, Event, ArtifactRef, Usage packages/session/ SessionRepository, EventStore, Projector, BranchManager
packages/state/ RunState, Checkpoint, RecoveryCoordinator packages/context-runtime/ ContextProjector, CompactionPlanner, MemoryRecall packages/memory/
MemoryStore, MemoryWriter, ContradictionResolver packages/artifact/ ArtifactStore, SnapshotStore, PatchStore packages/migration/ SchemaRegistry,
Upcaster, MigrationRunner packages/testkit/ InMemoryStore, ReplayRunner, CrashInjector, DeterministicClock
```
依赖方向应向内：
```text
Host/Delivery -> Harness -> State ports -> Storage adapters Context Runtime -> State projections Memory Runtime -> State entries + Memory store
```
`Agent Kernel` 只依赖 `KernelStatePort`，不能导入 SQLite、JSONL、具体云存储或 UI 类型。
### 模块职责矩阵
| 模块 | 负责 | 不负责 |
|---|---|---|
| SessionCoordinator | 打开会话、版本、分支、追加、checkpoint | 模型采样 |
| EventStore | 原子追加、读取、事件版本 | 业务视图解释 |
| Projector | 从 entries 构建视图 | 修改事实日志 |
| BranchManager | fork、active head、revert 语义 | 物理删除历史 |
| CompactionService | 规划、验证、写入 CompactionEntry | 任意删除原始事实 |
| MemoryWriter | 候选提取、审批、持久化 | 越过隐私策略 |
| MemoryRecall | 过滤、排序、冲突标注 | 直接改变 memory |
| ArtifactStore | 大对象、hash、范围读取、保留策略 | 修改 transcript |
| RecoveryCoordinator | checkpoint 恢复、in-flight 分类 | 盲目重放副作用 |
## 核心概念：五种状态视图
### Transcript
`Transcript` 是某个 `Session` 分支上的完整语义历史。
它包括：
- 用户和 assistant 的完整 `Message`；
- 工具调用与结果；
- approval、模型切换、toolset 变化；
- compaction 覆盖范围和结构化状态；
- branch、revert、checkpoint、错误和恢复记录；
- artifact、snapshot、patch 引用；
- provenance、usage 和 delivery 状态。
Transcript 不是 provider message 数组，也不是 UI token 流。
### Session
`Session` 是长期任务容器，拥有一个或多个 `Branch`，具有独立身份、租户、保留策略和 schema 版本。
```text
Session ├─ metadata ├─ branches │   ├─ main │   └─ experiment-1 ├─ semantic entries ├─ checkpoints └─ projections
```
### Run
`Run` 是一次可取消、可恢复的执行，属于一个 session branch。
它记录：
- `runId`、父 run、触发输入；
- frozen config、model/toolset；
- 预算计数和 abort 状态；
- 当前 `Turn`、`Attempt` 和 pending approval；
- 子任务、artifact 和 delivery 状态。
### Turn
`Turn` 是一次模型采样以及该采样产生的工具批次的原子语义单元。
典型结构：
```text
TurnStarted -> UserMessage or steering input -> ModelRequest -> AssistantMessage with zero or more ToolCall parts -> ToolResult entries for the batch
-> TurnCompleted or TurnFailed
```
裁剪或 compaction 不能拆开 assistant tool call 与对应 tool result。
### Working State
`WorkingState` 是当前 run 可变但可恢复的工作视图，不等于 transcript。
它包含：
- 当前目标、完成项、未完成项；
- 当前活动文件、测试结果、失败原因；
- pending approval；
- in-flight tool 及幂等状态；
- 当前 context plan 和 compaction 游标；
- memory candidate、artifact 和 steering/follow-up 队列。
它必须能由 durable entries 和 checkpoint 重建，不能只存在内存。
### 对比表
| 对象 | 时间跨度 | 事实/视图 | 是否可变 | 典型消费者 |
|---|---|---|---|---|
| Transcript | session/branch | 事实序列 | append-only | replay、审计 |
| Session | 长期 | 容器元数据 | 受控更新 | host、repository |
| Run | 一次执行 | 生命周期事实 | 状态机推进 | supervisor |
| Turn | 一次采样+工具批次 | 原子执行单元 | 完成后不改 | Kernel、context |
| Working State | 当前执行 | 投影/缓存 | 可更新 | Kernel、恢复器 |
| Memory | 跨任务 | 治理后的知识 | 修订/遗忘 | Context Compiler |
| Model Context | 一次请求 | 渲染视图 | 每 turn 重建 | Model Runtime |
## 数据模型与 TypeScript 接口
### 标识与版本
```typescript
type SessionId = string; type BranchId = string; type RunId = string; type TurnId = string; type AttemptId = string; type EntryId = string; type
MemoryId = string; type ArtifactId = string; type Sequence = number; type SchemaVersion = `${number}.${number}`; interface VersionStamp {
streamVersion: number; entrySequence: number; schemaVersion: SchemaVersion; }
```
ID 不得复用。provider request ID、tool call ID、business idempotency key 也必须分开。
### Session 与 Branch
```typescript
interface SessionRecord { id: SessionId; tenantId: string; ownerId?: string; createdAt: string; updatedAt: string; schemaVersion: SchemaVersion;
activeBranchId: BranchId; branchIds: BranchId[]; retention: RetentionPolicy; privacy: PrivacyPolicy; metadata: Record<string, string>; } interface
BranchRecord { id: BranchId; sessionId: SessionId; parentBranchId?: BranchId; forkedFrom?: EntryId; headEntryId?: EntryId; headVersion: number;
status: "active" | "archived" | "reverted"; createdAt: string; label?: string; }
```
### Run、Turn、Attempt
```typescript
interface RunRecord { id: RunId; sessionId: SessionId; branchId: BranchId; parentRunId?: RunId; status: RunStatus; trigger: "user" | "resume" |
"background" | "subagent" | "system"; configSnapshotId: string; startedAt: string; endedAt?: string; budget: BudgetCounters; lastDurableEntry?:
EntryId; } type RunStatus = | "created" | "preparing" | "sampling" | "waiting_for_approval" | "executing_tools" | "compacting" | "finalizing" |
"completed" | "failed" | "cancelled" | "recovering"; interface TurnRecord { id: TurnId; runId: RunId; ordinal: number; status: "open" | "sampling" |
"tools" | "completed" | "failed" | "cancelled"; inputEntryIds: EntryId[]; assistantEntryId?: EntryId; toolCallIds: string[]; toolResultEntryIds:
EntryId[]; startedAt: string; endedAt?: string; } interface AttemptRecord { id: AttemptId; turnId: TurnId; provider: string; apiFamily: string;
modelRef: string; requestId?: string; ordinal: number; status: "started" | "completed" | "failed" | "cancelled"; usage?: Usage; error?: ErrorRef; }
```
### Working State
```typescript
interface WorkingState { sessionId: SessionId; branchId: BranchId; runId: RunId; objective?: string; completed: StateFact[]; pending: StateFact[];
constraints: StateFact[]; changedFiles: FileChangeState[]; tests: TestState[]; failures: FailureState[]; pendingApprovals: ApprovalState[];
inFlightTools: InFlightToolState[]; activeModel?: ModelState; activeToolsetHash?: string; compaction?: CompactionCursor; memoryCandidates:
MemoryCandidate[]; artifacts: ArtifactRef[]; steeringQueue: EntryId[]; followUpQueue: EntryId[]; sourceVersion: number; }
```
### Repository 端口
```typescript
interface SessionRepository { create(input: CreateSessionInput): Promise<SessionRecord>; load(id: SessionId, branchId?: BranchId):
Promise<SessionView>; append( sessionId: SessionId, branchId: BranchId, entries: SessionEntry[], expectedVersion: number, ): Promise<AppendReceipt>;
fork(input: ForkInput): Promise<BranchRecord>; checkpoint(input: CheckpointInput): Promise<CheckpointRecord>; listRecoveryCandidates():
Promise<RecoveryCandidate[]>; } interface AppendReceipt { newVersion: number; firstEntryId: EntryId; lastEntryId: EntryId; committedAt: string; }
```
## Message 与 Part 模型
### Provider-neutral Message
```typescript
interface Message { id: string; role: "system" | "user" | "assistant" | "tool" | "developer"; parts: ContentPart[]; createdAt: string; source: "user"
| "model" | "tool" | "system" | "projection"; provenance?: Provenance; metadata?: Record<string, unknown>; }
```
### ContentPart
```typescript
type ContentPart = | TextPart | ImagePart | AudioPart | VideoPart | DocumentPart | ToolCallPart | ToolResultPart | ReasoningPart | CitationPart |
ArtifactPart | RedactedPart; interface TextPart { type: "text"; text: string; annotations?: Annotation[]; } interface ToolCallPart { type:
"tool_call"; callId: string; toolName: string; arguments: unknown; argumentsHash: string; idempotencyKey?: string; } interface ToolResultPart { type:
"tool_result"; callId: string; status: "success" | "error" | "denied" | "cancelled" | "unknown"; summary?: string; structured?: unknown;
artifactRefs?: ArtifactRef[]; truncated?: TruncationInfo; } interface ArtifactPart { type: "artifact"; ref: ArtifactRef; presentation: "inline" |
"link" | "model_summary"; }
```
### Message 转换规则
```text
semantic entry -> active branch projection -> remove UI-only events -> apply compaction ranges -> preserve tool call/result pairs -> convert custom
entries -> provider Message/Part
```
转换器必须保留 provider metadata，不能为了统一而丢掉 reasoning、citation、grounding、safety 或原始响应字段。
## Semantic Entry 事件模型
### 总体原则
`SessionEntry` 是 append-only 事实；修订用新 entry 表达，不覆盖旧 entry。
```typescript
interface BaseEntry { id: EntryId; sessionId: SessionId; branchId: BranchId; sequence: number; type: string; schemaVersion: SchemaVersion; occurredAt:
string; recordedAt: string; runId?: RunId; turnId?: TurnId; causationId?: EntryId; correlationId?: string; provenance?: Provenance; sensitivity:
Sensitivity; payloadHash: string; } type SessionEntry = | UserMessageEntry | AssistantMessageEntry | ToolCallEntry | ToolResultEntry | ApprovalEntry |
ModelChangeEntry | ToolsetChangeEntry | CompactionEntry | BranchEntry | RevertEntry | CheckpointEntry | ArtifactEntry | MemoryEntry | ErrorEntry |
DeliveryEntry | RunLifecycleEntry;
```
### 关键 Entry
```typescript
interface UserMessageEntry extends BaseEntry { type: "user_message"; message: Message; deliveryId?: string; } interface AssistantMessageEntry extends
BaseEntry { type: "assistant_message"; message: Message; attemptId: AttemptId; finishReason?: string; } interface ToolCallEntry extends BaseEntry {
type: "tool_call"; call: ToolCallPart; authorization?: PolicyDecisionSnapshot; } interface ToolResultEntry extends BaseEntry { type: "tool_result";
result: ToolResultPart; execution: ExecutionReceipt; } interface ApprovalEntry extends BaseEntry { type: "approval"; approval: ApprovalState;
decision?: "approved" | "rejected" | "expired" | "cancelled"; } interface CompactionEntry extends BaseEntry { type: "compaction"; coveredFrom:
EntryId; coveredTo: EntryId; summary: ContentPart[]; structuredState: StructuredTaskState; modelRef: string; usage: Usage; sourceHash: string;
verification: CompactionVerification; } interface CheckpointEntry extends BaseEntry { type: "checkpoint"; checkpointId: string; lastDurableEntry:
EntryId; stateHash: string; }
```
### Durable 与 Ephemeral
永久保存：
- user input accepted；
- assistant message completed；
- tool call ready；
- tool result；
- approval request/resolution；
- model/toolset change；
- compaction；
- checkpoint；
- final status；
- unknown side-effect outcome。
默认不永久保存：
- text delta；
- spinner；
- heartbeat；
- 可合并的 tool progress。
Ephemeral event 可被丢弃，但必须在 durable boundary 前完成必要聚合。
## Session 生命周期
### 创建
```text
parse host request -> resolve tenant/identity -> load safe config -> resolve trust -> create session metadata -> create main branch -> append
session_created -> emit durable SessionOpened
```
创建时冻结租户、隐私、保留和 schema policy；运行中不得由低层 workspace 配置绕过安全上限。
### 打开与继续
```text
load session metadata -> choose active branch -> validate schema -> load last checkpoint -> project durable entries -> find pending
approvals/in-flight tools -> compile context -> create new run
```
新 run 不应伪造旧 run 的 ID；恢复通过 `trigger: "resume"` 与 `parentRunId` 表达。
### 关闭
```text
stop accepting work -> settle model/tool tasks -> append final lifecycle entry -> checkpoint if needed -> flush durable events -> close projections
```
## Run/Turn/Attempt 状态机
### Run 状态
```text
created -> preparing -> sampling -> waiting_for_approval -> executing_tools -> sampling -> compacting -> finalizing -> completed 任意活动状态 -> cancelled
任意活动状态 -> failed 重启后 -> recovering recovering -> preparing | waiting_for_approval | failed
```
### 转移规则
| 当前 | 事件 | 下一状态 | 持久化要求 |
|---|---|---|---|
| created | bootstrap_ok | preparing | run_started |
| preparing | context_ready | sampling | context_compiled |
| sampling | assistant_complete | executing_tools/ finalizing | assistant_message |
| sampling | approval_needed | waiting_for_approval | approval |
| waiting_for_approval | decision | executing_tools/ sampling | approval |
| executing_tools | all_results | sampling/finalizing | tool_result |
| sampling | overflow | compacting | error + compaction_started |
| any | cancel | cancelled | cancellation |
| any | fatal | failed | error + run_failed |
### Attempt 语义
同一 `Turn` 的 provider transport retry 仍可属于一个 `Attempt` 的内部重试；重新生成、改上下文或 fallback 必须创建新的 `Attempt`，并记录原因、模型和 usage。
## Event Sourcing 与 Projector
### EventStore 端口
```typescript
interface EventStore { read(stream: StreamRef, fromVersion?: number): AsyncIterable<SessionEntry>; append( stream: StreamRef, entries: SessionEntry[],
expectedVersion: number, ): Promise<AppendReceipt>; readById(id: EntryId): Promise<SessionEntry | undefined>; flush(): Promise<void>; }
```
### Projector 端口
```typescript
interface Projector<TView> { name: string; version: number; apply(view: TView, entry: SessionEntry): TView; rebuild(entries:
AsyncIterable<SessionEntry>): Promise<TView>; }
```
至少提供：
- `TranscriptProjector`；
- `WorkingStateProjector`；
- `UsageProjector`；
- `ApprovalProjector`；
- `RecoveryProjector`；
- `ArtifactProjector`；
- `MemoryIndexProjector`。
### 投影一致性
事件追加成功后，durable projector 必须：
1. 记录输入 entry sequence；
2. 应用纯函数；
3. 写入 projection version；
4. 失败时进入重试或 degraded 状态；
5. 不让 UI projection 的失败静默丢失恢复状态。
Projection 可重建；不能把 projection 的手工修改当作事实来源。
### Replay 与幂等
每个 projector 应支持相同 entry 重放而结果不变：
```text
apply(view, entry) twice -> same semantic view
```
处理 duplicate entry 时检查 `lastAppliedSequence` 或 entry ID；不使用时间戳猜测去重。
## Branch、Fork 与 Revert
### Fork
Fork 创建新的 branch，不复制全部大对象：
```typescript
interface ForkInput { sessionId: SessionId; sourceBranchId: BranchId; fromEntryId: EntryId; label?: string; copyWorkingState: boolean; }
```
新分支记录 `parentBranchId` 和 `forkedFrom`，读取历史时沿父链解析到 fork 点，再读取自身 entries。
### Revert
Revert 不物理删除旧 entry，而是追加反向语义：
```typescript
interface RevertEntry extends BaseEntry { type: "revert"; targetEntryIds: EntryId[]; reason: string; resultingSnapshot?: ArtifactRef; }
```
文件变更的 revert 需要 snapshot/patch 校验；业务动作的 revert 只能在工具明确提供补偿操作时执行。
### Branch 合并
默认不自动合并有副作用的 branch。合并流程：
```text
compare common ancestor -> classify entries -> detect same-resource conflicts -> prepare merge plan -> approval if side effects -> append merge entry
-> update active head
```
模型文本可人工合并，文件 patch 必须经过三方合并和测试，外部业务状态不得假装可 merge。
## 乐观并发与冲突协调
### CAS 规则
所有 append 带 `expectedVersion`：
```typescript
append(sessionId, branchId, entries, expectedVersion)
```
版本不匹配时返回 `SessionConflict`，不得静默覆盖或自动丢弃其他客户端 entries。
### 冲突处理
```text
catch SessionConflict -> reload latest head -> classify local entries -> if UI-only: drop/rebase -> if append-only independent: rebase -> if same
turn/resource: surface conflict -> retry with bounded attempts
```
冲突响应需要包含：
- expected/current version；
- last common entry；
- remote entry IDs；
- 是否可自动 rebase；
- 建议恢复动作。
### Actor 选择
高并发 session 可使用 `SessionActor` 串行化状态所有权；跨 actor 操作仍需显式协议、幂等键和补偿，不把 actor mailbox 当作跨存储事务。
## Checkpoint 与恢复游标
### Checkpoint 模型
```typescript
interface CheckpointRecord { id: string; sessionId: SessionId; branchId: BranchId; runId: RunId; lastDurableEntry: EntryId; streamVersion: number;
activeTurnId?: TurnId; stateHash: string; workingState: WorkingState; pendingApprovals: ApprovalState[]; inFlightTools: InFlightToolState[];
compaction: CompactionCursor; modelState?: ModelState; toolsetHash?: string; configSnapshotId: string; createdAt: string; }
```
### 写入边界
至少在以下位置 checkpoint：
- user input accepted；
- assistant message durable commit；
- tool call authorization 完成；
- 每个 tool result durable commit；
- approval requested/resolved；
- compaction completed；
- run terminal state。
### Checkpoint 一致性
先写完整 checkpoint，再追加 `CheckpointEntry` 指向它；若引用 entry 已写但 blob 缺失，恢复器应标记不可用并从上一个 checkpoint 重建。
## Compaction 设计
### 触发条件
- 可用 input budget 低于阈值；
- provider 返回 context overflow；
- 模型切换到更小 context window；
- 工具结果大量累积；
- 会话阶段完成；
- 预计算摘要已准备且 source hash 仍匹配。
预算公式：
```text
usable input = context window - output reserve - reasoning reserve - tool reserve - safety margin
```
### CompactionPlan
```typescript
interface CompactionPlan { sourceBranchId: BranchId; keepEntries: EntryId[]; summarizeRanges: EntryRange[]; preservePairs: Array<[EntryId, EntryId]>;
offloadResources: string[]; structuredState: StructuredTaskState; targetTokens: number; sourceHash: string; } interface StructuredTaskState {
objective?: string; completed: string[]; pending: string[]; changedFiles: string[]; tests: TestState[]; failures: FailureState[]; constraints:
string[]; approvals: ApprovalState[]; artifacts: ArtifactRef[]; modelChanges: ModelState[]; }
```
### 两阶段压缩
```text
background candidate summary -> verify source hash and branch head -> synchronous summarize new tail -> validate coverage and invariants -> append
CompactionEntry -> checkpoint
```
后台候选摘要不能直接成为事实；source hash、branch head 或 tool pair 变化时必须丢弃并重新生成。
### 摘要验证
验证器检查：
- 覆盖范围连续且属于同一 branch；
- assistant tool call/result 成对；
- 文件名、测试状态、用户约束保留；
- 未完成项没有被写成完成；
- 数值、ID、approval 状态没有漂移；
- 摘要 token 不超目标；
- `sourceHash` 与输入一致。
失败时保留原历史，返回 diagnostic，不写入 CompactionEntry。
## Artifact、Snapshot 与 Patch
### ArtifactRef
```typescript
interface ArtifactRef { id: ArtifactId; uri: string; mediaType: string; size: number; hash: string; summary?: string; sensitivity: Sensitivity;
createdByRunId?: RunId; expiresAt?: string; retention: RetentionPolicy; }
```
### 三类对象
| 对象 | 语义 | 典型内容 |
|---|---|---|
| Artifact | 大输出或交付物 | 日志、图片、报告 |
| Snapshot | 某时刻资源状态 | 工作区、文件树、数据库版本 |
| Patch | 从一个状态到另一个状态的变更 | unified diff、操作列表 |
### ArtifactStore
```typescript
interface ArtifactStore { put(input: ArtifactInput): Promise<ArtifactRef>; get(ref: ArtifactRef, range?: ByteRange): Promise<ArtifactChunk>;
delete(ref: ArtifactRef, reason: string): Promise<void>; verify(ref: ArtifactRef): Promise<boolean>; }
```
大工具输出应分为 model-facing summary、structured result、user-facing artifact、raw diagnostic；模型不应被迫接收 50,000 行原始日志。
### Snapshot/Patch 审计
```typescript
interface SnapshotRecord { id: string; workspaceId: string; baseRef?: string; treeHash: string; files: SnapshotFile[]; createdAt: string; } interface
PatchRecord { id: string; baseSnapshotId: string; targetSnapshotId?: string; patchArtifact: ArtifactRef; affectedPaths: string[]; applyStatus:
"prepared" | "applied" | "rejected" | "reverted"; }
```
应用 patch 前必须校验 base hash；冲突或 workspace 已变化时拒绝静默覆盖。
## Memory 类型与记录模型
### 类型
```typescript
type MemoryType =
  | "semantic"
  | "episodic"
  | "procedural"
  | "working";
```
Memory 是 Context 的来源，不是全部 Context。`working` memory 可以与 WorkingState 互相投影，但不能绕过 session durability。
### MemoryRecord
```typescript
interface MemoryRecord { id: MemoryId; type: MemoryType; content: string; normalizedFacts?: FactClaim[]; sourceRefs: ResourceRef[]; provenance:
Provenance; confidence: number; createdAt: string; lastVerifiedAt?: string; expiresAt?: string; scope: ResourceScope; sensitivity: Sensitivity;
status: "candidate" | "active" | "stale" | "contradicted" | "forgotten"; supersedes?: MemoryId; supersededBy?: MemoryId; consent: ConsentState;
embeddingVersion?: string; }
```
### Scope 与 retention
```text
global -> organization -> user -> workspace -> directory -> session -> branch -> run -> turn
```
Retention：
```text
always | until_session_end | until_task_end until_file_changes | ttl | artifact_only | never_persist
```
安全上限不能被更低层 scope 覆盖；secret/regulated 默认不进入长期 memory。
## Provenance、Confidence、TTL 与 Scope
### Provenance
```typescript
interface Provenance { kind: "user" | "model" | "tool" | "file" | "retrieval" | "human_review" | "system"; sourceIds: string[]; sourceVersion?:
string; observedAt?: string; verifiedBy?: string; derivation?: "direct" | "extracted" | "summarized" | "inferred"; }
```
`model + inferred` 不能默认获得与 `user + direct` 相同的权威性。
### Confidence
置信度是可解释的排序信号，不是事实证明：
```text
confidence = source reliability × extraction quality × verification freshness × cross-source agreement - contradiction penalty
```
系统应保留组成因素，避免只存一个无法解释的浮点数。
### TTL 与新鲜度
召回前检查：
1. `status` 是否 active；
2. `expiresAt` 是否已到期；
3. 依赖文件 hash/branch 是否变化；
4. `lastVerifiedAt` 是否满足类型要求；
5. policy 是否仍允许该 scope。
过期 memory 可以作为低优先级候选，但不能伪装成当前事实。
## Memory Write 流程
### 写入门槛
只有同时满足以下条件才建议进入长期 memory：
- 对未来有复用价值；
- 相对稳定而非一次性闲聊；
- 有可追溯来源；
- 不违反隐私、租户和 retention；
- 用户同意或产品策略明确允许；
- 未发现未解决 contradiction。
### 流程
```text
observe transcript/tool/artifact -> extract candidate claims -> classify type and scope -> attach provenance -> sensitivity/egress check -> duplicate
and contradiction check -> confidence estimate -> user/policy approval if required -> persist MemoryEntry + MemoryRecord -> update index -> emit audit
event
```
### MemoryCandidate
```typescript
interface MemoryCandidate { claim: string; type: MemoryType; proposedScope: ResourceScope; sourceRefs: ResourceRef[]; sensitivity: Sensitivity;
confidence: number; reason: string; requiresApproval: boolean; }
```
compaction 前的 memory flush 只能提取允许持久化的候选，不得把模型猜测直接升级为事实。
## Memory Recall 流程
### Recall 端口
```typescript
interface MemoryStore { write(record: MemoryRecord): Promise<MemoryRecord>; recall(query: MemoryQuery): Promise<MemoryHit[]>; contradict(input:
ContradictionInput): Promise<ContradictionReport>; forget(input: ForgetInput): Promise<ForgetReceipt>; } interface MemoryQuery { text: string; scopes:
ResourceScope[]; types?: MemoryType[]; maxItems: number; tokenBudget: number; includeStale: boolean; sensitivityCeiling: Sensitivity; }
```
### 排序
```text
score = semantic relevance × scope match × authority/trust × freshness × confidence × task-stage fit - redundancy - sensitivity/egress cost -
contradiction penalty
```
不要只按向量相似度排序；必须做 metadata filter、去重、冲突标注和 token budget。
### Context 注入
Memory 进入 `ContextPlan` 时标记：
```typescript
interface MemoryHit { record: MemoryRecord; score: number; reasonCodes: string[]; citation: ResourceRef; stale: boolean; contradictionIds: MemoryId[];
}
```
注入格式应把 memory 作为数据，不授予其修改 system policy、注册工具或批准动作的权限。
## Contradiction、Forget 与修订
### Contradiction
冲突不是简单覆盖。定义：
```typescript
interface ContradictionInput { candidate: MemoryCandidate | MemoryRecord; existing: MemoryRecord[]; } interface ContradictionReport { conflict:
boolean; pairs: ContradictionPair[]; resolution: "keep_both" | "supersede" | "mark_review" | "reject_candidate"; }
```
决策顺序：
```text
same claim + newer verified source -> supersede same scope + equal authority -> mark_review 不同时间/条件 -> keep_both with validity conditions model
inference vs user direct -> prefer user, retain provenance privacy conflict -> reject candidate
```
### Forget
Forget 是审计过的 tombstone/状态变更，而不是无痕物理删除：
```typescript
interface ForgetInput { memoryId: MemoryId; requestedBy: string; reason: "user" | "retention" | "privacy" | "correction"; cascade: boolean; }
```
执行：
1. 标记 `forgotten`；
2. 立即从 recall index 排除；
3. 清理缓存和派生 embedding；
4. 按 policy 删除 artifact/raw source；
5. 保留最小 tombstone 以阻止复活；
6. 记录审计，不在普通日志打印内容。
## Durability 与存储后端
### 事实日志要求
持久化必须具备：
- append-only 或等价审计能力；
- 单 stream 原子版本；
- payload hash 和 schema version；
- fsync/提交语义明确；
- 可重放和可校验；
- checkpoint 原子可见；
- artifact 引用可验证。
### 后端抽象
```typescript
interface DurableStateBackend { begin(stream: StreamRef): Promise<StateTransaction>; read(stream: StreamRef, range?: EntryRange):
AsyncIterable<SessionEntry>; writeCheckpoint(checkpoint: CheckpointRecord): Promise<void>; health(): Promise<BackendHealth>; }
```
小型 CLI 可以使用 JSONL/本地数据库适配器；server/多客户端场景应明确 event log 与 projector；抽象不能把具体格式泄漏进 Kernel。
### 写入顺序
```text
validate entry -> compute payload hash -> reserve expected version -> append durable entry -> flush backend -> update mandatory projection -> publish
durable event
```
UI event 可在之后异步发送；不能先发“成功”再尝试持久化。
## 迁移与版本兼容
### Schema 规则
每个 entry、checkpoint、memory、artifact metadata 都带 `schemaVersion`。版本变更分为：
- additive：增加可选字段；
- semantic：字段含义变化，必须写 upcaster；
- breaking：新 stream 或离线迁移，不覆盖原数据。
### Upcaster
```typescript
interface EntryUpcaster { from: SchemaVersion; to: SchemaVersion; canHandle(entry: SessionEntry): boolean; upcast(entry: SessionEntry): SessionEntry;
}
```
读取时可 upcast，写入时写当前版本；迁移失败应保留原 entry 并将 session 置为 `migration_required`，而不是返回部分投影。
### Migration 流程
```text
snapshot source -> validate counts/hashes -> dry-run upcasters -> compare projection before/after -> migrate copy or transaction -> verify replay ->
switch version marker -> retain rollback window
```
不能以“JSON 能解析”作为迁移成功标准；需要验证 tool pair、branch head、working state 和 memory provenance。
## 隐私、安全与数据外发
### Sensitivity
```text
public | internal | confidential | secret | regulated
```
等级决定：
- 是否可发送给 provider；
- 是否可进入 trace；
- 是否可写长期 memory；
- 是否可继承给 subagent；
- retention 和删除方式。
### Data Egress
Context Compiler 和 MemoryRecall 在交给模型前执行：
```text
provider jurisdiction + deployment/model + resource sensitivity + tenant policy + redaction rules -> allow | redact | artifact_only | deny
```
redaction map 只存可信边界；模型输出回写时不能盲目反替换。
### 多租户隔离
所有 session、branch、memory、artifact、projection、trace 查询都必须带 tenant/owner scope。不能依赖调用方“记得过滤”。
### 日志边界
默认日志只记录：
- ID、hash、类型、大小；
- provenance kind；
- 版本、耗时、状态；
- 脱敏摘要。
不得记录未脱敏 secret、bearer token、完整敏感 prompt、regulated 原文。
## Crash Recovery 与未知副作用
### 恢复流程
```text
process restart -> load last valid checkpoint -> scan entries after checkpoint -> validate hash chain/sequence -> identify pending approvals ->
identify in-flight tools -> query idempotency/status -> classify completed/failed/unknown -> rebuild projections/context -> resume or require human
decision
```
### In-flightToolState
```typescript
interface InFlightToolState { callId: string; toolName: string; idempotencyKey?: string; authorizationId?: string; startedAt: string; backendRef?:
string; status: "prepared" | "running" | "completed" | "failed" | "unknown"; sideEffectClass: "none" | "reversible" | "irreversible"; lastProbeAt?:
string; }
```
状态未知时：
- 只读操作可查询后有限重试；
- 可逆操作先查询并提供补偿；
- 付款、发送、删除、部署、权限修改不得盲目重放；
- 写入 `unknown_outcome` durable entry；
- 必要时等待人工确认。
### Pending Approval
Approval 是 durable state。重启后恢复审批界面或返回 `waiting_for_approval`，不能因为 host 连接丢失而默认为允许。
### Event/Projection 修复
发现 projection 落后时：
```text
stop dependent delivery -> replay from last good sequence -> compare state hash -> atomically switch projection -> resume consumers
```
## 可观测性与诊断
### Trace 层级
```text
session span -> branch span -> run span -> turn span -> attempt/model span -> tool span -> compaction span -> memory write/recall span -> checkpoint
span
```
### 必备字段
```text
trace_id session_id branch_id run_id turn_id attempt_id entry_id/sequence provider/model/api_family stream_version projector version checkpoint id
compaction source hash memory ids and scores artifact ids and hashes usage/cost/cache retry/fallback sensitivity decision
```
### 指标
- append latency 和 conflict rate；
- projection lag；
- checkpoint success/failure；
- recovery duration；
- duplicate replay count；
- compaction factual retention；
- memory write acceptance/rejection；
- stale/contradicted recall rate；
- artifact orphan count；
- unknown side-effect count；
- storage bytes 与 retention deletion lag。
### Diagnostic Snapshot
应输出脱敏快照：
```text
session/branch/version last durable entry active run/turn pending approvals in-flight tools checkpoint age projection lag compaction cursor memory
index health artifact references last errors
```
## 测试策略
### 单元测试
- Entry schema、hash、upcaster；
- projector 纯函数和幂等；
- branch ancestor 解析；
- CAS 冲突；
- compaction plan 和 coverage；
- memory score、TTL、scope、contradiction；
- redaction 和 retention policy。
### 契约测试
每个 EventStore、SessionRepository、ArtifactStore、MemoryStore 后端必须通过统一契约：
- append 版本严格递增；
- expectedVersion 错误不会写入；
- reload 能重建同一 projection；
- checkpoint 可读且 hash 可验证；
- forget 后 recall 不返回；
- artifact hash 不匹配会失败。
### 属性测试
```text
replay(entries) == replay(shuffle? 不允许改变顺序) apply(entry) twice == apply(entry) once fork(source, point) 的历史 == source 到 point compaction 保留 required
state forget 不会在任意 projection 复活 memory
```
### 故障注入
在每个 durable boundary 后注入崩溃：
- append 前；
- append 后 flush 前；
- checkpoint blob 写完但引用 entry 前；
- tool side effect 后 result commit 前；
- compaction candidate 验证前后；
- projector 更新中；
- artifact 上传中；
- approval resolution 后 delivery 前。
验证“不重复副作用、不丢 durable 事实、不把未知当成功”。
### 集成与回放
使用 `FakeModelProvider`、`ScriptedModelStream`、`FakeToolRuntime`、`DeterministicClock`、`CrashInjector` 和 `ReplayRunner`，不要让核心测试依赖付费 provider。
## 反模式与审查规则
1. 把 provider message 数组当唯一数据库模型。
2. 只在 run 成功时保存 transcript。
3. 用 `isRunning` 代替状态机。
4. 把 token delta 全量写 durable log。
5. 截断字符串并切断 tool call/result 对。
6. compaction 删除原历史且没有 source range/hash。
7. checkpoint 只保存最后一条文本。
8. CAS 冲突时静默覆盖远端写入。
9. revert 直接删除历史 entry。
10. snapshot 没有 base hash，patch 可以覆盖新版本。
11. 所有对话自动写长期 memory。
12. memory 没有 provenance、confidence、TTL 或 sensitivity。
13. 过期或矛盾 memory 被当作确定事实。
14. forget 只删索引，不清理缓存和派生数据。
15. 未知写操作结果自动重放。
16. projection 可写且无法从事实日志重建。
17. 日志打印完整敏感 transcript。
18. 跨租户查询只依赖上层过滤。
19. migration 只验证 JSON 可解析。
20. 把 memory recall 当作授权或审批。
审查时至少要求：
```text
事实来源明确 版本控制明确 失败边界明确 副作用状态明确 隐私删除可验证 projection 可重建
```
## 实施清单与分阶段交付
### V1：可验证状态内核
- [ ] 定义 Message/Part/Entry/Usage/ArtifactRef；
- [ ] 实现 InMemory EventStore；
- [ ] 实现 Session、Run、Turn、Attempt 区分；
- [ ] 实现 append + expectedVersion；
- [ ] 实现 TranscriptProjector 和 WorkingStateProjector；
- [ ] 建立 fake provider、event recorder、replay test。
### V2：可恢复 Harness
- [ ] durable backend；
- [ ] CheckpointRecord；
- [ ] pending approval 和 in-flight tool；
- [ ] crash recovery；
- [ ] artifact offload；
- [ ] retry/fallback/usage 归因。
### V3：分支与上下文治理
- [ ] branch/fork/revert；
- [ ] snapshot/patch base hash；
- [ ] compaction plan、source hash、verification；
- [ ] ContextPlan 投影；
- [ ] projection lag 和 replay 修复。
### V4：Memory 与隐私
- [ ] memory type/scope/provenance/confidence/TTL；
- [ ] write gate、recall ranking；
- [ ] contradiction、supersede、forget tombstone；
- [ ] sensitivity、tenant、egress policy；
- [ ] retention deletion 和 privacy audit。
### V5：规模化与迁移
- [ ] schema registry/upcaster；
- [ ] event projector 多消费者；
- [ ] actor 或分布式 session coordinator；
- [ ] durable queue 与 recovery worker；
- [ ] conformance suite、fault injection、operations dashboard。
## 五个参考项目的启发来源
### Pi
- `session tree` 启发 branch、fork 和 steering/follow-up 的显式语义；
- headless agent loop 与 EventStream 启发 durable/ephemeral 分离；
- `AgentSession` 与 compaction 实现启发可恢复的 compaction entry；
- `resource loader` 启发 provenance 和上下文资源引用；
- 依据：现有 `references/agent-reference-architecture.md` 与 `references/engineering/context-engineering.md` 中列出的 Pi 源码路径。
### Grok Build
- Session/ChatState actor 启发状态所有权和串行写入；
- sampler 分层启发 Attempt、retry/fallback 和 usage 归因；
- 工具结果修剪启发 Artifact offload 与输出预算；
- 路径级工具锁启发 snapshot/patch 的资源冲突控制；
- 依据：现有参考文档列出的 `xai-grok-shell/src/session`、`xai-grok-sampler/src`、`xai-grok-tools/src` 源码范围。
### OpenCode
- `session/message/part` 启发本文的 provider-neutral Message/Part 模型；
- durable event/projector 启发事实日志和多视图重建；
- snapshot/patch/revert 启发文件状态的可逆变更；
- server/event bus 启发多客户端 durable state 与慢消费者恢复；
- 依据：现有参考文档列出的 `packages/opencode/src/session`、`tool`、`server` 源码范围。
### Claude Code
- subagents、memory、skills、hooks 和计划工作流启发不同 scope 的资源治理；
- `CLAUDE.md` 与 auto memory 方向启发用户/项目规则和长期 memory 的来源标注；
- permission modes 启发 memory 与 authorization 分离；
- 公开能力和安全语义以现有文档中标注的 Anthropic 官方资料为准，不把辅助源码仓库视为规范；
- 依据：现有 `references/agent-reference-architecture.md`、`context-engineering.md`、`harness-engineering.md` 的已调研归纳。
### OpenClaw
- compaction 前 memory flush 启发受治理的候选提取；
- Markdown memory 与混合检索启发多来源 provenance 和召回排序；
- Gateway/channel session key 启发 tenant/identity/session scope；
- 插件事务化加载启发 migration、registration 和 rollback 的原子边界；
- 依据：现有参考文档列出的 `agent-core`、`harness/registry`、`plugins`、`llm-core` 源码范围。
本设计的实现审查应回到上述已有源码归纳和本地工程文档；若新增 provider、存储后端或合规要求，应单独补充一手证据和迁移约束。
