# Agent Creator Skill：契约驱动的可验证控制面

## 本轮目标

先把当前文档型 Skill 升级为“可路由、可校验、可回归”的工程资产，再在下一轮基于稳定契约增加 Python/TypeScript Starter Kit。这样可以避免模板、文档和 Eval 各自定义不兼容概念。

## 1. 建立唯一 Canonical Contract

新增 `references/canonical-contract.md`：

- 定义稳定术语和编号：`TERM-*`、`INV-*`。
- 统一 API Family、Provider、Model、Deployment、Agent Kernel、Harness、Attempt、Trial、ToolCall、ToolExecution、Policy、Approval、Sandbox、Canonical Event、Session、Artifact、Unknown Outcome 等概念。
- 明确每个核心概念的规范所有者、消费者和禁止混淆项。
- 固化跨文档不变量，例如：模型输出不可信、工具调用不等于执行、审批不等于沙箱、Provider conversation state 不等于业务状态、Infra Error 不得算成功。
- 后续 Starter Kit 和工程文档只引用这些编号，不复制一套新定义。

## 2. 建立机器可读路由

新增 `references/routes.json` 作为唯一规范路由源：

- 顶层包含 `schema_version`、默认加载规则和 `routes`。
- 每条路由包含 `id`、意图、正向信号、负向信号、`primary`、最多两个 `supplements`、`contract_ids` 和优先级。
- 覆盖 architecture、API patterns、provider、protocol 和全部 engineering references。
- 明确一次任务默认只加载一个主文档和最多两个辅助文档；只有跨模块设计或审查任务才允许扩大加载范围。
- 为相近主题提供消歧信号，例如 Evaluation Runner vs Eval Dataset、Provider Conformance vs Contract Testing、Privacy vs Data Governance、Memory Product vs Memory Governance。

## 3. 收缩并修正渐进加载入口

修改 `SKILL.md`：

- 将当前大段逐文件路由列表替换为简短路由算法。
- 要求先读取 `canonical-contract.md` 中相关条目，再按 `routes.json` 选择资料。
- 保留核心 Agent 工作流、安全边界、测试要求和“快速变化信息仅查官方文档”规则。
- 保证 SKILL 主体仍是工作流入口，而不是完整文档目录。

修改 `references/engineering/index.md`：

- 声明 `references/routes.json` 是规范路由源，本页仅作人类领域概览。
- 删除或压缩与机器路由重复的完整线性阅读顺序。
- 删除“后续可继续拆分”中已经存在的四个文件，避免陈旧 Roadmap。
- 保留工程边界概览和人工浏览用途。

## 4. 增加 Skill 静态校验器

新增 `scripts/validate_skill.py`，仅使用 Python 3.10+ 标准库，检查：

- `SKILL.md` frontmatter、必要文件和基本结构。
- `routes.json` schema、路由 ID 唯一性、primary/supplement 文件存在性。
- 所有 `references/**/*.md` 都能从路由到达，不允许孤儿 Reference；导航页等明确豁免项需在配置中声明。
- 每条路由有触发信号，supplement 不自引用或形成无意义循环。
- 路由中的 `TERM-*`、`INV-*` 均存在于 Canonical Contract。
- Markdown 本地链接有效。
- `evals/evals.json` 的 ID 唯一、字段完整且每例都有 assertions。
- 高风险 Eval 至少包含一个 hard assertion 和一个禁止性断言。
- 不允许只写 `expected_output` 而没有可验证 assertions。
- “后续新增/拆分”列表不得引用已经存在的文件。
- `SKILL.md` 不再复制完整工程文档清单。

校验器应输出按类别分组的错误，并以非零退出码表示失败。

## 5. 为校验器增加 Mutation Tests

新增 `scripts/test_validate_skill.py`：

- 使用 `tempfile` 构造最小 Skill fixture，不修改真实文件。
- 覆盖正常通过。
- 覆盖缺失路由目标、重复路由 ID、孤儿 Reference、未知 Contract ID、失效 Markdown 链接。
- 覆盖 Eval 无 assertions、高风险仅 soft assertion、缺少禁止性断言。
- 覆盖 Roadmap 列出已存在文件。
- 断言错误类别和退出结果，证明校验器不是“永远通过”的装饰脚本。

## 6. 扩充 Skill 自身 Eval

修改 `evals/evals.json`：

- 保留现有三个案例和 ID。
- 增加 `schema_version`、tags、risk 和结构化 assertions。
- 扩充到约八个高区分度案例：
  1. Azure OpenAI 与 Bedrock API Family 差异。
  2. Gemini Developer API 到 Vertex AI 迁移。
  3. shell/文件/邮件工具的审批、沙箱、幂等和重复执行。
  4. 缤纷 Provider 无本地 Reference 时只使用官方资料并隔离差异。
  5. Structured Output 与 Tool Argument Schema 的区分。
  6. 流式 Tool Arguments 分片、截断和未知事件。
  7. Provider conversation、Agent execution、Business state 的所有权分离。
  8. 简单 Agent 不应无理由引入大型框架。
- Assertions 使用清晰的 `text`、`type`、`severity` 和禁止性标记；安全/API Family 混淆属于 hard failure，表达质量可作为 soft。

本轮不运行需要真实 Provider 凭据的在线 Eval；只保证数据格式、覆盖面和静态门禁完整。

## 7. 验证与验收

依次运行：

```bash
PYTHONUTF8=1 python scripts/validate_skill.py
PYTHONUTF8=1 python -m unittest discover -s scripts -p "test_*.py"
PYTHONUTF8=1 python "C:/Users/17659/.claude/skills/skill-creator/scripts/quick_validate.py" .
```

验收条件：

- 三项命令全部通过。
- 路由覆盖所有应加载的 Reference，无失效本地链接。
- Mutation Tests 能捕获预期缺陷。
- 每个 Eval 都含 assertions，高风险 Eval 满足 hard + negative 门禁。
- `SKILL.md` 的渐进加载部分显著缩短且仍能找到全部专题。
- 不修改或删除用户现有的无关内容，不创建提交。

## 本轮明确延后

- `assets/starter-kits/python/` 和 `assets/starter-kits/typescript/`。
- 完整 Eval Runner、LLM Judge 和在线 Provider Smoke Test。
- CI 平台配置。
- Retrieval、Realtime/Multimodal、Delegated Identity 新专题。

下一轮将基于本轮稳定的 Canonical Contract 和校验器，同步实现 Python/TypeScript Starter Kit，并使用共享 fixture 验证两种语言的行为对等性。