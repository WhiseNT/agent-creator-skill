# Azure AI Foundry / Azure OpenAI

> 调研基线：2026-07-20。实现前核对 Microsoft Learn 中目标区域、部署和模型的当前支持情况。

## 推荐接口

### Foundry 项目 Responses API

适合项目级 Agent、托管工具、数据隔离、身份传播、治理和可观测性。

```text
{project_endpoint}/openai/v1/responses
```

### Azure OpenAI 资源级 OpenAI/v1

适合只需要 Azure OpenAI 模型和较高 OpenAI SDK 兼容性的应用。

```text
https://<resource>.openai.azure.com/openai/v1/
```

除非特定能力要求，否则新代码不要默认使用旧式：

```text
/openai/deployments/{deployment}/...?api-version=YYYY-MM-DD
```

## 最重要的差异

`model` 通常填写 Azure **部署名**，不是模型目录中的基础模型名。

部署同时绑定模型版本、区域、容量类型、内容过滤和配额。不要根据基础模型名推断部署能力。

## 认证

生产优先使用 Microsoft Entra ID、托管身份或工作负载身份。API Key 适合简单场景。

不同 endpoint 可能使用不同 token scope；按目标 API 官方示例选择，不要全局硬编码。

## SDK

- OpenAI 接口：Python/TypeScript `openai`
- Entra 身份：`azure-identity` / `@azure/identity`
- Foundry 项目：`azure-ai-projects`

Azure AI Inference beta SDK 已弃用，官方退役日期为 **2026-08-26**；新实现应采用 GA OpenAI/v1 和稳定 SDK。

## 工具与 Agent 能力

- Chat Completions：`tools`、`tool_choice`、`tool_calls`
- Responses：工具定义与 output item / stream event
- Foundry 项目工具可包含 File Search、Code Interpreter、Memory、Web Search、MCP 及其他 Microsoft 数据源工具
- 客户端函数仍由应用执行并回传结果

旧 `functions` / `function_call` 不应出现在新实现中。

## 结构化输出

优先使用 strict JSON Schema。支持情况取决于模型、版本、区域和 API family。

应用端仍要再次验证，并区分拒答、内容过滤、截断和 schema 失败。

## 流式与内容过滤

OpenAI SDK 使用 `stream=True`，底层为 SSE。除文本增量外，还要处理工具调用、usage、完成和错误事件。

Azure 异步内容过滤可能在内容显示后才返回违规标记；UI 必须支持停止展示或撤回已显示内容。

## Batch

Azure OpenAI Batch 通常使用 Files + JSONL + Batch Job，并可能要求 Global Batch 部署。输入记录需要唯一 `custom_id`，且同一文件中的请求应指向一致的 URL/部署。

## 配额与错误

配额通常按订阅、区域、模型和部署类型划分。429 可能来自 TPM/RPM、突发或容量不足。

读取服务端重试头并执行指数退避；持续吞吐需求考虑合适部署容量，而不是无限重试。

## 最小 Python 示例

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.environ["AZURE_OPENAI_BASE_URL"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
)

response = client.responses.create(
    model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    input="解释工具调用。",
)

print(response.output_text)
```

## 最小 TypeScript 示例

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: process.env.AZURE_OPENAI_BASE_URL,
  apiKey: process.env.AZURE_OPENAI_API_KEY,
});

const response = await client.responses.create({
  model: process.env.AZURE_OPENAI_DEPLOYMENT!,
  input: "解释工具调用。",
});

console.log(response.output_text);
```

## 官方文档

- https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/endpoints
- https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses
- https://learn.microsoft.com/en-us/azure/foundry/agents/overview
- https://learn.microsoft.com/en-us/azure/foundry/agents/quickstarts/responses-api
- https://learn.microsoft.com/en-us/azure/foundry/openai/reference
- https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/structured-outputs
- https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/batch
- https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota
