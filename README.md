# Buddy

Buddy 可以把一台带触控屏的小型 Android 设备，变成一个常驻的本地 Agent 屏幕。

- 左侧显示宠物、状态、审批入口
- 右侧显示流式输出、媒体内容或其他界面
- 支持图片、视频、音频、HTML、stream、approval
- 支持对接 Codex、QwenPaw、Claude Desktop Buddy，以及 wrapper 型 CLI / agent

英文说明见 [README.en.md](README.en.md)。

## 现在能做什么

目前 Buddy 已经具备这些能力：

- Android 端显示应用
- 开机自启 helper
- 本地 HTTP / Python / CLI bridge
- 宠物系统，支持内置和自定义 spritesheet
- stream 输出界面
- approval 审批覆盖层
- QwenPaw 集成
- Codex 私有 sidecar 集成
- Claude Desktop Buddy 协议兼容桥

其中这些部分仍然属于实验性：

- 依赖宿主私有状态的集成
- 没有公开宿主 API 时的状态推断逻辑

## 仓库结构

项目大致分成 5 层：

1. `buddy-android/`
   Android 显示 app，本地 HTTP 服务和 WebView UI 都在这里。

2. `buddy-autostart/`
   开机自启 helper。

3. `bridge/`
   通用 bridge、Python client、CLI、compat 层。

4. `integrations/`
   面向具体宿主的集成入口。

5. `docs/`
   协议、兼容层、发布检查等文档。

## 快速开始

### 1. 安装到设备

推荐直接用：

```sh
./install-buddy-device.sh
```

这个脚本会：

- 构建 `buddy.apk`
- 构建 `buddy-autostart.apk`
- 安装两者
- 启用 autostart helper
- 拉起 Buddy 一次

### 2. 发送一个最简单的事件

```sh
python3 bridge/buddy.py --host <buddy-ip> message "hello" --title "Buddy"
```

### 3. 启动本地 bridge

```sh
python3 bridge/buddy.py --host <buddy-ip> serve
```

然后其他工具就可以调用：

```sh
curl -X POST http://127.0.0.1:8799/message \
  -H 'content-type: application/json' \
  -d '{"title":"Agent","body":"hello"}'
```

## 常见命令

### 文本 / 审批 / HTML

```sh
python3 bridge/buddy.py --host <buddy-ip> message "hello" --title "Agent"
python3 bridge/buddy.py --host <buddy-ip> approval "Allow?" "Continue running this task?"
python3 bridge/buddy.py --host <buddy-ip> html '<b style="font-size:32px">OK</b>' --title "HTML" --fullscreen
```

### 图片 / 视频 / 音频

```sh
python3 bridge/buddy.py --host <buddy-ip> image ./photo.png --title "Snapshot"
python3 bridge/buddy.py --host <buddy-ip> video ./clip.mp4 --title "Preview" --loop --fullscreen --fit cover
python3 bridge/buddy.py --host <buddy-ip> audio ./ding.wav --title "Done" --loop
python3 bridge/buddy.py --host <buddy-ip> stop-audio
```

### 宠物

```sh
python3 bridge/buddy.py --host <buddy-ip> pet list
python3 bridge/buddy.py --host <buddy-ip> pet set --pet-id codex
python3 bridge/buddy.py --host <buddy-ip> pet import --id moss ./my-pet-spritesheet.webp
python3 bridge/buddy.py --host <buddy-ip> pet set --pet-id moss
python3 bridge/buddy.py --host <buddy-ip> pet remove --id moss
```

## 宠物系统

Buddy 目前沿用了 Codex 桌面版那套宠物 spritesheet 思路。

内置宠物：

```text
claw, codex, dewey, fireball, rocky, seedy, stacky, bsod, null-signal
```

自定义宠物说明见：

- [pets/custom/README.md](pets/custom/README.md)

## Agent 集成

Buddy 把 agent 生命周期抽成了稳定协议：

```text
start -> log/chunk -> status/meta -> approval (optional) -> end
```

### CLI 示例

```sh
python3 bridge/buddy.py --host <buddy-ip> agent start --id run1 --name Codex --status running --body "Working..."
python3 bridge/buddy.py --host <buddy-ip> agent log --id run1 "Scanning repository...\n"
python3 bridge/buddy.py --host <buddy-ip> agent approval --id run1 "Allow continue?" "Need your approval."
python3 bridge/buddy.py --host <buddy-ip> agent end --id run1 --status done
```

### Python 示例

```python
from bridge import BuddyClient

buddy = BuddyClient(host="<buddy-ip>")
session = buddy.agent("run1", name="Codex", status="running", body="Working...")
session.log("Scanning repository...\n")
session.approval("Allow continue?", "Need your approval.")
session.end("done")
```

### 默认接入规则

如果第三方 agent 要接入这个项目，推荐默认遵守这条规则：

- 值得显示到 Buddy 的命令都走 `scripts/buddy-run.sh`
- 现成 stdout 流都走 `scripts/buddy-stdin.sh`
- 更复杂的宿主集成直接调用 `bridge/client.py`

例如：

```sh
export BUDDY_HOST=<buddy-ip>
export BUDDY_NAME=Codex
export BUDDY_STATUS=running

scripts/buddy-run.sh zsh -lc 'git status'
some-command 2>&1 | scripts/buddy-stdin.sh
```

## 兼容层

Buddy 的设备协议保持稳定，宿主差异通过 compat 层解决。

内置 compat 模块：

- [bridge/compat/claude_desktop_buddy.py](bridge/compat/claude_desktop_buddy.py)
- [bridge/compat/claude_code.py](bridge/compat/claude_code.py)
- [bridge/compat/codex_private.py](bridge/compat/codex_private.py)
- [bridge/compat/openclaw.py](bridge/compat/openclaw.py)
- [bridge/compat/qwenpaw.py](bridge/compat/qwenpaw.py)

### 已有集成

- **Claude Desktop Buddy**  
  兼容 Anthropic 文档公开的 heartbeat / turn / permission 协议。

- **Codex Desktop**  
  使用私有 sidecar monitor，从本地状态中推断 `thinking / waiting / done`。

- **QwenPaw**  
  支持安装型 runtime patch，也支持手动 debug bridge。

- **openclaw / CLI agents**  
  通过 wrapper / adapter 接入。

## 文档入口

- 协议说明：[docs/protocol.md](docs/protocol.md)
- 兼容层说明：[docs/compatibility.md](docs/compatibility.md)
- 发布检查单：[docs/publish-checklist.md](docs/publish-checklist.md)
- bridge 说明：[bridge/README.md](bridge/README.md)

## 示例

- [examples/python_agent_demo.py](examples/python_agent_demo.py)
- [examples/claude_code_compat_demo.py](examples/claude_code_compat_demo.py)
- [examples/claude_desktop_buddy_demo.py](examples/claude_desktop_buddy_demo.py)
- [examples/openclaw_compat_demo.py](examples/openclaw_compat_demo.py)
- [examples/qwenpaw_compat_demo.py](examples/qwenpaw_compat_demo.py)
- [examples/jsonl_demo.sh](examples/jsonl_demo.sh)
- [examples/wrapped_command_demo.sh](examples/wrapped_command_demo.sh)
- [examples/approval_poll_demo.py](examples/approval_poll_demo.py)

## 构建

```sh
./build-buddy-apk.sh
./build-autostart-apk.sh
```

## License

[MIT](LICENSE)
