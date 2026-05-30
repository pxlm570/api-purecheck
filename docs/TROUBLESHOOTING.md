# 常见问题排查

## 双击 start_windows.bat 后窗口闪退

请先确认已经把 zip 完整解压到普通目录，不要直接在压缩包预览窗口里运行脚本。

新版脚本会把启动错误写到：

```text
dist/start_windows.log
```

处理方式：

1. 进入项目目录；
2. 双击 `scripts/start_windows.bat`；
3. 如果仍然启动失败，打开 `dist/start_windows.log` 查看错误；
4. 常见原因是没有安装 Python、Python 不在 PATH、端口 `8765` 被占用，或目录权限异常。

如果浏览器出现 `chrome-error://chromewebdata` 或 `Unsafe attempt to load URL`，通常不是网页代码问题，而是本地服务没有启动成功。先看黑色终端窗口和 `dist/start_windows.log`。

## 页面看起来还是旧版

刷新浏览器不一定能加载新代码，因为后台 Python 服务可能仍然是旧进程。

处理方式：

1. 关闭正在运行 API PureCheck 的终端窗口，或按 `Ctrl+C`；
2. 重新运行：

```text
scripts/start_windows.bat
```

3. 打开：

```text
http://127.0.0.1:8765
```

4. 访问健康检查：

```text
http://127.0.0.1:8765/health
```

新版服务会返回版本和 UI 标记。

## API 返回 HTML 或 response is not valid JSON

这通常说明填入的是网站首页地址，而不是 API Base URL。

需要在中转站文档里查找真正的 API 地址，例如：

```text
https://example.com/v1
```

Anthropic / Claude Code 风格的中转站可能会给 `ANTHROPIC_BASE_URL` 根地址。API PureCheck 会自动尝试：

```text
/v1/messages
/messages
```

## 模型名错误

如果报告显示 `request_error` 或 HTTP 400，通常是模型名、API 类型或中转站兼容性问题。

处理方式：

- 使用中转站文档中的精确模型名；
- 不要把模型家族名当作模型名；
- 查看报告中的 `diagnostics.suggested_models`。

例如 DeepSeek 错误信息可能提示：

```text
deepseek-v4-pro
deepseek-v4-flash
```

## API Key 错误

如果报告显示 `auth_error`，通常是：

- API key 无效；
- API key 没有该模型权限；
- key 类型不匹配当前 API 类型；
- 中转站需要额外配置。

## OpenAI-compatible 地址怎么填

优先填写 base URL：

```text
https://example.com/v1
```

如果误填完整路径：

```text
https://example.com/v1/chat/completions
```

API PureCheck 会自动修正为：

```text
https://example.com/v1
```

## 检测结果概率不是 100%

这是正常的。API PureCheck 输出的是概率判断，不提供密码学证明。

如果请求全部成功且 API 自报模型与填写模型一致，报告会给出很高的一致性；但仍会保留极小的“其他模型”概率空间。
