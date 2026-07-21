# Security Operations Engineering 细粒度工程设计

> 本设计把 Agent 安全运营定义为贯穿 Model、Prompt、Context、Tool、State、Policy、Harness 与 Host 的控制平面。内容只使用本地参考架构和五个参考项目源码调研结论，不把 README 当作规范，不新增网络调研结论。

## 目录

1. [目标与非目标](#目标与非目标)
2. [职责边界](#职责边界)
3. [威胁模型](#威胁模型)
4. [安全控制面总体架构](#安全控制面总体架构)
5. [身份、租户、工作区信任](#身份租户工作区信任)
6. [核心数据模型与 TypeScript 接口](#核心数据模型与-typescript-接口)
7. [生命周期与状态机](#生命周期与状态机)
8. [安全决策流程](#安全决策流程)
9. [Secrets 与密钥生命周期](#secrets-与密钥生命周期)
10. [Provider Egress](#provider-egress)
11. [Prompt、Tool 与数据注入](#prompttool-与数据注入)
12. [Sandbox、Permission 与 Approval](#sandboxpermission-与-approval)
13. [Audit、Forensics 与事件管道](#auditforensics-与事件管道)
14. [SIEM、告警与分诊](#siem告警与分诊)
15. [事件严重度与事件响应](#事件严重度与事件响应)
16. [漏洞、补丁、依赖与供应链](#漏洞补丁依赖与供应链)
17. [插件、Skill、MCP 与扩展](#插件skillmcp-与扩展)
18. [滥用防护与速率限制](#滥用防护与速率限制)
19. [保留、删除、导出与 Break-glass](#保留删除导出与-break-glass)
20. [与 Model/Prompt/Context/Tool/State/Policy/Harness 集成](#与-modelpromptcontexttoolstatepolicyharness-集成)
21. [故障恢复与业务连续性](#故障恢复与业务连续性)
22. [安全测试策略](#安全测试策略)
23. [Tabletop 与 Runbook](#tabletop-与-runbook)
24. [指标、SLO 与报告](#指标slo-与报告)
25. [反模式](#反模式)
26. [实施清单](#实施清单)
27. [五个参考项目的启发来源](#五个参考项目的启发来源)

## 目标与非目标

### 目标

- 将安全规则落实为可执行的 Policy、Sandbox、Credential、Audit 和 Harness 控制。
- 区分身份认证、租户授权、工作区信任、工具可见性、动作审批和执行隔离。
- 让每个高风险动作具备 actor、scope、参数 hash、policy version、approval、sandbox attestation 和结果证据。
- 让敏感数据在 Context 编译、Provider 请求、Tool 参数、Artifact、Trace 和 Host 交付前分别经过 egress 决策。
- 让 prompt、工具、检索、文件、插件和 MCP 内容默认被视为不可信数据。
- 让安全事件可以从 canonical event 重放、关联、调查和证明真实副作用。
- 让告警有去重、分组、优先级、分诊、升级和关闭证据，而不是只有日志搜索。
- 让 incident response 覆盖 containment、eradication、recovery、验证和事后改进。
- 让依赖、插件、模型、provider、sandbox 和配置变化具有 provenance、审批和回滚路径。
- 让租户级、workspace 级、用户级和 run 级安全指标可归因而不泄露敏感内容。

### 非目标

- 本设计不替代产品业务授权、合规法务或组织级风险接受流程。
- 不把模型拒答或 provider safety filter 当作本地安全控制。
- 不把 prompt 中的“请遵守规则”当作文件、网络、进程或 secret 隔离。
- 不规定某个具体 SIEM、数据库、云 KMS、EDR 或商业供应商。
- 不要求永久保存完整 prompt、hidden reasoning、工具原始输出或全部用户文件。
- 不将普通 debug log 宣称为不可篡改 audit evidence。
- 不允许安全团队直接修改生产业务状态来“修复”事件。
- 不把平均模型质量分数抵消未授权副作用、secret 泄漏或跨租户访问。
- 不自动为所有 workspace 加载 hooks、插件、Skill、MCP、LSP 或环境变量加载器。

### 核心原则

```text
Security = identity + scope + policy + approval + sandbox + egress + audit + recovery

visibility != authorization
approval != execution isolation
provider safety != local policy
telemetry != audit
unknown outcome != success
```

## 职责边界

| 组件 | 负责 | 不负责 |
|---|---|---|
| Identity Resolver | 验证 principal、会话、设备和 token 状态 | 决定工具业务参数 |
| Tenant Policy | 租户、组织、workspace 的允许范围与数据策略 | 执行 OS 隔离 |
| Trust Resolver | 判断 workspace、目录、扩展来源是否可信 | 认证用户 |
| Security Control Plane | policy、风险、密钥、egress、事件规则配置 | 直接执行工具 |
| Model Runtime | provider 协议、stream、usage、credential lease 注入 | 租户授权或工具执行 |
| Prompt/Context Compiler | authority、sensitivity、redaction、上下文选择 | 赋予工具能力 |
| Tool Registry | schema、effect、owner、来源、健康与能力声明 | 最终授权动作 |
| Policy Engine | visibility、调用、参数、审批、egress 决策 | 代替 sandbox 执行 |
| Approval Service | 展示风险摘要、记录用户/管理员决定和范围 | 改写工具参数 |
| Sandbox Backend | 文件、网络、进程、资源和环境边界 | 解释业务意图 |
| Credential Broker | 短期 lease、轮换、撤销和绑定 | 把 secret 放进 prompt |
| Audit Writer | 安全事实、完整性、留存和访问记录 | 取代业务 session |
| Event Pipeline | 事件归一化、关联、投影、告警输入 | 直接封禁任意请求 |
| SIEM Connector | 将脱敏安全事件交付分析系统 | 作为业务 source of truth |
| Incident Commander | 分级、协调、containment、恢复和沟通 | 私自修改证据 |
| Host Adapter | 显示审批、告警、证据和控制结果 | 推断 durable truth |
| Security Testkit | 攻击场景、故障注入、oracle 和回归门禁 | 使用真实生产密钥 |

### 双人职责规则

- Policy 发布者与生产 break-glass 使用者不得默认为同一身份。
- 生产密钥轮换与轮换验证至少保留两类独立审计 actor。
- 事件关闭者必须不是唯一的事件处置者。
- 高风险规则变更需要 change ticket、版本、审批和回滚配置。
- SIEM 接入者只能获取所需 sensitivity 等级的事件投影。
- Forensics 复制必须记录原事件 hash、复制者、目的地和 expiry。

## 威胁模型

### 保护资产

- Tenant、Workspace、Session、Run、Turn、Attempt 和分支状态。
- 用户 prompt、项目源码、文件、附件、工具参数和工具结果。
- API key、OAuth token、云角色、cookie、环境变量和签名材料。
- Model request、provider response、reasoning summary、artifact 和 trace。
- Tool registry、Policy、Approval、Sandbox profile、模型目录和价格/路由配置。
- 文件、数据库、网络、消息、Git、部署和支付等外部副作用。
- Audit、事件、告警、快照、checkpoint、证据和 incident 记录。
- 供应链清单、插件包、Skill、MCP server、hooks、LSP 和生成器。

### 信任区域

```text
Z0 Public/Untrusted: 用户输入、网页、issue、源码注释、检索文本、模型输出
Z1 Workspace: 项目文件、规则文件、package scripts、hooks、插件声明
Z2 Run: Prompt/Context/Tool/State/Policy/Harness 执行控制
Z3 Credential/Security: KMS、broker、audit store、SIEM、incident controls
Z4 External: Provider、MCP、HTTP、数据库、消息系统、部署平台
```

- Z0 内容不能提升到 Z2 authority。
- Z1 未信任 workspace 不得自动执行声明性配置。
- Z2 仅由冻结的 policy、capability 和 sandbox 产生实际权限。
- Z3 secret 不以普通事件、prompt 或 artifact 形式返回 Z0。
- Z4 的响应、状态和 receipt 必须经过 schema、tenant 和 egress 校验。

### 攻击者能力

- 普通用户可提交恶意 prompt、路径、URL、附件和工具参数。
- 恶意文档、issue、测试输出、源码注释和网页可注入指令。
- workspace 提交者可放置 package script、hook、MCP manifest、Skill 和 symlink。
- 已认证但低权限用户可能尝试跨 workspace、跨租户或越权读取。
- 被攻陷的插件、MCP server、provider response 或宿主进程可能返回恶意数据。
- 外部攻击者可滥用公开入口、重放 token、耗尽额度或诱导高风险动作。
- 内部 operator 可能误用 break-glass、诊断快照或敏感 trace。
- 网络故障、进程崩溃和 acknowledgement 丢失可制造 unknown outcome。

### 安全假设与不变量

- 认证上下文由受信 host 注入，模型不能声明 actor 身份。
- 所有 path、URL、command、tool name 和 model output 都需规范化。
- Policy 版本和 config snapshot 在 run 内冻结，变化产生新版本或重新授权。
- 所有外部副作用都有 execution ID、幂等键或可查询状态。
- `tenantId`、`workspaceId` 和 `runId` 是不可由不可信 payload 覆盖的控制字段。
- 审批只对精确的 action、参数 hash、资源范围、有效期和 actor 生效。
- 未知副作用必须进入 `UnknownOutcome`，不能用取消状态伪造未执行。
- Audit 关键事件不能被 telemetry 采样、coalesce 或普通 retention 删除。

### 威胁分类矩阵

| 威胁 | 入口 | 资产 | 主要控制 | 证据 |
|---|---|---|---|---|
| Prompt injection | 文档/工具结果 | policy、secret | authority 分层、Context 包装 | context hash、deny event |
| Tool injection | 模型工具调用 | 外部系统 | schema、policy、approval、sandbox | call/approval/receipt |
| Path traversal | 参数/归档 | workspace 文件 | canonical path、root intersection | normalized path |
| SSRF/egress | URL、MCP | 内网/secret | URL policy、DNS/IP 校验、网络 sandbox | destination decision |
| Secret exfiltration | prompt/output/log | credential | lease、redaction、DLP | redaction audit |
| Cross-tenant | ID、artifact、replay | 租户数据 | authenticated scope、store filter | access audit |
| Supply chain | plugin/package/hook | runtime | provenance、签名、隔离 | manifest、attestation |
| DoS/abuse | 请求/工具/子 Agent | 额度/队列 | quotas、rate limits、budgets | ledger、throttle |
| Policy bypass | mode/approval | 高风险动作 | final boundary recheck | policy chain |
| Forensic tamper | log/event | 调查证据 | append-only、hash chain | integrity check |

## 安全控制面总体架构

```text
Identity/Device -> Tenant & Workspace Scope -> Trust Resolver
                         |
                         v
                 Security Control Plane
       Policy Catalog / Risk Rules / Egress / Quota
       Credential Broker / Key Registry / Rule Versions
                         |
       +-----------------+-----------------+
       v                                   v
 Context/Prompt Compiler              Tool/Model Runtime
       |                                   |
       +---------- Harness Supervisor -----+
                         |
       Policy -> Approval -> Sandbox -> Execution
                         |
      Canonical Events -> Audit -> SIEM/Alert -> Incident
                         |
              Artifact/Forensics/Retention
```

### 控制面与数据面

- 控制面包含 identity binding、租户策略、workspace trust、tool registry、model allowlist、egress profile、quota、secret lease、风险规则和响应动作。
- 数据面包含 prompt、context、模型流、tool call、工具结果、文件差异和 provider response。
- 数据面不能覆盖控制面字段或新增 capability。
- 高频 delta 进入受限 ephemeral pipeline，审批、policy、side effect 和终态进入 durable pipeline。
- 控制面配置每次发布生成 `ConfigSnapshot`，run 使用 snapshot hash。
- 规则回滚必须保留旧版本和影响范围，不原地覆盖审计事实。

### 配置发布流程

```text
draft -> schema validate -> security review -> impact simulation -> approval
-> staged publish -> canary observe -> active -> superseded/rollback
```

- 规则变更先在离线 fixture、回放事件和 shadow 流量上模拟。
- 关键 deny 规则采用 fail-closed；非关键指标规则允许降级但必须告警。
- 发布器验证 tenant scope、递归引用、默认值、优先级和冲突。
- Config snapshot 必须包括 policy、toolset、sandbox、egress、rate limit 和 key reference 版本。

## 身份、租户、工作区信任

### 身份层次

```text
Principal -> Organization -> Tenant -> Workspace -> Session -> Run -> Attempt -> ToolExecution
```

- Principal 是认证主体，不等于 user-visible display name。
- Organization 可管理多个 tenant，但默认不能跨 tenant 查询数据。
- Workspace 绑定 repository、根路径、来源、trust 状态和规则作用域。
- Session 保存语义历史；Run 是一次受 budget、policy 和 config snapshot 约束的执行。
- Attempt、ToolExecution 和 Approval 必须继承而不能覆盖父级租户绑定。

### IdentityContext

```typescript
interface IdentityContext {
  principalId: string;
  actorType: "user" | "service" | "worker" | "admin" | "break_glass";
  tenantId: string;
  organizationId?: string;
  workspaceId?: string;
  sessionId?: string;
  authMethod: "oidc" | "api_key" | "service_token" | "local";
  deviceId?: string;
  scopes: string[];
  authenticatedAt: string;
  expiresAt: string;
  assurance: "low" | "standard" | "high";
}
```

### WorkspaceTrust

```typescript
interface WorkspaceTrust {
  workspaceId: string;
  rootHash: string;
  source: "local" | "clone" | "archive" | "remote";
  state: "unknown" | "untrusted" | "trusted" | "quarantined";
  grantedBy?: string;
  grantedAt?: string;
  expiresAt?: string;
  trustScope: "metadata_only" | "read_only" | "execution";
  reviewedFiles: string[];
  reason?: string;
}
```

- `unknown` 与 `untrusted` 都不执行 hooks、package lifecycle、MCP、LSP 或插件。
- trust 绑定 root、tree hash、租户和 scope；仓库变化可触发重新审查。
- trusted 不等于所有文件可信，文件和工具仍需 policy、schema 和 sandbox。
- quarantine 只允许诊断、导出安全证据和清理，不允许运行代码。

### 租户隔离规则

- Event、Artifact、Session、Key、Quota、Policy 和 Alert 查询默认强制 tenant predicate。
- artifact ref 必须校验 owner、tenant、workspace、sensitivity、expiry 和用途。
- replay、diagnostic snapshot、export 和 incident evidence 重新授权，不复用创建时授权。
- cross-tenant correlation 只有脱敏聚合服务可做，并记录 purpose 和审批。
- worker lease、缓存键、队列分区和临时目录必须包含 tenant/workspace scope。
- 删除租户时先冻结新写入，再执行依赖图扫描、删除、验证和审计。

## 核心数据模型与 TypeScript 接口

### SecurityDecision

```typescript
interface SecurityDecision {
  decisionId: string;
  action: "allow" | "deny" | "ask" | "transform" | "quarantine";
  actor: IdentityContext;
  resource: SecurityResource;
  actionName: string;
  argumentsHash: string;
  policyVersion: string;
  risk: RiskRating;
  reasons: string[];
  obligations: Obligation[];
  approvalRef?: string;
  sandboxProfile?: string;
  egressProfile?: string;
  expiresAt?: string;
  evaluatedAt: string;
}
```

### SecurityResource、Risk 与 Obligation

```typescript
interface SecurityResource {
  tenantId: string;
  workspaceId?: string;
  sessionId?: string;
  runId?: string;
  kind: "file" | "directory" | "tool" | "model" | "artifact" | "secret" | "external_endpoint" | "database" | "message";
  id: string;
  sensitivity: Sensitivity;
  scopeHash: string;
}
type RiskRating = "info" | "low" | "medium" | "high" | "critical";
interface Obligation {
  kind: "redact" | "approval" | "sandbox" | "rate_limit" | "audit" | "dry_run" | "step_up_auth" | "two_person";
  value?: string;
}
```

### Approval 与 Sandbox

```typescript
interface ApprovalRequest {
  approvalId: string;
  tenantId: string;
  actorId: string;
  runId: string;
  toolCallId: string;
  toolName: string;
  actionSummary: string;
  argumentsHash: string;
  resourceScopes: string[];
  risk: RiskRating;
  policyVersion: string;
  sandboxProfile: string;
  expiresAt: string;
  requiresReauth?: boolean;
}
interface ApprovalDecision {
  approvalId: string;
  decision: "allow_once" | "allow_scoped" | "deny" | "expired" | "cancelled";
  decidedBy: string;
  decidedAt: string;
  scopeHash: string;
  reason?: string;
}
interface SandboxAttestation {
  sandboxId: string;
  backend: string;
  profile: string;
  filesystemBoundary: string;
  networkBoundary: string;
  processBoundary: string;
  resourceLimits: Record<string, number>;
  capabilities: string[];
  applied: boolean;
  createdAt: string;
  attestationHash: string;
}
```

### Secret 与 Key

```typescript
interface SecretRecord {
  secretId: string;
  tenantId: string;
  purpose: "provider" | "tool" | "webhook" | "signing" | "encryption";
  provider: "kms" | "vault" | "os_store" | "broker";
  version: number;
  status: "active" | "staged" | "rotating" | "revoked" | "expired";
  allowedScopes: string[];
  createdAt: string;
  expiresAt?: string;
  lastUsedAt?: string;
}
interface CredentialLease {
  leaseId: string;
  secretId: string;
  version: number;
  tenantId: string;
  audience: string;
  scopeHash: string;
  issuedAt: string;
  expiresAt: string;
  revocable: boolean;
}
```

### Audit 与安全事件

```typescript
interface SecurityAuditEvent {
  auditId: string;
  eventId: string;
  occurredAt: string;
  tenantId: string;
  actor: IdentityContext;
  action: string;
  resource: SecurityResource;
  decision?: SecurityDecision;
  approval?: ApprovalDecision;
  sandbox?: SandboxAttestation;
  outcome: "success" | "failure" | "denied" | "cancelled" | "unknown";
  evidenceRefs: string[];
  redactionState: "metadata_only" | "redacted" | "restricted";
  integrity: { previousHash?: string; eventHash: string; batchSignature?: string };
  retentionClass: string;
}
interface SecuritySignal {
  signalId: string;
  kind: string;
  severity: RiskRating;
  tenantId?: string;
  runId?: string;
  sourceEventIds: string[];
  detectorVersion: string;
  confidence: number;
  firstSeenAt: string;
  lastSeenAt: string;
  status: "new" | "triaged" | "contained" | "resolved" | "false_positive";
}
```

### Incident、漏洞与 Break-glass

```typescript
interface Incident {
  incidentId: string;
  severity: "SEV0" | "SEV1" | "SEV2" | "SEV3" | "SEV4";
  title: string;
  attackSurface: string[];
  affectedTenants: string[];
  signals: string[];
  commander?: string;
  timeline: string[];
  containment: string[];
  eradication: string[];
  recovery: string[];
  status: "declared" | "investigating" | "contained" | "recovering" | "closed";
  openedAt: string;
  closedAt?: string;
}
interface BreakGlassGrant {
  grantId: string;
  principalId: string;
  purpose: string;
  resources: string[];
  scopes: string[];
  approvedBy: string[];
  issuedAt: string;
  expiresAt: string;
  commandsAllowed: string[];
  evidenceRequired: boolean;
  revokedAt?: string;
}
```

## 生命周期与状态机

### Run 安全生命周期

```text
created -> identity_bound -> scope_resolved -> trust_checked -> policy_frozen
-> context_egress_checked -> running -> approval_pending -> running
-> settling -> audit_committed -> completed
```

```text
任意活动状态 -> cancelling -> side_effect_reconciled -> cancelled
任意活动状态 -> quarantined -> manual_review
policy_changed -> reauthorize -> running | denied
```

- `identity_bound` 只绑定受信 actor，不接受模型或工具 payload 的 actor 字段。
- `scope_resolved` 固定 tenant、workspace、artifact 和 resource scope。
- `trust_checked` 决定 metadata/read/execution 层级。
- `policy_frozen` 保存策略 hash、工具集 hash、sandbox 和 egress snapshot。
- `audit_committed` 前不能向 Host 声称安全完成。

### Tool Execution 安全状态机

```text
proposed -> schema_validated -> policy_evaluated -> approval_pending
approval_pending -> approved | denied | expired | cancelled
approved -> sandbox_attested -> scheduled -> running
running -> succeeded | failed | cancelled | unknown_outcome | quarantined
```

- 参数 hash、目标资源或 effect 改变时回到 `policy_evaluated`。
- 未完成的 provider tool arguments 不进入 `proposed`。
- sandbox attestation 缺失时高风险动作拒绝。
- `unknown_outcome` 需要 status query、补偿或人工调查。

### Secret 生命周期

```text
requested -> policy_checked -> issued -> leased -> used
leased -> renewed -> used
active -> staged -> rotating -> overlap -> revoked
active -> expired -> revoked
```

- lease 尽量短于 run deadline，并绑定 tenant、audience、scope hash。
- 轮换窗口允许旧版本短暂验证，但不扩大权限。
- revoke 触发缓存失效、worker 通知、provider credential refresh 和审计。

### Security Event 生命周期

```text
observed -> normalized -> enriched -> deduplicated -> correlated
-> risk_scored -> alerted -> triaged -> contained -> resolved -> retained/deleted
```

- 事件 normalize 失败不能静默丢弃；保留安全 metadata 和诊断。
- deduplicate 不得合并不同租户、不同资源或不同副作用。
- resolved 必须有验证证据和残余风险记录。

### Incident 生命周期

```text
detected -> acknowledged -> declared -> investigated -> contained
-> eradicated -> recovered -> validated -> communicated -> closed
```

- severity 变化需记录原因和 actor。
- close 前检查证据保留、监控恢复、补丁、回归测试和用户沟通。

## 安全决策流程

### 请求进入流程

```text
authenticate -> bind tenant/workspace/session -> resolve trust
-> classify resource sensitivity -> load policy snapshot
-> select tool/model capability -> compile context/prompt
-> egress preflight -> budget/rate preflight -> execute or ask
```

### 工具调用决策

```text
model emits complete call
-> validate call ID/name/schema/size
-> canonicalize paths/URLs/queries
-> classify effect and risk
-> check tenant/workspace/resource scope
-> evaluate policy
-> issue obligations
-> request scoped approval
-> create sandbox
-> final boundary recheck
-> execute -> record receipt/result -> redact egress
```

### Egress 决策

```text
payload classify -> origin/provenance -> sensitivity
-> provider/endpoint jurisdiction -> tenant policy
-> purpose/retention -> redaction transform
-> size/secret/PII scan -> allow | summarize | artifact_only | deny
```

### 告警分诊流程

```text
signal ingest -> schema/integrity check -> deduplicate
-> correlate identity/run/resource -> score severity/confidence
-> enrich with policy/approval/sandbox/receipt
-> create or update incident -> assign owner
-> containment decision -> notify/escalate -> evidence checkpoint
```

### 优先级规则

- 先处理仍在进行的外部副作用，再处理历史读取异常。
- 先处理跨租户、secret、未授权写入和 sandbox fail-open，再处理质量退化。
- confidence 低但影响面高的信号进入人工验证，不自动关闭。
- 高危 deny storm 可能意味着攻击、规则误配或 provider 退化，三者分别归因。

## Secrets 与密钥生命周期

### Secret 设计规则

- 模型上下文永远不需要 secret 原文。
- Tool 只获得 capability-based handle 或短期 lease。
- secret reference、lease ID、版本和 audience 可进入受控事件；原值不得进入普通日志。
- 认证失败只记录 category、provider、credential class 和 request ID。
- provider 请求使用最小权限、最小 scope、最短 TTL 和明确 region。
- secret-like 输出通过 redaction、tokenization、drop 或 quarantine 处理。

### Key Registry

```typescript
interface KeyRegistry {
  register(record: SecretRecord): Promise<void>;
  issueLease(request: LeaseRequest): Promise<CredentialLease>;
  renew(leaseId: string): Promise<CredentialLease>;
  revoke(secretId: string, reason: string): Promise<void>;
  listVersions(secretId: string): Promise<SecretRecord[]>;
}
interface LeaseRequest {
  tenantId: string;
  purpose: SecretRecord["purpose"];
  audience: string;
  scopes: string[];
  runId: string;
  maxTtlMs: number;
}
```

### 轮换流程

1. 发现过期、暴露、provider 失效或计划轮换原因。
2. 创建 staged 版本并验证格式、scope、tenant binding 和 endpoint。
3. 在非破坏性 health probe 中验证新版本。
4. 小范围切换并比较认证、错误、usage 和副作用指标。
5. 完成全量切换，撤销旧 lease 和旧版本。
6. 查询缓存、队列、artifact 和日志，确认没有明文残留。
7. 将旧版本置为 revoked，保存轮换证据。

### 泄漏响应

- 立即停止发放旧版本 lease。
- 撤销 token、API key、云角色 session 或 webhook secret。
- 按 source event、artifact、trace、tenant 和 provider 查询传播范围。
- 禁止仅删除日志行；保留删除审计和泄漏范围摘要。
- 轮换后运行 synthetic canary、egress 扫描和最小权限回归。
- 将 secret 事件升级到 incident，而非只创建普通告警。

## Provider Egress

### EgressProfile

```typescript
interface EgressProfile {
  profileId: string;
  tenantId: string;
  allowedProviders: string[];
  allowedApiFamilies: string[];
  allowedRegions: string[];
  allowedDataClasses: Sensitivity[];
  redactionProfile: string;
  allowedDestinations: string[];
  retentionConstraints: string[];
  requireArtifactFor: Sensitivity[];
  denyUnknownDestination: boolean;
  version: string;
}
```

- Provider、API family、deployment、region、credential 和 endpoint 都独立校验。
- `OpenAI-compatible` 不能免除 provider、region、能力和数据驻留检查。
- URL、附件和 artifact source 必须经过 destination allowlist 与 DNS/IP policy。
- 外部 provider response 不能直接成为 policy instruction。
- provider metadata 进入 ProviderPart 或受控 artifact，不直接进入 UI 或权限判断。
- egress 失败采用 `deny`、`summarize`、`artifact_only` 或安全降级，不静默发送。

### 数据分类

| 类别 | 示例 | 默认 provider 行为 | 日志行为 |
|---|---|---|---|
| public | 公共文档 | 可发送 | hash/metadata |
| internal | 项目代码 | 需 tenant allow | 脱敏摘要 |
| confidential | 客户资料 | 指定 provider/region | metadata-only |
| secret | token、cookie | 禁止 | 不记录原文 |
| regulated | 受监管数据 | 专用审批/区域 | restricted artifact |

### Egress 证据

- payload classification version。
- ContextPlan、PromptPlan、toolset 和 redaction hash。
- provider/model/deployment/region 和 policy snapshot。
- allow/transform/deny decision、reason code 和 actor。
- 内容 hash、大小、字段计数和 artifact ref，而不是默认原文。
- 失败 provider response 的 request ID、错误分类和安全摘要。

## Prompt、Tool 与数据注入

### Authority 分层

```text
system/product policy > organization policy > tenant policy > trusted workspace rule
> user task > verified evidence > retrieved/tool content > model-generated text
```

- 外部内容只拥有数据 authority，不拥有 policy、tool、approval 或 identity authority。
- 代码注释中写的“忽略安全规则”只是文件内容。
- 工具结果中的 URL、命令、路径和 JSON 字段必须重新校验。
- retrieved content 不能注册工具、扩大 scope、请求 secret 或绕过 approval。

### Injection 防御链

1. 在资源进入 Context 前记录 origin、tenant、sensitivity 和 trust。
2. 用明确的 untrusted wrapper 与安全 delimiter 包装外部内容。
3. Context Compiler 删除或隔离 instruction-like 字段。
4. Prompt 明确区分任务、规则、证据和不可信数据。
5. 模型输出的工具名、参数和目标由 Tool Runtime 再验证。
6. 工具结果回流前做 schema、size、secret 和 egress 扫描。
7. 高风险动作仍需 Policy、Approval 和 Sandbox。
8. 注入检测信号进入 audit 和 regression dataset。

### Tool 安全元数据

```typescript
interface ToolSecurityProfile {
  toolName: string;
  version: string;
  owner: string;
  source: "builtin" | "workspace" | "plugin" | "mcp" | "remote";
  effect: "read" | "write" | "external" | "admin";
  requiredScopes: string[];
  sensitivityIn: Sensitivity[];
  sensitivityOut: Sensitivity[];
  idempotency: "none" | "keyed" | "natural";
  networkTargets: string[];
  filesystemRoots: string[];
  processCapabilities: string[];
  riskDefault: RiskRating;
  schemaHash: string;
}
```

- tool description、schema、实现和 security profile 必须版本对应。
- description 不得声明超出实际 capabilities 的权限。
- 工具输出的错误、日志和第三方文本都按不可信数据处理。
- 大结果写 artifact，模型只收到 summary、hash、范围和敏感性。
- `unknown`、`denied`、`cancelled` 不能伪装成成功文本。

### Prompt 注入检测信号

- 外部内容要求读取 secret、修改 policy、执行隐藏命令或联系新 endpoint。
- 工具结果改变 task objective、approval actor 或 tenant ID。
- workspace 配置要求静默上传文件或关闭 sandbox。
- 多次重复调用相同不可逆动作且无状态推进。
- 模型声称已获批但没有对应 ApprovalDecision。

## Sandbox、Permission 与 Approval

### 四层边界

```text
visibility -> call validation -> action authorization -> execution isolation
```

- visibility 决定模型看不看得到工具。
- call validation 校验工具名、参数 schema、大小和语义范围。
- action authorization 决定是否允许、需要什么审批和 obligations。
- execution isolation 决定文件、网络、进程和资源真实边界。

### SandboxProfile

```typescript
interface SandboxProfile {
  profileId: string;
  filesystem: { roots: string[]; readOnly: boolean; followSymlinks: boolean };
  network: { mode: "none" | "allowlist" | "restricted"; destinations: string[] };
  process: { allow: string[]; deny: string[]; maxChildren: number };
  resources: { cpuMs: number; memoryBytes: number; diskBytes: number; wallClockMs: number };
  environment: { allowVars: string[]; secretHandles: string[] };
  failMode: "closed" | "quarantine";
  version: string;
}
```

- canonicalize 路径并检查 `..`、symlink、junction、mount 和 reparse point。
- workspace 根目录与允许根目录取交集，不能以相对路径绕过。
- 网络 allowlist 解析域名、重定向和最终 IP；拒绝内网和 metadata endpoint，除非明确允许。
- sandbox unavailable 时高风险命令 fail-closed。
- attestation 必须证明 profile 实际应用，而不是仅记录请求值。
- 取消时终止整个 process tree、释放 lease 和隔离未知副作用。

### Approval 规则

- approval 绑定 tenant、run、tool call、arguments hash、resource scope、policy version 和 expiry。
- `allow_once` 不自动转换为全局 allow。
- 修改参数、路径、URL、账户、文件范围或 effect 后必须重新审批。
- Host 无法展示安全摘要或无法返回可靠 decision 时保持 pending/deny。
- approval UI 不显示 secret 原文；显示最小必要路径、目的、影响和回滚能力。
- 自动审批只允许低风险、幂等、scope 明确且策略允许的动作。
- commit、push、deploy、删除、外部发送和凭据变更分别审批。

## Audit、Forensics 与事件管道

### Audit 最小事实

- 谁：principal、actor type、auth method、tenant、workspace。
- 何时：occurred、observed、monotonic duration、timezone。
- 做什么：action、tool/model、resource、effect、arguments hash。
- 依据什么：policy、trust、approval、sandbox、egress、config snapshot。
- 结果如何：success、denied、unknown、receipt、error category。
- 影响什么：文件、artifact、endpoint、数据库、消息和租户范围。
- 如何证明：event IDs、hashes、receipt、snapshot、artifact refs。

### Event Pipeline

```text
Provider/Kernel/Harness events
-> canonical envelope
-> security classifier
-> redactor
-> audit writer + operational stream
-> enrichment/correlation
-> detector/rule engine
-> alert store/SIEM
-> incident system
-> forensic archive
```

- canonical event 是 source of truth，SIEM 是分析投影。
- audit writer 与普通 telemetry 分离，关键事件优先级更高。
- redaction 在离开可信边界前完成；redaction 失败按 sink policy fail-closed。
- event ID、sequence、causation、trace、tool execution 和 approval 建因果链。
- 事件不可变追加；投影可重建，原事件不能被“修正”覆盖。
- 事件延迟、丢弃、gap、重复和 schema unknown 都是安全指标。

### Forensic Bundle

```typescript
interface ForensicBundle {
  bundleId: string;
  incidentId: string;
  scope: { tenants: string[]; runs: string[]; timeRange: [string, string] };
  eventRefs: string[];
  auditRefs: string[];
  artifactRefs: string[];
  snapshots: string[];
  hashes: Record<string, string>;
  collectionMethod: string;
  collectedBy: string;
  collectedAt: string;
  retentionUntil: string;
  redactionState: string;
}
```

- 采集先冻结 scope、时间窗和 retention hold。
- 复制原事件或内容必须生成 hash、链式校验和访问审计。
- 对外共享只使用最小化、脱敏和批准后的 bundle。
- 不把调查者的解释写回原始事件；解释写入附加 timeline。
- forensic bundle 到期后删除内容并保留删除事实。

### 完整性

- 单流 sequence 检查 gap、重复 terminal 和事件顺序。
- batch 使用 previous hash、event hash 和可选签名。
- 存储使用 append-only/WORM 或等价访问控制，能力不足时明确限制。
- integrity failure 触发安全信号，不静默重建原事件。
- 投影 mismatch 只修复 projector，不修改 audit source。

## SIEM、告警与分诊

### SIEM 事件契约

```typescript
interface SiemRecord {
  schemaVersion: string;
  eventTime: string;
  eventType: string;
  severity: RiskRating;
  tenantHash?: string;
  workspaceHash?: string;
  actorHash?: string;
  runHash?: string;
  source: string;
  outcome: string;
  reasonCodes: string[];
  correlationId?: string;
  evidenceRefs: string[];
  redactionState: "metadata_only" | "redacted";
}
```

- SIEM 只接收允许的字段集合和 sensitivity 等级。
- 高基数 ID 默认 hash 或放在受控索引，不作为普通 metric label。
- provider、tool、policy、sandbox、tenant 维度可聚合，但不得暴露 secret 或完整路径。
- SIEM 发送失败写本地 bounded buffer、告警并按风险策略 fail-closed。

### Detector 类型

- 规则：未审批高风险调用、sandbox unavailable、跨租户 ref、secret pattern、异常 egress。
- 统计：短时拒绝爆发、工具调用放大、token/egress 异常、provider 认证失败。
- 关联：同一 actor 多 workspace、同一 artifact 多租户、同一 secret 多 endpoint。
- 行为：Doom-loop、重复副作用、异常夜间 break-glass、规则变更后 deny storm。
- 完整性：sequence gap、audit sink lag、hash chain 断裂、projector mismatch。

### Alert 去重与分组

- 相同 detector、scope、resource、窗口和 root cause 可聚合。
- 不同 tenant、不同 secret、不同外部副作用必须分组隔离。
- suppressed alert 仍保留 count、first/last seen 和 suppression reason。
- 告警规则版本和去重 key 进入事件记录。
- 告警关闭需附 evidence，不以恢复正常指标自动清除高危事件。

### 分诊问题

1. 是否仍有进行中的高风险副作用？
2. 是否涉及跨租户、secret、凭据或身份伪造？
3. 是否能确定真实影响范围和攻击路径？
4. sandbox、policy、approval、egress 哪一层失效？
5. 是否是规则误配、provider 退化或真正攻击？
6. 是否需要暂停 tool、provider、workspace、tenant 或全局入口？
7. 证据是否完整、可信、未被污染？
8. 需要通知哪些 tenant、owner、法务或供应商？

## 事件严重度与事件响应

### Severity 定义

| 级别 | 例子 | 初始响应 | 目标 |
|---|---|---|---|
| SEV0 | 大范围 secret/跨租户或持续破坏性副作用 | 立即全员响应 | 先停止传播，持续指挥 |
| SEV1 | 单/多租户未授权外发、付款、删除、部署 | 立即值班升级 | 快速 containment 与影响确认 |
| SEV2 | 高风险控制绕过、sandbox fail-open、供应链高危 | 值班响应 | 限制影响并修复 |
| SEV3 | 可利用漏洞、异常滥用、审计缺口 | 工作时段升级 | 补丁、规则与回归 |
| SEV4 | 低风险诊断、配置漂移、轻微误报 | 排队处理 | 改进检测和文档 |

- severity 由影响、可利用性、持续性、可传播性、数据敏感度和证据置信度共同决定。
- 低置信度不能自动降低高影响事件级别。
- 误报只能关闭信号，不能删除原始证据。

### Containment

- 暂停受影响 tool、plugin、MCP、provider route、workspace 或 tenant。
- 撤销 credential lease、token、approval 和 background worker lease。
- 启用 read-only、dry-run、quarantine 或 deny-all 安全模式。
- 隔离可疑 artifact、workspace snapshot、插件包和网络目的地。
- 保留进程、事件、receipt、文件 diff 和队列状态，避免先清理再取证。
- 对未知副作用调用 status query，不盲目 retry 或 revert。

### Eradication

- 修复 Policy、sandbox、schema、path、egress、identity 或供应链根因。
- 轮换受影响 secrets 和签名密钥，清除缓存和旧 lease。
- 删除恶意插件、hook、MCP 配置和临时 worker，验证没有残留进程。
- 更新依赖、adapter、规则、模型 allowlist 或 provider route。
- 添加最小回归 scenario、deterministic oracle 和 CI gate。

### Recovery

- 在隔离环境用固定 fixture 重放攻击链。
- 验证 tenant、workspace、artifact、audit 和 receipt 一致性。
- 小范围 canary 恢复，观察 deny、egress、副作用和异常指标。
- 恢复权限遵循由低到高、由单租户到多租户的顺序。
- recovery 不等于 incident close；需要 residual risk 和 owner。

### Post-incident

- 保存 timeline、决策、证据、影响、根因和未解决问题。
- 复核 detector 是否漏报、误报、延迟或被采样掉。
- 复核是否存在保护控制、审批、审计或回滚缺口。
- 将动作转成 owner、due date、验收测试和 runbook 更新。
- 按通知策略向受影响租户提供准确、最小化的事实。

## 漏洞、补丁、依赖与供应链

### 资产清单

- runtime、provider adapter、SDK、transport、sandbox backend 和 host adapter。
- Tool、Skill、插件、MCP、LSP、hook、package、镜像和生成器。
- Model catalog、prompt/context compiler、policy bundle 和规则脚本。
- Worker、queue、event store、artifact store、SIEM connector 和 dashboard。

### VulnerabilityRecord

```typescript
interface VulnerabilityRecord {
  id: string;
  component: string;
  version: string;
  source: "scanner" | "provider" | "research" | "incident" | "advisory";
  severity: RiskRating;
  exploitability: "unknown" | "low" | "medium" | "high";
  affectedScopes: string[];
  mitigation: string[];
  fixedVersion?: string;
  dueAt: string;
  owner: string;
  status: "open" | "mitigated" | "patched" | "accepted" | "closed";
  evidenceRefs: string[];
}
```

### 补丁流程

```text
inventory -> detect -> validate applicability -> risk rank -> isolate/mitigate
-> reproduce -> patch/update -> conformance/security regression
-> staged rollout -> monitor -> close or risk-accept
```

- 高危 sandbox、secret、cross-tenant 和远程执行漏洞优先于一般质量问题。
- 暂无补丁时使用 capability disable、egress deny、version pin、quarantine 或 route removal。
- 依赖更新必须记录 lockfile、hash、来源、许可证和测试证据。
- provider SDK 升级要跑 raw frame replay、stream、tool、usage 和 error conformance。
- 风险接受必须有 scope、期限、补偿控制和签字人，不能永久绕过。

### Supply Chain Provenance

- 包、插件、Skill、MCP server 和模型配置记录来源、版本、digest、签名状态和 owner。
- 未知来源、篡改 digest、签名无效或依赖冲突进入 quarantine。
- 安装脚本、postinstall、hook 和 env loader 不因依赖声明自动执行。
- 生产允许清单与开发允许清单分离。
- 生成代码记录 generator、输入 hash、输出 hash 和版本。
- vendor 变更记录上游来源、许可证、补丁和审计结果。

## 插件、Skill、MCP 与扩展

### ExtensionTrust

```typescript
interface ExtensionTrust {
  extensionId: string;
  kind: "skill" | "plugin" | "mcp" | "lsp" | "hook";
  source: string;
  version: string;
  digest: string;
  signature?: string;
  publisher?: string;
  trust: "unknown" | "reviewed" | "trusted" | "quarantined";
  allowedTenants: string[];
  allowedTools: string[];
  sandboxProfile: string;
  expiresAt?: string;
}
```

- registry 事务化注册：所有依赖成功后才提交 active toolset，失败则回滚。
- 扩展描述、返回值和日志不拥有 policy authority。
- MCP transport、server process、工具列表和 endpoint 分别审计。
- MCP server 只能访问显式资源和网络 allowlist，不能继承 host 全部环境。
- Skill 可影响 Prompt 但不能修改 capability、approval 或 retention。
- hooks 运行前要通过 trust、scope、sandbox 和命令 policy。
- 插件升级或配置变化使 toolset hash 变化，已有 approval 不自动复用。

## 滥用防护与速率限制

### 预算层次

```text
organization -> tenant -> workspace -> principal -> session -> run -> attempt -> tool
```

- 每层同时限制请求数、并发、模型 tokens、工具次数、网络字节、artifact、CPU、磁盘和子 Agent。
- 父级剩余预算是子级预算上限；reserved 与 actual 分开记录。
- 高风险工具使用更严格的 burst、冷却和人工审批。
- deny、retry、fallback、compaction 和失败调用也计入资源使用。

### RateLimitPolicy

```typescript
interface RateLimitPolicy {
  key: "tenant" | "workspace" | "principal" | "ip_hash" | "tool" | "provider_route";
  windowMs: number;
  capacity: number;
  refillPerSecond: number;
  burst: number;
  action: "throttle" | "queue" | "deny" | "step_up_auth";
  exemptions: string[];
  version: string;
}
```

- 多维 key 防止单一 IP 或用户维度被绕过。
- 限流响应不泄露其他租户存在性或内部 quota。
- queue 必须有 lease、expiry、priority 和取消语义。
- fallback 不能绕过租户或 provider egress 额度。
- 异常放大包括 retry storm、subagent fan-out、tool loop、artifact flood 和 event flood。

### Abuse Signals

- 相同工具、参数和资源的短时重复调用。
- 多 workspace 使用同一 credential 或 endpoint。
- 大量 deny 后改变参数探测 schema、路径或 approval。
- 生成大量外发 URL、文件压缩包或消息。
- 通过错误、timeout、断线制造重复 side effect。
- 反复创建 background run、subagent 或大上下文。
- 用户行为与正常工作模式显著偏离。

## 保留、删除、导出与 Break-glass

### RetentionClass

```typescript
interface RetentionClass {
  id: string;
  dataKinds: string[];
  defaultTtlMs: number;
  legalHoldAllowed: boolean;
  deletionMode: "hard" | "crypto_shred" | "redact" | "archive";
  owner: string;
  version: string;
}
```

- ephemeral delta：秒到小时；普通 telemetry：天到月；session/artifact/audit 按产品和合规策略。
- retention 必须按 tenant、sensitivity、purpose 和 legal hold 计算。
- 删除内容前检查 event、artifact、projection、cache、queue、SIEM 和 forensic 引用。
- 删除任务幂等、可重试、可审计，并输出 count/hash/失败项摘要。
- legal hold 冻结内容但不扩大访问范围。
- 导出重新授权、最小化、脱敏、限时 URL 和访问审计。

### Break-glass

- 仅在常规权限无法处置正在进行的高风险事件时使用。
- grant 绑定 purpose、incident、tenant、resource、命令、TTL、双人审批和证据要求。
- 默认 read-only、metadata-only、最小 scope；高风险写入必须逐动作确认。
- break-glass 使用实时告警、命令审计、session 录制摘要和自动过期。
- 事件结束立即 revoke，查询所有访问、导出和命令结果。
- 未使用或超时 grant 也写状态，不能静默删除。

### 删除验证

```text
request -> authorize -> hold check -> dependency scan -> mark deleting
-> delete content -> invalidate projections/cache -> verify absence
-> write deletion audit -> notify completion/failure
```

## 与 Model/Prompt/Context/Tool/State/Policy/Harness 集成

### Model

- Model Runtime 接收 immutable routing、credential lease、egress 和 policy snapshot。
- provider adapter 不读取租户数据库、不选择隐式 fallback、不执行工具。
- provider usage、finish、safety、request ID 和 raw reference 进入受控事件。
- provider response 全部视为不可信，不能覆盖 `tenantId`、scope 或 policy。
- fallback 重新检查能力、区域、数据分类、预算和审批状态。

### Prompt

- Prompt 解释当前安全模式、工具 effect、审批和不可信数据边界。
- Prompt 不实现 path、network、secret、timeout、schema 或 policy enforcement。
- 不把 secret、完整 credential、受监管原文或无关 tenant 内容编入 prompt。
- prompt version、section hash 和 authority 级别记录在 snapshot。

### Context

- ContextPlan 保存 source、provenance、trust、sensitivity、freshness、egress 和 artifact ref。
- 先做租户 scope 和 egress，再做相关性排序和 token 裁剪。
- tool call/result、approval、policy 和安全规则保持成对与版本一致。
- 大输出 artifact-only；模型只获得安全摘要和证据引用。
- context compaction 不删除 pending approval、unknown outcome、incident signal 或 secret exposure evidence。

### Tool

- Tool Registry 提供 schema、effect、security profile、owner、version 和 capability。
- Tool Runtime 在 call boundary 和 execution boundary 双重校验。
- 路径、URL、SQL、command、archive 和 JSON 均使用结构化解析或 allowlist。
- 外部副作用使用幂等键、receipt、状态查询和补偿策略。

### State

- Session 保存语义事实；Audit 保存治理事实；Event Store 保存可重放事件。
- 记录 IdentityBound、TrustChecked、PolicyEvaluated、Approval、SandboxAttested、Egress、SecretLease、ToolOutcome、UnknownOutcome 和 Incident。
- 状态投影按 tenant 过滤，replay 只重建状态不执行副作用。
- 变更、policy、toolset、sandbox、egress 和 key 版本不可被原地改写。

### Policy

```text
identity -> tenant/workspace scope -> trust -> visibility
-> schema/action policy -> approval -> sandbox -> egress -> audit
```

- Policy 决定是否允许与 obligations；Sandbox 决定实际边界。
- policy deny、approval expire、sandbox fail-open 和 egress deny 都是 durable 事实。
- mode 改变必须同时改变 active toolset、sandbox、prompt、completion criteria 和 delivery。

### Harness

- Harness 创建 RunScope、预算、task group、event router 和 cancellation tree。
- Harness 冻结 config snapshot，监督所有 model/tool/approval/process/worker。
- Harness 在每个不可逆动作前后写 checkpoint 和 audit。
- Harness 处理 retry、fallback、unknown outcome、quarantine、recovery 和交付。
- Host 断开不等于取消；后台 worker 继续时必须受同一 tenant、policy 和 lease 控制。

## 故障恢复与业务连续性

### 故障分类

- identity/tenant resolution failure。
- policy catalog、trust registry 或 key broker unavailable。
- provider stream、tool process、sandbox 或 network failure。
- event store、audit writer、SIEM、artifact 或 projector failure。
- approval host disconnect、worker loss、lease expiry 和 process crash。
- side effect 已发生但 result、receipt 或 durable commit 未完成。

### 恢复流程

```text
load checkpoint -> verify identity/scope/config -> inspect open actions
-> query side-effect receipt -> classify known/unknown
-> revoke unsafe leases -> rebuild policy/sandbox
-> resume safe work | quarantine | manual review
```

- audit writer 故障时，高风险动作暂停；普通 telemetry 可 bounded degrade。
- sandbox 故障时只保留 read-only/metadata 任务。
- key broker 故障不缓存或打印 secret 来维持服务。
- 未知副作用先查询外部事实、幂等记录或补偿接口。
- 重启 worker 不得并行重放同一不可逆动作。
- 恢复完成需验证 event sequence、policy、tenant、side effect count、usage 和 terminal。

### 可用性降级矩阵

| 故障 | 允许 | 禁止 |
|---|---|---|
| SIEM 不可用 | 本地安全队列、只读诊断 | 丢 audit 或无告警继续高危写入 |
| Sandbox 不可用 | 本地只读 | 任意 shell、网络写入、外部副作用 |
| Approval host 断开 | 保持 pending | 自动 allow |
| Key broker 不可用 | 无 secret 的本地任务 | 使用过期/未绑定凭据 |
| Event projector 落后 | 查询 source event | 宣称已完成或忽略 gap |
| Provider 断流 | 保存 incomplete、有限 retry | 执行截断 tool call |
| Artifact store 不可用 | 小型 metadata 结果 | 假装完整证据存在 |

## 安全测试策略

### 测试分层

- 单元：scope、policy precedence、risk、redaction、path/URL、hash、状态机。
- 组件：Credential Broker、Egress Evaluator、Sandbox Backend、Audit Writer、Detector。
- 契约：Model Runtime、Tool、MCP、Plugin、Host、SIEM、Event Store。
- 集成：真实 Harness + fake model/tool + deterministic clock/IDs/store。
- 场景：注入、越权、secret、跨租户、审批、沙箱、恢复、滥用。
- 生产前：replay、shadow、canary、load、chaos、供应链扫描和 tabletop。

### SecurityTestScenario

```typescript
interface SecurityTestScenario {
  id: string;
  attacker: string;
  entrypoint: string;
  trustBoundary: string;
  assets: string[];
  fixture: string;
  expectedDecisions: string[];
  forbiddenEffects: string[];
  evidenceAssertions: string[];
  risk: RiskRating;
}
```

### 必测场景

1. 恶意文档要求读取 `.env`、发送外网并修改 policy。
2. 工具结果伪造 approval、tenantId 或 admin actor。
3. path traversal、symlink、junction、archive zip-slip 和 Windows reparse point。
4. URL 重定向到内网、metadata endpoint、localhost 或未允许端口。
5. provider output、MCP response、插件日志包含 synthetic secret。
6. 用户尝试读取另一个 tenant 的 session、artifact、trace 和 replay。
7. approval 后改变参数、路径、账户、scope 或工具版本。
8. sandbox unavailable、attestation mismatch、资源超限和进程逃逸。
9. provider 断流、tool side effect 后 crash、receipt 丢失和 retry。
10. 未信任 workspace 自动加载 hook、Skill、MCP、LSP 或 env loader。
11. 依赖 digest、签名、lockfile、许可证或 provenance 不一致。
12. rate limit、subagent fan-out、retry storm、artifact flood 和 event flood。
13. break-glass 过期、双人审批缺失、超 scope 访问和未 revoke。
14. audit hash chain 断裂、event gap、SIEM lag、projection mismatch。
15. 删除、legal hold、导出、跨区域 provider 和 retention expiry。

### 断言原则

- 不仅比较最终文本，还断言 policy、approval、sandbox、egress、audit 和 side effect。
- 一次未授权副作用、secret 外泄或 cross-tenant 访问即 hard fail。
- deny、unknown、inconclusive 与 pass 分离。
- 使用 synthetic canary secret，不使用生产凭据。
- 记录 code、config、policy、toolset、sandbox、dataset、provider 和 fixture 版本。
- 每个漏洞回归都带最小复现、根因、修复版本和长期检测。

## Tabletop 与 Runbook

### Tabletop 设计

- 每季度至少覆盖一次 provider key 泄漏、恶意 MCP、sandbox fail-open 和跨租户事件。
- 参与者包含 incident commander、security、runtime、tool owner、tenant support、legal/compliance 和 communications。
- 场景输入按时间注入：首个 signal、攻击扩散、provider 争议、证据不完整、用户询问和恢复压力。
- 观察是否能在不查看 secret 原文的情况下确定 scope、containment 和通知。
- 记录决策延迟、角色混乱、缺失工具、runbook 死链接和未测试的降级路径。

### Secret Leak Runbook

1. 宣布 SEV1/SEV0 候选，建立 incident channel 和 timeline。
2. 冻结泄漏 credential 的新 lease 和相关 route。
3. 查询 event、artifact、trace、provider request、tenant 和外发 endpoint 范围。
4. 对可疑 workspace/tool/MCP/worker quarantine。
5. 轮换 secret，验证旧 lease/token 已 revoke。
6. 运行 canary 和 redaction scan，确认没有持续外发。
7. 通知受影响 owner，保存最小事实和剩余不确定性。
8. 添加 injection/egress/secret 回归测试并更新 detector。
9. 验证恢复后再关闭 incident。

### Cross-tenant Runbook

1. 立即暂停相关 query、artifact、replay 和 worker route。
2. 按 tenant、workspace、principal、cache、queue、trace 和时间窗建立 scope。
3. 保留 source event、access audit、store query 证据和 projection 状态。
4. 关闭跨 tenant token、缓存键和共享 artifact URL。
5. 验证租户隔离、删除/导出和通知边界。
6. 修复 predicate、identity binding、缓存或 worker 归因。
7. 用双租户 deterministic fixture 验证正向允许和负向拒绝。

### Sandbox Fail-open Runbook

1. 将危险执行切换为 deny/quarantine/read-only。
2. 列出使用故障 profile 的 runs、workers、tool calls 和副作用。
3. 查询 process tree、文件 diff、网络连接和 side-effect receipt。
4. 隔离受影响 workspace 与扩展，撤销 elevated lease。
5. 修复 backend/profile/attestation，运行逃逸和边界回归。
6. canary 后逐级恢复，保留 residual risk 和 evidence。

## 指标、SLO 与报告

### 安全指标

- unauthorized action count，按 effect、tenant、tool 和 policy version 聚合。
- approval bypass、scope mismatch、expired approval reuse 次数。
- sandbox fail-open、attestation mismatch、quarantine 数量。
- secret detection、redaction failure、egress deny 和 data-class downgrade。
- cross-tenant access attempt、isolation test failure 和 cache contamination。
- audit append success、hash-chain failure、event gap、SIEM lag 和 dropped critical events。
- mean time to detect、acknowledge、contain、eradicate、recover、validate。
- vulnerability age、patch SLA、dependency provenance coverage 和 stale component 数。
- rate-limit hit、retry amplification、subagent fan-out 和 high-cost abuse。
- break-glass grants、duration、scope violations 和 revoke latency。

### SLO 示例

```text
critical audit durability = queryable critical audit / accepted critical action
security decision coverage = actions with policy decision / eligible actions
approval binding correctness = bound approvals / approved high-risk actions
cross-tenant isolation failures = 0
secret redaction escapes = 0
sandbox fail-open = 0
SIEM delivery availability = delivered security records / emitted security records
```

- SLO 分母包括失败、deny、cancel、unknown 和未完成 run，不只统计成功。
- 安全零容忍指标不使用平均数稀释单次严重失败。
- latency 记录 policy、approval、sandbox、audit 和 SIEM 各阶段。
- cost/usage 与 security signal 关联，用于识别异常放大而不暴露内容。

### 报告字段

- 时间窗、scope、版本、tenant aggregation、数据分类和 retention class。
- 信号、告警、incident、处置、残余风险和 evidence refs。
- detector、policy、sandbox、tool、provider、extension 版本。
- hard failure、inconclusive、误报和数据缺失分开。
- 趋势、分位数、SLO、top root causes 和 corrective actions。

## 反模式

1. 只在 system prompt 写“不要泄露 secret”。
2. 用 `allowSubagent` 或 `allowTool` 一个布尔值代替 scope、policy 和 sandbox。
3. 把工具可见性当作工具授权。
4. 父 run approval 被 child、重试或参数变更复用。
5. provider safety filter 代替本地 egress 和权限控制。
6. 未信任 workspace 自动执行 package scripts、hooks、MCP 或 env loader。
7. sandbox 请求成功就假设隔离已生效，没有 attestation。
8. 任意模型输出路径、URL、命令或 SQL。
9. tool result 可覆盖 tenant、actor、policy 或 approval 字段。
10. 将完整 prompt、工具参数、secret 和用户文件写入 telemetry。
11. SIEM 事件没有 schema、tenant scope、版本或 redaction 状态。
12. 普通 debug log 冒充 audit，无法证明不可变和完整性。
13. 只告警不保存因果链、receipt、approval 和 sandbox 证据。
14. 发现 secret 泄漏只删日志，不轮换、不查传播范围。
15. 事件恢复只重启进程，不查询 unknown side effect。
16. 通过无限 retry、fallback 或 subagent 绕过 quota。
17. 将跨 tenant 查询放入共享缓存而不做 scope key。
18. 删除时不处理 projection、artifact、SIEM、cache 和 legal hold。
19. break-glass 无 TTL、双人审批、命令白名单和自动 revoke。
20. 漏洞风险接受没有期限、补偿控制和回归测试。
21. 插件只看名称，不验证 digest、签名、来源和行为能力。
22. MCP server 继承 host 全部环境、网络和文件权限。
23. 把误报关闭当作删除原始安全证据。
24. 只测试 happy path，不测试 crash、cancel、gap、replay 和恢复。
25. 用平均模型质量抵消一次未授权副作用。

## 实施清单

### V1：安全边界

- [ ] 定义 IdentityContext、Tenant、WorkspaceTrust、RunScope 和 ResourceScope。
- [ ] 实现 tenant/workspace 强制过滤与 artifact ownership 校验。
- [ ] 建立 ToolSecurityProfile、Model allowlist 和 EgressProfile。
- [ ] 在 Tool Runtime 最终边界执行 schema、path、URL 和 tenant 校验。
- [ ] 建立 SandboxProfile、attestation 和 fail-closed 行为。
- [ ] 建立 scoped Approval，绑定参数 hash、resource、expiry 和 policy version。
- [ ] 建立 Credential Broker、短期 lease、revoke 和 redaction。

### V2：审计与检测

- [ ] 定义 SecurityAuditEvent、SecuritySignal、Integrity chain 和 retention class。
- [ ] 分离 durable audit、operational telemetry、SIEM 和 forensic archive。
- [ ] 实现事件 normalize、redact、deduplicate、correlate 和 detector。
- [ ] 实现 cross-tenant、secret、approval、sandbox、egress 和 supply-chain 检测。
- [ ] 建立 alert triage、incident、severity、owner、escalation 和 evidence。
- [ ] 建立 Diagnostic Snapshot 的授权、脱敏和短 TTL。

### V3：响应与治理

- [ ] 定义 SEV0-SEV4、containment、eradication、recovery 和 close criteria。
- [ ] 实现 key rotation、credential leak、cross-tenant 和 sandbox runbook。
- [ ] 建立漏洞、依赖、插件、MCP、模型和配置资产清单。
- [ ] 实现 provenance、digest、签名、allowlist、quarantine 和回滚。
- [ ] 建立 tenant/workspace/principal/run/tool 多层 rate limit 和 abuse signal。
- [ ] 实现 retention、delete、export、legal hold 与 deletion verification。
- [ ] 实现 break-glass 双人审批、TTL、实时审计和自动 revoke。

### V4：测试与运营

- [ ] 构建 deterministic security testkit、fake provider/tool、fake approval 和 fake sandbox。
- [ ] 覆盖 injection、secret、egress、path、SSRF、cross-tenant、supply chain 和 abuse。
- [ ] 在每个 durable boundary 注入 crash、timeout、duplicate、gap 和 unknown outcome。
- [ ] 将高风险安全场景设为 CI hard gate，建立回归数据集。
- [ ] 每季度执行 tabletop，复核 runbook、通知和恢复能力。
- [ ] 建立安全 SLO、零容忍指标、趋势和审计报告。
- [ ] 运行 canary、shadow、chaos、replay 和 provider/tool conformance。

## 五个参考项目的启发来源

### Pi

- headless agent loop、统一 EventStream 和 AgentSession 启发安全事件与 Host 解耦。
- session tree、steering/follow-up、compaction 和 branch 事实启发 run、scope、checkpoint 与恢复审计。
- 工具循环、事件流和资源加载启发 tool call/result、context provenance 与安全边界分离。
- CLI、TUI、RPC 共用 runtime 启发安全控制不能依赖单一 UI。
- 依据：本地参考架构、Agent Harness、Event/State/Context 文档中已记录的源码范围。

### Grok Build

- Session/ChatState/Sampler actor 启发身份绑定、单写者状态和安全配置 snapshot。
- permission decision、folder trust、sandbox 启发 visibility、authorization、approval 和 execution isolation 分层。
- 并行工具、路径级锁和输出限制启发资源 scope、side-effect serialization 与滥用控制。
- sampler/transport 分层启发 provider 失败、retry、usage 和安全事件归因。
- 依据：本地参考文档所列 session、sampler、tools、permission、sandbox 源码结论。

### OpenCode

- client/server、session/message/part、event bus 启发 durable security event、projector 和多客户端安全交付。
- permission、tool、MCP/LSP 分离启发扩展 provenance、能力声明与实际授权分开。
- snapshot/patch/revert 启发 forensic baseline、文件副作用证据与冲突恢复。
- server/event 架构启发 SIEM、audit、replay 和 cursor 不依赖 Host 连接。
- 依据：本地参考文档所列 session、server、permission、tool、snapshot 源码结论。

### Claude Code

- permission modes、hooks、skills、subagents、memory 和项目规则启发模式化安全边界、最小上下文与 scoped approvals。
- 任务/计划工作流启发高风险动作的 acceptance、human-in-the-loop 与事后验证。
- MCP 与扩展边界启发未信任内容不能新增 authority，扩展需要独立治理。
- 公开安全语义以本地文档已标注的 Anthropic 官方资料为准，辅助源码不作为规范。
- 依据：本地 Context、Harness、Permission/Sandbox、Subagent 文档的已调研归纳。

### OpenClaw

- AgentHarness registry 启发 Security Control Plane 通过 registry 组合 model、tool、sandbox、host 和 provider 能力。
- agent-core 与 Gateway/channel 分层启发安全事件、后台 worker、交付和身份 scope 解耦。
- tool/sandbox/elevated 分离启发高风险执行、break-glass 和独立 attestation。
- 后台运行、memory flush、事务化插件启发 lease、checkpoint、扩展回滚与失败恢复。
- 依据：本地参考文档所列 agent-core、harness/registry、openclaw-tools、plugins、Gateway 源码结论。

本设计的实现审查应回到已有本地参考文档和其记录的一手源码范围；新增 provider、插件、合规区域或组织策略时，应另行补充证据、迁移方案、版本和契约测试。
