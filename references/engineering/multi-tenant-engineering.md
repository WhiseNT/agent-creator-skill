# Multi-tenant Agent Engineering 细粒度工程设计
> 本文定义 Agent Harness 在多个 tenant、user、workspace、project、session、run 并发存在时的身份、隔离、配额、后台任务、数据生命周期和恢复边界。
>
> 依据仅来自当前目录已有的参考架构、Agent API 通用模式、Harness/Context/State/Permission/Subagent/Event/Evaluation 文档，以及五个参考项目的本地源码调研归纳；不把 README 当作规范，不新增网络调研结论。
## 目录
- [设计目标与非目标](#设计目标与非目标)；[多租户原则](#多租户原则)；[职责边界](#职责边界)
- [威胁模型与隔离目标](#威胁模型与隔离目标)；[Scope 层级](#scope-层级)；[核心身份数据模型](#核心身份数据模型)
- [TypeScript 接口](#typescript-接口)；[租户上下文装配](#租户上下文装配)；[Identity/Authn/Authz](#identityauthnauthz)
- [租户与用户授权](#租户与用户授权)；[Workspace/Project 隔离](#workspaceproject-隔离)；[Session/Run 隔离](#sessionrun-隔离)
- [配置隔离](#配置隔离)；[模型与 Provider 隔离](#模型与-provider-隔离)；[工具与插件隔离](#工具与插件隔离)
- [Memory 与 Context 隔离](#memory-与-context-隔离)；[Artifact 与文件隔离](#artifact-与文件隔离)；[Event/Trace/Audit 隔离](#eventtraceaudit-隔离)
- [数据模型与存储分区](#数据模型与存储分区)；[策略与决策流程](#策略与决策流程)；[配额、预算与 Rate Limit](#配额预算与-rate-limit)
- [Noisy Neighbor 防护](#noisy-neighbor-防护)；[Provider Egress 与数据驻留](#provider-egress-与数据驻留)；[Credential 与密钥](#credential-与密钥)
- [日志脱敏与隐私](#日志脱敏与隐私)；[后台任务与 Worker Lease](#后台任务与-worker-lease)；[缓存隔离](#缓存隔离)
- [加密与密钥轮换](#加密与密钥轮换)；[审计与合规事实](#审计与合规事实)；[生命周期、删除与导出](#生命周期删除与导出)
- [故障恢复](#故障恢复)；[Cross-tenant 防护](#cross-tenant-防护)；[与 Prompt/Context/Model/Tool/State/Policy/Harness 集成](#与-promptcontextmodeltoolstatepolicyharness-集成)
- [Subagent 与多租户](#subagent-与多租户)；[事件与可观测性](#事件与可观测性)；[生命周期与状态机](#生命周期与状态机)
- [安全与隐私检查](#安全与隐私检查)；[测试矩阵](#测试矩阵)；[反模式](#反模式)
- [实施清单](#实施清单)；[五个参考项目的启发来源](#五个参考项目的启发来源)
## 设计目标与非目标
### 目标
Multi-tenant Harness 必须：
- 明确 tenant、user、workspace、project、session、run 的 scope 和 owner。；在认证后生成不可伪造、不可由模型覆盖的 `TenantContext`。；将身份、授权、配置、模型、工具、插件、memory、artifact、event 和 trace 隔离。
- 为每个 tenant/user/workspace/project 提供可计算的配额、预算和 rate limit。；支持 provider egress、数据驻留、region/location 和敏感度策略。；将 secret 绑定到 tenant、principal、tool、destination、purpose 和 expiry。
- 防止跨租户查询、缓存命中、日志泄漏、artifact 引用和后台任务串线。；支持 worker lease、heartbeat、故障接管和 unknown side-effect 恢复。；防止 noisy neighbor 抢占 worker、provider quota、数据库连接和事件队列。
- 支持租户数据删除、导出、retention、加密和密钥轮换。；提供跨租户安全测试、故障注入、回放和审计能力。
### 非目标
本文不定义：
- 具体身份供应商、数据库产品或云厂商部署方式。；Provider adapter 内的租户策略实现。；仅依靠 prompt 约束租户隔离的方案。
- 仅依靠每条 SQL 手写 `where tenant_id = ...` 的方案。；把 trace 当作业务事实或授权来源。；把所有租户共享一个全局配置、缓存、工作目录或 secret。
- 用一个 `tenantId` 字符串替代完整的 identity/authz/scope 检查。
## 多租户原则
- 租户隔离是系统边界，不是 prompt 约束。；tenant context 必须由认证和服务器端路由生成。；Provider adapter 不能承载租户策略。
- Tenant isolation 不能只靠 prompt 或数据库 where 条件。；每个下游端口都必须接收已验证的 scope context。；默认 fail-closed；无法解析 tenant 或 owner 时拒绝。
- `visibility`、`authorization`、`execution isolation` 三者分离。；缓存、队列、worker、artifact、event、metric 都要有租户边界。；parent approval 不自动覆盖 child run。
- 不把 tenant ID 从模型参数、tool arguments 或文档内容读取。；所有租户维度的配额在动作前预检、事件后结算。；删除和导出是可审计、可恢复、可证明的生命周期动作。
### 为什么不能只靠 Prompt
Prompt 可能被：
- 模型忽略或误解。；workspace 文件、RAG、邮件和工具结果注入。；子 Agent、后台 worker 或 webhook 绕过。
- provider context cache、artifact URL 或日志泄漏。；多客户端 API 直接调用路径绕过。
Prompt 可以解释“只能使用当前 workspace”，但真正的 tenant/resource ownership 必须由 Policy、State、ArtifactStore、Queue、Worker、Provider Egress 和 Sandbox 强制。
### 为什么不能只靠数据库 where
单纯 where 条件无法覆盖：
- 缓存 key 缺少 tenant。；artifact URI 可猜测或授权后未复核。；worker lease 把任务交给错误租户。
- provider prompt cache 或 external egress 混租。；trace/log sink 在数据库之外。；文件系统、临时目录、子进程和网络连接。
- 删除/导出任务读取了已失效的授权快照。
正确方案是“入口身份 + scope-aware ports + 存储强制分区 + policy + execution boundary + audit”组合。
## 职责边界
### Multi-tenant Runtime 负责
- 解析和冻结 `TenantContext`。；维护 tenant/user/workspace/project/session/run scope。；identity/authn/authz 交接和 principal 映射。
- 配置、模型、工具、插件、memory、artifact、event 的隔离。；tenant-aware quota、budget、rate limit 和 fairness。；provider egress、region/data residency 和 credential routing。
- worker queue、lease、heartbeat、ownership recovery。；cache namespace、加密、key rotation、delete/export 和 audit。；cross-tenant invariant、故障恢复和安全测试。
### 不独自负责
- Provider 原始协议：由 Provider Runtime/Adapter 负责。；Prompt 文字和 Context 选取：由 Prompt/Context Runtime 负责。；工具 schema、调度和执行：由 Tool Runtime 负责。
- OS sandbox 和网络强制：由 Policy/Execution Backend 负责。；session semantic entries：由 State Harness 负责。；UI 审批和 delivery：由 Host Adapter 负责。
- 业务系统的最终资源 ownership：由领域服务查询并返回可信事实。
### 责任矩阵
| 问题 | 解释 | 强制 | 记录 |
|---|---|---|---|
| 模型看见什么 | Prompt/Context | Egress/Visibility | Context event |
| 模型能调用什么 | Tool visibility | Tool/Policy | Toolset snapshot |
| 当前动作是否允许 | Policy | Call/Approval | Policy entry |
| 能影响哪些资源 | Execution | Sandbox/backend | Attestation |
| 状态属于谁 | State | Repository scope | Entry/audit |
| 任务由谁执行 | Queue/Worker | Lease/ownership | Job event |
| 数据去了哪里 | Egress | Network/provider policy | Audit |
## 威胁模型与隔离目标
### 不可信输入
- 用户提交的 tenant、workspace、project、session、resource ID。；模型生成的 tenant/user/resource 参数。；workspace 配置、插件、hooks、MCP 描述和工具结果。
- RAG、网页、邮件、issue、日志和 artifact 内容。；Host 控制事件、恢复请求和 approval 回调。；provider metadata、remote worker 结果和第三方 webhook。
### 需要保护的资产
- 租户的 session/transcript、memory、artifact、文件和配置。；用户身份、组织成员关系和角色。；provider credential、secret、token 和 egress 记录。
- 配额、预算、计费和成本明细。；工具调用、审批、生产资源和外部业务动作。；审计日志、trace、诊断快照和删除/导出证明。
### 主要攻击路径
- 伪造 tenant ID 或 resource ID。；越权读取其他租户 session、artifact、memory。；cache key 缺少 tenant 导致内容串线。
- worker/queue 任务租户上下文丢失。；provider fallback 发送到不允许 region。；secret broker 给出过宽 credential。
- plugin/MCP 通过 child run 继承父租户全部权限。；日志、trace、error、artifact URL 泄露敏感内容。；删除/导出任务使用旧授权或错误 scope。
- noisy neighbor 消耗共享 provider quota、DB pool 或 worker。
### 隔离目标
```text
visibility isolation
  + authorization isolation
  + state isolation
  + execution isolation
  + egress isolation
  + operational isolation
  + lifecycle isolation
```
## Scope 层级
### 标准层级
```text
Tenant
  -> User
    -> Workspace
      -> Project
        -> Session
          -> Run
            -> Turn
              -> Attempt
```
并行关系：
```text
Tenant
  -> Organization policy
  -> Quota/Budget
  -> Credential namespace
  -> Provider egress
  -> Artifact root
  -> Event partition
```
### Scope 语义
- `tenant`：计费、安全、数据和资源 ownership 的最高业务边界。；`user`：发起请求、审批和个人配置的主体。；`workspace`：代码、文件、项目规则和信任边界。
- `project`：业务配置、工具集、插件和模型默认值容器。；`session`：长期 transcript、branch、memory view 和 delivery 状态。；`run`：一次可取消、可恢复、预算受限的执行。
- `turn`：一次采样及工具批次。；`attempt`：具体 provider/model/deployment 的采样尝试。
### Scope 继承
```text
tenant policy
  > user/workspace/project defaults
  > session policy
  > run override
```
低层只能收紧或在允许范围内细化，不能突破 tenant safety floor、data residency、配额和 provider allowlist。
### Scope 不变量
- 所有 ID 不得跨 tenant 复用或解释。；child run 的 tenant 必须等于 parent，除非显式跨租户委派且有专门 policy。；session、artifact、event、memory、queue job 的 owner scope 必须可验证。
- tenant context 在 run 内冻结；变更创建新 run 或显式 change entry。
## 核心身份数据模型
### PrincipalRef
```typescript
interface PrincipalRef {
  kind: "user" | "service" | "agent" | "worker" | "extension";
  id: string;
  issuer?: string;
  tenantId: string;
  authnSessionId?: string;
}
```
### TenantContext
```typescript
interface TenantContext {
  tenantId: string;
  organizationId?: string;
  principal: PrincipalRef;
  roles: string[];
  permissions: string[];
  userId?: string;
  workspaceId?: string;
  projectId?: string;
  sessionId?: string;
  runId?: string;
  policyVersion: string;
  issuedAt: string;
  expiresAt?: string;
  contextHash: string;
}
```
### ScopeRef
```typescript
interface ScopeRef {
  tenantId: string;
  userId?: string;
  workspaceId?: string;
  projectId?: string;
  sessionId?: string;
  runId?: string;
  branchId?: string;
  scopeVersion: number;
}
```
### ResourceOwnership
```typescript
interface ResourceOwnership {
  resourceType: string;
  resourceId: string;
  tenantId: string;
  ownerKind: "tenant" | "user" | "workspace" | "project" | "session" | "run";
  ownerId: string;
  sensitivity: Sensitivity;
  createdAt: string;
  deletedAt?: string;
}
```
## TypeScript 接口
### Authn/Authz Port
```typescript
interface IdentityPort {
  authenticate(input: HostCredential): Promise<AuthenticatedPrincipal>;
  authorize(input: AuthorizationInput): Promise<AuthorizationDecision>;
  resolveScope(input: ScopeRequest): Promise<ScopeResolution>;
}
interface AuthorizationInput {
  principal: PrincipalRef;
  action: string;
  resource?: ResourceRef;
  scope: ScopeRef;
  policyVersion: string;
}
```
### ScopeGuard
```typescript
interface ScopeGuard {
  assertTenant(context: TenantContext, tenantId: string): void;
  assertScope(context: TenantContext, scope: ScopeRef): void;
  authorizeResource(context: TenantContext, resource: ResourceOwnership): Promise<void>;
  childScope(parent: RunScopeContext, requested: ChildScopeRequest): Promise<RunScopeContext>;
}
```
### TenantAware Repository
```typescript
interface TenantAwareRepository<T> {
  get(scope: ScopeRef, id: string): Promise<T | undefined>;
  list(scope: ScopeRef, query: ScopedQuery): Promise<T[]>;
  append(scope: ScopeRef, entries: T[], expectedVersion: number): Promise<AppendReceipt>;
  delete(scope: ScopeRef, id: string, reason: string): Promise<DeleteReceipt>;
}
```
接口要求调用者提供 scope，但实现必须再次检查资源 owner；不能把 `scope` 当可信声明。
### QuotaPort
```typescript
interface QuotaPort {
  reserve(input: QuotaReservation): Promise<QuotaLease>;
  settle(lease: QuotaLease, actual: UsageDelta): Promise<void>;
  release(lease: QuotaLease, reason: string): Promise<void>;
  snapshot(scope: ScopeRef): Promise<QuotaSnapshot>;
}
```
### JobQueue
```typescript
interface TenantJobQueue {
  enqueue(job: TenantJob): Promise<JobReceipt>;
  lease(worker: WorkerIdentity, filter: JobFilter): Promise<JobLease | undefined>;
  heartbeat(lease: JobLease): Promise<void>;
  complete(lease: JobLease, result: JobResult): Promise<void>;
  fail(lease: JobLease, error: NormalizedError): Promise<void>;
  cancel(scope: ScopeRef, jobId: string): Promise<void>;
}
```
### TenantAware Cache
```typescript
interface TenantCache {
  get<T>(key: TenantCacheKey): Promise<T | undefined>;
  set<T>(key: TenantCacheKey, value: T, ttlMs: number): Promise<void>;
  delete(key: TenantCacheKey): Promise<void>;
  invalidateScope(scope: ScopeRef): Promise<void>;
}
interface TenantCacheKey {
  tenantId: string;
  namespace: string;
  scopeHash: string;
  resourceVersion?: string;
  policyVersion?: string;
  valueHash: string;
}
```
## 租户上下文装配
### Bootstrap 顺序
```text
receive host request
  -> authenticate principal
  -> resolve tenant membership
  -> resolve workspace/project ownership
  -> authorize session/run operation
  -> load tenant policy snapshot
  -> load quota/budget snapshot
  -> resolve provider egress and credential namespace
  -> create TenantContext
  -> freeze RunScopeContext
```
### RunScopeContext
```typescript
interface RunScopeContext {
  tenant: TenantContext;
  scope: ScopeRef;
  principal: PrincipalRef;
  policySnapshot: PolicySnapshot;
  quotaLease?: QuotaLease;
  egressSnapshot: EgressSnapshot;
  configSnapshotId: string;
  traceNamespace: string;
  abortSignal: AbortSignal;
}
```
### Context hash
`contextHash` 绑定：
- tenant、principal、workspace/project/session/run ID。；policy version。；membership/role version。
- egress profile。；credential class。；scope version。
执行边界重新计算并比对，防止批准 A、执行 B。
## Identity/Authn/Authz
### Authn
认证只回答“主体是谁”，不回答“能访问什么”。认证结果至少包括：
- issuer、subject、tenant membership。；authn session、token expiry 和 assurance level。；user/service/agent principal 类型。
- delegated/on-behalf-of 关系。
### Agent Principal
AgentPrincipal 不等于用户本人：
```text
UserPrincipal
  -> creates
AgentPrincipal(run-scoped capabilities)
  -> invokes
Tool/Provider/Worker
```
审计同时记录请求用户、AgentPrincipal、实际 service/worker principal。
### Authz
授权输入必须包含：
- principal。；action。；tenant/scope。
- resource ownership。；policy snapshot。；environment/host capability。
- approval/previous durable decision。
### OBO 约束
- token audience 和 scope 最小化。；tenant ID 由认证上下文注入。；下游服务不能只信 header 中的 tenant ID。
- provider/worker 使用短期、目的绑定凭据。；user token 不进入 model prompt 或 tool arguments。
## 租户与用户授权
### 成员关系
```typescript
interface TenantMembership {
  tenantId: string;
  principalId: string;
  roles: string[];
  status: "active" | "suspended" | "revoked";
  version: number;
  expiresAt?: string;
}
```
运行中 membership 变更：
- 新动作重新检查。；高风险已批准动作重新验证。；suspended/revoked 停止新调用。
- in-flight 副作用按 unknown/recovery 处理，不能伪造取消成功。
### Scope 授权矩阵
| 操作 | Tenant Admin | Workspace Member | Session Owner | Agent |
|---|---:|---:|---:|---:|
| 创建 session | 是 | 依策略 | 是 | 受限 |
| 读取 session | 依策略 | 受限 | 是 | 受限 |
| 导出 artifact | 依策略 | 依 owner | 是 | 否/受限 |
| 修改 policy | 是 | 否/受限 | 否 | 否 |
| 执行 destructive tool | 依审批 | 依审批 | 依审批 | 不可自行批准 |
| 删除 tenant 数据 | 强认证 | 否 | 否 | 否 |
### Approval
Approval 必须绑定：
- tenant、principal、run、action hash。；resource ownership 和 material parameters。；policy version、scope、expiry。
- approver identity 和 host proof。
父 run approval 不自动覆盖 child 或后台 job。
## Workspace/Project 隔离
### Workspace
Workspace 是文件和项目规则的边界：
- root path canonicalization。；owner tenant/workspace。；project trust state。
- snapshot/branch identity。；allowed filesystem roots。；MCP/plugin/hook provenance。
### Project
Project 是配置和扩展的边界：
- model defaults。；active tools。；skills、hooks、MCP/LSP。
- context resources。；retention 和 delivery defaults。
项目配置不能覆盖 tenant safety floor、provider allowlist、数据驻留和 quota。
### Trust
```text
Safe phase
  tenant/global built-ins
  non-executable workspace metadata
Trusted phase
  project hooks/plugins/MCP/LSP/env loaders
```
未信任 workspace 不因 tenant 成员关系而自动信任项目代码。
## Session/Run 隔离
### Session
Session record 必须包含：
- tenantId、ownerId、workspaceId、projectId。；branch、retention、privacy、schema version。；active model/toolset/config snapshot。
- artifact root 和 event stream ref。
### Run
Run freeze：
- tenant context hash。；policy/config snapshot。；model/deployment/egress。
- toolset hash。；sandbox profile。；quota reservation。
- trace namespace。
### Run 恢复
恢复 run 时重新验证：
- tenant membership。；session/branch owner。；policy version。
- quota/budget 剩余。；provider egress 和 credential。；in-flight tool ownership。
### CAS
所有 session append 带 expectedVersion；冲突不能静默覆盖。多客户端必须按 tenant+session partition 读取和写入。
## 配置隔离
### 配置层级
```text
built-in defaults
  < tenant policy
  < tenant model/tool defaults
  < user settings
  < workspace/project settings
  < session settings
  < run overrides
```
### 安全规则
- 低层只能收紧安全上限。；配置快照必须记录 source、version、hash、tenant scope。；run 中途修改只影响新 run，或生成显式 ConfigChangeEntry。
- secret config 只保存 secret reference，不保存值。；workspace 配置不得设置任意 provider endpoint 或关闭审计。
### ConfigSnapshot
```typescript
interface TenantConfigSnapshot {
  id: string;
  tenantId: string;
  policyVersion: string;
  modelPolicyHash: string;
  toolPolicyHash: string;
  egressPolicyHash: string;
  quotaPolicyHash: string;
  retentionPolicyHash: string;
  sources: ConfigSourceRef[];
  createdAt: string;
}
```
## 模型与 Provider 隔离
### Tenant Model Policy
```typescript
interface TenantModelPolicy {
  allowedProviders: string[];
  allowedApiFamilies: string[];
  allowedModels: ModelRef[];
  allowedRegions: string[];
  deniedRegions: string[];
  requiredCapabilities: string[];
  fallbackPolicy: FallbackPolicy;
  dataClassRules: DataClassEgressRule[];
}
```
### 路由流程
```text
tenant policy
  -> candidate model refs
  -> catalog capability filter
  -> region/data residency filter
  -> credential namespace
  -> health/circuit filter
  -> quota reservation
  -> ResolvedModel
```
Provider adapter 接收 `ResolvedModel` 和 `TenantRoutingSnapshot` 的只读结果，不能在 adapter 内自行读取 tenant 表、修改 fallback 或绕过 egress。
### Prompt/Context Cache
provider prompt cache 的 key 必须考虑：
- tenant/project policy hash。；resource hashes。；toolset hash。
- model/deployment。；region/egress profile。；sensitivity/redaction profile。
跨 tenant 共享 prompt cache 默认禁止，即便文本看起来相同。
## 工具与插件隔离
### Tool Visibility
有效工具集：
```text
registry candidates
  ∩ tenant allowlist
  ∩ user/workspace policy
  ∩ project trust
  ∩ host capability
  ∩ model capability
  ∩ sandbox capability
  ∩ run overrides
```
### Tool Execution Context
```typescript
interface TrustedExecutionContext {
  tenantId: string;
  userId?: string;
  workspaceId?: string;
  projectId?: string;
  sessionId: string;
  runId: string;
  principal: PrincipalRef;
  allowedResourceRoots: string[];
  networkPolicy: NetworkPolicy;
  secretBindings: SecretBinding[];
  authorizationSnapshot: AuthorizationSnapshot;
}
```
tenant/user/project ID 由 Harness 注入；模型不能在工具参数里覆盖。
### 插件/MCP
插件和 MCP 必须带：
- provenance、owner tenant、trust state。；active toolset snapshot。；child/run capability intersection。
- sandbox profile、network policy、output budget。；auth scope 和 schema snapshot。；registration transaction 和 rollback。
一个租户的插件不能污染全局 registry；若有 process-wide catalog，记录 tenant namespace 并过滤。
## Memory 与 Context 隔离
### Memory Scope
```text
global -> organization -> tenant -> user -> workspace -> project -> session -> branch -> run -> turn
```
默认不允许跨 tenant recall。跨 workspace recall 需要显式 policy；regulated/secret 不进入长期 memory。
### MemoryRecord 扩展
```typescript
interface TenantMemoryRecord extends MemoryRecord {
  tenantId: string;
  ownerScope: ScopeRef;
  visibility: "private" | "workspace" | "project" | "tenant";
  egressPolicyVersion: string;
  deleteToken?: string;
}
```
### ContextPlan 过滤
在进入 provider 前执行：
```text
candidate resources
  -> tenant/scope ownership
  -> sensitivity ceiling
  -> policy authority
  -> provider jurisdiction
  -> redaction
  -> token budget
```
不能因为 memory 相似度高就跨租户注入；不能把 memory recall 当授权。
## Artifact 与文件隔离
### Artifact Namespace
推荐 URI：
```text
artifact://tenant/{tenantId}/workspace/{workspaceId}/project/{projectId}/session/{sessionId}/{artifactId}
```
真实存储可哈希或分区，但逻辑 owner 必须可验证。
### Artifact 访问
每次 `get(ref)` 都检查：
- tenant context。；owner scope。；principal permission。
- artifact sensitivity。；expiry/retention。；purpose和range。
不能只依赖不可猜测 URI；URL 签名必须短 TTL、绑定 tenant 和用途。
### Workspace 文件
- root path canonicalize。；tenant/workspace owner 绑定 sandbox mount。；不把共享宿主 temp 目录作为租户隔离。
- snapshot/patch 带 tenant/workspace/base hash。；删除和导出生成 durable audit。
## Event/Trace/Audit 隔离
### Canonical Event
事件至少包含：
```text
tenantId
workspaceId
sessionId
runId
traceId
scopeHash
sensitivity
retentionClass
```
缺失 tenant 的业务事件默认拒绝进入 durable store。
### Event Store
- partition 优先 tenant+session 或 tenant+run。；query API 强制 tenant scope。；replay 前重新授权。
- projection 和 cursor 不跨 tenant 复用。；event ID 全局唯一但不可通过 ID 推断其他租户事实。
### Trace
- tenant ID 可进入受控 trace attribute，不作为公开 metric label。；cross-tenant correlation 被拒绝并审计。；diagnostic snapshot 做 tenant-aware authorization。
- operator 支持 break-glass 访问时必须强认证、短 TTL、全量 audit。
### Audit
Audit 记录：
- 请求 principal、tenant、scope。；model/provider/egress。；policy/approval/sandbox。
- resource hash、outcome、unknown side effect。；delete/export/key rotation。
普通 debug log 不能替代 audit。
## 数据模型与存储分区
### Partition 策略
按数据类型选择：
| 数据 | 首选分区 |
|---|---|
| Session/Event | tenant + session/run |
| Artifact | tenant + workspace/project |
| Memory | tenant + owner scope |
| Queue Job | tenant + priority/class |
| Quota | tenant + resource class |
| Audit | tenant + time/retention class |
| Cache | tenant namespace + scope hash |
| Credential metadata | tenant + provider |
### 纵深防御
- API 层 scope guard。；repository 层 owner check。；storage partition/row-level policy。
- artifact object policy。；queue lease owner check。；cache namespace。
- event/replay authorization。；audit cross-check。
### 失败策略
tenant scope 缺失、owner 不匹配、schema 版本不兼容或 policy 不可用时：
```text
拒绝读取/写入
  -> 记录安全事件
  -> 不泄露资源存在性
  -> 返回稳定错误码
```
## 策略与决策流程
### Tenant-aware Action
```typescript
interface TenantActionRequest extends ActionRequest {
  tenantContextHash: string;
  scope: ScopeRef;
  resourceOwners: ResourceOwnership[];
  egress?: EgressRequest;
}
```
### 决策管线
```text
authenticate
  -> resolve tenant membership
  -> resolve scope/resource ownership
  -> visibility
  -> schema/business validation
  -> quota reservation
  -> call policy
  -> approval
  -> execution/sandbox policy
  -> provider/tool egress
  -> execute
  -> result redaction
  -> durable commit
  -> quota settlement
```
### Policy 优先级
```text
built-in safety floor
  < organization/tenant policy
  < workspace/project policy
  < session policy
  < run override
```
低层不能放宽 tenant data residency、secret、destructive、quota 或 cross-tenant deny。
## 配额、预算与 Rate Limit
### 配额维度
- 并发 run 数。；active model attempts。；tool calls。
- subagent 数量和递归深度。；input/output/reasoning tokens。；provider request 数。
- artifact bytes。；storage bytes。；event rate。
- worker CPU/memory/wall time。；egress bytes。；费用预算。
### 层级预算
```text
tenant budget
  -> user budget
    -> workspace budget
      -> project budget
        -> session budget
          -> run budget
            -> turn/attempt/tool budget
```
子层 reservation 不得超过父层剩余预算。
### Reservation/Settlement
- 动作前 reserve。；provider/tool 事件后更新 actual。；成功、失败、取消和 unknown 都 settle。
- 未使用 reservation release。；并发 reservation 使用原子 lease，避免超卖。
### Rate Limit
使用 token bucket、并发 semaphore 或等价端口；按 tenant/user/workspace/provider/deployment 分层。429 处理不能只依赖 provider；本地 quota 先行保护。
### Budget 事件
durable 记录：
- reservation。；consumption。；release。
- exceeded。；throttle。；budget override。
## Noisy Neighbor 防护
### 共享资源
- provider connection pool。；worker pool。；event router queue。
- artifact upload bandwidth。；DB connection pool。；CPU/memory/disk。
- catalog refresh。
### 隔离策略
- tenant-aware concurrency semaphore。；weighted fair queue。；per-tenant queue depth。
- priority ceiling。；bounded worker lease。；per-tenant circuit 和 backoff。
- 大 artifact 上传限速。；单租户事件 burst coalescing。；热 session 分片或 actor owner。
### 不应做
- 让一个 tenant 无限占满全局 worker。；让重试风暴共享同一无界队列。；让单个 session 的 stream 阻塞其他租户 durable writer。
- 用 tenant ID 作为所有 metrics label 导致 cardinality 爆炸。
### Fairness 指标
- tenant queue wait p50/p95。；reserved/actual concurrency。；worker lease utilization。
- provider quota share。；artifact/event bytes。；starvation count。
- throttle/reject rate。
## Provider Egress 与数据驻留
### EgressSnapshot
```typescript
interface EgressSnapshot {
  tenantId: string;
  allowedProviders: string[];
  allowedRegions: string[];
  deniedRegions: string[];
  allowedDataClasses: Sensitivity[];
  redactionProfile: string;
  artifactOnlyClasses: Sensitivity[];
  policyVersion: string;
}
```
### 决策
```text
resource sensitivity
  + tenant policy
  + provider jurisdiction/deployment
  + region/location
  + purpose
  + retention
  -> allow full | redact | summarize | artifact-only | deny
```
### Provider fallback
fallback 重新执行 egress 和 data residency 检查；不能因为 primary 故障就发送到不允许的 provider/region。
### URL/附件
- provider 访问 URL 需 allowlist 和 SSRF 检查。；artifact reference 需 tenant owner 验证。；base64/上传内容按 sensitivity 分类。
- tool result 回传模型前重新评估 egress。
## Credential 与密钥
### Secret namespace
```text
secret://tenant/{tenantId}/provider/{provider}/credential/{credentialId}
secret://tenant/{tenantId}/tool/{toolId}/binding/{bindingId}
```
### SecretBinding
```typescript
interface TenantSecretBinding extends SecretBinding {
  tenantId: string;
  principalId: string;
  sessionId?: string;
  runId: string;
  allowedProviderOrTool: string;
  allowedDestination?: string;
  purpose: string;
  expiresAt: string;
  rotationVersion: string;
}
```
### 原则
- secret 值不进入 prompt、tool args、event、log、artifact。；provider adapter 只拿 lease/handle。；remote worker 只拿短期、目的绑定 credential。
- worker 失去 lease 时撤销或过期 binding。；subagent 默认不继承 secret；需显式 child binding。
## 日志脱敏与隐私
### Sensitivity
```text
public | internal | confidential | secret | regulated
```
### Redaction Pipeline
```text
classify
  -> tenant/scope check
  -> secret/PII detector
  -> field allowlist
  -> replace/tokenize/drop
  -> verify forbidden fields absent
  -> route by sink clearance
```
### 默认日志字段
- ID/hash、kind、state、size、count。；tenant/scope hash 或受控 ID。；provider/model/deployment。
- latency、usage、cost、error category。；policy/approval/sandbox version。
### 不记录
- 明文 secret、token、cookie。；完整敏感 prompt、reasoning、文件内容。；未脱敏 tool args、provider request/response。
- 跨租户 resource existence 诊断。
### 日志访问
operator/debug 访问敏感诊断必须重新授权并审计；脱敏失败对外 sink fail-closed。
## 后台任务与 Worker Lease
### TenantJob
```typescript
interface TenantJob {
  id: string;
  tenantId: string;
  scope: ScopeRef;
  kind: "run" | "subagent" | "compaction" | "memory" | "export" | "delete" | "recovery";
  priority: number;
  idempotencyKey: string;
  configSnapshotId: string;
  checkpointRef?: CheckpointRef;
  expiresAt?: string;
}
```
### Lease
```typescript
interface JobLease {
  jobId: string;
  tenantId: string;
  workerId: string;
  leaseVersion: number;
  issuedAt: string;
  leaseUntil: string;
  heartbeatAt: string;
}
```
### Worker 接管
```text
queued
  -> leased
  -> running
  -> checkpointed
  -> completed
leased/running -- heartbeat timeout --> worker_lost
worker_lost
  -> probe in-flight side effects
  -> acquire recovery lease
  -> resume | unknown/manual | terminal_failed
```
### 约束
- lease 绑定 tenant 和 scope。；同一 idempotency key 不允许并发不可逆执行。；worker 不得通过 job payload 覆盖 tenant context。
- queue 过滤先按可信 tenant policy，再按优先级。；UI 断开不等于后台 job 取消。；job result 交付回原 tenant/session，不能广播到全局频道。
## 缓存隔离
### 缓存类别
- model catalog。；compiled prompt/context。；provider prompt cache。
- toolset snapshot。；session projection。；memory retrieval。
- artifact metadata。；quota snapshot。；credential metadata。
### Cache key
至少包含：
```text
tenantId
scope hash
resource version/hash
policy version
model/deployment
region/egress profile
toolset hash
compiler/runtime version
sensitivity profile
```
### 禁止缓存
- 明文 secret/bearer token。；未脱敏 regulated content。；未绑定 tenant 的 artifact URL。
- 可复用 approval grant。；未知 owner 的 tool result。；跨 tenant 共享 prompt/context 内容。
### 失效
以下变化必须失效：
- membership/role。；policy/egress。；workspace/project trust。
- file/branch/session head。；model/deployment capability。；credential rotation。
- delete/export request。；artifact owner 或 retention。
## 加密与密钥轮换
### 加密层级
- 传输：TLS/受控代理/云签名。；存储：tenant-aware encryption at rest。；字段：secret、regulated payload、敏感配置。
- artifact：对象级或 tenant prefix key。；audit：独立完整性和 retention 保护。
### EncryptionContext
```typescript
interface EncryptionContext {
  tenantId: string;
  purpose: "session" | "artifact" | "memory" | "audit" | "credential" | "export";
  keyVersion: string;
  associatedData: string[];
}
```
### Key rotation
- 生成新 key version。；新写入使用新 key。；旧数据按租户和 retention 批量重加密。
- 校验 hash、owner 和 projection。；失败可重试且不丢失旧版本。；保留 rotation audit。
- 删除旧 key 前确认受保留数据已迁移或按 policy 删除。
### 失败策略
无法获取 key、AAD 不匹配或 decrypt 失败时：
- 拒绝读取/外发。；不尝试无边界 fallback。；记录安全 diagnostic。
- 触发恢复或人工处置。
## 审计与合规事实
### AuditEvent
```typescript
interface TenantAuditEvent {
  id: string;
  tenantId: string;
  actor: PrincipalRef;
  action: string;
  scope: ScopeRef;
  resourceHashes: string[];
  decision?: "allow" | "ask" | "deny" | "transform";
  outcome: "success" | "failure" | "cancelled" | "unknown";
  policyVersion?: string;
  configSnapshotHash?: string;
  causedBy?: string;
  integrity: AuditIntegrity;
  occurredAt: string;
}
```
### 必须审计
- 登录、租户成员变化和角色变化。；session/run 创建、恢复、取消。；model/provider/deployment/fallback。
- tool visibility、policy、approval、sandbox。；artifact read/write/share/delete/export。；memory write/recall/forget。
- worker lease、接管、unknown outcome。；key rotation、retention、delete/export。；cross-tenant deny 和安全事件。
### 审计完整性
- append-only 或等价机制。；tenant partition。；sequence/hash chain 或批次签名。
- 访问审计。；retention lock。；不把普通日志当不可篡改审计。
## 生命周期、删除与导出
### Tenant 生命周期
```text
Provisioning
  -> Active
  -> Suspended
  -> Deleting
  -> Deleted
  -> Tombstoned
```
### Session/Artifact 生命周期
```text
Created -> Active -> Archived -> RetentionExpired -> Deleting -> Deleted
```
### Delete 流程
```text
request deletion
  -> authenticate and authorize
  -> freeze new work
  -> cancel/settle jobs
  -> mark tenant deleting
  -> revoke credentials
  -> delete/invalidate caches
  -> delete artifacts/memory/state/events per policy
  -> rebuild/retire projections
  -> verify references and residuals
  -> write deletion receipt
  -> tombstone owner
```
### 删除注意
- 先停止新写入，再清理派生索引。；pending unknown side effect 不能因为删除请求就伪造完成。；audit 保留最小 tombstone 和删除事实。
- backup、replica、export artifact 遵循 retention policy。；删除期间新的读取默认拒绝或返回 deleting 状态。
### Export 流程
- 强认证和最小范围。；生成 manifest、scope、版本、hash 和敏感度。；只导出该 tenant owner 的 state/artifact/memory/event view。
- 外部导出目标经过 egress policy。；导出 artifact 短 TTL、加密、访问审计。；导出完成后可按 policy 自动删除临时包。
## 故障恢复
### 进程崩溃
```text
load tenant-aware checkpoint
  -> verify scope/context hash
  -> inspect pending approval and in-flight tools
  -> query idempotency/status
  -> recover worker lease
  -> rebuild projections/cache
  -> resume or manual intervention
```
### 数据库/事件存储故障
- 停止依赖 durable state 的新动作。；不在 memory/cache 中宣称成功。；使用 bounded retry 和幂等 append。
- 恢复后校验 tenant partition、sequence、projection。；cross-tenant query 失败默认返回 deny/error，不返回空列表造成误判。
### Provider 故障
- Fallback 重新检查 tenant provider allowlist、region、egress、capability、quota。；adapter 不偷偷改变租户。；失败 attempt usage/cost 保留。
- provider-side unknown job 先 query status。
### Worker 丢失
- lease timeout 后禁止并行接管不可逆动作。；probe 结果；确认成功补写；确认失败有限重试；未知标记 manual。；新 worker 继承 tenant context，但重新验证 policy 和 config snapshot。
### Cache 故障
cache miss 不应扩大权限；cache stale 不应绕过 policy；缓存故障可降级到 durable source，但不能跨 tenant fallback。
## Cross-tenant 防护
### 所有边界检查
- API/HTTP 请求。；repository get/list/append。；SQL/NoSQL/向量检索。
- ArtifactStore get/put/delete。；MemoryStore recall/write。；EventStore replay/subscription。
- Queue enqueue/lease/complete。；Cache get/set/invalidate。；Provider egress。
- Sandbox mount/network/secret。；Audit/diagnostic/export。
### CrossTenantGuard
```typescript
interface CrossTenantGuard {
  checkRequest(context: TenantContext, requested: ScopeRef): void;
  checkResource(context: TenantContext, owner: ResourceOwnership): void;
  checkReference(context: TenantContext, ref: TenantResourceRef): void;
  recordViolation(input: CrossTenantViolation): Promise<void>;
}
```
### 资源 ID 策略
- 不从模型接受 tenant ID 作为可信字段。；外部 resource ID 解析后查询 owner。；owner mismatch 返回统一 `resource_not_available`，避免泄露存在性。
- 资源引用带 tenant/owner/version/hash。；任何 cross-tenant attempt 产生安全事件。
### Prompt injection
外部内容不能：
- 改 tenant scope。；注册跨租户工具。；读取其他 tenant artifact。
- 要求 provider 发送秘密。；创建跨租户 approval。；关闭 egress 或 sandbox。
## 与 Prompt/Context/Model/Tool/State/Policy/Harness 集成
### Prompt
Prompt 可说明当前 tenant/workspace 边界和禁止行为，但不携带 secret、完整 policy 或可伪造 tenant ID。动态工具描述只来自 tenant-filtered active toolset。
### Context
Context Compiler 必须接收：
- TenantContext。；ScopeRef。；sensitivity ceiling。
- provider egress/deployment。；memory/artifact ownership。；policy version。
ContextPlan 只选择同 tenant、授权 scope 和允许敏感度的资源。
### Model/Provider
```text
Tenant Model Policy
  -> Provider Runtime routing snapshot
  -> ResolvedModel
  -> egress checked ModelRequest
```
Provider adapter 不能读取 tenant 策略或自行决定 fallback。
### Tool
Tool Runtime 在 `prepare` 和 `execute` 都检查：
- resource ownership。；tenant/workspace root。；principal permissions。
- idempotency scope。；quota reservation。；sandbox mount/network。
### State/Memory/Artifact
每个 repository port 都是 tenant-aware；session/transcript、memory、artifact、projection 不能共享未带 scope 的全局对象。
### Policy
Policy 决定 visibility/call/approval/execution/egress；tenant safety floor 不可被 workspace/run override 放宽。
### Harness
Harness 负责 bootstrap、冻结 config、创建 RunScope、注入 scope-aware ports、监督 quota/lease/cancel/recovery 和 durable settlement。
## Subagent 与多租户
### Child Scope
```typescript
interface ChildTenantScope {
  parentTenantId: string;
  childTenantId: string;
  parentRunId: string;
  childRunId: string;
  allowedScopes: ScopeRef[];
  allowedTools: string[];
  egressProfile: string;
  budget: ControlBudget;
}
```
默认 `childTenantId === parentTenantId`，但 child scope 必须更窄。
### 继承规则
- 继承 tenant policy 的安全上限。；不继承全部 parent transcript、memory、secret 或 approval。；toolset 是 parent active toolset 与 child policy 的交集。
- artifact 只能访问 assignment 明确列出的 refs。；child quota 从 parent remaining budget 中 reserve。；child trace 独立 namespace，父侧只接收结构化 result。
### 跨租户委派
默认禁止。若产品确有 B2B/OBO 场景：
- 必须有双方 tenant policy。；明确 data egress 和 consent。；使用受限 shared artifact/reference。
- 每个动作双租户审计。；不允许 child 通过 prompt 获得另一租户权限。
## 事件与可观测性
### Event Envelope
```typescript
interface TenantEventEnvelope extends CanonicalEvent {
  tenantId: string;
  scopeHash: string;
  authorizationContextHash: string;
  retentionClass: string;
  redactionState: "raw" | "redacted" | "tokenized" | "metadata_only";
}
```
### Event Router
- tenant queue 与 control/data plane 分离。；单租户 burst 不阻塞其他租户 durable writer。；slow client 只影响自己订阅。
- subscription 重连重新 authorize tenant/session。；cursor 不跨 tenant 复用。
### Trace/Metric
- trace 传播 tenant/run/session scope hash。；provider/tool/worker span 保留 causation。；不用 tenant ID、user ID、resource path 做高基数指标 label。
- 以 tenant 分层聚合和受控抽样查看成本。
### 关键指标
- per-tenant run/tool/model success。；quota reservation/settlement drift。；queue/lease/worker utilization。
- noisy neighbor throttle/reject。；cross-tenant deny/violation。；cache hit/miss/invalidation。
- provider egress allow/deny。；deletion/export completion lag。；key rotation failures。
- unknown side-effect count。
## 生命周期与状态机
### Tenant 状态机
```text
Provisioning
  -> Active
  -> Suspended
  -> Deleting
  -> Deleted
```
### Run 租户状态机
```text
Received
  -> Authenticated
  -> ScopeResolved
  -> PolicyFrozen
  -> QuotaReserved
  -> Preparing
  -> Sampling
  -> WaitingForApproval | ExecutingTools
  -> Settling
  -> Completed | Failed | Cancelled | Suspended | RecoveryRequired
```
### Job 状态机
```text
Queued
  -> Leased
  -> Running
  -> Checkpointed
  -> Completed
Running -> WorkerLost -> Recovering
Running -> Cancelled | Failed | UnknownOutcome
```
### Delete 状态机
```text
Requested
  -> Authorized
  -> Frozen
  -> Revoking
  -> Deleting
  -> Verifying
  -> Deleted | DeleteBlocked
```
### 状态不变量
- Suspended/Deleting tenant 不接受新的 provider/tool side effect。；Quota 未 reserve 不能开始模型或工具动作。；Lease owner/tenant 不匹配不能 heartbeat/complete。
- terminal run 不能写新业务事件。；DeleteBlocked 必须给出可恢复原因和审计记录。
## 安全与隐私检查
### 最小权限
- agent principal 只获得 run 所需 capability。；worker 只获得 job 所需 scope。；provider credential 只绑定 provider/region/purpose。
- artifact read 只允许最小 range 和 TTL。；operator 诊断默认 metadata-only。
### Fail-closed 条件
- tenant/owner 无法解析。；membership suspended/revoked。；policy/egress 不可用。
- credential scope 无法限定。；worker tenant 不匹配。；artifact owner/hash 不匹配。
- cache namespace 不完整。；audit 是 obligation 但 sink 不可用。；delete/export authorization 失效。
### Prompt injection 防护
对 source code、README、RAG、email、tool output、MCP 描述和 OCR 内容做：
- trust/authority 标注。；scope/tenant 检查。；不允许改变 policy、tenant、approval、toolset 或 egress。
- 高风险动作按实际参数重新校验。
### Secret 泄漏响应
- 阻断 egress。；替换模型/用户视图中的 secret。；标记 artifact 和 event sensitivity。
- 产生 security audit event。；按策略撤销/轮换 credential。；保留 hash、时间、scope 和检测规则，不复制 secret。
## 测试矩阵
### 身份与 Scope
| 场景 | 期望 |
|---|---|
| tenant ID 缺失 | fail-closed |
| user 属于其他 tenant | deny 且不泄露资源存在性 |
| workspace owner mismatch | deny |
| session owner mismatch | deny |
| run resume membership revoked | suspend/recovery |
| child 请求扩大 scope | deny |
| operator break-glass | reauth + audit |
### 状态与存储
- `get/list/append/delete` 的 tenant partition。；CAS conflict 不覆盖其他租户。；replay/subscription 不能跨 tenant。
- projection rebuild 保持 owner。；artifact hash/owner/expiry。；memory recall 不返回其他租户。
- delete 后 cache/index/artifact/event view 全部失效。
### Provider/Egress
- allowlisted provider/region 成功。；denied region/provider 在编译前拒绝。；fallback 重新执行 egress。
- secret/regulated content 变成 redact/artifact-only/deny。；prompt cache key 跨租户不命中。；provider response metadata 不改变 tenant scope。
### Tool/Plugin/Sandbox
- 模型伪造 tenant/resource 参数。；path traversal、symlink/junction、SSRF。；MCP 描述要求读取其他 tenant artifact。
- plugin 注册跨租户工具。；tool execution context tenant 注入不可覆盖。；sandbox mount 只包含当前 workspace。
- child 不继承父 secret/approval。
### Quota/Noisy Neighbor
- tenant/user/workspace/run 预算层级。；reservation 超卖竞争。；token/tool/artifact/worker 并发上限。
- 一个 tenant burst 不饿死其他租户。；provider 429 与本地 throttle 分类。；quota settle 在失败、取消、unknown 后正确。
### Worker/Recovery
- lease heartbeat、超时接管。；worker tenant mismatch。；side effect 后 crash 不重复。
- checkpoint 恢复重新授权。；UI 断开后台继续。；cancel/expire 释放 lock、secret、artifact 临时资源。
### 删除/导出/密钥
- 删除前冻结新工作。；pending unknown action 需要人工/状态探测。；导出只包含授权 scope。
- delete tombstone 阻止 memory/artifact 复活。；key rotation 中断可恢复。；旧 key 不再用于新写入。
### 事件/日志/Trace
- 事件缺 tenant 拒绝 durable append。；tenant cursor 不能跨用。；redaction 扫描 synthetic secret。
- diagnostic 不泄露完整 prompt/path。；cross-tenant violation 可审计。；slow client 不阻塞其他 tenant。
### Evaluation 集成
每个高风险 scenario 至少包含：
- trajectory/event assertion。；final state assertion。；negative side-effect oracle。
- tenant/resource ownership assertion。；quota/termination assertion。；redaction/egress assertion。
- recovery assertion。
## 反模式
- tenant ID 从模型参数或 prompt 读取。；只在 system prompt 写“不要访问其他租户”。；只靠数据库 where 条件做隔离。
- repository 允许不带 scope 的全局 `get(id)`。；provider adapter 内硬编码 tenant allowlist。；fallback 直接换到未授权 provider/region。
- cache key 缺少 tenant/policy/resource version。；artifact URL 可访问但未重新检查 owner。；worker job payload 可以覆盖 trusted tenant context。
- lease 只绑定 job ID，不绑定 tenant/worker/version。；background job 依赖前台连接。；child 自动继承父全部 memory、secret、approval。
- plugin/MCP 进入全局 registry 污染其他租户。；shared temp/worktree 未做租户隔离。；trace/log/audit sink 不做租户路由。
- 用 tenant ID 做所有 metrics label 导致高基数爆炸。；quota 只在任务结束结算，允许并发超卖。；noisy neighbor 占满全局 worker/connection/event queue。
- 删除只删主表，不删 cache、artifact、embedding、projection。；导出包没有 manifest、scope、hash 和短 TTL。；key rotation 只更新配置，不迁移旧数据或审计。
- unknown side effect 在租户删除后被当作已取消。；operator 诊断绕过租户授权。；cross-tenant deny 返回资源存在性细节。
- 只测试 happy path，不测试 lease、recovery、delete、egress、cache 和 worker crash。
## 实施清单
### Identity 与 Scope
- [ ] 定义 PrincipalRef、TenantContext、ScopeRef、ResourceOwnership。；[ ] 认证和租户成员关系版本化。；[ ] 生成不可伪造的 TenantContext/contextHash。
- [ ] 所有 scope-aware port 强制 tenant context。；[ ] child、worker、operator scope 有独立授权。；[ ] cross-tenant violation 统一记录和脱敏。
### 数据与状态隔离
- [ ] Session/Event 按 tenant+session/run 分区。；[ ] Memory、Artifact、Projection、Audit 带 owner scope。；[ ] repository 二次 owner 检查，不只依赖调用者过滤。
- [ ] CAS、replay、subscription、cursor 重新授权。；[ ] delete/export 有冻结、验证、receipt 和 tombstone。；[ ] 删除清理 cache、index、embedding、artifact 和 projection。
### Provider/Tool/Policy
- [ ] Tenant Model Policy 和 EgressSnapshot。；[ ] Provider adapter 不承载租户策略。；[ ] fallback 重新检查 provider/region/capability/egress/quota。
- [ ] tool execution 注入可信 tenant/workspace context。；[ ] plugin/MCP tenant namespace、trust、rollback。；[ ] policy safety floor 不可被 workspace/run 覆盖。
### 配额与公平
- [ ] tenant/user/workspace/project/session/run 预算层级。；[ ] reservation/settlement/release 原子化。；[ ] provider/tool/token/artifact/worker/event quota。
- [ ] tenant-aware queue、semaphore、weighted fairness。；[ ] noisy neighbor 告警、throttle 和 starvation 指标。；[ ] retry/fallback/compaction/subagent 成本归因。
### Worker、Cache、Secret
- [ ] JobQueue、JobLease、heartbeat、recovery lease。；[ ] lease 绑定 tenant、worker、version、idempotency key。；[ ] cache key 包含 tenant/scope/policy/resource/model。
- [ ] secret lease 和 SecretBinding 目的/TTL/rotation。；[ ] child/worker 不默认继承 secret。；[ ] 加密 context、key version、rotation 和 revoke。
### 事件、隐私与运营
- [ ] Canonical Event 缺 tenant 时拒绝 durable append。；[ ] event/trace/audit 分离并带 sensitivity/retention。；[ ] redaction 先于外部 sink。
- [ ] tenant ID 不作为高基数 metric label。；[ ] diagnostic snapshot 重新授权、metadata-only、短 TTL。；[ ] data residency、provider egress、artifact export 全量审计。
### 测试与 Conformance
- [ ] identity/scope/storage/cache/queue/provider/tool/sandbox 全矩阵。；[ ] synthetic secret 和 cross-tenant negative tests。；[ ] noisy neighbor、quota race、lease loss 和 worker crash。
- [ ] delete/export/key rotation/recovery tests。；[ ] provider fallback egress conformance。；[ ] evaluation hard assertions 覆盖真实副作用和 tenant ownership。
## 五个参考项目的启发来源
### Pi
- headless loop、EventStream、session tree 和 AgentSession 启发 Session/Run/Branch 的明确 scope。；CLI/TUI/RPC 共用 runtime 启发 Host 断线、delivery 和 durable state 解耦。；resource loader、compaction 和 checkpoint 启发 context/memory/artifact 的版本与来源治理。
- parent/child steering/follow-up 方向启发 child run 不复制全部父 transcript。
### Grok Build
- Session/ChatState/Sampler actor 启发单一状态 owner、串行写入和高并发下的 scope 所有权。；permission decision、folder trust、sandbox 启发 tenant policy、workspace trust、execution isolation 分离。；并行工具和路径级锁启发 tenant resource lock、noisy neighbor 和写冲突保护。
- 输出预算和独立 trace 启发 per-tenant artifact/event quota 与诊断隔离。
### OpenCode
- client/server、session/message/part 和 durable event/projector 启发 tenant-aware server、projection、replay 和多客户端 cursor。；snapshot/patch/revert 启发 workspace/project 文件状态的基线 hash、冲突和恢复。；permission/tool/server 分离启发跨层授权不能靠 provider 或 UI 自行解释。
- durable event 与 projector 启发删除、导出、审计和 recovery 的事实来源。
### Claude Code
- permission modes、hooks、skills、subagents、memory 和计划工作流启发 scope-specific capabilities。；项目规则与 auto memory 方向启发 workspace/project/session memory 的 provenance、trust 和 retention。；subagent 产品能力启发 child run 的独立预算、上下文、工具和 approval。
- 公开能力与安全语义以现有本地文档中标注的 Anthropic 官方资料为准。
### OpenClaw
- Gateway/channel/session key 启发 identity routing、tenant/session scope 和多渠道 delivery 隔离。；AgentHarness registry、agent-core、provider runtime 启发统一装配和 capability intersection。；tool/sandbox/elevated 分层启发 tenant policy、execution backend、secret 和高权限通道分离。
- 后台运行、memory flush、事务化插件注册启发 worker lease、memory retention、plugin rollback 和失败恢复。
本设计的实现审查应回到已有本地参考文档和其列出的源码范围；若增加跨租户委派、具体 IAM、存储后端、合规区域或新的 provider，应另行补充一手证据、迁移设计和测试契约。
