# Session Replay Engineering 细粒度工程设计

> 本文定义 Session 的 durable 事实、事件日志、树状分支、checkpoint、replay cursor、reducer/projector、上下文重建和隔离重放。它沿用 `Session`、`Run`、`Turn`、`Attempt`、`Message/Part`、`Provider`、`ModelRef`、`ModelCapabilities`、`Projector`、`Checkpoint`、`ArtifactRef`、`ContextPlan`、`Harness`、`ProviderAdapter`、`UsageLedger`、`CircuitBreaker`、`PolicySnapshot`、`ToolsetSnapshot` 和 `TenantContext` 等术语。
>
> 本设计只整理当前目录已有参考架构、Agent API 模式、Harness、State/Memory、Event/Observability、Context、Prompt、Tool、Artifact、Permission/Sandbox、Subagent、Provider Runtime、Provider Routing、Host Adapter、Coding Agent、Multi-tenant 和 Evaluation 文档中的源码调研结论；不把 README 当作规范，不新增网络调研结论。

## 目录

1. [设计目标与非目标](#设计目标与非目标)
2. [核心判断与术语](#核心判断与术语)
3. [职责边界](#职责边界)
4. [总体架构与包布局](#总体架构与包布局)
5. [Durable Semantic Entries](#durable-semantic-entries)
6. [Event Log 与 Session Tree](#event-log-与-session-tree)
7. [Run、Turn、Attempt 生命周期](#runturnattempt-生命周期)
8. [Checkpoint 与 Replay Cursor](#checkpoint-与-replay-cursor)
9. [Reducer、Projector 与快照](#reducerprojector-与快照)
10. [Context、Prompt、Toolset、Policy 与 Model Snapshot 重建](#contextprompttoolsetpolicy-与-model-snapshot-重建)
11. [Deterministic 与 Nondeterministic Replay](#deterministic-与-nondeterministic-replay)
12. [Tool Result 与 Artifact Capture](#tool-result-与-artifact-capture)
13. [Side-effect Quarantine](#side-effect-quarantine)
14. [Redaction 与隐私](#redaction-与隐私)
15. [Partial Replay、Time Travel 与 Fork/Resume](#partial-replaytime-travel-与-forkresume)
16. [Crash Recovery 与 Unknown Outcome](#crash-recovery-与-unknown-outcome)
17. [Schema Migration 与版本兼容](#schema-migration-与版本兼容)
18. [Multi-client Cursor 与交付](#multi-client-cursor-与交付)
19. [Audit、Forensics 与可观测性](#auditforensics-与可观测性)
20. [测试策略与运营用例](#测试策略与运营用例)
21. [生命周期与状态机](#生命周期与状态机)
22. [安全、隔离与威胁模型](#安全隔离与威胁模型)
23. [实施清单](#实施清单)
24. [反模式](#反模式)
25. [五个参考项目的启发来源](#五个参考项目的启发来源)

## 设计目标与非目标

### 目标

Session Replay 必须能够：

- 以 durable semantic entries 保存用户意图、assistant message/part、tool 调用、结果、审批、policy、context、model、usage、error、checkpoint 和控制事实。
- 以 append-only event log 作为事实来源，用 reducer/projector 从指定 cursor 重建 session/run 状态。
- 表达 session tree、branch、run、turn、attempt 之间的父子关系和分叉原因。
- 在 replay 时重建当时的 ContextPlan、prompt 编译结果、toolset、policy、model capabilities、routing snapshot 和 tenant scope。
- 区分 deterministic replay、recorded replay、simulated replay 与 live re-execution，明确每种模式的证据强度。
- 捕获 tool result、artifact、外部 receipt 和 unknown outcome，避免把“曾经发出”当作“已经成功”。
- 支持 crash recovery、partial replay、time travel、fork/resume、schema migration 和多客户端 cursor。
- 让测试、审计、故障取证、质量评估和运维排障都能使用同一套可追溯事实。

### 非目标

本文不定义：

- 将 session replay 当成无隔离的真实环境重放；真实工具和外部副作用必须 quarantine。
- 只保存最终 transcript，不保存 context、tool、policy、model、错误和版本事实。
- 通过重新请求 provider 就声称得到与原运行相同的 model 行为。
- 用 UI transcript、trace span 或缓存快照替代 durable event log。
- 让 replay 过程绕过当前 tenant、authorization、egress、secret 和 sandbox policy。
- 在没有明确 fork 和新 run 的情况下修改既有 session 历史。

## 核心判断与术语

### 核心判断

```text
Session Replay = durable facts + versioned reducers + explicit replay mode + isolated effects + auditable cursor
```

```text
State/Event Store 保存事实。
Reducer 将事件折叠为可验证状态。
Projector 生成不同用途的视图。
Context Runtime 重新计算可发送上下文。
Provider Runtime 只在允许的模式下调用 provider。
Tool Runtime 负责执行或模拟工具。
Policy/Sandbox 强制副作用边界。
Harness 负责调度、预算、恢复、fork 和交付。
Host Adapter 只消费投影和提交控制命令。
```

### Replay 不是盲目重放副作用

Replay 的默认目标是“重建语义和证据”，不是“再次触发真实世界动作”。

- 已记录的 provider response、tool result 和 artifact 可以作为输入重放。
- 未记录的 nondeterministic 结果只能被标记为 unavailable 或重新采样，不可伪称相同。
- 写文件、执行命令、发邮件、支付、部署、删除和 webhook 等动作必须进入 quarantine，除非新 run 有显式 policy、approval、sandbox 和幂等证明。
- replay 发现事件事实与外部当前状态不一致时，应记录 divergence，而不是修改历史。

### 术语

- `Session`：长期对话与任务事实的容器，可含多个 branch、run 和 delivery cursor。
- `Run`：一次有边界的执行，具有预算、policy、route、恢复和终止状态。
- `Turn`：一次模型采样及其关联工具批次。
- `Attempt`：具体 Provider/Model/Deployment 的调用尝试。
- `SemanticEntry`：面向业务语义的 durable 状态条目，如 message、tool result、checkpoint。
- `EventLog`：不可变、可排序、版本化的事实日志。
- `ReplayCursor`：重放所处的 session/branch/run/event 位置和 reducer 版本。
- `Checkpoint`：某一 cursor 对应的状态、依赖快照、hash 和恢复信息。
- `Projector`：将 canonical events 投影成 transcript、context、audit、host 或 evaluation 视图。
- `ArtifactRef`：大对象、原始 provider payload、命令输出或文件快照的受控引用。
- `ReplayMode`：`semantic`、`recorded`、`deterministic`、`simulated`、`live_quarantined` 等显式模式。

## 职责边界

### Replay Runtime 负责

- 读取带 scope、版本和 hash 的 event log、semantic entries、checkpoint 和 artifact refs。
- 校验 parent chain、sequence、schema、tenant、session/branch ownership 和 cursor。
- 用 reducer/projector 重建状态、transcript、ContextPlan、toolset、policy、model 和 usage view。
- 根据 replay mode 选择 recorded input、deterministic stub、simulation 或隔离的新 attempt。
- 生成 divergence、missing input、unknown outcome、migration 和 replay evidence。
- 在 fork/resume 时创建新的 branch/run，保留源 cursor、原因和 policy snapshot。

### Replay Runtime 不负责

- 直接把任意历史事件写回生产工具、文件系统、网络或 provider。
- 以当前配置静默覆盖历史 policy、model、toolset、tenant 或 prompt 版本。
- 把 projector 视图当作可编辑的事实表。
- 删除原 event、修改原 cursor 或覆盖已有 branch 以“修复”重放结果。
- 因客户端请求 replay 而绕过权限、redaction、retention 和 artifact ACL。

### 强制边界

```text
EventLog/StateStore -> ReplayReader -> CursorValidator
                    -> Reducer/Projector
                    -> Context/Tool/Policy/Model reconstruction
                    -> Recorded inputs or Quarantine runtime
                    -> Replay evidence / new fork
```

```text
Replay 只读历史事实；任何新副作用必须属于新的 Run，
拥有独立 scope、checkpoint、预算、policy 和 audit。
```

## 总体架构与包布局

```text
Session/Branch/Run target
  -> Auth + Tenant Scope Guard
  -> Replay Plan Builder
  -> Cursor/Schema/Integrity Validator
  -> Checkpoint Loader
  -> Event Reader
  -> Reducer
  -> Projector(s)
  -> Snapshot Reconstruction
  -> Replay Input Resolver
  -> Deterministic Stub / Tool Quarantine / Provider Recording
  -> Divergence Detector
  -> Replay Report / Fork / Host Delivery
```

推荐包布局：

```text
packages/session-replay/
  contracts.ts
  semantic-entry.ts
  event-log.ts
  session-tree.ts
  cursor.ts
  checkpoint.ts
  reducer.ts
  projector.ts
  replay-plan.ts
  context-reconstruction.ts
  tool-replay.ts
  provider-replay.ts
  artifact-capture.ts
  quarantine.ts
  redaction.ts
  migration.ts
  divergence.ts
  forensics.ts
  cursors.ts
  modes.ts
  testkit/
```

依赖方向：

```text
Harness -> ReplayPlan / ReplayPort
Replay -> State/Event/Artifact ports
Projector -> canonical event contracts
Context reconstruction -> ContextPlan contracts
Tool/provider replay -> explicit quarantine ports
Host Adapter -> replay snapshot and event projection
```

## Durable Semantic Entries

### Entry 类型

```typescript
interface SemanticEntry {
  entryId: string;
  sessionId: string;
  branchId: string;
  runId?: string;
  turnId?: string;
  attemptId?: string;
  kind: SemanticEntryKind;
  parentEntryIds: string[];
  payload: unknown;
  schemaVersion: number;
  occurredAt: string;
  recordedAt: string;
  scope: ScopeRef;
  sensitivity: Sensitivity;
  contentHash: string;
  sourceEventId: string;
}
```

主要 `kind` 包括：

- `session.created`、`session.branch_created`、`session.renamed`；
- `user.message`、`assistant.message`、`message.part`；
- `tool.call`、`tool.result`、`tool.error`、`tool.approval`；
- `run.started`、`run.completed`、`run.failed`、`run.cancelled`；
- `turn.started`、`turn.completed`、`attempt.started`、`attempt.completed`；
- `context.plan`、`prompt.compiled`、`toolset.snapshot`、`policy.snapshot`；
- `model.resolved`、`routing.snapshot`、`usage.observed`、`cost.settled`；
- `checkpoint.created`、`replay.started`、`replay.diverged`、`fork.created`。

### Semantic 与 transport 分离

Transport event 可以有 provider delta、heartbeat、delivery ack 和 trace marker；这些不一定是 semantic entry。Reducer 的输入必须明确哪些事件构成 durable truth，哪些只是临时观察。

- `message.delta` 可以在 stream 阶段短暂存在，完成后归并为 immutable message/part。
- `Host ack` 只能记录交付事实，不能变成 assistant message。
- `trace span` 只能提供观测证据，不能授权 replay 修改状态。
- raw provider payload 以 `ArtifactRef` 保存并由 semantic entry 引用，不把完整 payload 嵌入所有视图。

### Entry 不变量

- 同一 entry ID 幂等写入且 content hash 不可变。
- entry scope 必须与 session/branch/run/tenant 的 ownership 一致。
- parent entry 必须存在或显式标为 pending reference；不可产生孤立事实。
- schema、source event、adapter/model/policy/context 版本可追溯。
- redaction 后若无法验证原值，必须标记 `redacted` 而不是空字符串。

## Event Log 与 Session Tree

### Event log

```typescript
interface CanonicalEventRecord {
  eventId: string;
  streamId: string;
  sessionId: string;
  branchId: string;
  runId?: string;
  seq: number;
  globalOrder?: string;
  type: string;
  schemaVersion: number;
  payloadRef: ArtifactRef | InlinePayload;
  parentEventIds: string[];
  occurredAt: string;
  appendedAt: string;
  scope: ScopeRef;
  producer: string;
  contentHash: string;
}
```

Event log 采用 append-only 语义。追加时检查 expected stream version、seq、scope、parent chain 和 idempotency key。事件顺序以 stream-local seq 为准，跨 stream 通过 parent links、clock evidence 和 Harness order 解释。

### Session tree

```text
Session
  ├─ Branch main
  │   ├─ Run A
  │   │   ├─ Turn 1
  │   │   │   └─ Attempt 1
  │   │   └─ Turn 2
  │   └─ Run B (resume)
  └─ Branch experiment (fork at cursor C)
      └─ Run C
```

branch 不是复制整份 transcript 的平面列表，而是：

- `baseBranchId`、`forkCursor`、`branchPolicy` 和 overlay entries；
- 可见 ancestor chain 与 branch-local entries 的合并规则；
- 独立的 current head、checkpoint、cursor 和 delivery state；
- fork reason、requester、approval 和 source run 引用。

### 分支不变量

- 历史 ancestor immutable；branch 只能 append overlay。
- fork 处的 ContextPlan、toolset、policy、model 和 tenant snapshot 必须明确继承还是重建。
- branch 间不得共享可变 checkpoint、tool lease、工作区或 provider cache。
- 合并不是 replay 默认动作；若需合并，必须创建可审计的 merge entry 和冲突结果。

## Run、Turn、Attempt 生命周期

### 生命周期

```text
Session active
  -> Run created
  -> Turn started
  -> Attempt started
  -> provider response / tool call
  -> Tool execution or recorded result
  -> Turn completed
  -> next Turn / Run completed
```

### 状态机

```text
Run:     created -> queued -> running -> waiting_tool
                         -> paused -> completed/failed/cancelled/unknown
Turn:    created -> sampling -> tool_pending -> sampling -> completed
Attempt: created -> validated -> dispatched -> streaming
                  -> completed/failed/cancelled/unknown_outcome
```

每次状态转换都应产生 canonical event 或 semantic entry。模型文本中的“已完成”不能替代状态事实。

### Replay 中的层次

- replay 可以只重建 Session/Branch/Run，不重新执行 Turn/Attempt。
- partial replay 可以从最近 checkpoint 恢复，并只读取后续 event。
- 重新生成 Turn 会创建新的 replay attempt，不覆盖历史 attempt。
- tool pending 状态需要保留调用参数、授权决定、lease 和结果是否已记录。

## Checkpoint 与 Replay Cursor

### Checkpoint

```typescript
interface Checkpoint {
  checkpointId: string;
  sessionId: string;
  branchId: string;
  runId?: string;
  cursor: ReplayCursor;
  stateHash: string;
  reducerVersion: string;
  projectorVersions: Record<string, string>;
  contextPlanRef?: ArtifactRef;
  toolsetSnapshotRef?: ArtifactRef;
  policySnapshotRef?: ArtifactRef;
  modelSnapshotRef?: ArtifactRef;
  workspaceSnapshotRef?: ArtifactRef;
  ledgerCursor?: string;
  createdAt: string;
  reason: "turn_boundary" | "tool_boundary" | "periodic" | "crash_recovery" | "manual";
}
```

checkpoint 是加速和恢复证据，不是新的真相源。加载后必须验证 state hash、依赖引用、scope 和 event tail。

### ReplayCursor

```typescript
interface ReplayCursor {
  sessionId: string;
  branchId: string;
  runId?: string;
  eventSeq: number;
  entryId?: string;
  checkpointId?: string;
  reducerVersion: string;
  projectorVersions: Record<string, string>;
  cursorHash: string;
}
```

cursor 必须可序列化、可授权、可过期或撤销，并且不能仅用 UI offset 表示。多客户端 ack cursor 与 replay cursor 分离：前者是交付位置，后者是状态重建位置。

### Checkpoint 选择

- turn boundary 是默认语义边界；tool boundary 用于副作用恢复。
- 大 session 可按 event 数、字节、时间或 context 变更创建周期 checkpoint。
- checkpoint 创建失败不应静默丢事件；运行可继续但标记恢复风险。
- 重放发现 checkpoint 与 event tail 不一致时，丢弃 checkpoint 视图并从更早可靠点重建。

## Reducer、Projector 与快照

### Reducer

Reducer 将 immutable events 折叠为可验证状态：

```typescript
interface SessionReducer<S> {
  initial(): S;
  apply(state: S, event: CanonicalEventRecord): ReduceResult<S>;
  version: string;
  invariants: InvariantCheck[];
}
```

Reducer 必须尽量纯函数、幂等、可检测未知 event。不能通过网络、当前时间、随机数或全局配置改变历史状态。

### Projector

一个 event log 可以有多个 projector：

- `TranscriptProjector`：生成用户可见 message/part；
- `ContextProjector`：生成候选上下文和来源；
- `RunStateProjector`：生成运行状态与 pending tool；
- `AuditProjector`：生成权限、审批、外发、控制和恢复审计；
- `EvaluationProjector`：生成 fixture、label、quality evidence；
- `HostProjector`：按宿主能力投影事件和 artifact。

projector 视图可重建、可版本化，不拥有原始事实。

### Snapshot 验证

快照必须带 source cursor、schema/reducer/projector version、state hash、createdAt 和 scope。读取快照时：

```text
verify ownership -> verify version compatibility -> verify state hash
-> verify cursor -> read event tail -> apply reducer -> compare hash
```

## Context、Prompt、Toolset、Policy 与 Model Snapshot 重建

### 重建输入

Replay 到 cursor 时至少需要恢复：

- visible semantic entries、branch ancestor 和用户/assistant/tool message；
- 当时的 `ContextPlan`、选取原因、截断/摘要策略和 source hash；
- Prompt compiler、template、system instruction 和 policy floor 版本；
- `ToolsetSnapshot`、工具 schema、visibility、approval 和 execution profile；
- `PolicySnapshot`、`TenantContext`、egress、sandbox、budget 和 approval 状态；
- `ModelRef`、`ResolvedModel`、`ModelCapabilities`、`RoutingSnapshot` 和 adapter version；
- workspace/file snapshot、artifact refs、usage ledger cursor 和 environment metadata。

### Context reconstruction

优先使用已记录的 ContextPlan；若不存在，才依据当时版本的 Context/State 规则重建，并标记 `reconstructed_not_recorded`。不能用今天的 memory、当前 branch 或最新 system prompt 静默替代历史输入。

```text
cursor
  -> visible entries
  -> branch ancestry
  -> ContextPlan snapshot or versioned reconstruction
  -> prompt compilation evidence
  -> toolset/policy/model snapshots
  -> replay input bundle
```

### 差异处理

缺失或不兼容依赖分为：

- `exact`：使用原快照和记录输入；
- `compatible`：使用兼容 projector/adapter，产生 warning；
- `reconstructed`：根据版本规则重建，不能宣称完全相同；
- `missing`：停止该段 replay，保留 partial report；
- `unsafe`：因 scope、policy、secret 或 side effect 风险拒绝。

## Deterministic 与 Nondeterministic Replay

### Replay 模式

```typescript
type ReplayMode =
  | "semantic"          // 只重建 durable state
  | "recorded"           // 使用已记录 provider/tool 输入
  | "deterministic"      // 使用固定 clock/random/provider/tool doubles
  | "simulated"          // 运行模型或工具模拟器
  | "live_quarantined"   // 新 attempt，严格隔离和审计
```

### Deterministic 条件

要声称 deterministic，需要固定：

- provider response/stream fixture 或可证明相同的本地 double；
- clock、random seed、locale、排序、schema 和 tokenizer/估算版本；
- tool result、文件树、网络返回、环境变量和 workspace snapshot；
- prompt/context/toolset/policy/model/adapter 的版本和 hash。

即使满足条件，也应将“同一输入得到同一 replay 结果”限定为该测试 harness，而不是宣称真实 provider 永远确定。

### Nondeterministic 处理

以下因素通常导致 divergence：模型采样、实时 provider alias、当前文件、时间、网络、工具外部状态、异步事件顺序和 secret rotation。处理方式：

- 使用录制结果；
- 使用 stub 并记录替代关系；
- 在隔离新 run 中重新执行并比较 semantic diff；
- 将 divergence、unknown 和 missing evidence 显式写入 report。

## Tool Result 与 Artifact Capture

### Tool 事实

每个 tool call/result 至少保存：

```typescript
interface ToolReplayRecord {
  callId: string;
  toolName: string;
  argumentsHash: string;
  argumentsRef?: ArtifactRef;
  policySnapshotId: string;
  approvalRef?: string;
  executionProfile: string;
  startedAt: string;
  completedAt?: string;
  outcome: "success" | "error" | "cancelled" | "unknown" | "redacted";
  resultRef?: ArtifactRef;
  sideEffectReceipt?: ArtifactRef;
  replayability: "recorded" | "deterministic" | "simulatable" | "unsafe";
}
```

tool result 是历史事实，但不是当前外部系统事实。Replay 读取 result 时标记 `recorded_at` 和 source environment。

### Artifact capture

Artifact 适用于：

- provider raw payload、stream recording、命令 stdout/stderr；
- 文件 snapshot、patch、diff、构建/测试结果；
- 大型 tool result、图片/音频/视频和安全诊断包；
- replay report、migration evidence 和 forensic bundle。

每个 `ArtifactRef` 必须有 owner scope、content hash、MIME、大小、retention、redaction profile 和 ACL。重放不得因 artifact URL 已存在就绕过当前授权。

### 未捕获结果

如果历史只记录 tool call 没有 result，不得填充“成功”；标记 `missing_tool_result`，可在 semantic replay 停在 pending，在 simulation 中用明确 stub，或在新 quarantined run 中重新执行。

## Side-effect Quarantine

### 隔离等级

```text
Level 0: no execution, reducer/projector only
Level 1: pure parser and deterministic in-memory doubles
Level 2: ephemeral filesystem/process sandbox, no network
Level 3: allowlisted test endpoint with synthetic data
Level 4: live external effect (默认禁止)
```

默认 replay 最高为 Level 1。进入 Level 2/3 必须有新的 Run、policy、approval、budget、lease、workspace 和 artifact namespace。

### Quarantine 约束

- 工具调用必须绑定 `ReplayExecutionContext`，明确 mode、source cursor、tenant、sandbox profile 和 egress allowlist。
- 真实 provider 只能在 `live_quarantined` 使用专用 model/credential/region 和最小数据。
- 文件、命令、网络、子进程和 webhook 均需显式 capability；默认 deny。
- side-effect receipt 与 semantic result 分开保存；不能把模拟成功写成真实成功。
- 发现重复执行风险时停止并生成 `unsafe_replay`。

### Fork 与副作用

任何可能改变外部世界的动作都必须 fork 到新 branch/run。源 session 只保留“请求 fork”和“fork 结果”事实，不被新副作用隐式污染。

## Redaction 与隐私

### Redaction 层次

- 展示层：按 Host、角色和目的隐藏内容；
- replay 输入层：去除不需要的 PII、secret、凭据和大附件；
- artifact 层：分区、加密、短 retention 和 ACL；
- forensic 层：允许最小必要提升，但需审批和审计；
- 删除层：从索引、cache、projection、fixture 和导出中清除。

### Redaction 不变量

- redaction 不能改变 entry ID、seq、parent、hash relation、scope 和 outcome 状态。
- 无法暴露 payload 时，保留类型、长度、hash、redaction reason 和是否可 replay。
- replay 不得通过 provider error、tool argument、artifact filename、URL、trace attribute 或时间 metadata 泄露被隐藏值。
- 跨 tenant/session/branch 的 artifact、cursor、cache、snapshot 必须拒绝。

## Partial Replay、Time Travel 与 Fork/Resume

### Partial replay

partial replay 适用于：

- 从 checkpoint 到指定 event 的状态检查；
- 只重放某个 Turn 或某个 tool boundary；
- 仅投影 transcript、audit、context 或 evaluation；
- 失败后从最后可验证 cursor 继续。

报告必须列出 `startCursor`、`endCursor`、未读取的 ancestor、missing dependency 和是否完整。

### Time travel

Time travel 是“在历史 cursor 查看状态”，不是修改过去。读取必须使用当时有效的 reducer/projector/context/policy version。当前权限只决定谁能查看历史，不会改变历史内容。

### Fork/Resume

```text
source session + source branch + fork cursor
  -> authorize fork
  -> copy immutable references, not mutable state
  -> choose inherited/rebuilt snapshots
  -> create new branch
  -> create new Run
  -> checkpoint before first action
  -> append fork/resume entries
```

resume 可以继续未完成 run，但必须检查 lease、unknown outcome、tool result 和 policy expiry。若无法证明可安全继续，应 fork 新 run，并把源 run 标记为 recovered/unknown。

## Crash Recovery 与 Unknown Outcome

### 崩溃恢复顺序

```text
load session scope
  -> locate last durable event
  -> validate latest checkpoint
  -> inspect run/turn/attempt status
  -> inspect tool lease and provider receipt
  -> inspect ledger settlement
  -> classify completed/failed/unknown
  -> append recovery event
  -> resume or fork
```

### Unknown outcome

网络断开、进程崩溃或 provider 超时可能发生在请求已接受之后。此时：

- 不自动复制发送原请求；
- 读取 idempotency receipt、provider request ID、stream tail 和 ledger evidence；
- 若可查询且安全，使用只读状态查询；
- 否则写 `attempt.unknown_outcome`，暂停 run，要求恢复策略或人工决定；
- 任何新尝试都使用新 attempt，并将潜在重复成本/副作用展示给 Harness。

### Checkpoint 恢复

checkpoint 只恢复内部状态，不能恢复外部副作用。tool lease 需要重新校验，secret 需要重新发放，workspace 需要重新锁定，provider circuit/budget 需要读取当前策略并保留历史快照。

## Schema Migration 与版本兼容

### 版本维度

```text
entrySchemaVersion
eventSchemaVersion
reducerVersion
projectorVersion
checkpointVersion
replayPlanVersion
contextPlanVersion
promptCompilerVersion
toolSchemaVersion
policyVersion
modelSnapshotVersion
adapterVersion
artifactManifestVersion
```

### Migration 原则

- 原始 event immutable；migration 生成新读取视图或新版本事件，不覆盖历史 payload。
- 每个 migration 声明输入/输出 schema、可逆性、丢失字段、redaction 影响和验证器。
- reducer 可读取旧 event；不能因未知 future event 静默跳过必需状态。
- checkpoint 不能直接跨不兼容 reducer 使用；应从兼容 ancestor 重建。
- migration 后比较 entry count、parent chain、seq、scope、hash relation、usage 和终止状态。

### Migration 状态

```text
planned -> sampled -> validated -> dual_read
        -> promoted -> deprecated
```

失败 migration 保留原读路径；不能以“修复快照”删除 forensic 证据。

## Multi-client Cursor 与交付

### Cursor 类型

- `replay cursor`：重建状态的位置；
- `delivery cursor`：某客户端已收到/确认的 HostEvent；
- `audit cursor`：审计消费者已处理的位置；
- `projection cursor`：某 projector 的构建位置；
- `checkpoint cursor`：快照覆盖的位置。

它们可相同但不能混用。客户端 ack 不代表 run 成功、tool 成功或 artifact 已持久化。

### 多客户端规则

- 每个 client 使用独立 cursor、权限和 redaction profile。
- event delivery 支持 cumulative ack、resume、重复投递和 backpressure。
- 新 client 可从 snapshot + tail 订阅；不能要求 server 为每个 client 复制整棵 session tree。
- 控制命令通过 Harness 排序和授权；一个客户端的 cancel/steering 不应绕过其他客户端可见的 audit。
- 断线重连读取 durable cursor；客户端本地 transcript 不作为恢复依据。

## Audit、Forensics 与可观测性

### Audit facts

审计至少记录：

- 谁在何时以什么 `TenantContext` 读取、重放、导出、fork 或 resume；
- source session/branch/run/cursor、replay mode、reducer/projector 版本；
- 使用了哪些 context、prompt、toolset、policy、model、artifact 和 provider receipt；
- 哪些 tool/provider 被模拟、跳过、拒绝或隔离执行；
- divergence、unknown outcome、migration、redaction、approval 和外部副作用 receipt。

### Forensic bundle

forensic bundle 不是“全部原始数据打包”，而是最小可验证证据集合：

```text
session/branch/run identity
source and target cursors
reducer/projector/replay versions
semantic entry manifest
context/toolset/policy/model hashes
artifact manifest and redaction report
usage/cost references
error/divergence/recovery events
```

大 payload 通过受控 `ArtifactRef` 引用。导出需要 scope、目的、expiry 和审计。

### 指标

- replay requested/running/completed/partial/failed/unsafe；
- checkpoint hit ratio、tail events、reducer duration；
- missing input、schema migration、divergence、unknown outcome；
- fork/resume、tool quarantine deny、provider recording hit/miss；
- artifact fetch/redaction/retention、cursor lag、multi-client backpressure；
- crash recovery time、duplicate attempt prevention、ledger reconciliation。

## 测试策略与运营用例

### 单元和契约测试

- reducer 对空流、重复 event、乱序、未知 event、非法 parent 和 schema 版本的行为；
- projector 在不同 host/redaction/capability 下的稳定输出；
- cursor 签名、scope、过期、resume 和幂等；
- checkpoint hash、snapshot + tail 重建、branch ancestry 和 fork；
- context/prompt/toolset/policy/model snapshot 的 exact/compatible/reconstructed 分类；
- artifact manifest、redaction、retention 和 ACL；
- provider/tool recorded replay 与 unknown outcome 分类。

### 故障注入

注入 checkpoint 损坏、event gap、重复 event、截断 artifact、migration 失败、lease 过期、provider 断流、tool 结果缺失、网络恢复、客户端重复 ack 和跨 tenant cursor。期望是 fail closed、保留证据、生成 recovery event，而不是猜测成功。

### Evaluation 用例

Replay 可用于：

- 复现模型/工具循环，比较 prompt/context/toolset 变化；
- 对同一历史输入测试新的 reducer/projector/provider adapter；
- 验证 coding agent 的文件 snapshot、patch、命令输出和测试证据；
- 评估 context 压缩、fallback、cost policy 和 safety policy；
- 为人工 review 提供 time travel transcript、audit 和 divergence。

Evaluation 结果应引用 source cursor 和 fixture hash，不能回写成原 session 的 assistant message。

### 运营用例

- 用户断线后从 checkpoint + event tail 恢复；
- provider 事故后对失败 attempt 做 recorded replay 和 usage 对账；
- 安全事件中导出最小 forensic bundle；
- schema migration 前 dual-read 检查旧 session；
- 发现 tool side effect 不一致时暂停 run，进行 quarantine replay；
- 多客户端同时浏览 session 时保持各自 cursor 和权限。

## 生命周期与状态机

### Replay Job

```text
requested
  -> authorized
  -> planned
  -> checkpoint_loaded
  -> events_reduced
  -> inputs_resolved
  -> replaying
  -> compared
  -> reported
  -> completed/partial/failed/unsafe
```

### Fork/Resume

```text
fork_requested -> source_validated -> branch_created
  -> run_created -> checkpointed -> resumed
  -> completed/paused/failed/unknown
```

任何 `unsafe`、`unknown`、`partial` 结果都必须携带原因、cursor、缺失证据和下一步建议。

### 幂等

Replay plan、checkpoint load、projector build、artifact resolve、fork request、usage reconciliation 和 report publication 都使用稳定 idempotency key。重复请求返回既有 receipt，不重复执行工具或 provider。

## 安全、隔离与威胁模型

### 不可信输入

- 用户提交的 session/branch/run/cursor/artifact ID；
- 模型生成的 tool arguments、文件路径、URL、tenant/resource ID；
- historical prompt、provider payload、tool result、webhook、插件和 hook；
- 客户端控制命令、resume token、redaction profile 和 fork metadata。

### 主要威胁

- 越权读取其他 tenant/session/branch 的 event、checkpoint、raw payload 或 artifact；
- 通过 replay 重新发送历史 secrets、请求或外部副作用；
- 通过 branch overlay、cursor 或 projector 绕过 policy；
- 旧 snapshot、当前配置和历史事实混合导致错误 resume；
- event/schema bomb、超大 artifact、递归 payload 和恶意工具结果；
- 多客户端 cursor、cache、worker lease 或导出任务串线。

### 强制保护

- 入口身份生成且冻结 `TenantContext`；不信任 URL、prompt、tool args 中的 scope。
- 每个 event、checkpoint、artifact、cursor 和 branch 再次检查 owner，不只依赖查询条件。
- replay 默认 read-only；live_quarantined 必须新 run、新 scope、新 sandbox、新预算和新审计。
- secret 不进入历史 payload；必要时保存 secret version/ref，而不是值。
- redaction、retention、delete/export 应传播到 projections、caches、fixtures、forensic bundles。
- 旧 policy 只能解释历史，当前副作用必须重新满足当前 policy floor。

## 实施清单

### 事实与存储

- [ ] 固定 semantic entry、canonical event、session tree、branch overlay 和 parent chain。
- [ ] 建立 append-only event log、expected version、幂等和 content hash。
- [ ] 定义 message/part、tool、run/turn/attempt、usage、error、checkpoint 和 control entries。
- [ ] 为大型 payload 建立 ArtifactRef、ACL、retention、redaction 和 manifest。

### 重建与执行

- [ ] 实现 ReplayCursor、Checkpoint、Reducer、Projector 和 snapshot validation。
- [ ] 记录并恢复 ContextPlan、prompt compiler、ToolsetSnapshot、PolicySnapshot、ResolvedModel、RoutingSnapshot。
- [ ] 明确 semantic、recorded、deterministic、simulated、live_quarantined 模式。
- [ ] 建立 tool/provider recording、deterministic doubles、unknown outcome 和 divergence detector。
- [ ] 实现 partial replay、time travel、fork/resume 和 crash recovery。

### 版本与运营

- [ ] 为 event/entry/reducer/projector/checkpoint/context/tool/policy/model/adapter/artifact 定义版本。
- [ ] 建立 sampled migration、dual-read、hash/invariant 校验和回滚。
- [ ] 分离 replay、delivery、audit、projection、checkpoint cursor。
- [ ] 配置 multi-client resume、backpressure、cursor lag 和权限测试。
- [ ] 建立 forensic bundle、replay report、usage reconciliation 和运营告警。

### 安全测试

- [ ] 覆盖跨 tenant/session/branch/artifact/cursor 越权。
- [ ] 覆盖真实工具、文件、网络、provider、secret 和 webhook 的 quarantine。
- [ ] 覆盖缺失 result、重复 event、损坏 checkpoint、schema bomb 和 redaction 泄漏。
- [ ] 验证 replay 不会把模拟结果写成历史事实或绕过当前 policy。

## 反模式

- 只保存最终聊天文本，不保存 ContextPlan、ToolsetSnapshot、PolicySnapshot、ModelRef 和版本。
- 用当前 prompt、当前工具列表或当前 model alias 重放旧 session，却声称结果可复现。
- 把 Host ack、trace span 或 UI transcript 当成 durable execution truth。
- 在原 branch 上修改历史或用新 replay 结果覆盖旧 assistant message。
- 断线后自动重发 provider/tool request，忽略 unknown outcome 和幂等证据。
- 将 tool call 当作 tool success，或将 provider stream EOF 当作业务完成。
- 让 replay 直接使用生产 workspace、credential、网络、消息、支付或部署。
- 共享 checkpoint、cache、artifact root 或 mutable workspace 给不同 branch/tenant。
- 把 cursor offset 当作权限证明，或把客户端 ack 当作执行成功。
- migration 直接删除旧 event、覆盖 payload 或用 golden 更新掩盖数据丢失。
- 只对 transcript 做 redaction，遗漏 artifact、error、URL、metadata、cache 和 forensic export。
- 用一次成功 replay 证明真实 provider、真实工具和当前外部系统仍然一致。

## 五个参考项目的启发来源

- `earendil-works/pi`：启发 session、message/part、tool loop、stream event 和可恢复上下文需要分层；本设计进一步用 semantic entries、attempt 和 projector 固化边界。
- `xai-org/grok-build`：启发 provider/model、运行事件、配置快照和原始响应证据需要可追踪；本设计把它们纳入 replay input bundle 和 divergence report。
- `anomalyco/opencode`：启发 session、permission、tool、event 和 provider 结果不能只靠 UI transcript 表达，应保留可投影事实。
- `claude-code-best/claude-code`：启发 coding agent 的 workspace、patch、命令输出、测试 artifact、checkpoint 和用户 steering 都需要可恢复、可审计的状态。
- `openclaw/openclaw`：启发多宿主、后台任务、插件、外部 channel 和长生命周期 session 需要 cursor、scope、隔离、重连和副作用边界。

这些启发只用于解释本地调研中已经记录的架构模式；本设计的 replay 结论仍以 durable event、snapshot、policy、quarantine、cursor 和 Harness 恢复边界为准。
