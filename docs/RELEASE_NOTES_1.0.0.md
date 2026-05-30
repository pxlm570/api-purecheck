# API PureCheck 1.0.0 Release Notes

API PureCheck 1.0.0 是面向普通用户、学生和开发者的本地中转站 API 纯度检测工具。

## 核心卖点

- 一页完成 API 地址、Key、模型名、检测强度填写；
- 检测前明确显示请求数，默认标准模式只需 8 次请求；
- 输出纯度结论、模型概率、置信度、风险检查和访问诊断；
- 支持 OpenAI-compatible 与 Anthropic Messages API；
- 内置 GPT、Claude、DeepSeek、Kimi、GLM、MiniMax 模型族画像；
- API key 只在本机请求中使用，报告自动脱敏；
- Windows 用户可直接运行 `scripts/start_windows.bat`。

## 检测强度

- 快速：预计 3 次请求，最低成本，适合先试通；
- 标准：预计 8 次请求，默认推荐；
- 深度：预计 18 次请求，适合需要更充分证据时使用。

## 适合场景

- 检查中转站是否像它声称的 GPT / Claude / DeepSeek 等模型；
- 判断 API 地址、模型名、协议类型是否配置正确；
- 给学生和普通用户一份可读的概率参考报告；
- 给开发者提供 CLI、JSON、Markdown、HTML 输出。

## 边界说明

本工具输出的是基于协议特征、黑盒探针、模型族画像和风险检查的概率判断，不是法律证明，也不需要真实官方 API 回归作为发布前提。

