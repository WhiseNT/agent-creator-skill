# Amazon Bedrock

> 调研基线：2026-07-20。模型支持、区域和配额必须在目标 AWS Region 中重新核对。

## 推荐接口

### Converse / ConverseStream

支持时优先使用 Bedrock 统一消息接口：

- `messages`
- `system`
- `toolConfig`
- `inferenceConfig`
- 统一的 `output`、`stopReason`、`usage` 和 `metrics`

模型特有参数放入 `additionalModelRequestFields`。

### InvokeModel

以下情况使用：

- Converse 未暴露的模型特有能力；
- 图像、视频等专用生成模型；
- 非聊天模型；
- 必须使用供应商原生请求体。

### 兼容接口

Bedrock 还提供 OpenAI Responses、Chat Completions 和部分厂商兼容 API。推荐兼容 endpoint 通常位于：

```text
bedrock-mantle.{region}.api.aws
```

兼容接口仍使用 AWS 的模型目录、区域、权限和配额语义。

## 认证

生产优先使用 IAM Role、临时凭据、IAM Identity Center 或工作负载身份。AWS SDK 自动执行 SigV4。

Bedrock API Key 不能让应用绕过 IAM 权限设计；不要把长期 AWS access key 写入代码。

## Endpoint 与模型标识

```text
bedrock.{region}.amazonaws.com
bedrock-runtime.{region}.amazonaws.com
bedrock-mantle.{region}.api.aws
```

`modelId` 可能是：

- 基础模型 ID；
- cross-region inference profile；
- application inference profile；
- provisioned throughput ARN；
- custom/imported model deployment ARN。

不能假设它总是一个短模型名。

## SDK

- Python：`boto3`
- TypeScript：`@aws-sdk/client-bedrock-runtime`
- OpenAI 兼容接口：`openai`

## 工具调用

Converse 使用 `toolConfig`，模型输出 `toolUse`，应用执行后回传 `toolResult`。

支持三种概念：

1. 客户端工具：应用执行；
2. Responses 服务端工具：可连接 Lambda 或 AgentCore Gateway；
3. 模型特有工具：按供应商文档调用。

不要看到工具定义就假设 Bedrock 会自动执行客户端函数。

## 结构化输出

支持形式取决于 API family 和模型，包括 Converse `outputConfig.textFormat`、模型原生字段、`response_format` 或 strict tool。

Schema 支持子集和首次编译行为可能不同；应本地预检并缓存稳定 schema。

## 多模态与流式

Converse 的 `ContentBlock` 可表达文本、图片、文档、视频、工具调用和工具结果，但具体模型只支持其中一部分。

流式使用 `ConverseStream` 或 `InvokeModelWithResponseStream`。长时间推理需要足够的客户端 read timeout，并处理连接中断。

## Agent 与 RAG

新项目优先评估 **AgentCore**，其能力包括 Runtime、Memory、Gateway、Identity、Browser、Code Interpreter、Observability 和 Registry。

Agents Classic 将于 **2026-07-30** 起不再向新客户开放；不要为新项目把它作为默认方案。

Knowledge Bases 提供 Retrieve、RetrieveAndGenerate、结构化查询、reranking 和 agentic retrieval。Guardrails 不一定自动过滤检索引用内容，应用仍需处理不可信上下文。

## Batch

使用 `CreateModelInvocationJob`，输入输出位于 S3，通常为 JSONL：

```json
{"recordId":"id-1","modelInput":{}}
```

批任务可使用模型原生 `InvokeModel` schema 或统一 `Converse` schema，按模型支持矩阵选择。

## 错误

常见分类：

- 400 `ValidationException`：修复 schema/modelId；
- 403 `AccessDeniedException`：检查 IAM、模型授权和 Marketplace；
- 404 `ResourceNotFoundException`：检查区域和 ARN；
- 408 `ModelTimeoutException`：调整超时或任务；
- 429 `ThrottlingException` / `ModelNotReadyException`：退避并读取 SDK 重试行为；
- 503 `ServiceUnavailableException`：退避、评估 cross-region 或 provisioned throughput。

## 最小 Python 示例

```python
import os
import boto3

client = boto3.client(
    "bedrock-runtime",
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

response = client.converse(
    modelId=os.environ["BEDROCK_MODEL_ID"],
    messages=[{
        "role": "user",
        "content": [{"text": "解释工具调用。"}],
    }],
    inferenceConfig={"maxTokens": 256, "temperature": 0.2},
)

print(response["output"]["message"]["content"][0]["text"])
```

## 最小 TypeScript 示例

```typescript
import {
  BedrockRuntimeClient,
  ConverseCommand,
} from "@aws-sdk/client-bedrock-runtime";

const client = new BedrockRuntimeClient({
  region: process.env.AWS_REGION ?? "us-east-1",
});

const response = await client.send(new ConverseCommand({
  modelId: process.env.BEDROCK_MODEL_ID!,
  messages: [{
    role: "user",
    content: [{ text: "解释工具调用。" }],
  }],
  inferenceConfig: { maxTokens: 256, temperature: 0.2 },
}));

console.log(response.output?.message?.content?.[0]?.text);
```

## 官方文档

- https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/models-api-compatibility.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/
- https://docs.aws.amazon.com/bedrock/latest/userguide/agents-how.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/kb-how-retrieval.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference-create.html
- https://docs.aws.amazon.com/general/latest/gr/bedrock.html
