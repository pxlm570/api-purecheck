# API PureCheck

> 你的中转站，真的纯吗？

API PureCheck 是一个轻量、本地运行的中转站 API 纯度检测工具。你填入 API 地址、Key 和声称模型，它会用少量请求完成协议检查、行为探针、模型族画像和风险扫描，给出一份普通用户也能看懂的概率报告。

它主要帮你回答三个问题：

- 这个 API 能不能正常访问？
- 它像不像声称的模型？
- 这条中转链路有没有明显异常？

## 最快开始

如果你只是想马上检测，不想折腾环境，直接走 Windows 发布包：

1. 打开最新发布页：

```text
https://github.com/pxlm570/api-purecheck/releases/latest
```

2. 下载 `api-purecheck-windows.zip`。
3. 如果你的电脑还没有 Python，请先安装 Python 3.11 或更高版本。
4. 安装 Python 时，勾选：

```text
Add python.exe to PATH
```

5. 解压下载好的 zip。
6. 双击运行：

```text
scripts/start_windows.bat
```

7. 浏览器会自动打开；如果没有自动打开，就手动访问：

```text
http://127.0.0.1:8765
```

## 页面里怎么填

打开页面后，你会看到这些输入项：

- `API 地址`：填中转站文档里的 `base_url`，不要填网站首页。
- `API Key`：填你的 key。它只会发给本机服务，再由本机去请求你填写的 API 地址。
- `API 类型`：大多数 OpenAI 风格接口选 `OpenAI-compatible`；Claude 官方或 Claude Code 风格接口通常选 `Anthropic Messages API`。
- `模型族`：选你准备检测的大类，比如 GPT、Claude、DeepSeek、Kimi、GLM、MiniMax。
- `声称模型`：填中转站文档里写的完整模型名，不要只填模型族。
- `检测强度`：第一次推荐 `standard`，成本和信息量更平衡。

如果你不确定某一项怎么填，优先以中转站自己的使用文档为准。

## 第一次检测怎么做

第一次使用时，建议按这个顺序：

1. 先把配置填完整。
2. 先点“只预估请求数”，确认这次检测大概要发起多少次请求。
3. 可以接受成本后，再点“开始检测”。
4. 检测完成后，下载 JSON、Markdown 或 HTML 报告。

当前内置检测强度：

- `quick`：3 个请求，最低成本，适合先确认 API 是否打通。
- `standard`：8 个请求，默认推荐，覆盖核心探针、流式完整性和错误泄漏检查。
- `deep`：18 个请求，更充分，但仍然控制成本。

## 报告怎么看

报告里最值得先看的部分是：

- `纯度结论`：这条 API 当前表现是否接近你填写的声称模型。
- `置信度`：当前证据是否足够稳定，还是只能给出保守判断。
- `最可能匹配`：当前候选模型的概率分布。
- `其他模型`：保留给未知模型、候选集外模型或证据不足的概率空间。
- `风险检查`：检查模型身份、token 注入、上下文截断、错误泄漏、响应改写和 stream 完整性等异常。
- `访问诊断`：如果请求失败，这里通常会直接告诉你更可能是地址错了、模型名错了、权限错了，还是协议类型不匹配。

## 常见填写误区

- 把网站首页当成 API 地址：错误。应填文档里的 `base_url`。
- 把 `gpt`、`claude`、`deepseek` 这种模型族名字当成模型名：错误。应填完整模型名。
- Claude 风格中转站却选了 `OpenAI-compatible`：容易报参数错误或请求被拒绝。
- 不先做请求数预估就直接跑 `deep`：可能浪费额度。

## 开发者和 CLI

如果你想直接从源码运行，先进入项目目录。

最省事的方式有两种：

1. 不安装，直接运行：

```powershell
python -m api_purecheck --help
python -m api_purecheck serve
```

2. 安装本地命令后再运行：

```powershell
python -m pip install -e .
api-purecheck --help
api-purecheck serve
```

命令行检测示例：

```powershell
api-purecheck check `
  --base-url https://example.com/v1 `
  --api-key YOUR_API_KEY `
  --model gpt-4o `
  --api-type openai-compatible `
  --level standard
```

只检查配置，不发起真实请求：

```powershell
api-purecheck check `
  --config examples/config.example.json `
  --dry-run
```

导出 JSON 报告：

```powershell
api-purecheck check `
  --config examples/config.example.json `
  --format json `
  --output report.json
```

## 已支持内容

- 本地 Web UI
- CLI
- OpenAI-compatible API
- Anthropic Messages API
- GPT / Claude / DeepSeek / Kimi / GLM / MiniMax 模型族
- 概率报告、置信度、证据解释和风险检查
- JSON / Markdown / HTML 报告导出

## 隐私原则

- API key 默认只在本地使用。
- 默认不上传 API key、请求或响应。
- 日志和报告会自动脱敏 API key。
- 检测前会提示请求数量和可能成本。

## 重要边界

API PureCheck 输出的是概率判断，不是密码学证明，也不是法律审计报告。它适合帮你快速发现可疑链路、兼容性问题、模型名错误和明显异常。

## 补充文档

- [用户指南](docs/USER_GUIDE.md)
- [常见问题排查](docs/TROUBLESHOOTING.md)
- [v1.0.0 发布说明](docs/RELEASE_NOTES_1.0.0.md)

## 开发验证

运行测试：

```powershell
python -m unittest discover -s tests
```

Windows 发布前自检：

```powershell
scripts/check_windows.ps1
```
