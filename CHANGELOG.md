# Changelog

## 1.0.0

正式 Windows 用户版。

### Added

- 首屏完成填写、请求数预估、检测和报告下载；
- 纯度结论卡片、关键指标卡片、访问诊断和下一步建议；
- Windows 启动脚本增加 Python 检查、端口占用提示和中文失败提示；
- 面向用户的瘦身发布包 `dist/api-purecheck-windows.zip`；
- `docs/RELEASE_NOTES_1.0.0.md`。

### Changed

- 默认检测成本降低：quick 3 次、standard 8 次、deep 18 次；
- 报告主表达调整为纯度结论、报告置信度和总体风险；
- 文案从工程说明调整为普通用户可读的产品表达；
- 发布包只包含用户运行所需文件，不包含测试、内部计划、工程规范和临时产物。

## 0.1.0

初始 MVP+ 版本。

### Added

- 本地 Web UI；
- CLI：`check`、`serve`、`calibrate`、`monitor`、`models`、`profiles`、`batch`；
- OpenAI-compatible adapter；
- Anthropic Messages API adapter；
- quick / standard / deep 三档检测；
- GPT、Claude、DeepSeek、Kimi、GLM、MiniMax 模型族画像；
- 模型族一致性；
- `unknown/out-of-set` 概率；
- 三态风险检查：`clean / anomaly / inconclusive`；
- token 注入轻量检查；
- 上下文截断 canary 检查；
- 错误响应泄漏检查；
- 响应改写检查；
- OpenAI-compatible / Anthropic stream 完整性检查；
- 行为画像 `behavior_fingerprint`；
- 初步模型族倾向 `family_likelihoods`；
- JSON / HTML / Markdown / text 报告；
- Web UI 报告下载；
- 自定义探针文件；
- 可选 baseline 采集和加载；
- Windows 启动脚本、自检脚本和源码打包脚本；
- 手工回归清单、用户手动事项清单、Release Notes。

### Known Limitations

- 不是密码学证明；
- 不提供法律或投诉级审计结论；
- 行为指纹分类器仍是启发式初版；
- 未实现 Claude signature / channel fingerprint 深度识别；
- 真实官方 API 回归不作为发布前提；用户可自愿用自己的 key 做额外自测。
