# Workflow Versioning Engineering 细粒度工程设计

> 本文定义 Agent Workflow 的版本化、发布、执行锁定、迁移、回滚和演进控制面，覆盖 Workflow Definition、Run Snapshot、Step Schema、Tool/Provider Contract、Subagent、Artifact、Queue、State、Policy、Harness、Evaluation 与 Observability。
>
> 本设计只基于当前目录已有的参考架构、本地 `agent-harness.md`、State & Memory、Agent Product、Workflow Orchestration、Context、Prompt、Harness、Tool、Permission & Sandbox、Subagent、Event & Observability、Evaluation、Provider Schema Evolution、Durable Queue、Privacy、Agent Memory Product、Memory Governance 以及五个参考项目源码归纳；不依赖 README，不进行网络搜索。
>
> 核心结论：Workflow Versioning 不是给 definition 增加 `version` 字符串。它必须把 definition、contract、policy、provider、prompt、tool、memory、artifact、queue、run、migration、rollback 和 audit 组合成可复现的 execution snapshot；运行中的实例不能被静默重写。

## 目录

1. [设计目标与非目标](#设计目标与非目标)
2. [版本化边界与 truth](#版本化边界与-truth)
3. [Definition、Snapshot、Run 与包布局](#definitionsnapshotrun-与包布局)
4. [版本身份、Hash、Lineage 与不可变性](#版本身份hashlineage-与不可变性)
5. [Schema、Contract、Compatibility 与 Validation](#schemacontractcompatibility-与-validation)
6. [发布通道、状态机与环境](#发布通道状态机与环境)
7. [Run Snapshot、Step Execution 与动态能力](#run-snapshotstep-execution-与动态能力)
8. [Migration、Resume、Pause、Cancel 与 Rollback](#migrationresume-pause-cancel-与-rollback)
9. [Provider、Tool、Prompt、Context、Memory、Policy 集成](#providertoolpromptcontextmemorypolicy-集成)
10. [Queue、Subagent、Artifact、State 与副作用](#queuesubagentartifactstate-与副作用)
11. [数据模型与 TypeScript contracts](#数据模型与-typescript-contracts)
12. [Durable Events、Receipt 与 Observability](#durable-eventsreceipt-与-observability)
13. [故障模型、Reconciliation 与 Recovery](#故障模型reconciliation-与-recovery)
14. [安全、隐私、权限与供应链](#安全隐私权限与供应链)
15. [测试、Evaluation 与发布门禁](#测试evaluation-与发布门禁)
16. [反模式与实施清单](#反模式与实施清单)
17. [五个参考项目的启发](#五个参考项目的启发)
18. [Definition of Done](#definition-of-done)

## 设计目标与非目标

### 目标

- 让 definition 有不可变版本、内容 hash、父版本 lineage、变更摘要和兼容性结论。
- 让每个 Run 锁定可重放的 WorkflowSnapshot，而不是每次执行读取 latest。
- 区分 definition、published version、deployment、run snapshot、step attempt、artifact 和 output。
- 对 prompt、tool schema、provider profile、context recipe、memory policy、permission profile、queue、subagent contract 建立版本锁。
- 支持 draft、validate、review、canary、active、deprecated、retired、blocked、rollback、sunset。
- 支持不迁移运行中的 run、安全边界迁移、可恢复 resume 和受控 rollback。
- 让 schema evolution 有 additive、compatible、breaking、unsafe 四级判断。
- 对 queued、running、paused、waiting approval、waiting input、retrying、completed、failed、cancelled、unknown 有明确状态。
- 让副作用具备 idempotency key、attempt identity、commit receipt、fencing 和 reconciliation。
- 让 subagent、workflow step、tool、provider fallback 不能绕过父级 snapshot 和 policy。
- 让 artifact、memory、context、event、queue 和 audit 可按版本追踪和删除。
- 用 deterministic replay、fault injection、contract test、golden fixture 和 evaluation 证明演进安全。

### 非目标

- 不把 workflow version 当作所有资源的全局版本号。
- 不允许运行中 run 通过读取 latest definition 获得隐式行为变化。
- 不用 git branch、文件名或 UI label 作为唯一版本身份。
- 不承诺任意 breaking change 都能自动迁移。
- 不用 prompt 告诉模型“请使用旧版本”代替 runtime snapshot。
- 不把 provider API model name 当作完整 provider contract。
- 不把 tool schema compatible 当作业务语义 compatible。
- 不把 retry 当作安全 recovery。
- 不把 rollback 当作删除已经发生的外部副作用。
- 不把 event projector 的状态当 canonical definition。
- 不把用户看到的“已发布”当作 deployment 已生效。

## 版本化边界与 truth

### 五种 truth

```text
Definition Truth  设计者提交的不可变工作流版本
Deployment Truth  某环境/租户当前选择的版本及策略
Snapshot Truth    某个 Run 实际锁定的完整执行输入
Execution Truth   每个 step/attempt/副作用的真实状态
Presentation Truth UI、日志、模型文本对运行状态的解释
```

Presentation Truth 不能覆盖前四种 truth。

### 核心边界

`WorkflowDefinition` 描述允许做什么；`Deployment` 描述环境选择什么；`RunSnapshot` 描述本次使用什么；`StepAttempt` 描述实际做了什么；`Artifact` 保存输出；`Receipt` 证明决策和副作用。

### Definition 与 Run 的关系

- Definition 可以发布新版本。
- 已启动 Run 默认不自动切换到新版本。
- Resume 读取原 snapshot，而不是当前 latest。
- 只有显式 migration 才能改变 Run snapshot，且必须留下 migration receipt。
- rollback 影响未来 run、queued run 或 deployment，不修改已完成 run 的历史。
- UI 的 “latest” 只作用于新 run 的选择器。

### 兼容性原则

版本升级必须同时检查结构、语义、policy、provider、资源、数据和副作用兼容性。

```text
Version Safety = Schema Compatibility × Semantic Compatibility × Policy Compatibility × Side-effect Compatibility × Recovery Compatibility
```

任一项为零，不能自动迁移。

## Definition、Snapshot、Run 与包布局

### Definition

Definition 包括 metadata、inputs、outputs、steps、edges、conditions、loops、budgets、timeouts、retry、compensation、policy requirements、provider requirements、memory requirements、artifact contracts、subagent contracts、approval gates、version metadata。

Definition 不包含用户 private memory 原文、运行时 token、provider secret、当前 deployment 的动态 credential、不可复现的随机值。

### Deployment

Deployment 绑定 environment、tenant/workspace selector、published version、traffic percentage、feature flags、provider profile、policy profile、migration policy、rollback target 和 approval evidence。

Deployment 可以按 tenant、workspace、project、region、channel、cohort、canary group 选择版本，但选择过程必须可审计。

### RunSnapshot

RunSnapshot 是 execution 的完整输入边界，至少包括 definition version/hash、deployment version、policy profile、permission profile、prompt pack、tool registry、provider profile、context recipe、memory policy、queue policy、budget、clock mode、random seed、feature flags、environment capabilities、input refs 和 artifact policy。

### 包布局

```text
packages/workflow-contracts/  definition.ts snapshot.ts schema.ts compatibility.ts errors.ts
packages/workflow-registry/   registry.ts lineage.ts publication.ts deployment.ts approvals.ts
packages/workflow-runtime/    run.ts step.ts attempt.ts scheduler.ts resume.ts migration.ts rollback.ts
packages/workflow-policy/     policy-snapshot.ts permissions.ts budgets.ts egress.ts
packages/workflow-state/      events.ts projections.ts checkpoints.ts receipts.ts reconciliation.ts
packages/workflow-ops/        canary.ts rollout.ts recovery.ts quarantine.ts dashboards.ts
packages/workflow-testkit/    fake-clock.ts replay.ts fault-injection.ts contracts.ts fixtures.ts
```

依赖方向是 `Host/Product -> Registry/Deployment -> Harness -> Runtime -> State/Event/Queue/Artifact/Provider adapters`；Agent Kernel 只消费 Context/Model ports，不自行读取 latest workflow definition。

## 版本身份、Hash、Lineage 与不可变性

### Version identity

一个版本至少由 `workflowId`、`versionId`、`versionNumber`、`contentHash`、`canonicalizationVersion`、`parentVersionId`、`createdBy`、`createdAt`、`status`、`compatibility`、`sourceRef` 组成。

`versionNumber` 只用于人读；`contentHash` 用于内容身份；`versionId` 用于 durable 引用；三者不能互相替代。

### Canonicalization

Canonical serialization 必须固定字段顺序、默认值、数字精度、Unicode normalization、引用排序、空值策略和 schema version。

不能对 JSON 直接调用未经约定的 stringify 作为跨语言内容 hash。

### Hash 层级

```text
step schema hash
  -> step definition hash
  -> workflow definition hash
  -> prompt/tool/provider/context bundle hash
  -> run snapshot hash
  -> attempt input/output hash
  -> artifact manifest hash
```

### Lineage

父版本只能被引用，不能被修改。

fork 版本必须记录 source version、fork reason 和 inherited changes。

merge 版本必须记录两个 parent、冲突结论和人工 review。

rollback 版本是新的 deployment selection，不是把 `latest` 指针改回去后抹掉历史。

### Immutable rules

- Published、Active、Deprecated、Retired 版本的内容不可变。
- 任何修改生成新的 version ID、hash 和 receipt。
- deployment selection 变化生成 deployment revision。
- run snapshot 变化生成 migration revision。
- step attempt 状态不能通过 UI 直接改写。
- audit、receipt、event 和 artifact manifest append-only。

## Schema、Contract、Compatibility 与 Validation

### Contract 分类

```text
Input Contract       run 输入和变量
Step Contract        step 读写、依赖、输出、错误
Tool Contract        tool 名称、schema、权限、side effect
Provider Contract    model/API/region/retention/capability/fallback
Context Contract     资源来源、scope、预算、优先级、投影
Memory Contract      recall/write purpose、scope、confirmation、TTL
Artifact Contract    MIME、schema、owner、retention、derived views
State Contract       event、checkpoint、terminal status、resume
Policy Contract      visibility、call、approval、execution、egress
```

### Schema version

每种 contract 有独立 `schemaId`、`schemaVersion`、`schemaHash`、`compatibilityClass`、`migrationHandler` 和 `validatorVersion`。

Workflow version 不应替代每个 contract 的 schema version。

### Compatibility levels

- `additive`：只增加可选字段、向后默认安全。
- `compatible`：结构变化但旧 consumer 可正确解释。
- `conditionally_compatible`：需要 feature flag、capability 或数据条件。
- `breaking`：旧 snapshot、step 或 output 无法正确运行。
- `unsafe`：可能改变权限、外发、删除、金额、资源或安全语义，默认禁止自动迁移。

### Validation 阶段

```text
parse -> canonicalize -> schema validate -> reference resolve -> graph validate -> type check -> policy check -> capability check -> resource/budget check -> compatibility check -> deterministic lint -> human review
```

### Validation 规则

- step ID 在一个版本内唯一且不能复用已删除 step 的语义。
- 输入变量有类型、来源、是否 secret、默认值和 redaction policy。
- edge 的条件引用存在变量，循环有 bound 和 termination condition。
- retry、timeout、compensation、approval、cancel 行为明确。
- tool 能力在 registry 存在且 permission profile 允许。
- provider fallback 有独立 capability、region、retention 和 egress decision。
- memory/context 需求不超过 policy profile 和 assignment scope。
- artifact output 有 owner、retention、schema、delete path。
- 每个 side effect 有 idempotency strategy 和 reconciliation strategy。
- 高风险 step 必须有 approval、budget、audit 和 abort path。

### Breaking change 清单

- 删除或重命名必需输入。
- 改变输入/输出类型或单位。
- 改变 tool 参数语义、权限或 side effect。
- 改变 provider/region/training/retention contract。
- 改变 memory scope、purpose、TTL、confirmation 或 deletion。
- 改变 artifact schema、owner、retention、encryption 或 public exposure。
- 改变 retry、compensation、approval、cancel、timeout 语义。
- 改变默认分支、循环边界、排序、预算或 token 估算。
- 改变 subagent assignment、parent fan-in 或 failure propagation。
- 改变事件类型、checkpoint 或 resume 解释。

## 发布通道、状态机与环境

### Version lifecycle

```text
Draft -> Validating -> Reviewed -> Staged -> Canary -> Active -> Deprecated -> Retired
                 \-> Blocked
```

`Draft` 可编辑但不可被 Run 引用；`Validating` 执行自动检查；`Reviewed` 有人工证据；`Staged` 已进入环境但无流量；`Canary` 只服务明确 cohort；`Active` 可被新 Run 选择；`Deprecated` 不接受新默认但可完成旧 Run；`Retired` 不再启动且保留历史 reader；`Blocked` 不能发布，必须有原因和修复。

### Deployment lifecycle

```text
Planned -> Approved -> Staged -> RollingOut -> Active -> Pausing -> RolledBack -> Closed
```

Deployment 与 Definition status 分离；一个版本可在一个环境 Active、另一个环境 Canary。

### Release channels

- `internal`：开发和合约测试。
- `staging`：集成、回放和故障注入。
- `canary`：有限租户、workspace 或 cohort。
- `production`：经批准的稳定流量。
- `emergency`：仅 break-glass 或 incident fix，必须短期和可回收。

### 发布证据

发布必须附：definition hash、contract matrix、test report、security scan、policy diff、provider diff、migration plan、rollback target、canary cohort、owner、approval、expiry 和 runbook。

## Run Snapshot、Step Execution 与动态能力

### Snapshot freeze

Run 创建时解析并冻结：

- workflow definition version/hash。
- deployment revision。
- contract schema 和 validator version。
- prompt pack、tool registry、provider profile。
- context recipe、memory policy、permission profile。
- feature flags、budget、timeout、retry、clock/random seed。
- tenant/user/workspace/project scope。
- artifact、queue、subagent 和 privacy policy。

### Snapshot exceptions

动态数据可以读取：当前时间、外部状态、队列 lease、用户新输入、provider response、工具结果；但这些必须作为 input/event/attempt 记录，不能隐式改变 workflow definition。

动态 capability 必须通过 `CapabilityLease`、expiry、scope、purpose 和 receipt 进入 Run。

### Step lifecycle

```text
Pending -> Ready -> Running -> WaitingInput/WaitingApproval/WaitingExternal -> Succeeded
                                      \-> Retrying -> Running
                                      \-> Failed/Cancelled/TimedOut/Unknown/Quarantined
```

Step 的 terminal outcome 不能仅由模型文本决定。

### Attempt identity

每个 attempt 绑定 run snapshot hash、step version/hash、attempt number、input hash、idempotency key、worker lease、provider attempt、output hash、side-effect receipt 和 completion time。

### Deterministic scheduling

调度器必须定义 ready step 的排序、并发上限、resource lock、budget reservation、cancel 传播、retry jitter、clock 和 random source。

重放使用固定 snapshot、fixture clock、deterministic IDs、recorded provider/tool outputs 和 side-effect oracle。

## Migration、Resume、Pause、Cancel 与 Rollback

### Resume

Resume 首先读取原 RunSnapshot、checkpoint、open attempt、leases、pending approvals、pending external effects 和 policy expiry。

Resume 不能把原 run 迁移到 latest；如 snapshot 过期或 provider contract 变化，应进入 `migration_required`、`blocked` 或 re-approval。

### Pause

Pause 只阻止新 step/attempt，不删除已提交副作用；必须保存 checkpoint、queue lease 状态、pending approval、cancel token、budget ledger 和 remote operation refs。

### Cancel

Cancel 传播到 child run、queued step、future retry、background flush、provider request、artifact publish 和 notification；已发生副作用进入 reconciliation，不宣称已回滚。

### Migration classes

```text
No-op migration       只变 UI label/metadata
Safe boundary         在 step boundary 切换，旧 attempt 完成
Data migration        变换 checkpoint/input/artifact schema
Semantic migration    重新解释业务条件，需要 approval/review
Side-effect migration 影响外部系统，默认不自动
Security migration    收紧权限/egress/retention，可即时阻断
```

### Migration protocol

```text
request -> inspect run snapshot -> compare old/new contracts -> impact inventory -> dry-run -> approval -> freeze boundary -> transform checkpoint/artifact -> create migration revision -> resume -> reconcile -> receipt
```

只能在安全边界迁移；不能在不可幂等外部副作用中间改变 step 语义。

### Rollback

Rollback 是 deployment selection、new run routing 或 future queued run 的策略改变。

已完成 Run 不回写旧版本；已发生外部副作用不因 rollback 消失；进行中的 Run 需要明确 continue-old、pause-and-migrate、cancel-and-reconcile 三选一。

Rollback 必须附 rollback target、reason、approval、traffic scope、expiry、health evidence 和 post-rollback reconciliation。

## Provider、Tool、Prompt、Context、Memory、Policy 集成

### Provider

Provider profile 至少锁定 provider、API family、deployment/model、region、capability、limits、pricing class、retention、training policy、delete capability、tool calling semantics、structured output semantics、fallback graph、timeout、retry 和 egress requirements。

model name 变化可能不是兼容变化；要比较 message schema、tool call、finish reason、usage、stream、error、structured output 和 privacy contract。

Fallback 产生新 Attempt、新 ProviderDecision、新 egress receipt；primary allowance 不能授权 fallback；hedge、shadow、speculative path 重新执行 privacy、budget、region、retention 检查。

### Tool

Tool contract 包括 name、version、input/output schema、scope、permission、approval、side effect class、idempotency、timeout、compensation、artifact output、audit、availability。

工具 schema 兼容不代表业务语义兼容；工具 rename、权限变化、side effect 变化、输出单位变化都应视为 breaking/unsafe。

Tool registry snapshot 只允许当前版本声明的工具；模型不能动态注册高权限 tool。

### Prompt

Prompt pack 是版本化资源，至少包含 system、developer、workflow instructions、tool descriptions、memory/context instructions、output schema、language、safety text、template variables、source hash、redaction policy。

Prompt 版本变化必须可 diff、可 replay、可按 provider 投影；不得把 prompt 文本作为 policy enforcement。

Prompt 中不能写入 secret、完整用户 memory、未锁定的 latest 变量或暗示成功的状态；模型输出仍需 runtime 验证。

### Context

Context recipe 定义资源 selector、scope、purpose、priority、freshness、budget、summarization、offload、dedupe、redaction、source attribution。

ContextPlan 随 RunSnapshot 记录 selected、summarized、offloaded、dropped、filtered 和 reason；新的 context compiler 不能静默改变旧 run 的历史 plan。

### Memory

Workflow definition 只能声明 memory capability requirement，不内嵌用户 memory 原文。

每次 memory recall/write/export/delete 使用 frozen MemoryPolicyProfile、purpose、scope、sensitivity、consent、TTL、provider egress 和 receipt。

Workflow memory recall 可进入 ContextPlan，但 memory view 不获得 instruction authority；child candidate 不直接激活到 user/workspace/tenant memory。

### Policy

Policy 分为 visibility、call、approval、execution、egress；workflow version 只声明 capability requirement，不能绕过 effective policy。

策略收紧可以即时阻断新动作，但不能静默修改旧 receipt；策略放宽不能自动改变旧 snapshot。

### Harness

Harness bootstrap 组装 registry、definition、deployment、snapshot、provider、tool、policy、memory、context、state、queue、artifact 和 observer。

Harness run loop 管理 budget、step scheduler、checkpoint、cancel、pause、resume、child、queue、provider attempts、terminal settlement 和 recovery；Kernel 不拥有版本选择权。

## Queue、Subagent、Artifact、State 与副作用

### Queue

队列 job payload 只放 snapshot ref/hash、run/step/attempt ID、assignment、idempotency key、lease policy、input/artifact refs 和最小 policy snapshot。

队列可重复投递；worker 必须使用 fencing token、lease expiry、attempt identity 和 side-effect query 防止旧 worker 继续执行。

`unknown` 状态不能简单 retry；先查询 execution receipt、remote status、artifact manifest、event log 和 canonical state。

### Subagent

Subagent assignment 锁定 child workflow version、parent snapshot hash、scope、purpose、budget、allowed tools、provider、artifact boundary、memory package、deadline、cancel propagation 和 output schema。

child 不能读取 latest parent definition，不能获得父级全部 tools/memory，不能把 child output 自动升级为 parent truth。

parent fan-in 必须验证 child snapshot hash、output schema、artifact hash、provenance、policy、partial/unknown 状态和 resource limits。

### Artifact

Artifact manifest 绑定 run、step、attempt、workflow version、schema、owner、scope、purpose、sensitivity、retention、content hash、derived refs、provider target、delete path。

raw、sanitized、summary、preview、export、embedding input 是不同 view；artifact publish 成功不等于 workflow step 成功，必须分别记录。

### State

State 分为 definition state、deployment state、run state、step state、attempt state、approval state、artifact state、queue state、provider state 和 reconciliation state。

State event append-only；projection 可重建；checkpoint 必须包含 snapshot hash、graph cursor、ready/running/waiting/terminal steps、budget ledger、open side effects、child refs、artifact refs、approval refs 和 version。

### 副作用分类

```text
pure                 可直接重放
idempotent           可用同一 key 安全重试
queryable            可查询结果后决定 retry
compensatable        可执行补偿但不保证删除历史
non-compensatable    默认 unknown 后人工/恢复处理
```

每个 side effect 必须声明 class、idempotency key、commit receipt、query API、compensation、retention、audit 和 reconciliation handler。

## 数据模型与 TypeScript contracts

### 基础类型

```typescript
type WorkflowId=string; type WorkflowVersionId=string; type DeploymentId=string; type DeploymentRevisionId=string; type RunId=string; type StepId=string; type StepVersionId=string; type AttemptId=string; type SnapshotHash=string; type SchemaHash=string; type ArtifactId=string; type JobId=string; type ReceiptId=string;
type VersionStatus="draft"|"validating"|"reviewed"|"staged"|"canary"|"active"|"deprecated"|"retired"|"blocked";
type RunStatus="created"|"queued"|"running"|"paused"|"waiting_input"|"waiting_approval"|"waiting_external"|"retrying"|"completed"|"failed"|"cancelled"|"timed_out"|"unknown"|"quarantined";
```

### Definition

```typescript
interface WorkflowDefinition { workflowId:WorkflowId; versionId:WorkflowVersionId; versionNumber:string; contentHash:string; canonicalizationVersion:string; parentVersionId?:WorkflowVersionId; metadata:WorkflowMetadata; inputs:InputContract[]; outputs:OutputContract[]; steps:StepDefinition[]; edges:EdgeDefinition[]; policies:PolicyRequirement[]; providerRequirements:ProviderRequirement[]; memoryRequirements:MemoryRequirement[]; artifactContracts:ArtifactContract[]; subagentContracts:SubagentContract[]; budgets:BudgetPolicy; retries:RetryPolicy; approvalGates:ApprovalGate[]; compatibility:CompatibilityReport; status:VersionStatus; createdBy:PrincipalRef; createdAt:string; }
```

### Snapshot

```typescript
interface WorkflowRunSnapshot { snapshotId:string; workflowId:WorkflowId; workflowVersionId:WorkflowVersionId; definitionHash:string; deploymentId:DeploymentId; deploymentRevisionId:DeploymentRevisionId; contractHashes:Record<string,SchemaHash>; promptPackHash:string; toolRegistryHash:string; providerProfileHash:string; contextRecipeHash:string; memoryPolicyHash?:string; permissionProfileHash:string; featureFlagsHash:string; budget:BudgetPolicy; clockMode:"real"|"deterministic"; randomSeed?:string; scope:ScopeRef; inputRefs:ResourceRef[]; artifactPolicyHash:string; createdAt:string; snapshotHash:SnapshotHash; expiresAt?:string; }
```

### Run、Step、Attempt

```typescript
interface WorkflowRun { runId:RunId; workflowId:WorkflowId; snapshot:WorkflowRunSnapshot; status:RunStatus; graphCursor:GraphCursor; checkpointId?:string; createdAt:string; startedAt?:string; endedAt?:string; terminalReason?:string; migrationRevision?:string; }
interface StepAttempt { attemptId:AttemptId; runId:RunId; stepId:StepId; stepVersionId:StepVersionId; snapshotHash:SnapshotHash; attemptNumber:number; inputHash:string; idempotencyKey:string; leaseId?:string; status:"ready"|"running"|"waiting"|"succeeded"|"failed"|"cancelled"|"timed_out"|"unknown"; outputRefs:ResourceRef[]; outputHash?:string; sideEffectReceipts:ReceiptId[]; providerAttemptId?:string; startedAt?:string; endedAt?:string; }
```

### Registry、Deployment、Migration

```typescript
interface WorkflowDeployment { deploymentId:DeploymentId; workflowId:WorkflowId; revisionId:DeploymentRevisionId; environment:string; selector:DeploymentSelector; workflowVersionId:WorkflowVersionId; trafficPercent:number; channel:"internal"|"staging"|"canary"|"production"|"emergency"; policyProfileHash:string; providerProfileHash:string; rollbackTarget?:WorkflowVersionId; approvedBy:PrincipalRef[]; status:"planned"|"approved"|"staged"|"rolling_out"|"active"|"pausing"|"rolled_back"|"closed"; expiresAt?:string; }
interface WorkflowMigration { migrationId:string; runId:RunId; fromSnapshotHash:SnapshotHash; toWorkflowVersionId:WorkflowVersionId; classification:"noop"|"safe_boundary"|"data"|"semantic"|"side_effect"|"security"; safeBoundary:GraphCursor; checkpointTransform?:string; approvals:ApprovalRef[]; dryRunHash:string; status:"requested"|"approved"|"frozen"|"transformed"|"resumed"|"blocked"|"rolled_back"; receiptId:ReceiptId; }
```

### Ports

```typescript
interface WorkflowRegistryPort { getDefinition(id:WorkflowVersionId):Promise<WorkflowDefinition>; validate(input:DefinitionInput):Promise<ValidationReport>; publish(id:WorkflowVersionId):Promise<PublicationReceipt>; resolveDeployment(input:DeploymentResolveInput):Promise<WorkflowDeployment>; compare(a:WorkflowVersionId,b:WorkflowVersionId):Promise<CompatibilityReport>; }
interface WorkflowRuntimePort { start(input:StartRunInput):Promise<WorkflowRun>; pause(runId:RunId):Promise<WorkflowReceipt>; resume(runId:RunId):Promise<WorkflowReceipt>; cancel(runId:RunId):Promise<WorkflowReceipt>; migrate(input:MigrationRequest):Promise<WorkflowReceipt>; rollback(input:RollbackRequest):Promise<WorkflowReceipt>; }
interface WorkflowStatePort { append(event:WorkflowEvent):Promise<EventCommit>; load(runId:RunId):Promise<WorkflowRunState>; checkpoint(input:CheckpointInput):Promise<CheckpointReceipt>; reconcile(input:ReconciliationInput):Promise<ReconciliationReceipt>; }
```

## Durable Events、Receipt 与 Observability

### Durable Events

`workflow.version.created`、`validated`、`reviewed`、`published`、`blocked`、`deprecated`、`retired`、`deployment.created`、`deployment.approved`、`canary.started`、`traffic.changed`、`rollback.requested/completed`、`run.created`、`snapshot.locked`、`step.ready/started/waiting/succeeded/failed`、`attempt.started/completed/unknown`、`checkpoint.created`、`run.paused/resumed/cancelled/completed`、`migration.requested/approved/transformed/resumed/blocked`、`provider.attempted`、`tool.called`、`approval.requested/resolved`、`artifact.created/published/deleted`、`child.started/completed`、`reconciliation.finding`、`recovery.required`。

### Receipt

Receipt 证明 definition/deployment/snapshot/attempt/migration/rollback/side effect 的决策和事实；必须记录 actor、scope、version/hash、purpose、policy、input/output hash、provider/tool、idempotency key hash、status、obligations、timestamp、correlation、integrity。

Receipt 不默认包含完整 prompt、secret、完整用户 memory 或 hidden reasoning；可用 ref/hash/summary/metadata 代替。

### Trace

```text
product request -> registry/deployment -> harness bootstrap -> snapshot -> scheduler -> step -> attempt -> tool/provider/child -> artifact/state/event -> terminal settlement
```

高基数字段不作为 metrics label；workflow version、step ID、provider、outcome、migration class 可作为受控维度；用户输入、path、artifact 内容、tenant 原文不能直接作为 label。

### 指标

发布：validation latency、blocked rate、canary error、rollback rate、version adoption、contract failures。

运行：queue latency、step/attempt latency、retry、timeout、approval wait、pause duration、resume success、unknown side effect、terminal settlement latency。

迁移：eligible/running/blocked、dry-run mismatch、checkpoint transform failure、rollback、reconciliation lag。

安全：unauthorized tool/provider call、policy deny、cross-tenant access、secret egress、scope escalation、artifact retention violation，目标为零。

一致性：snapshot hash coverage、event projection lag、orphan attempt、duplicate side effect、unreconciled receipt、artifact manifest mismatch。

## 故障模型、Reconciliation 与 Recovery

### Failure classes

```text
definition_invalid
contract_incompatible
deployment_conflict
snapshot_lock_failed
policy_expired
capability_missing
input_invalid
approval_timeout
queue_lost
lease_expired
provider_timeout
provider_unknown
tool_unknown
artifact_publish_unknown
state_projection_lag
checkpoint_corrupt
child_partial
side_effect_unknown
migration_blocked
rollback_incomplete
receipt_commit_failed
```

### Recovery rules

- Snapshot lock 失败时不启动 Run。
- Definition 读取成功但 deployment receipt 未提交时不显示已发布。
- Step attempt timeout 后先查询 side effect，再决定 retry。
- Provider unknown 不自动把同一敏感请求重发到 fallback。
- Artifact publish unknown 先查 manifest/hash/remote status。
- Queue lease 过期后旧 worker 被 fencing，新 worker 必须验证 attempt。
- Checkpoint corrupt 进入 recovery，不从最新 definition 猜测状态。
- Projection lag 不改变 canonical event truth。
- migration blocked 保持旧 snapshot 可 resume。
- rollback 不撤销已发生的外部副作用，只改变未来选择或启动 reconciliation。
- receipt commit 失败时动作进入 unknown，不向用户报告完成。

### Reconciliation

```text
load run snapshot -> compare event stream/checkpoint/step attempts/queue/artifact/provider -> classify missing/orphan/stale/duplicate/unknown -> safe repair or quarantine -> append finding -> verify -> receipt
```

Reconciliation Finding 至少有 finding ID、run/step/attempt、snapshot hash、对象类别、expected/observed status、severity、safe repair、repair plan、证据和时间。

### Recovery Queue

Recovery job 绑定 run、snapshot、attempt、side-effect refs、query strategy、idempotency key、deadline、owner、policy snapshot 和 escalation path；不把全部输入正文放入 payload。

## 安全、隐私、权限与供应链

### Permission layers

```text
Visibility -> Call -> Approval -> Execution -> Egress
```

Workflow version 不能自动获得未来工具或 provider 权限；deployment selector 不能改变 tenant safety floor；emergency channel 必须短期、最小范围、可撤销。

### Scope

Run snapshot 锁定 tenant、organization、user、workspace、project、session、branch、run、subagent scope；step assignment 只能取交集；child 默认只获得 delegated resources。

### Secrets

Definition 只引用 secret binding ID，不保存 secret value；snapshot 记录 secret version/ref、scope、purpose、expiry、rotation epoch，不记录原文；logs、artifacts、provider receipts、replay fixture 必须 redaction。

### Privacy

Workflow definition 不内嵌个人 memory；MemoryRecall、MemoryWrite、Export、Delete 各自执行 purpose、scope、sensitivity、consent、TTL、egress；artifact raw、summary、preview、embedding input、provider copy 是不同 privacy view。

### Supply chain

锁定 prompt pack、tool registry、provider adapter、validator、migration handler、container/image、package lock、configuration hash、operator identity 和 release evidence。

第三方 connector 变更若影响 schema、权限、外发、retention、删除或 side effect，按 breaking/unsafe 处理并重新 review。

## 测试、Evaluation 与发布门禁

### Testkit

```text
FakeWorkflowRegistry FakeDeploymentResolver FakePolicyEngine FakeProvider FakeToolRegistry FakeQueue FakeStateStore FakeArtifactStore FakeApprovalStore FakeClock DeterministicIds ReplayRunner FaultInjector SideEffectOracle ReconciliationOracle GoldenFixtureRunner
```

### 单元测试

- canonicalization、hash、version lineage、fork、merge、diff。
- schema validation、graph/type/condition/loop/budget。
- compatibility classification、migration handler、rollback selection。
- deployment selector、traffic、canary、approval、expiry。
- snapshot freeze、attempt identity、idempotency、fencing。
- scheduler ordering、budget reservation、cancel/pause/resume。
- provider/tool/prompt/context/memory/policy contract。
- checkpoint、event projection、terminal settlement。
- artifact manifest、retention、redaction、delete path。

### 组件测试

- Registry 与 Product version UI/API。
- Deployment 与 Harness bootstrap。
- Runtime scheduler 与 State/Event Store。
- Queue worker 与 lease/fencing。
- Provider fallback 与 egress re-check。
- Tool permission、approval 和 side effect reconciliation。
- Subagent snapshot inheritance 与 parent fan-in。
- Artifact publish、export、delete。
- Migration dry-run、checkpoint transform、resume、rollback。

### 安全负向场景

1. Run 通过 latest 读取到未锁定版本。
2. deployment 选择跨 tenant/workspace。
3. 模型提交未知 tool 或高权限参数。
4. tool schema 不变但 side effect 语义改变。
5. provider fallback 跨 denied region 或 retention contract。
6. prompt injection 修改 workflow/policy/version。
7. child 读取全部 parent tools/memory。
8. migration 放宽 scope、TTL、egress 或 approval。
9. rollback 伪造为外部副作用已撤销。
10. duplicate queue delivery 重复扣款、发送、删除或发布。
11. lease 过期旧 worker 继续写 artifact/state。
12. checkpoint 恢复读取 latest definition。
13. artifact export 混入其他 tenant。
14. secret 出现在 prompt、trace、artifact、receipt、fixture。
15. event projection 把 partial/unknown 显示为 completed。
16. retired version 被新 Run 选择。
17. emergency deployment 永久未过期。
18. migration handler 丢失 open side effect。
19. provider remote status unknown 后重复敏感上传。
20. user 输入伪造 approval、deployment 或 operator identity。

### Deterministic assertions

每个 scenario 至少断言 definition/deployment/snapshot hash、version lineage、policy/permission/egress decision、graph cursor、step/attempt terminal status、queue/lease/idempotency、provider/tool request、artifact manifest、event/receipt、用户 explanation、真实外部副作用和 recovery outcome。

### Evaluation

自动 judge 可评估：definition 可读性、错误解释、迁移计划完整性、step 选择、summary 忠实度、用户下一步提示。

自动 judge 不能证明：definition 已发布、snapshot 已锁定、tool/provider 已调用、artifact 已删除、rollback 已撤销副作用、cross-tenant 未发生或未知状态已结算。

### 发布 hard gates

- contract validation 和 compatibility 无未解释 blocking result。
- snapshot lock、receipt、event、checkpoint、artifact manifest 都可验证。
- cross-tenant、unauthorized tool/provider、secret egress、duplicate side effect、snapshot drift、unknown-to-success、retired-version launch 为零。
- canary 有明确 cohort、traffic、SLO、rollback target、owner、expiry。
- migration 有 dry-run、safe boundary、approval、reconciliation、rollback reader。

## 反模式与实施清单

### 反模式

1. 用 `latest` 参与已启动 Run。
2. 只存版本字符串，不存 hash、schema 和 lineage。
3. 用 git commit、文件名或 UI label 作为唯一身份。
4. 修改 published definition 原地覆盖历史。
5. workflow version 替代所有 contract version。
6. tool schema compatible 就认为业务安全。
7. provider model name 变化不做 contract diff。
8. prompt 文本承担权限和状态真相。
9. migration 在 step 中间切换语义。
10. rollback 伪装成外部副作用已撤销。
11. retry 未查询 unknown side effect。
12. queue lease 过期 worker 继续执行。
13. child 读取 parent 全部 tools/memory。
14. artifact 只有一个 raw view。
15. memory/context 不锁 purpose、scope、TTL、egress。
16. pause 删除 side effect 或等待状态。
17. cancel 不传播 child、queue、provider、artifact。
18. checkpoint 不含 snapshot hash。
19. event projection 当作 canonical truth。
20. emergency deployment 没有 expiry 和 revoke。
21. receipt 复制完整 prompt、secret、memory。
22. metrics 使用输入正文或 tenant 原文。
23. 只测成功，不测 denied/unknown/recovery。
24. 迁移失败后直接读取 latest 继续。
25. canary 没有独立 cohort 和 rollback criterion。
26. 将 UI 显示的 published 当成流量已切换。
27. 版本退休后删除历史 reader。
28. 用模型输出决定 step terminal status。
29. 让 migration handler 改写旧 event。
30. 把 deployment rollback 当作数据删除。

### 实施清单

#### P0 版本契约

- [ ] 定义 WorkflowDefinition、VersionIdentity、Lineage、Canonicalization、Hash。
- [ ] 定义每个 contract 的 schemaId/version/hash/compatibility。
- [ ] 定义 WorkflowRunSnapshot 和 snapshot hash。
- [ ] 定义 Run、Step、Attempt、Artifact、Receipt、Checkpoint。
- [ ] 定义 Definition/Deployment/Run/Attempt truth 边界。

#### P1 注册、验证与发布

- [ ] registry、lineage、diff、validator、publish、review。
- [ ] deployment selector、channel、cohort、traffic、expiry。
- [ ] canary、health SLO、rollback target、approval evidence。
- [ ] retired/blocked 版本 reader 和历史解释。
- [ ] provider/tool/prompt/context/memory/policy contract diff。

#### P2 Runtime 与状态

- [ ] snapshot freeze、deterministic scheduler、budget、timeout、retry。
- [ ] step/attempt identity、idempotency、lease、fencing、checkpoint。
- [ ] pause、resume、cancel、waiting approval/input/external。
- [ ] terminal settlement、event append、projection、receipt。
- [ ] child assignment、fan-in、artifact manifest、memory boundary。

#### P3 Migration、Recovery 与 Rollback

- [ ] compatibility matrix、migration class、safe boundary。
- [ ] dry-run、impact inventory、checkpoint/artifact transform。
- [ ] migration revision、approval、resume、reconciliation。
- [ ] rollback selection、traffic stop、future run policy、post-rollback review。
- [ ] unknown side effect、provider status、artifact status recovery。

#### P4 安全、隐私与评测

- [ ] permission layers、scope intersection、secret references、redaction。
- [ ] provider egress、memory policy、artifact retention/delete。
- [ ] security negative cases、supply-chain evidence、emergency expiry。
- [ ] deterministic replay、fault injection、contract conformance、golden fixtures。
- [ ] hard gates、SLO dashboard、operator runbook。

## 五个参考项目的启发

### Pi

headless loop 与 Harness 分离支持 workflow version selection、snapshot、budget、resume 不进入 Kernel；session tree、branch、compaction entry 启发 run lineage、checkpoint 和 safe-boundary migration；CLI/TUI/RPC 共用 runtime 启发 Registry、Host、Run View 共用 durable events；provider message 与 session truth 分离支持 execution truth 与 model output 分离；执行隔离弱提醒 workflow policy、tool egress 和 artifact cleanup 必须 runtime 强制。

### Grok Build

Session/ChatState actor 启发 run/step 状态所有权；permission decision、folder trust、sandbox、resource lock 启发 capability、scope、execution backend、lock 分离；工具输出预算和上下文修剪启发 snapshot budget、ContextPlan、artifact-only；分层 sampler 启发 provider attempt 和 cost class 版本化；显式错误状态启发 unknown、reconciliation、recovery queue。

### OpenCode

session/message/part 和 durable event/projector 启发 Definition、Run、Attempt、Artifact View 不直接绑 UI；snapshot/patch/revert 启发 version diff、checkpoint transform、rollback reader；client/server 分离启发 registry/runtime API；permission、MCP/LSP、状态迁移复杂度启发 tool/provider contract 和 migration compatibility matrix。

### Claude Code

memory、skills、hooks、subagents、permission modes、计划工作流启发 workflow capability declaration、approval、最小委派、子任务边界；项目规则和 auto memory 并存提醒 definition 不应把 memory 当 static policy；subagent 能力启发 child snapshot、budget、fan-in、output schema；用户可见的计划与控制体验启发 version diff、migration explanation、rollback explanation。

### OpenClaw

AgentHarness registry 启发 registry-driven assembly、provider/tool/channel adapter 可装配；agent-core 与 Gateway/channel 分离启发 deployment、delivery、notification、background worker 解耦；tool、sandbox、elevated 分层启发 execution/egress/emergency 权限分离；compaction 前 flush 启发 checkpoint 与 migration input 边界；事务化插件注册启发 deployment rollback、adapter compatibility、cleanup worker 和失败恢复。

## Definition of Done

Workflow Versioning 只有同时满足以下条件才算完成：

- Definition、Deployment、RunSnapshot、StepAttempt、Artifact、Receipt、Checkpoint 有独立身份与边界。
- published definition、deployment revision、snapshot、event、receipt、artifact manifest 不可变且可验证。
- 新 Run 选择 deployment，旧 Run 使用原 snapshot，resume 不读取 latest。
- prompt、tool、provider、context、memory、policy、artifact、queue、subagent contract 有独立 hash/version/compatibility。
- additive、compatible、conditional、breaking、unsafe 变化可解释。
- 发布有 staged/canary/active/deprecated/retired/blocked 生命周期。
- migration 只在安全边界执行，有 dry-run、approval、checkpoint transform、reconciliation、rollback reader。
- rollback 不伪造撤销外部副作用，unknown 进入 recovery。
- queue、lease、fencing、idempotency、attempt identity 防止重复副作用和旧 worker 继续执行。
- provider fallback、tool、subagent、memory、artifact 和 egress 不绕过 snapshot/policy。
- pause、resume、cancel、approval、child、artifact、remote operation 状态可恢复。
- 可重放、可审计、可解释，且日志和 receipt 不泄露 secret、完整 prompt 或敏感 memory。
- 跨租户、未授权调用、secret egress、duplicate side effect、snapshot drift、unknown-to-success、retired launch 为零。
- 职责边界必须明确：Registry/Compiler 解释版本，Coordinator 冻结 snapshot，Runtime 执行，State/Event 记录事实，Policy/Sandbox 强制边界，Host 只投影和提交控制。
- 决策流程必须记录 version resolution、compatibility、policy、migration、approval、rollback 和 reconciliation 的输入、结果与 receipt。
- 故障恢复必须先校验 snapshot、checkpoint、lease、side-effect receipt 和 provider status，再决定 resume、retry、quarantine、migration 或 manual。
- 可观测性必须关联 definition hash、deployment revision、snapshot、step/attempt、provider/tool、artifact、policy 和 migration ID。
- 测试策略必须覆盖 fixture、contract、compatibility、migration dry-run、deterministic replay、fault injection、canary 和 incident regression。
- 任何“工作流已发布”“任务已完成”“已回滚”都必须由 registry、snapshot、attempt、receipt、artifact、provider、reconciliation 事实证明，而不是由模型或 UI 文案声称。
