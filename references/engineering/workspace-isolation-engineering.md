# Workspace Isolation Engineering 细粒度工程设计
> Workspace Isolation 不是给 shell 增加一个 `cwd`。它是围绕 `workspace/project/repository/session/run` 建立可验证的资源身份、文件系统边界、变更所有权、执行后端、信任门、并发控制、清理和审计系统。
>
> 本文只整理当前目录已有的参考架构、Agent Harness 以及 Prompt、Context、Tool、State/Memory、Permission/Sandbox、Subagent、Event/Observability、Evaluation、Coding Agent、Provider Runtime、Artifact、Multi-tenant 文档中已有的源码调研结论；不依赖 README，不新增网络调研结论。
## 目录
1. [设计目标与非目标](#设计目标与非目标) 2. [核心判断与术语](#核心判断与术语) 3. [职责边界](#职责边界) 4. [威胁模型与隔离目标](#威胁模型与隔离目标) 5. [隔离层级与资源图](#隔离层级与资源图) 6. [总体架构与包布局](#总体架构与包布局) 7. [核心数据模型](#核心数据模型) 8. [TypeScript 接口](#typescript-接口) 9. [Workspace/Project/Repository 解析](#workspaceprojectrepository-解析) 10. [Root Canonicalization](#root-canonicalization) 11. [Path Containment](#path-containment) 12. [Symlink、Junction 与 Reparse Point](#symlinkjunction-与-reparse-point) 13. [Filesystem Mount 与 Sandbox Profile](#filesystem-mount-与-sandbox-profile) 14. [Branch、Worktree 与 Baseline](#branchworktree-与-baseline) 15. [User/Agent/Generated/Vendor 变更所有权](#useragentgeneratedvendor-变更所有权) 16. [File Lock 与并发协调](#file-lock-与并发协调) 17. [Temp、Artifact 与 Cache 隔离](#temparticle-与-cache-隔离) 18. [Subagent Ownership](#subagent-ownership) 19. [Project Trust 与扩展加载](#project-trust-与扩展加载) 20. [MCP/LSP/Plugin/Env Hook 边界](#mcplsppluginenv-hook-边界) 21. [策略决策流程](#策略决策流程) 22. [Workspace 生命周期与状态机](#workspace-生命周期与状态机) 23. [Run 生命周期与状态机](#run-生命周期与状态机) 24. [与 Context/Prompt/Tool/State/Policy/Harness 集成](#与-contextprompttoolstatepolicyharness-集成) 25. [一次写操作的端到端流程](#一次写操作的端到端流程) 26. [TOCTOU 与执行前复核](#toctou-与执行前复核) 27. [故障恢复与未知结果](#故障恢复与未知结果) 28. [Cleanup、Retention 与孤儿资源](#cleanupretention-与孤儿资源) 29. [安全与隐私](#安全与隐私) 30. [Cross-workspace Attack 防护](#cross-workspace-attack-防护) 31. [Windows/Native Host 注意事项](#windowsnative-host-注意事项) 32. [可观测性与审计](#可观测性与审计) 33. [测试策略与测试矩阵](#测试策略与测试矩阵) 34. [反模式](#反模式) 35. [实施清单](#实施清单) 36. [五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与非目标
### 目标
Workspace Isolation Runtime 必须：
- 将 `workspace` 作为文件系统和项目规则边界，将 `project` 作为配置、扩展和 trust 边界。；将 `repository`、`branch`、`worktree`、`baseline` 和 dirty working tree 建模为可验证事实。；将 `session`、`run`、`turn`、`attempt` 与 workspace 资源建立不可伪造的 scope 关系。；对每个路径进行 canonicalization、ownership、containment 和 sensitivity 判定。；能处理符号链接、junction、reparse point、挂载点、大小写语义和相对路径差异。；对文件、目录、仓库、branch、生成目录和 vendor 目录提供共享/独占锁。；将用户已有修改视为受保护输入，不覆盖 `user` 或 `unknown` 变更。；为 shell、构建、测试、MCP、LSP、plugin、hook 和 env loader 选择声明式 Sandbox Profile。；隔离临时目录、Artifact、缓存、事件、日志、credential 和 provider egress。；让 subagent 只拥有显式授予的工作区视图、文件范围和资源锁。；让 cleanup、retention、crash recovery、orphan reaper 和审计都可以恢复、解释和测试。；支持本地 native host，不能把 Linux-only 的路径或 mount 假设硬编码为通用安全边界。
### 非目标
本文不负责：
- 实现 provider SDK、模型协议或 Agent Kernel 的模型循环。；通过 Prompt 文本保证模型不会读取 workspace 外文件。；把 Git branch 当作完整的 OS 隔离或租户隔离。；通过 `cwd`、目录命名或不可猜 URL 替代 Policy、Sandbox 和 ownership 检查。；自动覆盖用户未提交修改，或把 `git reset`、`clean`、`rebase` 当普通工具。；承诺所有外部副作用都能通过 patch 或 snapshot 撤销。；让项目配置、MCP 描述、工具结果或 artifact 内容自行授予执行权限。；取代 ArtifactStore、SessionRepository、PolicyEngine 或 SubagentSupervisor。
### 质量公式
```text
Workspace Safety = Identity Correctness × Canonical Path Correctness × Containment Enforcement × Mount/Sandbox Strength × Ownership and Lock Discipline × Recovery and Cleanup
```
任一乘项接近零，workspace 名义上的“隔离”都可能被绕过。
## 核心判断与术语
### Workspace 不是目录字符串
`Workspace` 是带有 tenant、owner、canonical root、trust、repository identity、retention 和执行边界的资源容器。路径只是它的一个定位输入。
### Project 与 Repository 的区别
- `workspace`：允许访问的文件和运行资源边界。；`project`：模型默认值、规则、skills、hooks、MCP/LSP、插件和配置的边界。；`repository`：VCS 身份、远程引用、HEAD、branch、tree hash 和工作树事实。；`session`：长期 transcript、branch、memory view、artifact 引用和 delivery 状态。；`run`：一次可取消、可恢复、预算受限的实际执行。；`worktree`：repository 的一个物理或逻辑工作树视图，不等同于 branch 安全边界。；`baseline`：写入前的 tree、index、工作树和用户修改快照。；`workspace view`：授予某个 run 或 child 的只读/读写路径投影。
### 三个必须分开的问题
```text
模型看得到哪些资源？       Context/Prompt/egress 模型能提出哪些动作？       Tool visibility/Call Policy 动作实际能影响哪些资源？   Sandbox/mount/process/filesystem enforcement
```
## 职责边界
| 模块 | 负责 | 不负责 | |---|---|---| | `WorkspaceResolver` | 入口路径、workspace/project/repository 身份和 scope 解析 | 修改文件 | | `CanonicalPathService` | 绝对化、规范化、真实路径和大小写语义 | 代替 Policy 授权 | | `ContainmentGuard` | root、路径、资源和 mount 的包含关系 | 执行工具 | | `RepositoryResolver` | VCS、branch、HEAD、worktree、remote 和 baseline | 选择模型 | | `WorkspaceState` | 文件 hash、owner、用户变更、Agent 变更和锁 | provider stream | | `SnapshotStore` | 变更前后资源快照、tree hash 和 patch 引用 | 撤销外部业务动作 | | `LockManager` | 文件、目录、repo、branch、workspace 资源锁 | 三方合并决策 | | `SandboxBackend` | mount、进程、网络、资源和 secret 强制边界 | 业务授权 | | `ProjectTrustGate` | project-local 可执行资源的信任状态 | 判断任意代码是否正确 | | `PolicyEngine` | visibility、call、approval、execution、egress 决策 | 生成 shell 命令 | | `ToolRuntime` | 工具 schema、调度、幂等、结果和执行 receipt | 自行扩大 path scope | | `SubagentSupervisor` | child run、ownership、能力交集、结果合并 | 默认共享可变 workspace | | `ArtifactStore` | 大输出、diff、日志、snapshot、TTL 和引用授权 | 修改 transcript | | `SessionRepository` | session/run/entry/checkpoint 的 durable 事实 | 物理文件隔离 | | `Harness` | 装配、监督、取消、恢复、预算和事件路由 | 变成 God Object |
强制关系：
```text
Prompt explains workspace rules. Context selects allowed code and evidence. Tool schema constrains path shape. Policy authorizes canonical resources. Sandbox/mount enforces effects. State records actual changes. Harness supervises recovery and delivery.
```
## 威胁模型与隔离目标
### 不可信输入
以下内容一律按不可信输入处理：
- Host 传入的 cwd、workspaceId、projectId、repositoryId 和 sessionId。；模型生成的 path、glob、URL、命令、环境变量名和资源 ID。；workspace 内的 `AGENTS.md`、`CLAUDE.md`、脚本、配置、注释、测试输出和生成代码。；MCP/LSP server 的工具描述、schema、启动参数和返回内容。；plugin、hook、`.envrc`、shell profile、package script 和 project-local executable。；symlink、junction、mount point、reparse point 和压缩包中的路径。；remote worker、provider metadata、cache、artifact URL 和恢复请求。
### 需要保护的资产
- workspace 外的主机文件、其他 repository、用户 home、SSH key、credential 和进程。；不同 tenant、user、workspace、project、session、run、subagent 的文件、artifact、cache、trace 和 memory。；用户已有修改、baseline、branch、生成源和 vendor 的完整性。；审批内容、policy snapshot、sandbox attestation、side-effect receipt 和删除证明。
### 主要攻击路径
- `../`、编码分隔符、大小写、UNC、设备路径和 alternate data stream 绕过 containment。；symlink 或 junction 在检查后被替换，导致 TOCTOU 越界。；访问 workspace 内 link 指向 workspace 外，或 mount 将外部卷映射到允许目录。；child run 继承父的绝对路径、secret、锁或可变对象引用。；插件/MCP/LSP 在未 trust 时执行，或通过 env hook 获得宿主 credential。；共享 `/tmp`、artifact bucket、provider cache、日志和编译缓存造成串线。；cleanup 删除用户文件、其他 run 的临时目录或仍被引用的 artifact。；sandbox 失败后静默回退到 host shell，或 attestation 与实际 mount 不一致。
### 隔离目标
```text
identity isolation + path isolation + filesystem isolation + branch/change isolation + execution isolation + subagent isolation + temp/artifact/cache isolation + operational/lifecycle isolation
```
## 隔离层级与资源图
### 标准层级
```text
Tenant -> User -> Workspace -> Project -> Repository -> Worktree/Branch -> Session -> Run -> Turn/Attempt -> ToolExecution/Subagent
```
同一 repository 可以有多个 worktree；同一 workspace 可以包含多个 project；session 可以跨多个 run，但不能跨 workspace 静默迁移。
### Scope 不变量
1. `workspace.tenantId` 必须等于 `session.tenantId` 和 `run.tenantId`。 2. `session.workspaceId`、`run.workspaceId` 必须绑定到已解析的 workspace record。 3. `run.rootPath` 只能来自冻结的 `WorkspaceView`，不能来自模型参数。 4. child run 的 workspace 默认等于父 run 的 workspace，但 view、roots、locks 和 artifacts 必须取交集。 5. repository identity、branch identity、tree hash 和 canonical root 必须一起记录。 6. path lock key 使用 canonical path 或稳定 resource ID，不能使用用户输入字符串。 7. artifact、cache、event、log、temp 和 worker lease 必须带 scope namespace。
### 资源关系
```text
WorkspaceRecord
  ├─ ProjectRecord / TrustRecord
  ├─ RepositoryRecord / WorktreeRecord
  ├─ WorkspaceView[]
  ├─ TempNamespace / ArtifactScope / CacheNamespace
  ├─ LockNamespace
  └─ RetentionPolicy
SessionRecord
  ├─ workspaceId / projectId
  ├─ branchIds / checkpoints
  └─ durable semantic entries
RunRecord
  ├─ frozen WorkspaceView
  ├─ sandbox attestation
  ├─ owner and locks
  └─ childRunIds
```
## 总体架构与包布局
```text
Host Adapter
  -> Tenant/Identity Resolver
  -> Workspace Resolver
  -> Project Trust Gate
  -> Coding Harness / Run Supervisor
       ├─ Context/Prompt Compiler
       ├─ Repository/Baseline Service
       ├─ Tool Runtime
       ├─ Policy/Approval
       ├─ Sandbox/Mount Backend
       ├─ Lock Manager
       ├─ Session/State Repository
       ├─ Artifact/Temp/Cache Manager
       ├─ Subagent Supervisor
       └─ Event/Audit Router
            -> Agent Kernel
```
推荐包布局：
```text
packages/workspace/
  contracts.ts
  resolver.ts
  identity.ts
  canonical-path.ts
  containment.ts
  views.ts
  repository.ts
  baseline.ts
  ownership.ts
  locks.ts
  cleanup.ts
  trust.ts
  testkit/
packages/execution/
  mount-policy.ts
  sandbox-profile.ts
  attestation.ts
  native-host/
packages/coding-agent/
  snapshot.ts
  patch.ts
  change-classifier.ts
```
依赖方向：
```text
Host -> Harness -> Workspace/Policy ports Workspace adapters -> native filesystem/VCS/Sandbox Kernel -> ports only
```
## 核心数据模型
### 标识与版本
```typescript
type TenantId = string;
type WorkspaceId = string;
type ProjectId = string;
type RepositoryId = string;
type WorktreeId = string;
type SessionId = string;
type RunId = string;
type ChildRunId = string;
type SnapshotId = string;
type LockId = string;
type PathResourceId = string;
type WorkspaceViewId = string;
type ScopeVersion = number;
```
### Workspace 与 Project
```typescript
interface WorkspaceRecord {
  id: WorkspaceId;
  tenantId: TenantId;
  ownerId?: string;
  displayName?: string;
  inputRoot: string;
  canonicalRoot: string;
  rootIdentity: RootIdentity;
  projectIds: ProjectId[];
  repositoryIds: RepositoryId[];
  trust: ProjectTrustState;
  allowedMounts: FilesystemMount[];
  retention: RetentionPolicy;
  privacy: PrivacyPolicy;
  scopeVersion: ScopeVersion;
  createdAt: string;
  updatedAt: string;
}
interface ProjectRecord {
  id: ProjectId;
  workspaceId: WorkspaceId;
  tenantId: TenantId;
  configHash: string;
  ruleSources: ResourceSource[];
  extensionSources: ExtensionSource[];
  trust: ProjectTrustState;
  defaultMode?: CodingAgentMode;
  createdAt: string;
}
interface RootIdentity {
  canonicalPath: string;
  deviceOrVolume?: string;
  fileId?: string;
  casePolicy: "sensitive" | "insensitive" | "unknown";
  resolvedAt: string;
  resolutionVersion: string;
}
```
### Repository、Worktree 与 Baseline
```typescript
interface RepositoryRecord {
  id: RepositoryId;
  workspaceId: WorkspaceId;
  tenantId: TenantId;
  root: string;
  canonicalRoot: string;
  vcs: "git" | "none" | "other";
  remoteRefs: string[];
  contentHash: string;
  trust: ProjectTrustState;
  worktreeIds: WorktreeId[];
}
interface WorktreeRecord {
  id: WorktreeId;
  repositoryId: RepositoryId;
  workspaceId: WorkspaceId;
  canonicalRoot: string;
  branch?: BranchState;
  detached: boolean;
  managedBy: "user" | "agent" | "system";
  activeRunId?: RunId;
  createdAt: string;
}
interface BaselineRef {
  id: BaselineId;
  workspaceId: WorkspaceId;
  repositoryId?: RepositoryId;
  worktreeId?: WorktreeId;
  commit?: string;
  treeHash: string;
  indexHash?: string;
  files: SnapshotFileRef[];
  capturedAt: string;
}
```
### Workspace View
```typescript
interface WorkspaceView {
  id: WorkspaceViewId;
  workspaceId: WorkspaceId;
  tenantId: TenantId;
  owner: "user" | "run" | "subagent" | "system";
  ownerId: string;
  roots: ViewRoot[];
  readOnly: boolean;
  followSymlinks: "deny" | "within_roots" | "allow_trusted";
  allowedSpecialFiles: boolean;
  tempNamespace: string;
  artifactScope: ArtifactScope;
  cacheNamespace: string;
  policyVersion: string;
  viewHash: string;
  expiresAt?: string;
}
interface ViewRoot {
  canonicalRoot: string;
  access: "read" | "read_write";
  purpose: "source" | "generated" | "vendor" | "test_output" | "temp" | "artifact";
  allowMount: boolean;
}
```
### 变更、所有权和锁
```typescript
interface FileState {
  path: string;
  canonicalPath: string;
  resourceId: PathResourceId;
  contentHash?: string;
  baseHash?: string;
  size: number;
  status: "unchanged" | "added" | "modified" | "deleted" | "renamed" | "generated" | "vendor";
  owner: "user" | "agent" | "subagent" | "tool" | "generated" | "vendor" | "unknown";
  observedAt: string;
  sourceVersion: string;
}
interface LockRequest {
  ownerId: string;
  scope: ScopeRef;
  keys: string[];
  mode: "shared" | "exclusive";
  timeoutMs: number;
  leaseMs: number;
}
interface LockLease {
  id: LockId;
  ownerId: string;
  keys: string[];
  mode: "shared" | "exclusive";
  acquiredAt: string;
  expiresAt?: string;
  fenceToken: string;
}
```
### Mount、Temp、Cache 和 Cleanup
```typescript
interface FilesystemMount {
  source: string;
  target: string;
  mode: "ro" | "rw" | "tmpfs" | "bind";
  canonicalSource: string;
  canonicalTarget: string;
  allowSymlinkEscape: boolean;
  ownerScope: ScopeRef;
}
interface TempNamespace {
  id: string;
  tenantId: TenantId;
  workspaceId: WorkspaceId;
  runId?: RunId;
  path: string;
  purpose: "command" | "build" | "test" | "plugin" | "mcp" | "lsp" | "artifact_staging";
  retention: RetentionPolicy;
  cleanupState: "active" | "pending" | "cleaned" | "quarantined";
}
interface CleanupLease {
  resourceType: "workspace" | "worktree" | "temp" | "artifact" | "cache" | "mount";
  resourceId: string;
  ownerId: string;
  expiresAt: string;
  fenceToken: string;
}
```
## TypeScript 接口
### Workspace Resolver
```typescript
interface WorkspaceResolver {
  resolve(input: WorkspaceResolveInput): Promise<WorkspaceResolution>;
  inspect(path: string): Promise<WorkspaceInspection>;
  revalidate(view: WorkspaceView): Promise<WorkspaceValidation>;
}
interface WorkspaceResolveInput {
  tenant: TenantContext;
  inputPath?: string;
  workspaceId?: WorkspaceId;
  projectId?: ProjectId;
  sessionId?: SessionId;
  mode: CodingAgentMode;
}
interface WorkspaceResolution {
  workspace: WorkspaceRecord;
  project?: ProjectRecord;
  repository?: RepositoryRecord;
  worktree?: WorktreeRecord;
  view: WorkspaceView;
  diagnostics: Diagnostic[];
}
```
### Canonical Path 与 Containment
```typescript
interface CanonicalPathService {
  canonicalize(input: string, base?: string, options?: CanonicalizeOptions): Promise<CanonicalPath>;
  identity(path: string): Promise<RootIdentity>;
  compare(a: CanonicalPath, b: CanonicalPath): PathComparison;
}
interface CanonicalizeOptions {
  requireExists?: boolean;
  resolveFinalComponent?: boolean;
  rejectDevicePaths?: boolean;
  rejectAlternateDataStreams?: boolean;
  rejectSpecialFiles?: boolean;
}
interface CanonicalPath {
  input: string;
  absolute: string;
  canonical: string;
  existingPrefix?: string;
  segments: string[];
  rootIdentity: RootIdentity;
  symlinkChain: string[];
  junctionChain: string[];
  unresolvedFinalComponent?: string;
  hash: string;
}
interface ContainmentGuard {
  assertContained(root: CanonicalPath, target: CanonicalPath, mode: ContainmentMode): ContainmentReceipt;
  checkMounts(view: WorkspaceView, target: CanonicalPath): Promise<ContainmentReceipt>;
  resourceKey(path: CanonicalPath): string;
}
type ContainmentMode = "lexical" | "resolved" | "open_handle" | "mount_enforced";
interface ContainmentReceipt {
  allowed: boolean;
  rootHash: string;
  targetHash: string;
  resolvedTarget: string;
  reasonCode: string;
  checkedAt: string;
}
```
### Sandbox 与 Attestation
```typescript
interface WorkspaceSandbox {
  prepare(view: WorkspaceView, profile: SandboxProfile, context: SandboxContext): Promise<SandboxInstance>;
  attest(instance: SandboxInstance): Promise<SandboxAttestation>;
  execute(instance: SandboxInstance, command: CommandSpec, signal: AbortSignal): Promise<CommandResult>;
  dispose(instance: SandboxInstance): Promise<void>;
}
interface WorkspaceIsolationPolicy {
  rootMode: "host_path" | "bind_mount" | "container_mount" | "remote_view";
  minimumIsolation: SandboxProfile["isolationLevel"];
  denyWorkspaceParentReads: boolean;
  denyUnlistedMounts: boolean;
  defaultReadOnly: boolean;
  allowNetwork: boolean;
  allowProjectExecutables: boolean;
  tempIsolation: "per_run" | "per_workspace" | "shared_read_only";
}
```
### Ownership 与 Subagent
```typescript
interface OwnershipService {
  classify(view: WorkspaceView, baseline: BaselineRef): Promise<FileState[]>;
  assertWritable(path: CanonicalPath, ownerId: string): Promise<void>;
  transfer(input: OwnershipTransfer): Promise<OwnershipReceipt>;
}
interface OwnershipTransfer {
  resourceKeys: string[];
  from: string;
  to: string;
  reason: string;
  expectedHashes: Record<string, string>;
  policyVersion: string;
}
interface WorkspaceOwnershipGrant {
  parentRunId: RunId;
  childRunId: ChildRunId;
  viewId: WorkspaceViewId;
  resourceKeys: string[];
  access: "read" | "read_write";
  lockKeys: string[];
  artifactRefs: ArtifactRef[];
  expiresAt?: string;
  grantHash: string;
}
```
## Workspace/Project/Repository 解析
### 解析顺序
```text
authenticate principal -> resolve tenant membership -> resolve workspace/project IDs or inspect input path -> canonicalize input root -> locate repository/worktree metadata -> load safe non-executable metadata -> compute root and content identities -> resolve project trust -> create WorkspaceView -> freeze run configuration
```
### 输入路径规则
1. `workspaceId`、`projectId` 和 `sessionId` 不能由模型覆盖。 2. 传入路径必须经过 host identity、tenant ownership 和 canonicalization。 3. 若路径同时命中已有 workspace 和另一个 tenant 的记录，拒绝，而不是“就近选择”。 4. 不存在的目标文件可在已存在父目录上进行 canonicalization，但最终写入前必须重新检查。 5. repository root、workspace root 和 project root 分开记录；不能用 `git rev-parse` 结果代替 workspace root。 6. 非 Git workspace 需要显式记录 `vcs: "none"`，并降低 branch/revert 能力声明。 7. 如果 repository 位于 workspace 外，必须创建显式 `WorkspaceView`，不能仅凭“当前 cwd 在目录内”放行。 8. 解析失败、root identity 不稳定或访问权限不足时，返回 diagnostic 并 fail-closed。
### Repository Identity 校验
```text
input path -> canonical workspace root -> locate VCS metadata without executing hooks -> read HEAD/index/tree metadata -> compare repository identity with registry -> capture baseline -> publish workspace.resolved
```
`RepositoryIdentity` 必须包含 root、VCS、HEAD、branch、upstream、dirty 状态、tree hash 和 trust 事实。远程 URL 只是 provenance，不是本地 ownership 证明。
## Root Canonicalization
### 两阶段 canonicalization
1. **词法阶段**：解析相对路径、盘符、UNC、分隔符、`.`、`..` 和输入编码。 2. **实体阶段**：对已存在前缀解析真实路径、文件 ID、卷标识、symlink/junction/reparse chain 和大小写语义。
目标不存在时不能假设最终路径实体已固定；只可固定其已存在父目录和不变的创建约束。
### Canonicalization 不变量
- 所有允许路径都保存 `input`、`absolute`、`canonical`、`rootIdentity` 和 hash。；比较路径时使用平台语义，不用简单字符串前缀。；`C:\repo` 与 `c:/REPO` 是否相同由卷和文件系统事实决定，不能由配置猜测。；解析后的 root identity 若发生变化，已有 view 立即失效。；设备路径、命名管道、特殊文件、alternate data stream 和不可解析 reparse point 默认拒绝。；规范化结果不能被模型、项目文件或工具参数重新覆盖。
### 接口不变量
`canonicalize` 只负责事实解析；`ContainmentGuard` 负责授权边界；`SandboxBackend` 负责最终执行约束。三者不能合并成一个“安全路径工具”而缺少独立 receipt。
## Path Containment
### 判断顺序
```text
parse path -> canonicalize existing prefix -> resolve links/reparse points according to profile -> compare root identity -> compare segment boundary -> check mount table -> check ownership/sensitivity -> issue containment receipt
```
### 允许条件
目标必须满足：
- 与允许 root 具有相同 root identity，或被显式授予的 mount 映射覆盖。；在 segment 边界上位于 root 内，不能用 `repo2` 匹配 `repo`。；没有穿越未声明 symlink、junction、mount、device 或特殊文件。；resource owner、tenant、workspace 和 run scope 与当前 view 相容。；读写模式、文件类型、大小和操作 effect 满足 Policy obligation。
### 禁止的简化
```text
startsWith(root)       // 错误：前缀碰撞和大小写问题 path.join(root, input) // 错误：不处理 link、device 和目标替换 cwd === root           // 错误：cwd 不限制子进程后续访问
```
### Path Resource Key
```typescript
function resourceKey(path: CanonicalPath): string { return `path:${path.rootIdentity.fileId ?? path.rootIdentity.canonicalPath}:${path.canonical}`; }
```
锁、audit、ownership 和 approval 都引用 resource key；模型可见路径是展示字段，不是安全身份。
## Symlink、Junction 与 Reparse Point
### 默认策略
- `read-only-workspace`：允许读取 link 本身；跟随 link 必须仍在 view roots 内。；`write-workspace-no-network`：只允许已解析目标在同一 workspace root 内的 link。；`build-with-package-network`：mount 和 reparse 仍需 attestation，不因网络 profile 放宽。；未信任项目：不执行会创建、替换或解析未知 link 的 project-local hook。
### 检查与执行
```text
lstat/open metadata -> record link/reparse identity -> resolve target under policy -> containment check -> acquire canonical resource lock -> open with no-follow or verified handle -> revalidate identity immediately before effect
```
若平台无法安全表达 no-follow 或 handle-relative 操作，写操作应转移到更强 Sandbox Backend，不能静默使用宿主路径。
### Link 变化
写入过程中若 link chain、目标 file ID、volume identity 或 parent directory version 变化：
1. 中止写入或标记 `unknown`； 2. 写入 `workspace.path_changed` 和 diagnostic； 3. 释放新资源锁； 4. 重新 canonicalize 和重新审批； 5. 不把结果归因给原来的 path。
## Filesystem Mount 与 Sandbox Profile
### Mount 原则
Filesystem mount 是 enforcement，不是展示。每个挂载必须声明 source、target、mode、owner scope、symlink 规则和 cleanup 责任。
```text
workspace source -> /workspace:ro/rw run temp        -> /tmp/run:rw artifact staging-> /artifacts:rw cache           -> /cache:rw or isolated secrets         -> broker handle only host home       -> not mounted
```
### Profile 组合
```text
organization safety floor + workspace policy + tool obligation + run mode + host capability -> strictest compatible SandboxProfile
```
最低建议：
| 模式 | 源码 | temp | 网络 | project executable | sandbox | |---|---|---|---|---|---| | `offline` | ro | run-local | deny | deny | local/isolated | | `read_only` | ro | run-local | policy | deny | os/container | | `plan` | ro | plan artifact | policy | deny | isolated | | `implementation` | scoped rw | run-local | policy | trust gate | container/remote | | `review` | ro | run-local | policy | deny | isolated |
`write-workspace` 不是 unrestricted host write；仍需 mount、lock、ownership 和 post-write verification。
### Attestation 要求
```typescript
interface WorkspaceAttestation {
  viewHash: string;
  profileHash: string;
  mounts: FilesystemMount[];
  networkDenied: boolean;
  processBoundary: string;
  tempNamespace: string;
  secretBindings: string[];
  degradations: SandboxDegradation[];
  observedAt: string;
}
```
attestation 缺失、view hash 不匹配、未声明 mount 出现或 profile 发生降级时，高风险动作不得开始。
## Branch、Worktree 与 Baseline
### Branch 不是隔离边界
branch 只表达版本线；它不能阻止同一宿主路径上的并发写入，不能隐藏用户 dirty changes，也不能隔离进程、secret、temp 或 artifact。
### Worktree 策略
- read-only/review 默认复用已有 worktree 的只读 view。；implementation 若 policy 要求，可创建 run-owned worktree，并将其与 `runId`、baseline 和 cleanup lease 绑定。；同一 repository 的 branch/commit/worktree 操作使用 repo 级独占锁。；worktree 删除前先验证 owner、lease、未完成 child、pending artifact 和用户变更。；detached HEAD、无 VCS 和共享 worktree 都必须在 `WorkspaceState` 中显式标记。
### Baseline 捕获
第一次写操作前保存：
```text
canonical workspace root repository/worktree/branch/HEAD index and working tree status per-file hash and mode user/unknown/generated/vendor changes repo map hash policy/sandbox/toolset/config snapshots
```
baseline 不能只保存 commit；dirty working tree 是同等重要的输入。
## User/Agent/Generated/Vendor 变更所有权
### 分类顺序
```text
capture baseline -> compare current tree/index/worktree -> classify existing changes as user/unknown/generated/vendor -> reserve agent target paths -> apply minimal patch -> re-read and classify resulting changes
```
### 规则
- baseline 前已存在且非生成流程产生的差异默认为 `user` 或 `unknown`。；Agent 只能声明自己创建、持锁、基于 expected hash 应用的差异。；generated output 应追溯到 source、generator version 和 input hash。；vendor 变更必须保留 provenance、版本、许可证和上游 patch 证据。；用户在运行中修改目标文件时进入 conflict，不静默覆盖。；`git clean`、全量格式化、生成器覆盖和 vendor sync 必须独立审批。
### Change Receipt
```typescript
interface ChangeReceipt { changeId: string; owner: "agent" | "subagent" | "user" | "generated" | "vendor" | "unknown"; paths: FileState[]; baseSnapshotId: SnapshotId; patchRef?: PatchRef; lockIds: LockId[]; verification: VerificationReport[]; createdAt: string; }
```
## File Lock 与并发协调
### 锁层级
```text
workspace:<id> repo:<repository-id> worktree:<worktree-id> branch:<repository-id>#<branch> directory:<canonical-path> file:<resource-key> generated-root:<canonical-path> vendor-root:<canonical-path>
```
### 规则
1. 独立只读可并行。 2. 同一文件写入使用 exclusive。 3. 目录级生成器使用 directory 或 generated-root exclusive。 4. branch、commit、rebase、worktree 操作用 repo/worktree exclusive。 5. 多锁按稳定排序获取，避免死锁。 6. 不在持锁期间等待人工审批；审批前只持短期准备 lease。 7. 取消、crash、lease expiry 必须释放或隔离锁。 8. 锁 lease 过期后，旧执行器的 fence token 无权提交写入。 9. 完成顺序不等于模型 call ordinal；反馈仍按 call ID 和 ordinal 配对。
### 锁与 ownership
锁证明“当前有权尝试访问”，不证明目标仍未改变。执行前仍要检查 expected hash、root identity、policy snapshot 和 view hash。
## Temp、Artifact 与 Cache 隔离
### Namespace
```text
temp://tenant/<tenant>/workspace/<workspace>/run/<run>/... artifact://tenant/<tenant>/workspace/<workspace>/session/<session>/... cache://tenant/<tenant>/workspace/<workspace>/project/<project>/<key>
```
真实后端可以哈希分区，但逻辑 ref 必须保留 owner、scope、sensitivity、retention 和 policy version。
### Temp 规则
- 每个 run 默认独立 temp namespace；child 默认独立子命名空间。；不把系统共享 temp 目录当作隔离边界。；temp 中的 secret、socket、日志和构建产物按敏感度处理。；命令结束后先 quarantine，再扫描引用和 lease，最后删除。；cleanup 失败的 temp 不得被下一个 run 复用；标记 orphan 并进入 reaper。
### Artifact 规则
- 大日志、diff、snapshot、测试报告和二进制写入 ArtifactStore。；ArtifactRef 的 scope 不能因 path 参数而升级。；provider 只能获得 egress policy 允许的 view；模型不得直接访问本地 path。；删除 workspace 不立即删除仍被 durable session、audit 或 retention 保护的 artifact。
### Cache 规则
cache key 至少包含 tenant、workspace/project scope、resource hash、policy/toolset hash、model/deployment 和 redaction profile。 跨 workspace 共享代码缓存必须证明内容不含 secret、artifact owner 不变且策略允许；默认采用 workspace scoped cache。
## Subagent Ownership
### 默认模型
```text
parent run owns workspace view -> child receives a narrowed view -> child receives explicit resource/lock grant -> child publishes patch/artifact/finding -> parent validates and merges
```
child 不默认继承：
- 父 transcript、全部 memory、全部 artifact；；父的绝对路径、host env、secret binding；；父持有的独占锁；；父的 approval grant；；父的可写 workspace 全部根目录。
### Child 写入规则
- 多个 child 默认使用独立 worktree 或独立 output root。；若必须共享目录，父先按 path 划分 owner 并授予锁；未声明路径写入直接拒绝。；child 结果必须是 schema 化 `ChildResult`，带 patch、artifact、evidence、changed paths 和 side-effect summary。；parent fan-in 前验证 base hash、patch applicability、ownership transfer 和测试证据。；child 失败、取消或 unknown outcome 不得自动把其所有变更标成 parent agent 变更。
## Project Trust 与扩展加载
### Trust 的语义
Project Trust 只决定项目是否可以提供会改变 Agent 行为或执行代码的资源。它不等于 sandbox 已启用，也不等于每个命令安全。
```typescript
type ProjectTrustState = | { state: "unknown" } | { state: "untrusted"; reason?: string } | { state: "trusted"; rootHash: string; grantedBy: PrincipalRef; expiresAt?: string } | { state: "revoked"; reason: string };
```
### 两阶段 Bootstrap
```text
Safe phase
  built-ins
  tenant/user config
  non-executable metadata
  source inspection
  trust explanation
Trusted phase
  project rules with authority
  plugins/hooks
  MCP/LSP commands
  env loaders
  workspace-defined tools
```
root 移动、关键配置 hash 变化、owner 变化、policy 变化或 trust expiry 时重新确认；信任状态变化会使 context/toolset/cache/view 失效。
## MCP/LSP/Plugin/Env Hook 边界
### 统一注册事实
每个扩展贡献必须带：
```typescript
interface ExtensionBinding {
  extensionId: string;
  source: ResourceSource;
  workspaceId: WorkspaceId;
  projectId?: ProjectId;
  trust: ProjectTrustState;
  command?: CommandSpec;
  toolStableIds: string[];
  sandboxProfile: SandboxProfile;
  networkPolicy: NetworkPolicy;
  envRefs: string[];
  registrationVersion: string;
}
```
### 加载规则
- 未 trust 时可读取元数据，但不可启动 MCP/LSP、plugin、hook 或 env loader。；注册使用 transaction；部分失败要反向 dispose 并恢复旧 toolset snapshot。；扩展进程不应拥有父 run 的完整环境；只注入最小 env 和 broker handle。；MCP/LSP server 的 schema、返回值和“管理员批准”声明都不具备 policy authority。；hook 执行前仍需 Tool/Policy/Sandbox；hook 不能修改 policy snapshot 或 approval record。；project-local package script 视为 executable extension，不因“测试命令”名称降低风险。
## 策略决策流程
### 五层决策
```text
candidate workspace resources -> visibility: model/context 是否看得到 -> canonicalization/validation -> call policy: 具体 path/action 是否可提出 -> approval: 是否需要人类确认 -> execution policy: 选择 profile/mount/backend -> attestation -> execute -> result/artifact egress
```
### Path Action
```typescript
interface WorkspaceActionRequest {
  actionId: string;
  principal: PrincipalRef;
  workspaceId: WorkspaceId;
  projectId?: ProjectId;
  repositoryId?: RepositoryId;
  runId: RunId;
  effect: EffectClass;
  paths: CanonicalPath[];
  expectedHashes?: Record<string, string>;
  operation: "read" | "write" | "delete" | "rename" | "execute" | "mount";
  viewHash: string;
  provenance: ActionProvenance;
}
```
### 决策要点
- canonical action 的 root、resource key、owner 和 target hash 必须稳定。；workspace 规则只能收紧安全边界，不能放宽 tenant safety floor。；transform 修改路径或 mount 后回到 canonicalization、validation 和 risk classification。；approval 绑定 action hash、view hash、policy version、profile hash 和 expiry。；host 不支持 approval 时，高风险动作 fail-closed。
## Workspace 生命周期与状态机
```text
Unknown -> Resolving -> Canonicalized -> OwnershipVerified -> TrustPending | Trusted -> ViewCreated -> Active -> Quiescing -> Cleaning -> Retained | Deleted | Quarantined
```
### 转移规则
| 当前 | 事件 | 下一状态 | durable 要求 | |---|---|---|---| | Resolving | root resolved | Canonicalized | workspace.resolved | | Canonicalized | owner verified | OwnershipVerified | ownership snapshot | | OwnershipVerified | trust unknown | TrustPending | trust request | | TrustPending | approved | Trusted | trust entry | | Trusted | view created | ViewCreated | view hash | | ViewCreated | run opened | Active | run/workspace link | | Active | no active runs | Quiescing | cleanup requested | | Cleaning | refs clear | Retained/Deleted | cleanup receipt | | any active | identity changed | Quarantined | security audit |
workspace 进入 Quarantined 后不得创建新写 run；read-only forensic view 可以由运维显式创建。
## Run 生命周期与状态机
```text
Created
  -> PreparingWorkspace
  -> BaselineCaptured
  -> SandboxPrepared
  -> Running
  -> WaitingForApproval | WaitingForLock
  -> Executing
  -> Verifying
  -> Checkpointing
  -> Completed
  -> Settling
  -> Cleaned
```
任意活动状态都可进入 `Cancelled`、`Failed`、`Recovering` 或 `UnknownSideEffect`。terminal run 之后不得出现新的 workspace 业务写事件；cleanup 和审计作为 settlement 子流程记录。
## 与 Context/Prompt/Tool/State/Policy/Harness 集成
### Context
`ContextResource` 记录 workspace、directory、branch、run scope、canonical path、hash、trust、authority、sensitivity 和 freshness。ContextCompiler 只把当前 view 内且 provider egress 允许的代码/规则加入 `ContextPlan`。
### Prompt
Prompt 解释：当前 workspace root 的展示名、允许的路径范围、read-only/implementation 模式、用户变更保护、tool result 的不可信属性和完成标准。Prompt 不实现 containment，也不接受模型提供的 root 覆盖。
### Tool
Tool schema 使用相对 workspace path 或稳定 resource ref；ToolValidator 将其转换为 canonical action。工具的 `cwd` 是执行投影，不是授权来源。shell 使用结构化 executable/args/cwd/envRefs/timeout/output budget。
### State
Session/Run durable entries 保存 workspaceId、viewHash、baseline、branch、toolset、policy、sandbox attestation、ownership、lock、patch、artifact 和 cleanup 状态。恢复时重新验证 membership、root identity、policy、view、lock fence 和 in-flight effect。
### Policy
Policy 输入使用 canonical action，不接收未解析 JSON 或自由文本路径。visibility、call、approval、execution、egress 分层输出；transform 后必须重新校验。
### Harness
Harness Bootstrap 先解析 tenant/workspace/trust，再装配 registry、Context/Prompt、Sandbox、Lock、Session、Artifact 和 Event。Run Supervisor 将所有 model stream、tool、subagent、approval、cleanup 归入 RunScope 的 structured concurrency。
### Event/Artifact
关键事件包括 `workspace.resolved`、`workspace.view.created`、`baseline.captured`、`sandbox.attested`、`lock.acquired`、`path.revalidated`、`change.applied`、`ownership.transferred`、`cleanup.completed` 和 `workspace.quarantined`。大 diff、日志、snapshot 和 forensic bundle 使用 ArtifactRef，不把宿主路径写进低信任日志。
## 一次写操作的端到端流程
```text
model ToolCallReady
  -> parse relative path
  -> resolve against frozen view root
  -> canonicalize and resolve links
  -> assert tenant/workspace containment
  -> compare expected hash and baseline
  -> classify user/agent ownership
  -> evaluate call policy and risk
  -> request narrow approval if needed
  -> acquire locks in stable order
  -> prepare sandbox/mount
  -> attest profile and view
  -> revalidate action hash
  -> apply patch or execute structured command
  -> read-back hash/diff
  -> record ChangeReceipt and ArtifactRef
  -> commit ToolResult/State Entry
  -> update ContextPlan and checkpoint
  -> release lock and settle temp
```
模型声称“已经修改完成”不是事实；只有 read-back、diff、receipt 和 durable entry 才能证明。
## TOCTOU 与执行前复核
### Action Hash
```typescript
interface WorkspaceAuthorizationSnapshot {
  actionHash: string;
  viewHash: string;
  rootIdentityHash: string;
  targetIdentityHashes: Record<string, string>;
  baselineId: BaselineId;
  policyVersion: string;
  sandboxProfileHash: string;
  lockFenceTokens: string[];
  issuedAt: string;
  expiresAt?: string;
}
```
### 复核点
至少在以下时刻重算：
1. approval 创建前； 2. approval 返回后； 3. 获锁后； 4. sandbox attestation 后； 5. 打开目标文件/进程前； 6. 执行完成 read-back 前； 7. cleanup 删除前。
任何 root、link chain、file ID、hash、mount、policy、trust、membership 或 lock fence 变化都使 snapshot 失效。未知结果不得自动重试写操作。
## 故障恢复与未知结果
### 分类
- `not_started`：没有拿到 execution receipt，可安全重试前置准备。；`started_known_success`：有明确 receipt，可幂等查询或继续验证。；`started_known_failure`：副作用明确失败，保留日志和状态。；`unknown_outcome`：进程崩溃、远端断线或 ack 丢失，禁止盲目重放。；`identity_changed`：root/link/mount 改变，转入 quarantine。
### 恢复流程
```text
load last checkpoint -> verify workspace/root identity -> verify session/run owner and membership -> inspect locks and sandbox instances -> query in-flight tool receipts -> classify unknown effects -> restore read-only forensic view if needed -> resume only at durable boundary
```
父 run 取消时：停止新任务、传播 abort、等待子任务 settle、写 cancellation/unknown entry、释放锁、关闭 sandbox、保留必要 artifact。
## Cleanup、Retention 与孤儿资源
### Cleanup 顺序
```text
stop accepting work
  -> cancel descendants
  -> settle tools and deliveries
  -> flush durable events
  -> checkpoint
  -> close extension processes
  -> remove secret bindings
  -> unmount filesystem
  -> release locks
  -> quarantine temp/artifacts
  -> scan references
  -> delete eligible resources
  -> write cleanup receipt
```
必须先 unmount 再删除 mount source；必须先停止进程再删除其 cwd 或 temp；cleanup 失败则保留 quarantine，不重用路径。
### Retention
- session/transcript、audit、unknown outcome 和 deletion proof 由各自 retention class 决定。；run temp 默认 `until_task_end` 或短 TTL；forensic bundle 可由 incident policy 延长。；artifact 只有在无 durable 引用、无 legal/retention hold、无 pending recovery 时才能 GC。；worktree 删除前确认不是用户 worktree，且没有未交付 patch。；reaper 使用 cleanup lease 和 fence token，避免旧 worker 删除新 run 资源。
### Orphan Reaper
reaper 定期扫描 namespace、mount、process、lock、artifact staging、worker lease 和 event cursor；发现 owner 不存在或 lease 过期时先 quarantine，再执行安全回收，并记录审计。
## 安全与隐私
### 最小化原则
- 不把宿主绝对路径、用户名、home、环境变量值或 secret 放入模型上下文。；模型只看到展示路径、相对路径、必要 symbol/range 和 artifact ref。；日志、trace、event、artifact 和 error 分别执行 sensitivity/redaction。；`.env`、SSH、credential、token、浏览器 profile、系统目录和设备文件默认 deny。；provider egress 只发送允许的 summary/sanitized view；cache key 不跨 workspace 混用。
### Trust 与 Injection
workspace 内容、代码注释、测试输出和 MCP 返回值默认是 data/authority none。它们不能注册工具、修改 policy、创建 approval、选择 mount、绑定 secret 或改变 egress。
### 审批与高风险
删除、覆盖用户变更、安装依赖、执行项目脚本、发布、commit、push、部署、访问 secret 和跨 workspace 读取必须以具体 canonical action、material parameters、profile 和 expiry 为审批对象。
## Cross-workspace Attack 防护
### 入口防护
- 所有 API 使用服务器端 `TenantContext` 和 scope guard；不信任请求体中的 tenant/workspace。；session、artifact、memory、event、cache、queue、worker 和 local path 都要做 owner 复核。；workspace 选择不能因 path collision、symlink 或 cache hit 而自动跨 scope。
### 执行防护
- sandbox mount 只暴露当前 view；host home、其他 workspace 和共享 temp 不挂载。；remote worker lease 绑定 tenant、workspace、run、profile hash 和 worker identity。；plugin/MCP/LSP 使用 namespace、注册事务和显式 capability intersection。；child scope 取父能力、workspace view、policy、budget 和 egress 的交集。
### 事后检测
检测跨 workspace path、artifact ref、cache key、event stream、trace attribute、provider request、worker lease 和 cleanup 操作；发现一次越界即暂停相关 workspace 并生成 security incident。
## Windows/Native Host 注意事项
### 路径与卷
- 处理盘符大小写、UNC 路径、长路径前缀、混合分隔符、相对 drive current directory 和设备路径。；使用 volume/file identity 辅助路径字符串比较；不要假设所有卷大小写敏感或全部不敏感。；junction、mount point 和 reparse point 可能改变真实目标；必须记录解析链和 policy 结果。；默认拒绝 `\\.\`、`\\?\GLOBALROOT`、设备命名空间、命名管道和 alternate data stream，除非专用 backend 明确支持。
### 进程与环境
- 不使用 shell 字符串拼接；使用结构化 argv，明确 executable、cwd、envRefs 和 inherited handles。；环境变量、用户 profile、自动加载脚本和注册表相关配置不能作为隐式 project trust。；native host 不能假设 `chmod`、Unix mount、`/proc`、`/tmp` 或 `flock` 语义存在；LockManager 和 SandboxBackend 应提供平台实现。；进程终止、job object、句柄关闭和 cleanup 需要记录实际状态；终止失败不能伪造已清理。
### 测试要求
Windows native、container/remote Linux 和无 VCS workspace 都必须有独立 conformance；平台差异进入 `EnvironmentSnapshot`，不能用开发机隐式行为作为断言。
## 可观测性与审计
### 关键指标
```text
workspace.resolve.success/failure
canonicalization.reject.count
containment.reject.count
symlink/junction escape attempts
mount.attestation.failure
sandbox.degradation.count
user-change.conflict.count
lock.wait/timeout/deadlock
cross-workspace invariant violation
orphan temp/mount/process count
cleanup latency/failure
unknown outcome count
```
### Trace 关系
```text
host request -> workspace.resolve -> trust.resolve -> baseline.capture -> sandbox.prepare/attest -> tool.execution -> change.verify -> artifact.put -> session.append -> cleanup
```
事件必须带 tenant、workspace、project、repository、worktree、session、run、childRun、viewHash、rootIdentityHash、policyVersion 和 sensitivity；不要把完整 secret 或原始模型 prompt 放入 trace。
### Audit 最小事实
- 谁在什么 scope 对什么 canonical resource 做了什么 operation。；使用了哪个 view、baseline、policy、approval、sandbox profile 和 attestation。；target hash、link/mount identity、lock fence、结果和 cleanup receipt。；任何 deny、transform、quarantine、cross-workspace attempt、unknown outcome 和 deletion。
## 测试策略与测试矩阵
### 分层
1. **Unit**：路径解析、segment boundary、大小写、hash、scope intersection、lock ordering、retention。 2. **Component**：Resolver、ContainmentGuard、Snapshot、Ownership、Sandbox adapter、Cleanup、Artifact namespace。 3. **Integration**：真实 Harness + fake provider + fake tools + session/event/artifact stores。 4. **Scenario**：模型提出越界 path、审批后 link 替换、用户并发修改、child fan-out、crash recovery。 5. **Platform conformance**：Windows native、容器、远程 worker、无 Git、网络禁用。 6. **Security regression**：cross-workspace、secret egress、MCP injection、junction escape、cache collision。
### 测试矩阵
| 维度 | 正常 | 边界 | 拒绝/恢复 | |---|---|---|---| | path | 子文件 | 不存在目标/长路径 | `..`、编码、device path | | root | 单 workspace | 多 repository/worktree | root identity 改变 | | link | workspace 内 symlink | 深层 link | 外链、junction、reparse | | mount | ro source | rw temp | 未声明 mount/attestation 失败 | | branch | clean branch | dirty user change | concurrent checkout/rebase | | ownership | agent 新文件 | generated/vendor | user/unknown 覆盖冲突 | | lock | 共享读 | 多路径写 | timeout、死锁、fence 过期 | | subagent | 独立 view | patch merge | 越权写父目录 | | trust | trusted | expiry/revoke | 未 trust 执行 hook/MCP | | cleanup | 正常退出 | 延迟删除 | crash、孤儿 mount/process | | platform | native Windows | case/UNC | device path/ADS | | tenant | 同租户分离 | cache reuse | cross-workspace ref/worker |
### Oracle
断言以文件 hash、tree hash、mount/attestation、side-effect ledger、durable event、artifact ref 和实际进程/网络事实为准；不以模型最终文本声称为准。
## 反模式
1. **只设置 cwd**：cwd 不限制绝对路径、子进程、环境、挂载和 link。 2. **字符串 startsWith containment**：没有 segment、root identity 和 link 语义。 3. **branch 即沙箱**：branch 不能隔离主机和用户 dirty changes。 4. **共享 temp/cache**：缺少 tenant/workspace/run namespace，容易串线和泄密。 5. **全量继承父 workspace 给 child**：把 parent capability 当成 child authorization。 6. **trust 作为万能批准**：project trust 不代表命令、secret 或生产动作安全。 7. **检查后再直接打开路径**：未处理 TOCTOU、link 替换和 mount 变化。 8. **锁只用用户输入路径**：大小写、link 和别名可造成同资源多把锁。 9. **cleanup 直接 rm -rf**：可能删除用户文件、其他 run 或仍被引用 artifact。 10. **sandbox 失败静默降级**：把安全 profile 变成 host execution。 11. **把 artifact URI 当权限**：不可猜并不等于授权；每次 get 都要 scope check。 12. **日志记录完整环境**：会泄露 secret、home、token 和路径。 13. **用最终文本证明修改完成**：没有 read-back、diff、receipt 和 durable state。 14. **跨 workspace 复用 provider prompt cache**：忽略 policy、sensitivity、toolset 和 owner。 15. **为测试维护另一条 runtime**：无法发现真实 Harness 中的隔离回归。
## 实施清单
### P0：不可绕过的安全边界
- [ ] 定义 Tenant/Workspace/Project/Repository/Session/Run scope 和 owner。；[ ] 实现 canonical path、root identity、segment containment 和 resource key。；[ ] 统一 Tool/Policy/Sandbox 的 canonical action 与 action hash。；[ ] 捕获 baseline，分类 user/unknown/generated/vendor 变更。；[ ] 为 shell、文件、命令、MCP/LSP/plugin 提供 fail-closed profile。；[ ] 实现 per-run temp、artifact、cache namespace。；[ ] 写入 workspace/view/baseline/sandbox/ownership/lock durable events。
### P1：并发与恢复
- [ ] 实现 canonical lock key、稳定获取顺序、lease、fence token 和 orphan reaper。；[ ] 支持 worktree、branch、snapshot、patch、revert 和用户冲突。；[ ] 设计 child view、ownership grant、patch merge 和 approval 不继承规则。；[ ] 实现 TOCTOU 复核、unknown outcome、checkpoint 和 forensic view。；[ ] 完成 Windows/native、container、remote worker conformance。
### P2：治理与运营
- [ ] 建立 cleanup/retention/deletion/hold/audit 规则。；[ ] 建立 cross-workspace invariant、越界尝试和 mount degradation 告警。；[ ] 将 workspace safety scenario 纳入 Evaluation CI gates。；[ ] 输出 operator diagnostic snapshot，不泄露原始 secret。；[ ] 为扩展 provenance、trust expiry、policy/schema migration 建立回滚路径。
### Definition of Done
- 没有只依赖 cwd、branch 或 prompt 的隔离断言。；每个写操作都有 canonical path、ownership、policy、sandbox、lock、read-back 和 durable receipt。；crash、link 替换、用户并发修改、cleanup 失败和跨 workspace 请求都有可测试结果。；Windows/native host 与 Linux/container 的差异有明确 capability 和测试矩阵。
## 五个参考项目的启发来源
### Pi
- headless kernel、session tree、compaction 和 CLI/TUI/RPC 共用 runtime 说明 workspace 资源应由 Harness 绑定，而不是塞入 Kernel。；它的执行隔离较弱，提醒实现不能把“可恢复 session”误当作 OS 文件隔离。
### Grok Build
- actor/调度、permission decision、folder trust、sandbox 和路径锁说明 path authorization、trust 和 execution 是三层不同问题。；同一路径写入串行化可直接映射到 canonical resource lock；同时要防止 fail-open 的沙箱降级。
### OpenCode
- client/server、session/message/part、snapshot/patch/revert、MCP/LSP 和 durable event/projector 说明 workspace 变更必须可投影、可回放和可审查。；新旧状态模型并存时，需要显式 schema/version 与 migration，不能只信磁盘当前状态。
### Claude Code
- permissions、hooks、subagents、skills、memory 和 MCP 形成完整 harness，启发 project trust、扩展 provenance 和 child capability intersection。；hooks 与插件仍应视为宿主代码或隔离进程代码，不能仅凭 prompt 约束。
### OpenClaw
- AgentHarness registry、agent-core、gateway、tool/sandbox/elevated 分层和事务化插件注册说明 workspace 执行能力应通过装配快照冻结。；多 channel/provider 组合会放大临时目录、artifact、credential 和 delivery 的隔离复杂度，必须使用统一 scope 和事件协议。
6. 非 Git workspace 需要显式记录 `vcs:
