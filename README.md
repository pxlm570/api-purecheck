# API PureCheck

> 你的中转站，真的纯吗？

API PureCheck 是一个轻量、本地运行的中转站 API 纯度体检工具。填入 API 地址、Key 和模型名，它会用少量请求完成协议检查、行为探针、模型族画像和风险扫描，直接告诉你：这条 API 链路到底像不像它声称的模型。

它的目标很直接：让普通用户、学生和开发者快速发现可疑的模型降级、替换、fallback、路由漂移或中转链路异常。

## 它能帮你做什么

API PureCheck v1.0 已具备本地 Web UI、CLI、脱敏报告、模型族画像和风险检查能力。它适合快速回答三个问题：

- 这个 API 能不能正常访问？
- 它像不像声称的模型？
- 这条中转链路有没有明显异常？

模型概率判断默认使用协议特征、行为探针和模型族画像；风险检查使用 `clean / anomaly / inconclusive` 三态结果。真实官方基线不是必需项，工具会在报告里明确说明判断依据和置信度。

当前内置检测强度：

- quick：3 个请求，最低成本，适合先确认 API 是否打通；
- standard：8 个请求，默认推荐，覆盖核心探针、流式完整性和错误泄漏检查；
- deep：18 个请求，更充分，但仍控制成本。

## 普通用户 3 步开始

1. 双击运行：

```text
scripts/start_windows.bat
```

2. 打开页面：

```text
http://127.0.0.1:8765
```

3. 填入 API 地址、Key 和声称模型，先看请求数，再点“开始检测”。检测完成后即可下载 JSON / Markdown / HTML 报告。

## 使用方式

Windows 用户可以直接运行：

```text
scripts/start_windows.bat
```

PowerShell 用户也可以运行：

```powershell
scripts/start_windows.ps1
```

启动本地页面：

```bash
api-purecheck serve
```

启动后打开：

```text
http://127.0.0.1:8765
```

命令行检测：

```bash
api-purecheck check \
  --base-url https://example.com/v1 \
  --api-key YOUR_API_KEY \
  --model gpt-4o \
  --api-type openai-compatible \
  --level standard \
  --baseline-dir baselines
```

只校验配置，不发起请求：

```bash
api-purecheck check \
  --config examples/config.example.json \
  --dry-run
```

导出 JSON 报告：

```bash
api-purecheck check \
  --config examples/config.example.json \
  --format json \
  --output report.json
```

导出 HTML 报告：

```bash
api-purecheck check \
  --config examples/config.example.json \
  --format html \
  --output report.html \
  --dry-run
```

导出 Markdown 报告：

```bash
api-purecheck check \
  --config examples/config.example.json \
  --format markdown \
  --output report.md \
  --dry-run
```

采集可信模型基线：

```bash
api-purecheck calibrate \
  --provider openai \
  --base-url https://api.openai.com/v1 \
  --api-key YOUR_API_KEY \
  --model gpt-4o \
  --api-type openai-compatible \
  --level quick \
  --output baselines/gpt-4o/2026-xx.jsonl
```

轻量监控：

```bash
api-purecheck monitor \
  --config examples/config.example.json \
  --runs 3 \
  --interval-seconds 3600 \
  --output-dir reports/monitor
```

先预估请求数：

```bash
api-purecheck monitor \
  --config examples/config.example.json \
  --runs 3 \
  --dry-run
```

批量预估多个 endpoint：

```bash
api-purecheck batch \
  --file examples/batch.example.json \
  --dry-run
```

查看常见模型名示例：

```bash
api-purecheck models
api-purecheck models --provider anthropic
api-purecheck models --provider gpt
api-purecheck models --provider claude
api-purecheck profiles
```

使用自定义探针：

```bash
api-purecheck check \
  --config examples/config.example.json \
  --probe-file examples/probes.example.json \
  --dry-run
```

## 隐私原则

- API key 默认只在本地使用。
- 默认不上传 API key、请求或响应。
- 日志和报告必须自动脱敏 API key。
- 检测前会提示请求数量和可能成本。

## v1.0 已支持

- 本地 Web UI；
- CLI；
- OpenAI-compatible API；
- GPT / Claude 候选模型；
- DeepSeek / Kimi / GLM / MiniMax 等常见国产模型族；
- “其他模型”概率；
- 概率报告、置信度、三态风险项和证据解释；
- token 注入、上下文截断、错误泄漏、响应改写等轻量风险检查；
- HTML / JSON / Markdown 报告导出。

补充文档：

- [常见问题排查](docs/TROUBLESHOOTING.md)

## 开发验证

当前项目暂不依赖第三方包。运行测试：

PowerShell 下直接从源码运行：

```powershell
python -m api_purecheck --help
python -m api_purecheck check --config examples/config.example.json --dry-run
```

运行测试：

```bash
python -m unittest discover -s tests
```

Windows 发布前自检：

```powershell
scripts/check_windows.ps1
```

`scripts/check_windows.ps1` 会检查 CLI、dry-run、模型画像和单元测试。Web 页面建议发布前用浏览器打开一次，确认首屏和下载按钮显示正常。
