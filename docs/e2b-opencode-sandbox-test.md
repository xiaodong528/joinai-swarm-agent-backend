# E2B OpenCode 沙箱手工测试

本文档记录如何启动一个可保活的 E2B `opencode` 模板沙箱，然后人工进入沙箱测试 OpenCode。

## 适用场景

- 想验证 E2B 官方 `opencode` 模板是否可用。
- 想把后端生成的 `opencode.json` 写进沙箱后，手工进入沙箱操作。
- 想避免后端请求结束后沙箱被回收，保留一段时间用于人工调试。

## 前置条件

本项目假设已经创建本地 Python 环境并安装依赖：

```powershell
conda create -y -p .\.conda python=3.12
.\.conda\python.exe -m pip install --ignore-installed -r requirements-dev.txt
.\.conda\python.exe -m pip install e2b
```

需要在当前 PowerShell 会话里设置环境变量。不要把真实 key 写进仓库文件。

```powershell
$env:E2B_API_KEY='e2b_...'
$env:OPENCODE_PROVIDER_KEY='sk-...'
$env:E2B_SANDBOX_TIMEOUT='3600'
```

其中：

- `E2B_API_KEY` 用于创建和连接 E2B 沙箱。
- `OPENCODE_PROVIDER_KEY` 会写入沙箱内的 OpenCode provider 配置。
- `E2B_SANDBOX_TIMEOUT` 是沙箱保活秒数，默认脚本使用 `3600`。

## 启动保活沙箱

运行：

```powershell
$env:PYTHONNOUSERSITE='1'
$env:PYTHONPATH='.'
Start-Process `
  -FilePath ".\.conda\python.exe" `
  -ArgumentList @("scripts\hold_opencode_sandbox.py") `
  -WorkingDirectory (Get-Location) `
  -WindowStyle Hidden `
  -RedirectStandardOutput "tmp\hold.stdout.log" `
  -RedirectStandardError "tmp\hold.stderr.log" `
  -PassThru
```

脚本会：

- 创建 E2B `opencode` 模板沙箱。
- 创建 `/home/user/workspace`。
- 验证 `opencode` 命令和版本。
- 把沙箱信息写入 `tmp/opencode_sandbox_hold.json`。
- 每 30 秒执行一次心跳。
- 收到停止信号时不主动 `kill()` 沙箱。

查看状态：

```powershell
Get-Content tmp\opencode_sandbox_hold.json -Encoding utf8
Get-Content tmp\opencode_sandbox_hold.log -Encoding utf8 -Tail 20
```

状态文件里最重要的是：

```json
{
  "sandbox_id": "xxxx",
  "workspace": "/home/user/workspace",
  "opencode_check_stdout": "/home/user/.opencode/bin/opencode\n1.2.6"
}
```

## 写入 OpenCode 配置

保活沙箱启动后，运行：

```powershell
$env:PYTHONNOUSERSITE='1'
$env:PYTHONPATH='.'
.\.conda\python.exe scripts\provision_held_opencode_sandbox.py
```

脚本会连接 `tmp/opencode_sandbox_hold.json` 里的 `sandbox_id`，并把配置写到：

```text
/home/user/workspace/opencode.json
```

当前脚本写入的 provider 是 DeepSeek OpenAI-compatible：

```json
{
  "provider": {
    "deepseek": {
      "name": "DeepSeek",
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "https://api.deepseek.com",
        "apiKey": "来自 OPENCODE_PROVIDER_KEY"
      }
    }
  },
  "model": "deepseek/deepseek-v4-pro"
}
```

## 进入沙箱

推荐使用 E2B CLI：

```powershell
e2b auth login
e2b sandbox connect <sandbox_id>
```

进入后执行：

```bash
cd /home/user/workspace
opencode
```

或者直接运行一次：

```bash
cd /home/user/workspace
opencode run "hello"
```

如果只想远程执行单条命令：

```powershell
e2b sandbox exec <sandbox_id> "cd /home/user/workspace && opencode --version"
```

## 不使用 CLI 的验证方式

也可以用 Python SDK 连接同一个沙箱执行命令：

```powershell
.\.conda\python.exe -c "from e2b import Sandbox; s=Sandbox.connect('<sandbox_id>', timeout=3600); r=s.commands.run('cd /home/user/workspace && opencode --version', timeout=30); print(r.stdout); print(r.stderr)"
```

这种方式适合快速验证，不是交互式终端。

## 停止保活

本地保活进程是普通 Python 进程，可以查看：

```powershell
Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, StartTime
```

停止保活进程：

```powershell
Stop-Process -Id <pid>
```

注意：`scripts/hold_opencode_sandbox.py` 不会主动调用 `sandbox.kill()`。如果需要立即销毁 E2B 沙箱，请用 E2B 控制台、E2B CLI，或额外脚本显式 kill 对应 `sandbox_id`。

## 常见问题

### 状态文件不存在

检查 `tmp/hold.stderr.log`：

```powershell
Get-Content tmp\hold.stderr.log -Encoding utf8
```

常见原因是 `E2B_API_KEY` 没有设置，或者本机网络无法访问 E2B API。

### 已进入沙箱但找不到配置

确认当前目录：

```bash
cd /home/user/workspace
ls -la
cat opencode.json
```

### opencode run 找不到模型或 provider

确认 `opencode.json` 里有：

```json
{
  "model": "deepseek/deepseek-v4-pro"
}
```

并确认 `provider.deepseek.options.apiKey` 是通过 `OPENCODE_PROVIDER_KEY` 写入的真实 key。
