# Windows部署与故障处理

## 正常步骤

完整解压ZIP → 02环境自检 → 缺CLI时03安装 → 04登录本人模型 → 05真实AI试跑 → 06启动。

本包带Windows x64嵌入式Python 3.13.17和所需依赖，无需全局Python、Node或Git。仅实时模型需要Codex CLI、本人的可用模型账号和网络。首次CLI安装会下载较大的官方运行时，课前完成。

| 现象 | 处理 |
| --- | --- |
| HTML可用但实时AI不可用 | 两种入口不同。05试跑成功才算本机模型接通；今天主讲仍可用离线HTML |
| CMD一闪而过或找不到python.exe | “全部解压”整个包，再运行；不要只从ZIP拖出某个文件。AI可在终端运行查看错误 |
| 无法打开exe/公司策略阻止 | 检查是否Windows x64、来源文件是否完整，并遵循设备策略；不要关闭系统防护或全局更改执行策略 |
| 文件清单SHA256不一致 | 重新解压原包，不改清单掩盖问题。需要修改源码时由AI另存开发副本并记录变更 |
| 找不到CLI | 先运行03官方安装。已有桌面/独立安装/npm版本也可自动发现原生exe |
| 已有CLI但无法运行 | CLI是完整运行时，不能仅复制codex.exe。让AI用官方安装补全相邻运行文件 |
| 不能登录 | 使用自己的可用账号、核对网络。普通登录失败可用07设备码登录，需本账号允许该功能 |
| `login status`未检测登录但已配provider | 标准登录状态不覆盖所有自定义provider；保持原配置，以05真实试跑结果为准 |
| 模型超时、配额不足或权限错误 | 不伪造成功；核对本人模型权限、额度和网络后重试。不能把历史记录伪装成新模型结果 |
| 8765被占用 | 先识别。已有v0.3会直接打开；其他服务不要强杀，可改用8770并告知实际地址 |
| 浏览器打不开 | 启动窗口是否仍运行？手动打开打印的127.0.0.1地址。Ctrl+C会停止服务 |
| 页面仍在上次会话 | 点“新建正常情景”生成独立课堂记录，不删除旧账本 |
| 没有可采纳按钮 | 调查未结束/失败、缺规则、版本已变或候选不满足校验；看页面说明，不跳过人审 |
| 完成登记后显示待核实 | 核对少完成、累计已履约是否留空、剩余ETA；不要直接改数据库消除风险 |

## 给AI的具体命令

在解压根目录：

```powershell
& '.\.runtime\python\python.exe' -X utf8 -B '.\tools\handoff.py' check
& '.\.runtime\python\python.exe' -X utf8 -B '.\tools\handoff.py' live-smoke
& '.\.runtime\python\python.exe' -X utf8 -B '.\tools\handoff.py' start --port 8765
```

改端口示例：

```powershell
& '.\.runtime\python\python.exe' -X utf8 -B '.\tools\handoff.py' start --port 8770
```

离线HTML中的“打开实时应用”固定指向8765。改端口后用终端打印的新地址，不能点旧链接后误认为连接失败。

仅在当前终端指定数据或CLI路径：

```powershell
$env:FDE_AGENT_WORK = 'D:\FDEGroup8Data\agent'
$env:FDE_CODEX_EXE = '这里填写这台电脑实际找到的原生codex.exe完整路径'
```

第二行是格式示例，先查实际路径再设，不要把说明文字直接当路径执行。CLI参数和所有路径由程序以参数数组传递，不拼接模型输出执行命令。

## 数据、证据与停止

- 日常账本：`%LOCALAPPDATA%\FDEGroup8\agent-v0.3\ledger.sqlite3`；运行记录在该目录`runs`。
- 自检/试跑报告：`%LOCALAPPDATA%\FDEGroup8\handoff-reports`。
- 05试跑使用独立账本，只调查，不采纳、不完成。它不会预填日常页面的签审。
- 旧真实证据在包内`historical-evidence`；离线演示证据在`presentation`，都不作为实时模型输入。
- Ctrl+C停止实时服务，数据保留。新建情景即可重新演示，无需删除数据库。

## 设备适用范围

主包内Python和二进制依赖为**x64**，已在Windows x64制作电脑验证。Windows ARM或32位设备须由部署AI另配对应运行时与依赖，不能声称本包已原生验证。离线HTML仍可用。

本包未代替在组员电脑的实际验收；完成02和05后，AI应告诉你真实的通过/失败结果。
