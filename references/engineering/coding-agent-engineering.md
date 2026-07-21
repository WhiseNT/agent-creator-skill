# Coding Agent Engineering 细粒度工程设计
> 本文定义面向真实代码库的 Coding Agent Harness。它沿用本地参考文档中的 `Agent Kernel`、`Harness`、`ContextPlan`、`PromptCompiler`、`ToolRuntime`、`Policy`、`Sandbox`、`Session`、`Run`、`Turn`、`Attempt`、`ArtifactRef`、`Snapshot`、`Patch`、`Checkpoint`、`Projector` 和 durable/ephemeral event 术语。
>
> 本设计只整理当前目录已有参考架构、Agent Harness 以及 Prompt、Context、Tool、State/Memory、Permission/Sandbox、Subagent、Event/Observability、Evaluation 文档中已记录的源码调研结论；不把 README 当作规范，不新增网络调研结论。
## 目录

1. [设计目标与非目标](#设计目标与非目标)
2. [Coding Agent 的定义](#coding-agent-的定义)
3. [职责边界](#职责边界)
4. [总体架构与包布局](#总体架构与包布局)
5. [核心数据模型](#核心数据模型)
6. [Repository Discovery 与 Repo Map](#repository-discovery-与-repo-map)
7. [Workspace、Branch 与 Baseline](#workspacebranch-与-baseline)
8. [代码阅读与证据系统](#代码阅读与证据系统)
9. [任务规范化与计划](#任务规范化与计划)
10. [编辑策略与变更所有权](#编辑策略与变更所有权)
11. [Snapshot、Patch、Diff 与 Revert](#snapshotpatchdiff-与-revert)
12. [命令、构建、Lint 与测试执行](#命令构建lint-与测试执行)
13. [进度、Checkpoint 与用户 Steering](#进度checkpoint-与用户-steering)
14. [Review 模式](#review-模式)
15. [并发与文件锁](#并发与文件锁)
16. [生成代码与 Vendor](#生成代码与-vendor)
17. [模式、Host Adapter 与离线能力](#模式host-adapter-与离线能力)
18. [生命周期与状态机](#生命周期与状态机)
19. [一次任务的决策流程](#一次任务的决策流程)
20. [与 Context、Prompt、Tool、State、Policy、Harness 集成](#与-contextprompttoolstatepolicyharness-集成)
21. [提交与提交前检查边界](#提交与提交前检查边界)
22. [故障恢复](#故障恢复)
23. [安全与隐私](#安全与隐私)
24. [可观测性](#可观测性)
25. [测试策略](#测试策略)
26. [反模式](#反模式)
27. [实施清单](#实施清单)
28. [五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与非目标
### 目标
Coding Agent 必须能够：
进入一个未知或部分已知的 repository，并先建立可验证的导航地图；
- 区分用户已有改动、Agent 改动、生成物、vendor 和构建缓存；
- 在明确的 workspace、branch、commit 基线和 trust 状态下工作；
- 用文件范围、symbol、测试和命令输出形成证据链；
- 将用户自然语言转成可验收的 `TaskSpec` 与文件级计划；
- 以最小、可审查、可回退的 patch 修改代码；
- 在每次副作用边界前执行 policy、审批、锁和 snapshot 检查；
- 运行有界命令、编译、lint、测试和静态检查，并保留完整 artifact 引用；
- 通过 checkpoint、session entry 和 working state 支持崩溃恢复；
- 允许用户 steering 当前 loop，区分 steering 与 follow-up；
- 提供 read-only、offline、plan、implementation、review 等明确模式；
- 在 CLI、TUI、IDE、RPC、HTTP 或 batch host 中复用同一 headless runtime；
- 把结果交付为解释、diff、测试证据、artifact 或显式提交请求。
### 非目标
Coding Agent 不负责：
只通过 shell 字符串包装命令并假装拥有代码理解能力；
- 把全仓库文本一次性注入 model context；
- 以 prompt 代替文件权限、policy、sandbox 或审批；
- 自动覆盖用户已有未提交改动；
- 把最终文本声称的“已完成”当作文件或测试事实；
- 把 `git commit`、`git push`、发布和部署默认视为普通编辑；
- 让 subagent 共享未加锁的可变工作区；
- 在未知副作用结果时盲目重放命令；
- 通过 vendoring 隐式扩大依赖、许可证或安全边界。
### 核心判断
```text
Coding Agent = Agent Kernel + repository-aware Context + evidence-driven planning + controlled editing + executable verification + durable workspace state + policy/sandbox/host integration
```
Coding Agent 不等于 shell wrapper。Shell 只是一个受 `ToolRuntime`、`Policy`、`Sandbox`、`ArtifactStore` 和 `Harness` 监督的执行后端。
## Coding Agent 的定义
Coding Agent 是在代码库中读取、推理、修改和验证的 Agent 产品形态。 它同时处理三种对象：
```text
Repository truth   文件、符号、依赖、测试、配置、Git 状态 Task truth         用户目标、约束、验收标准、未完成项 Run truth          当前模型、工具、权限、命令、patch、错误、checkpoint
```
这三者不能混为一张聊天消息表。
### Agent Kernel 与 Coding Harness
`Agent Kernel` 只负责模型—工具循环、停止、取消和基础事件。 `Coding Harness` 负责：
workspace 解析与项目 trust；
- repo map、代码资源和证据；
- 文件、diff、snapshot、patch 和 revert；
- 命令执行、构建、lint、测试和输出 artifact；
- branch、baseline、checkpoint、steering 和 review；
- file lock、subagent ownership、host adapter；
- policy、approval、sandbox、提交边界和审计。
```text
Kernel 回答：下一次模型采样或工具结果如何推进？ Coding Harness 回答：在哪个仓库、基于哪个基线、可改什么、如何验证和恢复？
```
## 职责边界
| 模块 | 负责 | 不负责 |
|---|---|---|
| `RepositoryResolver` | 根目录、仓库身份、分支和基线解析 | 修改文件 |
| `RepoMapBuilder` | 目录、symbol、依赖、测试和配置导航索引 | 替代源码阅读 |
| `EvidenceStore` | 文件范围、命令、测试、diff 和来源引用 | 判断最终产品策略 |
| `TaskPlanner` | 任务拆解、依赖、验收、风险和 checkpoints | 直接执行写操作 |
| `EditEngine` | 受约束的文本/结构化 patch | 授权危险命令 |
| `WorkspaceState` | 文件 hash、用户改动、Agent 改动和基线 | provider 原始消息转换 |
| `CommandRunner` | 结构化 argv、超时、stdout/stderr 和退出状态 | 绕过 sandbox |
| `VerificationRunner` | 编译、lint、测试和结果归因 | 修改测试通过结论 |
| `PolicyEngine` | visibility、call、approval、execution、egress | 生成自然语言提示 |
| `SnapshotStore` | 变更前后可验证资源快照 | 自动合并任意外部副作用 |
| `LockManager` | 文件、目录、repo、branch 资源锁 | 代替三方合并 |
| `ReviewEngine` | diff、风险、回归、测试缺口检查 | 默认修改代码 |
| `Harness` | 装配、监督、恢复、预算和事件路由 | 变成巨型 God Object |
| `HostAdapter` | 展示进度、diff、审批、artifact 和控制事件 | 推断 durable truth |
强制边界：
```text
Prompt explains coding workflow. Context selects relevant code and evidence. Tool schema constrains action shape. Policy authorizes the action. Sandbox limits its effect. State records what actually happened. Harness supervises recovery and delivery.
```
## 总体架构与包布局
```text
Host Adapters CLI / TUI / IDE / RPC / HTTP / Batch | Application Orchestrator request / queue / subagent / delivery | Coding Harness bootstrap / modes / trust / budgets / recovery |             |              | Repository     Agent Kernel    Verification Context        model loop      build/lint/test |             |              | Edit Runtime   Tool Runtime    Artifact Store |             |              | Policy/Sandbox/Locks/Session/Event Backbone
```
推荐包布局：
```text
packages/coding-agent/ contracts.ts modes.ts repository.ts repo-map.ts baseline.ts evidence.ts planning.ts workspace-state.ts edit-engine.ts patch.ts snapshot.ts diff.ts revert.ts command-runner.ts verification.ts locks.ts steering.ts review.ts generated.ts vendor.ts host-adapters/ testkit/
```
依赖方向：
```text
Host -> Coding Harness -> Kernel/ports Repository/Edit/Command implement ports Infrastructure -> State/Artifact/Event contracts
```
Kernel 不应导入 Git CLI、Node child process、IDE API 或具体数据库类型。
## 核心数据模型
### 基本标识
```typescript
type WorkspaceId = string; type RepositoryId = string; type BranchId = string; type BaselineId = string; type TaskId = string; type PlanId = string; type EvidenceId = string; type ChangeId = string; type SnapshotId = string; type PatchId = string; type CommandId = string; type LockId = string; type CheckpointId = string;
```
### 模式与任务
```typescript
type CodingAgentMode = | "offline" | "read_only" | "plan" | "implementation" | "review"; interface TaskSpec { taskId: TaskId; objective: string; constraints: string[]; acceptanceCriteria: AcceptanceCriterion[]; referencedPaths: string[]; assumptions: string[]; unresolvedQuestions: string[]; requestedMode?: CodingAgentMode; } interface AcceptanceCriterion { id: string; description: string; kind: "file" | "diff" | "test" | "command" | "review" | "artifact" | "state"; required: boolean; verifier: "harness" | "parent" | "user" | "automated_test"; }
```
### Repository 与基线
```typescript
interface RepositoryIdentity { id: RepositoryId; root: string; vcs: "git" | "none" | "other"; remoteRefs: string[]; trust: ProjectTrustState; contentHash: string; } interface WorkspaceState { workspaceId: WorkspaceId; repository: RepositoryIdentity; branch: BranchState; baseline: BaselineRef; userChanges: FileState[]; agentChanges: FileState[]; generatedChanges: FileState[]; vendorChanges: FileState[]; ignoredChanges: FileState[]; locks: LockRef[]; dirty: boolean; } interface BranchState { name?: string; head?: string; upstream?: string; detached: boolean; cleanAtStart: boolean; } interface BaselineRef { id: BaselineId; commit?: string; treeHash: string; indexHash?: string; workspaceSnapshot?: SnapshotRef; capturedAt: string; }
```
### 证据与计划
```typescript
interface EvidenceRef { id: EvidenceId; kind: "file_range" | "symbol" | "command" | "test" | "git" | "diff" | "artifact" | "event"; ref: string; path?: string; lineRange?: [number, number]; contentHash?: string; artifact?: ArtifactRef; capturedAt: string; sensitivity: Sensitivity; confidence: number; } interface PlanStep { id: string; objective: string; dependencies: string[]; inputEvidence: EvidenceRef[]; targetPaths: string[]; expectedChanges: string[]; verification: VerificationSpec[]; checkpointBefore: boolean; checkpointAfter: boolean; risk: "low" | "medium" | "high" | "critical"; } interface TaskPlan { planId: PlanId; task: TaskSpec; repository: RepositoryId; baseline: BaselineRef; steps: PlanStep[]; rejectedAlternatives: string[]; openRisks: string[]; planHash: string; }
```
### 文件变更
```typescript
interface FileState { path: string; canonicalPath: string; contentHash?: string; size: number; mode?: string; status: "unchanged" | "added" | "modified" | "deleted" | "renamed" | "generated" | "vendor"; owner: "user" | "agent" | "tool" | "unknown"; baseHash?: string; lastObservedAt: string; } interface ChangeSet { changeId: ChangeId; baseSnapshot: SnapshotRef; targetPaths: string[]; patchRefs: PatchRef[]; affectedSymbols: string[]; generated: boolean; vendor: boolean; reversible: boolean; verification: VerificationReport[]; }
```
### 执行与验证
```typescript
interface CommandSpec { commandId: CommandId; executable: string; args: string[]; cwd: string; envRefs: string[]; effect: "read" | "build" | "test" | "lint" | "write" | "external"; timeoutMs: number; outputBudget: OutputBudget; sandboxProfile: string; approval: ApprovalPolicy; } interface VerificationSpec { kind: "compile" | "lint" | "test" | "typecheck" | "command" | "diff" | "snapshot"; command?: CommandSpec; expected?: string; required: boolean; } interface VerificationReport { name: string; status: "passed" | "failed" | "skipped" | "inconclusive"; command?: CommandResult; evidence: EvidenceRef[]; artifactRefs: ArtifactRef[]; diagnostics: Diagnostic[]; }
```
## Repository Discovery 与 Repo Map
### Discovery 原则
首次进入 workspace 时，不直接编辑，也不把所有文件读取进上下文。
```text
resolve cwd -> identify repository root -> inspect VCS and branch -> capture baseline -> enumerate top-level structure -> detect language/build/test entry points -> load trust-safe metadata -> build repo map -> select task-relevant slices
```
### Repo Discovery 结果
必须至少记录：
canonical repository root；
- VCS 类型、HEAD、branch、upstream 和 dirty 状态；
- 顶层目录和重要配置入口；
- package/module/workspace 边界；
- 语言、构建、测试、lint、生成代码和 vendor 目录；
- 项目规则文件及其作用范围；
- `.gitignore`、构建缓存和临时目录；
- 未信任或可执行的 hooks、plugins、MCP、LSP、env loader；
- repo map 的 source hash、生成时间和失效条件。
### RepoMap
```typescript
interface RepoMap { repository: RepositoryId; root: string; entries: RepoMapEntry[]; symbols: SymbolIndexEntry[]; dependencies: DependencyEdge[]; testTargets: TestTarget[]; configEntrypoints: string[]; generatedRoots: string[]; vendorRoots: string[]; sourceHash: string; generatedAt: string; expiresOn: RepoMapInvalidation[]; }
```
Repo map 是导航索引，不是源码替代品。
### 失效条件
repo map 在以下情况失效：
branch、commit 或 workspace tree hash 变化；
- 目标目录文件 hash 变化；
- 生成代码、package manifest 或 lockfile 变化；
- project trust、工具集或语言解析器版本变化；
- 发现新的目录边界或重命名；
- map TTL 到期。
### 代码库上下文选择
```text
repo map -> symbol/file search -> target file slices -> imports/callers/dependents -> tests/config -> full read of edit units
```
未知文件先搜索；已知文件可定点读取；大文件按 symbol/range；修改前读取完整相关结构。
## Workspace、Branch 与 Baseline
### 启动快照
在第一次写操作前必须保存：
workspace root canonical path；
- branch/HEAD/upstream；
- index 与工作树状态；
- 用户已有修改的 path/hash/patch；
- ignored/generated/vendor 目录识别；
- 当前 repo map hash；
- policy、sandbox、mode 和 host capability snapshot。
### 用户已有改动
用户已有改动是受保护输入：
```text
baseline capture -> classify user changes -> refuse blind overwrite -> target patch against current file -> recheck hash immediately before write
```
如果目标文件在 run 中被用户或其他进程修改，编辑必须进入 conflict，而不是静默覆盖。
### Branch 策略
默认行为：
read-only/review 不创建 branch；
- plan 可以创建 plan artifact，但不修改产品 branch；
- implementation 是否创建 branch 由 host/policy/用户配置决定；
- commit、push、merge、rebase、reset 等属于独立高风险动作；
- detached HEAD 和无 VCS workspace 必须显式记录限制。
`Coding Agent` 不应把 branch 创建当作安全隔离的唯一手段。仍需 snapshot、patch、lock、policy 和恢复记录。
### Baseline 不变量
```text
base tree hash + per-file hash + branch identity + workspace root
```
不能只保存“当前 commit”而忽略 dirty working tree。
## 代码阅读与证据系统
### 证据优先
模型的代码结论分为：
`verified`：由文件、symbol、命令或测试直接支持；
- `inferred`：多个证据合理推断；
- `unverified`：尚未读取或验证；
- `contradicted`：与已有证据冲突。
### Evidence Ledger
```typescript
interface EvidenceLedger { taskId: TaskId; entries: EvidenceLedgerEntry[]; assumptions: AssumptionRecord[]; contradictions: ContradictionRecord[]; lastVerifiedTreeHash: string; } interface EvidenceLedgerEntry { evidence: EvidenceRef; claim: string; status: "verified" | "inferred" | "unverified" | "contradicted"; usedBy: string[]; }
```
### 阅读顺序
推荐顺序：
1. 用户明确提到的文件和配置； 2. repo map 与目标目录； 3. 入口函数、类型、接口和调用者； 4. 相关测试和 fixture； 5. 错误、重试、权限和配置； 6. 生成代码与 vendor，仅在依赖链需要时阅读； 7. 命令执行结果和实际 diff。
### 证据与 Context
证据进入 `ContextPlan` 时必须带：
source、path、line range、symbol；
- content hash、branch、commit 或 snapshot；
- trust、authority、sensitivity；
- relevance、freshness、estimated tokens；
- 是否可以向 provider 外发；
- 是否应 offload 为 artifact。
代码注释、测试输出和外部文档通常是数据，不拥有 system 或 policy authority。
## 任务规范化与计划
### TaskSpec 解析
将用户输入规范化为：
```text
objective constraints acceptance criteria referenced resources assumptions unresolved questions requested mode
```
不得把“修复 bug”擅自改写为“重构整个模块”。
### 计划阶段
计划必须回答：
目标文件和 symbol 是什么；
- 现有行为与证据是什么；
- 需要修改哪些接口、实现、测试和配置；
- 哪些步骤可并行，哪些必须串行；
- 每一步的风险、锁和 snapshot；
- 如何验证编译、lint、测试和回归；
- 哪些操作需要用户确认；
- 哪些事项超出任务范围。
### Plan Artifact
Plan mode 只允许写入专用 plan artifact 或 session state，不允许修改产品代码。
```typescript
interface PlanArtifact { plan: TaskPlan; evidence: EvidenceRef[]; affectedPaths: string[]; verificationPlan: VerificationSpec[]; approvalRequests: string[]; expiresAt?: string; }
```
### 计划不可盲信
实现开始前检查：
baseline hash 是否仍匹配；
- 用户 steering 是否改变目标；
- workspace 是否已被外部修改；
- policy、toolset、sandbox 是否变化；
- plan 中的路径和命令是否仍可用。
## 编辑策略与变更所有权
### 编辑粒度
优先级：
```text
structured AST/refactor tool > exact Edit with surrounding context > bounded patch > full-file rewrite only when justified
```
每次 edit 必须：
先读相关文件；
- 明确 old hash；
- 指定目标 path 和 symbol/range；
- 检查用户已有改动；
- 生成 patch preview；
- 通过 schema/business/policy；
- 写后重新读取并验证 hash。
### EditRequest
```typescript
interface EditRequest { path: string; baseHash: string; operation: "replace_range" | "insert" | "delete" | "rename_symbol" | "apply_patch"; range?: [number, number]; oldTextHash?: string; newContent: string; reason: string; owner: "agent" | "subagent"; generated?: boolean; vendor?: boolean; }
```
### 变更所有权
每个 path 或 lock resource 要有 owner：
parent run；
- child run；
- user/unknown；
- generated pipeline；
- vendor updater。
Agent 不得把 `user` 或 `unknown` 变更标成自己的改动。
### 最小变更
尽量保持：
原有格式、命名和模块边界；
- 不相关用户修改；
- 生成文件的上游来源；
- vendor 目录的既定更新流程；
- 测试和配置的最小覆盖面。
## Snapshot、Patch、Diff 与 Revert
### Snapshot 模型
```typescript
interface SnapshotRef { id: SnapshotId; workspaceId: WorkspaceId; treeHash: string; files: SnapshotFileRef[]; branch?: BranchState; createdAt: string; retention: RetentionPolicy; } interface SnapshotFileRef { path: string; hash: string; size: number; mode?: string; artifact?: ArtifactRef; }
```
### Patch 模型
```typescript
interface PatchRef { id: PatchId; baseSnapshotId: SnapshotId; affectedPaths: string[]; artifact: ArtifactRef; patchHash: string; applyStatus: "prepared" | "applied" | "rejected" | "reverted" | "conflicted"; verification: VerificationReport[]; }
```
### 变更顺序
```text
capture base snapshot -> prepare patch -> validate base hashes -> acquire path locks -> apply patch -> read-back and compute diff -> run targeted checks -> checkpoint -> expose diff/artifact
```
### Revert
Revert 是追加的语义事实，不是删除历史：
文本 patch 可以反向应用，但必须检查 base hash；
- 文件已被用户改动时进入三方合并或冲突；
- snapshot 可用于恢复 Agent 自己的变更；
- 外部命令、发布、发送和部署不能假设可通过文件 revert 撤销；
- 不可逆动作只能调用显式补偿工具。
### Diff 视图
至少提供：
unified diff；
- 文件级统计；
- symbol 级影响；
- 生成/用户/vendor 标注；
- base/target hash；
- 测试和命令证据；
- redacted user-facing view；
- 完整 artifact 引用。
## 命令、构建、Lint 与测试执行
### Command Runner
Coding Agent 必须使用结构化命令模型：
```text
executable + args + cwd + minimal env + sandbox + timeout + output budget
```
优先结构化 argv，不把模型自由文本拼成 shell。
### 命令分类
| 类别 | 默认行为 |
|---|---|
| read/search | 低风险，通常可自动执行 |
| compile/typecheck | workspace 内受限执行 |
| lint/format | 可能写文件，显式标记 effect |
| unit/integration test | 受 sandbox、网络和资源预算约束 |
| package install | 外部网络和脚本，通常 ask |
| git diff/status | 只读诊断 |
| git commit | 独立高风险审批 |
| git push/merge/rebase | 默认 ask 或 deny |
| deploy/publish | critical，独立 elevated 流程 |
### 输出与 Artifact
命令结果分成：
```text
model-facing summary structured CommandResult user-facing log artifact raw diagnostic artifact trace/usage record
```
命令输出超过预算时：
保留退出码、失败测试、首个错误和关键上下文；
- 完整 stdout/stderr 写入 ArtifactStore；
- 返回 `truncated: true`、原始大小、保留范围和 `ArtifactRef`；
- 不让模型误以为看到了完整日志。
### 编译与 lint
验证顺序通常为：
```text
syntax/typecheck -> targeted lint -> targeted unit test -> affected integration test -> broader suite if budget allows
```
Agent 必须报告跳过原因，不把未运行的检查写成通过。
### 测试隔离
测试命令需要声明：
cwd 和目标 package；
- 是否写 workspace；
- 是否需要 network；
- 是否可并行；
- 是否会启动 daemon；
- test artifact 和 coverage 位置；
- timeout、CPU、memory、disk 和 process limit。
## 进度、Checkpoint 与用户 Steering
### Progress State
```typescript
interface CodingProgress { taskId: TaskId; currentStep?: string; completedSteps: string[]; pendingSteps: string[]; changedFiles: FileState[]; verification: VerificationReport[]; failures: FailureState[]; risks: string[]; lastCheckpoint?: CheckpointRef; steeringQueue: SteeringMessage[]; followUpQueue: SteeringMessage[]; }
```
进度必须基于 durable state、events、diff 和命令事实，不只依赖模型自然语言。
### Checkpoint 时机
至少在以下位置写 checkpoint：
repository/baseline discovery 完成；
- plan artifact 完成；
- 每个高风险 edit 前；
- patch 应用后；
- 每个有副作用命令准备完成后；
- 每个 verification 结果完成后；
- approval requested/resolved；
- compaction 完成；
- run terminal。
### Steering 与 Follow-up
`steering`：在当前 loop 或下一可安全边界尽快注入，优先改变方向；
- `follow-up`：当前任务稳定完成后处理；
- 新 steering 不得跳过 pending approval、锁或 durable commit；
- steering 改变目标时，旧计划标记 superseded，重新计算 affected paths 和预算；
- host 断开不等于取消 run。
```typescript
interface SteeringMessage { id: string; source: "user" | "host" | "system"; text: string; priority: "interrupt" | "normal"; receivedAt: string; appliesTo: "current_turn" | "next_turn" | "after_current_task"; }
```
## Review 模式
### Review 的职责
Review mode 关注：
correctness、回归和安全问题；
- diff 与 baseline 是否一致；
- 测试缺口、未验证声明和风险；
- 用户已有改动是否被误伤；
- generated/vendor 变更是否来自正确来源；
- policy、sandbox、命令和 artifact 证据是否完整。
### Review 默认边界
默认 read-only；
- 只暴露 diff、read、search、test/静态诊断工具；
- 写工具隐藏且直接调用也拒绝；
- 可以生成 review artifact，不修改产品文件；
- commit/push/merge 不属于 review 自动动作。
### Review Finding
```typescript
interface ReviewFinding { id: string; severity: "info" | "low" | "medium" | "high" | "critical"; category: "correctness" | "security" | "regression" | "performance" | "maintainability" | "test_gap"; path: string; lineRange?: [number, number]; claim: string; evidence: EvidenceRef[]; confidence: number; suggestedFix?: string; status: "verified" | "inferred" | "unverified"; }
```
结论按严重度排序；风格偏好不能冒充缺陷；每个 finding 必须有文件/行或可复现实验证据。
## 并发与文件锁
### 为什么需要锁
多个 tool call、subagent、formatter、test watcher 或用户 IDE 可能同时读写同一资源。
```text
execution completion order != model result order
```
### 锁接口
```typescript
interface ResourceLockManager { acquire(request: LockRequest, signal: AbortSignal): Promise<LockLease>; } interface LockRequest { ownerId: string; keys: string[]; mode: "shared" | "exclusive"; timeoutMs: number; } interface LockLease { lockId: LockId; keys: string[]; release(): Promise<void>; expiresAt?: string; }
```
### 锁键
```text
file:<canonical-path> directory:<canonical-path> repo:<repository-id> branch:<repository-id>#<branch> workspace:<workspace-id> generated-root:<path> vendor-root:<path>
```
路径必须 canonicalize：分隔符、大小写语义、符号链接、junction、reparse point 和相对路径都不能绕过锁。
### 并发规则
独立只读可并行；
- 同一文件写入 exclusive；
- 目录级生成器默认 exclusive；
- 同一 repo 的 branch/commit 操作 exclusive；
- 多锁按稳定顺序获取，避免死锁；
- 不在持锁期间等待人工审批；
- 取消、崩溃和租约过期必须释放或隔离锁；
- 结果回传按模型 call ordinal 排序。
## 生成代码与 Vendor
### 分类
`generated` 与 `vendor` 都不是普通源码：
generated：由 schema、IDL、代码生成器或构建步骤产出；
- vendor：第三方复制、锁定或镜像的依赖源码；
- generated source：可编辑上游；
- generated output：通常不应手改；
- vendored patch：必须有来源、版本和许可证证据。
### 生成代码策略
Agent 先寻找生成入口：
```text
schema/IDL/source template -> generator command/version -> generated output -> compile/test
```
若用户要求修改 generated output，Agent 必须：
说明上游源文件和生成命令；
- 尽量修改 source，不直接改 output；
- 记录 generator version、input hash、output hash；
- 把生成命令和差异作为 artifact；
- 防止生成器覆盖用户已有改动。
### Vendor 策略
vendor 更新需要：
dependency/version/source provenance；
- license 和 security policy 检查；
- lockfile/hash；
- 变更范围和上游 diff；
- 生成/同步命令证据；
- 不把 vendor 内部代码自动当作本项目风格；
- 默认不编辑 vendor，除非任务明确且有 upstream patch 计划。
## 模式、Host Adapter 与离线能力
### 模式矩阵
| 模式 | 读取 | 搜索 | 编辑 | 命令 | 外部网络 | 提交 |
|---|---:|---:|---:|---:|---:|---:|
| `offline` | 已缓存/本地 | 本地 | 默认否 | 本地只读/受限 | 否 | 否 |
| `read_only` | 是 | 是 | 否 | 低风险只读 | policy | 否 |
| `plan` | 是 | 是 | 仅 plan artifact | 诊断/只读 | policy | 否 |
| `implementation` | 是 | 是 | policy 允许 | sandbox 后 | policy | 独立 ask |
| `review` | 是 | 是 | 否 | diff/test/诊断 | policy | 否 |
模式必须同时改变：
active toolset；
- policy；
- sandbox；
- prompt；
- completion criteria；
- delivery options。
只改 prompt 文本而保留写工具不是安全模式。
### Offline
Offline 模式：
不调用 web、外部 provider 或任意网络命令；
- 只使用本地缓存、repo、session、artifact 和本地 model runtime；
- 缺失依赖或索引时返回明确 diagnostic；
- 不伪造“已在线验证”；
- 外部网络相关测试只能标记 skipped/inconclusive。
### Host Adapter
```typescript
interface CodingHostPort { capabilities(): HostCapabilities; deliver(event: HostEvent): Promise<void>; requestApproval(request: ApprovalRequest): Promise<ApprovalDecision>; showDiff(patch: PatchRef): Promise<void>; receiveControl(): AsyncIterable<HostControlEvent>; resume(runId: string, cursor?: EventCursor): Promise<void>; }
```
CLI/TUI/IDE/RPC/HTTP 只投影 canonical events；Host 不重新解释 finish reason、tool completeness 或 durable state。 Host 不支持审批时，高风险动作 fail-closed。
## 生命周期与状态机
### Coding Run 状态机
```text
Created -> Bootstrapping -> Discovering -> BaselineCaptured -> Planning -> AwaitingPlanApproval | Editing -> Verifying -> Reviewing -> AwaitingCommitApproval -> Delivering -> Completed 任意活动状态 -> Cancelled 任意活动状态 -> Failed Failed -> Recovering -> Discovering | Planning | Verifying | AwaitingApproval
```
### Edit 状态机
```text
Proposed -> ReadValidated -> BaseHashChecked -> LockAcquired -> PolicyAllowed -> PatchPrepared -> Applied -> ReadBackVerified -> DiffCommitted -> Reverted | Conflicted | Failed
```
### Command 状态机
```text
Prepared -> Authorized -> SandboxReady -> Queued -> Running -> OutputCaptured -> ResultNormalized -> ArtifactCommitted -> Completed | Failed | Cancelled | UnknownOutcome
```
### Review 状态机
```text
ReviewStarted -> BaselineCompared -> DiffInspected -> EvidenceCollected -> FindingsProduced -> VerificationChecked -> ReviewReported
```
状态不能用 `isRunning: boolean` 替代。
## 一次任务的决策流程
```text
1. Receive host request 2. Normalize TaskSpec and requested mode 3. Resolve workspace/repository/tenant 4. Load safe configuration 5. Resolve project trust 6. Capture branch, dirty state and baseline 7. Discover repo map and invalidation rules 8. Select evidence and build ContextPlan 9. Compile mode-aware Prompt and active toolset 10. Decide plan vs implementation vs review 11. Build TaskPlan and checkpoints 12. Before each edit: re-read, hash-check, policy, lock, snapshot 13. Apply minimal patch 14. Read-back, diff, syntax/typecheck 15. Execute targeted lint/tests with bounded CommandRunner 16. Offload logs/diffs/images to ArtifactStore 17. Update WorkingState and checkpoint 18. Handle steering, failures or compaction 19. Review changes and acceptance criteria 20. Ask separately for commit/push/deploy 21. Deliver final result with evidence and remaining risks
```
### 关键决策表
| 情况 | 决策 |
|---|---|
| workspace 不明确 | 先 discovery，不编辑 |
| 用户改动覆盖目标 | conflict，等待 steering/显式选择 |
| 项目未信任 | 只加载安全元数据和 read-only 工具 |
| plan 未批准 | 只能返回计划和证据 |
| base hash 变化 | 重新读取、重算 patch，不覆盖 |
| sandbox 不可用 | 隐藏/拒绝危险命令 |
| approval host 不可用 | fail-closed |
| 测试输出过大 | artifact offload，模型只收摘要 |
| 命令退出码非零 | 记录失败，是否修复由计划和策略决定 |
| side effect 结果未知 | query status，不盲目重试 |
| 用户 steering 改目标 | supersede 旧计划，重建 context |
| review 发现高风险 | 停止交付，标记未完成 |
## 与 Context、Prompt、Tool、State、Policy、Harness 集成
### Context 集成
Coding Context 的优先级：
```text
product/organization policy > user instructions > trusted workspace rules > task-local plan/evidence > relevant code/tests/config > tool output and retrieved content
```
`ContextCompiler` 负责：
repo map 与相关 file slices；
- 目录范围规则；
- 当前 branch/baseline/runtime facts；
- plan、working state、recent turns；
- tool result summary 与 artifact refs；
- token budget、去重、trust/authority 和 egress；
- 保持 tool call/result 对。
不要把 entire repository 或完整测试日志塞入 prompt。
### Prompt 集成
Prompt 必须解释：
当前 coding mode；
- 目标、约束和完成标准；
- repo map 只是索引，证据需要回到源码；
- 编辑前读取和 hash-check；
- 用户改动不可覆盖；
- 工具用途、副作用、审批和输出预算；
- review 中如何给出文件/行证据；
- generated/vendor 的处理规则；
- 失败和不确定结果如何报告。
Prompt 不实现：
path boundary；
- lock；
- command timeout；
- commit authorization；
- JSON/schema/business validation。
### Tool 集成
推荐工具集合：
```text
discover_repository read_file/read_range search_code/list_tree inspect_git_status/inspect_diff create_plan apply_edit/apply_patch create_snapshot/show_diff/revert_patch run_command/run_tests/run_lint/run_build request_approval spawn_subagent write_artifact review_changes
```
工具按 mode 动态裁剪；隐藏工具直接调用也必须拒绝。
### State 集成
Session 保存语义历史，不等于 provider messages：
`RepositoryDiscoveredEntry`；
- `BaselineCapturedEntry`；
- `PlanCreatedEntry`；
- `EditPreparedEntry`；
- `PatchAppliedEntry`；
- `CommandStartedEntry`；
- `VerificationCompletedEntry`；
- `ReviewFindingEntry`；
- `SteeringEntry`；
- `CheckpointEntry`；
- `CommitRequestedEntry`；
- `UnknownOutcomeEntry`。
`WorkingState` 保存当前 objective、changed files、tests、failures、pending approvals、locks、artifacts 和 steering queue。
### Policy/Sandbox 集成
决策顺序：
```text
mode/tool visibility -> canonical path/command validation -> call policy -> approval -> execution backend -> sandbox attestation -> result egress
```
Project trust、tool policy、approval、sandbox 是四个不同问题。
### Harness 集成
Harness 负责：
两阶段 safe/trusted bootstrap；
- 冻结 run config、repo、toolset、policy、sandbox snapshot；
- 创建 `RunScope`、预算、task group、event router；
- 监督 model、tool、command、approval、lock、subagent 和 delivery；
- 在 durable boundary 写 session/checkpoint；
- 在崩溃时识别未知命令和文件副作用；
- 将 live event、durable event、artifact、trace 和 host delivery 分开。
## 提交与提交前检查边界
### 默认边界
“代码已修改并验证”不等于“已提交”。 提交是独立动作：
```text
working tree diff -> user-facing review -> required tests/checks -> commit message proposal -> explicit approval -> git commit -> verify commit/tree/status
```
### CommitRequest
```typescript
interface CommitRequest { repository: RepositoryId; branch: BranchState; expectedTreeHash: string; patchRefs: PatchRef[]; message: string; checks: VerificationReport[]; includePaths: string[]; excludeUserChanges: boolean; approvalId?: string; }
```
### 提交前检查
至少检查：
diff 仅包含允许路径；
- 用户已有变更没有被纳入；
- generated/vendor 变更有来源；
- required compile/lint/test 已运行；
- secret、凭据和临时文件未加入；
- branch/HEAD 未被外部改变；
- commit scope、message 和 policy 满足要求；
- host 能展示最终 diff 和 artifact。
`push`、`merge`、`rebase`、`tag`、`release`、`deploy` 分别授权，不能由 commit approval 隐式覆盖。
## 故障恢复
### 错误分类
```text
workspace_resolution repository_discovery project_trust baseline_conflict repo_map_stale context_overflow model_transport tool_validation policy_denied approval_unavailable lock_timeout edit_conflict command_timeout command_failed artifact_store verification_failed session_conflict host_disconnect unknown_side_effect
```
### 恢复步骤
```text
load last checkpoint -> verify repository root/branch/tree hash -> scan files and user changes -> inspect pending edit/command records -> query idempotency/status for external effects -> rebuild repo map/context -> resume safe step or wait for user
```
### 文件编辑崩溃
如果 patch 应用后但 durable commit 前崩溃：
1. 读取目标文件和 snapshot； 2. 计算实际 diff； 3. 判断 patch 是否完整、重复或冲突； 4. 若可证明已应用，补写 `PatchAppliedEntry`； 5. 若不完整，使用 snapshot/patch 恢复 Agent 自己的部分； 6. 若存在用户并发修改，标记 conflict，不自动覆盖。
### 命令崩溃
命令、测试、构建可能启动子进程或写文件：
记录 process tree、cwd、sandbox profile 和 execution ID；
- 取消时终止整个进程树；
- workspace 写入未知时先扫描 diff；
- 外部副作用未知时执行 query/status；
- 不因为 UI 显示取消就宣称没有副作用；
- 孤儿进程、锁和 sandbox 进入 quarantine/cleanup。
### Recovery 不变量
```text
不重复不可逆副作用 不丢失 durable edit/verification/approval 事实 不把 unknown 当 success 不覆盖用户已有改动 不绕过新的 policy/sandbox
```
## 安全与隐私
### 不可信输入
以下都视为不可信：
用户描述中的路径、命令和 URL；
- 模型生成的工具名、参数和 patch；
- 源码注释、文档、issue、测试输出；
- package scripts、hooks、MCP/LSP 描述；
- 生成代码和 vendor 内容；
- 环境变量名、配置文件和重定向结果。
### 文件安全
canonicalize 路径；
- 检查 `..`、符号链接、junction、reparse point 和 mount；
- 允许根目录取交集；
- 默认不挂载 home、SSH、cloud config 和无关 secret；
- 删除 root/workspace root 必须拒绝或 critical approval；
- archive 解压检查 zip-slip；
- TOCTOU 通过 hash、lock、snapshot 和执行前重校验缓解。
### 命令安全
优先 structured argv；
- 最小 PATH 和环境；
- 禁止任意 shell 拼接；
- sandbox 强制 CPU、memory、disk、process、network 和 stdout 限制；
- package install、lifecycle scripts、外网、daemon 和 privileged command 独立决策；
- sandbox 不可用时危险命令 fail-closed。
### 数据外发
Context、command output、artifact、trace、host delivery 都执行 egress policy：
```text
provider/model jurisdiction + resource sensitivity + tenant policy + purpose + redaction -> allow | redact | summarize | artifact_only | deny
```
日志默认只记录 ID、hash、类型、大小、状态、耗时和脱敏摘要。
## 可观测性
### Trace 层级
```text
session -> coding run -> discovery -> context/prompt compile -> plan -> edit/patch -> command/verification -> review -> approval/commit -> artifact/delivery
```
### 必备字段
```text
trace_id session_id workspace_id repository_id branch baseline tree hash run_id turn_id attempt_id task_id plan_id change_id snapshot_id patch_id mode toolset_hash policy_version sandbox_profile lock_ids command_id path_hashes evidence_ids artifact_ids exit_code test_count usage/cost retry/fallback steering cause recovery status
```
完整路径、命令参数、源码和 prompt 必须按 sensitivity 脱敏或仅记录 hash。
### 指标
discovery 与 repo map latency；
- context compile token 和 cache hit；
- plan-to-edit time；
- patch conflict rate；
- user-change preservation rate；
- lock wait/deadlock/lease leak；
- command success、timeout、cancel、unknown outcome；
- compile/lint/test pass rate；
- review finding precision 和未验证声明数；
- snapshot/patch/revert success；
- recovery duration、duplicate side effect、orphan process；
- cost 按主模型、retry、compaction、subagent、command、artifact 归因。
### Diagnostic Snapshot
应能在脱敏情况下回答：
当前 workspace、branch、baseline 和 dirty state；
- 当前 plan step、changed files 和锁；
- pending approval、in-flight command、未知副作用；
- active toolset、policy、sandbox 和 host capability；
- 最近错误、artifact、checkpoint 和 projector lag。
## 测试策略
### Testkit
```text
FakeModelProvider ScriptedModelStream FakeRepository FakeVcs InMemoryRepoMap FakeEditEngine SnapshotStore PatchApplier FakeCommandRunner FakeSandboxBackend FakePolicy/Approval ResourceLockManager InMemorySessionRepository DeterministicClock/IDs EventRecorder CrashInjector ReplayRunner SideEffectRecorder
```
### 单元测试
覆盖：
repository root、branch、dirty state 和 baseline hash；
- repo map 构建、去重和失效；
- file range/symbol evidence；
- TaskSpec、TaskPlan 和 acceptance criteria；
- edit base hash、用户改动检测和 exact replacement；
- patch apply、diff、snapshot、revert 和冲突；
- command argv、cwd、env、timeout、output budget；
- review finding、severity 和 evidence；
- mode tool visibility、policy 和 host capability；
- steering、follow-up、checkpoint 和 state projection。
### 集成测试
至少包括：
1. 未知仓库 discovery 后只读回答； 2. plan mode 只写 plan artifact； 3. implementation 对单文件做最小 patch； 4. 用户并发修改导致 conflict； 5. 两个独立只读命令并行； 6. 同文件写入由锁串行； 7. build/lint/test 输出超限并 offload； 8. 测试失败后保留证据并生成下一步； 9. review mode 不产生产品写入；
10. offline mode 拒绝网络； 11. sandbox unavailable 时拒绝危险命令； 12. approval host disconnect 后保持 pending； 13. crash after patch before commit 可恢复； 14. command side effect unknown 不重放； 15. commit 前检查排除用户变更； 16. subagent 使用独立 worktree/lock/patch； 17. host resume 从 durable cursor 恢复； 18. compaction 保留 changed files、tests 和 pending work。
### 故障注入
在以下边界注入 crash/timeout/failure：
baseline capture 前后；
- plan append 前后；
- patch 写入前后；
- diff 读取前后；
- command side effect 前后；
- tool result commit 前后；
- test artifact 上传中；
- approval consume 前后；
- checkpoint blob 和引用之间；
- commit 前检查和 commit 之间；
- host disconnect 与 durable delivery 之间。
### 评测断言
不能只比较最终文本，必须断言：
repository/baseline/branch 事实；
- 文件 hash、patch、diff 和实际副作用；
- tool call/result、policy/approval、lock 和 sandbox 事件；
- 编译、lint、测试的真实退出码；
- checkpoint、replay、恢复和 unknown outcome；
- 用户 steering 是否按优先级生效；
- 成本、延迟和 artifact 预算。
## 反模式
1. 把 Coding Agent 实现成 `while + shell(command)`。 2. 未发现 repository 就开始编辑。 3. 把整个仓库塞进 context。 4. 用 prompt 说“不要覆盖用户改动”，但不做 hash/patch 检查。 5. 只保存当前 commit，不保存 dirty working tree baseline。 6. 直接反射执行模型生成的文件路径或命令。 7. 先写文件，之后才检查 policy、lock 和 snapshot。 8. `apply_patch` 不校验 base hash。 9. 把用户、Agent、generated、vendor 修改混在一起。
10. 生成代码只改 output，不记录 generator source。 11. vendor 更新没有版本、hash 和许可证 provenance。 12. 所有命令都使用 unrestricted host shell。 13. 测试输出无限进入 model context。 14. 只运行测试，不记录命令、cwd、退出码和 artifact。 15. 把测试未运行写成“验证通过”。 16. 用 `isRunning` 替代 run/edit/command 状态机。 17. 并行写同一文件，没有 canonical lock key。 18. 等待 approval 时持有文件锁。 19. cancel 只停止 UI，不停止子进程。 20. 未知命令结果自动重试。 21. review 模式仍暴露 edit/commit 工具。 22. plan、implementation、review 只改角色文字，不改 capability。 23. steering 消息被重复执行或越过 durable boundary。 24. commit approval 隐式覆盖 push/deploy。 25. 用 branch 代替 sandbox、policy 和 audit。 26. 只看最后 diff，不检查用户已有修改。 27. revert 直接删除 session/history entry。 28. 子 Agent 共享主 workspace 且没有 owner/merge。 29. 日志写入完整 prompt、secret、命令和用户文件。 30. 只测 happy path，不测冲突、崩溃、恢复和 unknown outcome。
## 实施清单
### V1：可验证 Coding Kernel
[ ] 定义 CodingAgentMode、TaskSpec、AcceptanceCriterion。；[ ] 实现 repository root、VCS、branch、dirty state discovery。；[ ] 实现 baseline/tree/file hash snapshot。；[ ] 实现 read/search、repo map、EvidenceRef。；[ ] 建立 headless Kernel 与 fake provider。；[ ] 建立 mode-aware tool visibility。；[ ] 实现最小 plan artifact。
### V2：编辑与验证
[ ] 定义 EditRequest、ChangeSet、SnapshotRef、PatchRef。；[ ] 实现 base hash、用户改动保护和 read-back verification。；[ ] 实现 diff、patch、revert 和冲突诊断。；[ ] 实现结构化 CommandRunner。；[ ] 编译、lint、测试命令有预算和 artifact offload。；[ ] 实现 VerificationReport 和 completion checks。
### V3：安全与并发
[ ] project trust safe/trusted 两阶段 bootstrap。；[ ] policy、approval、sandbox、egress 分层。；[ ] canonical path 与 argv 校验。；[ ] ResourceLockManager 和 lease recovery。；[ ] sandbox attestation 与 fail-closed。；[ ] secret、network、process、filesystem 最小能力。；[ ] 未知副作用和 status query。
### V4：持久化与产品模式
[ ] Session semantic entries 与 WorkingState projector。；[ ] Run/Turn/Attempt/Edit/Command/Review 状态机。；[ ] steering/follow-up、checkpoint、compaction。；[ ] offline/read-only/plan/implementation/review 完整矩阵。；[ ] CLI/TUI/IDE/RPC Host Adapter。；[ ] durable event、replay、multi-client resume。
### V5：规模化与治理
[ ] subagent assignment、独立 workspace/patch/merge。；[ ] generated/vendor provenance 和供应链检查。；[ ] review artifact、审计、cost attribution。；[ ] provider/tool/backend/host conformance suite。；[ ] crash/chaos/recovery 评测和 CI gates。；[ ] commit/push/deploy 分离授权与审计。；[ ] 多租户、retention、删除和诊断快照。
## 五个参考项目的启发来源
### Pi
headless agent loop、统一 provider event 和 CLI/TUI/RPC 共用 runtime，启发 Kernel 与 Coding Harness 分离；
- session tree、steering/follow-up 和 compaction entry，启发 branch、checkpoint、用户控制和可恢复工作状态；
- resource loader、项目规则和按工具动态生成提示，启发 repo/context 编译；
- 执行并发但结果顺序稳定，启发 command/tool feedback 的 call-order 投影。
### Grok Build
Session/ChatState/Sampler actor，启发 workspace/session 状态所有权与串行提交；
- permission decision、folder trust、sandbox，启发 project trust、policy、approval 和 execution 分层；
- 并行工具与路径级锁，直接启发文件锁、canonical resource key 和并发策略；
- 工具输出上限和上下文修剪，启发命令日志 artifact offload 与 token budget。
### OpenCode
client/server 与事件总线，启发 Host Adapter、durable event、多客户端 resume；
- session/message/part，启发 provider message 与 coding transcript 分离；
- snapshot/patch/revert，启发 workspace baseline、变更审计、冲突和恢复；
- permission、MCP/LSP 和 projector，启发扩展与状态投影边界。
### Claude Code
permission modes、hooks、skills、subagents、memory、计划和任务工作流，启发 coding mode、审批、steering、子任务和项目规则；
- `CLAUDE.md` 与 auto memory 方向，启发目录范围规则、working memory 和 provenance；
- 公开能力和安全语义仍以现有本地文档中标注的官方资料为准，辅助源码不作为规范。
### OpenClaw
AgentHarness registry、agent-core 和 Gateway/channel，启发 capability registry、Host/交付分层和后台运行；
- tool、sandbox、elevated 分离，启发危险命令与 commit/deploy 的独立通道；
- 事务化插件注册，启发 generated/vendor/extension 加载失败时回滚；
- memory flush、后台任务和多渠道 session key，启发 durable checkpoint、artifact、租约和身份范围。
本设计的实现审查应回到上述本地参考文档及其已记录源码范围。新增 provider、VCS、编译器、sandbox 或企业合规要求时，应另行补充一手证据、迁移方案和契约测试。
