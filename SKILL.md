---
name: coloros17-memory-vendor
description: 通过 ADB 和手机管家性能检测日志查询 ColorOS 17 手机的 RAM、UFS 厂商、料号与容量。用户询问 ColorOS 17 的内存颗粒、闪存供应商或混用时使用；不用于存储清理或单凭跑分判断厂家。
---

# ColorOS 17 内存与闪存厂商查询

本技能限定用于 ColorOS 17 手机，获取当前连接设备的实际硬件证据，分别报告 RAM 和 UFS。流程在一台 OPPO 手机上验证成功，不代表所有 ColorOS 17 机型都会输出相同日志。

## 前提与设备选择

电脑安装 Android Platform Tools，`adb` 可执行；手机启用 USB 调试并完成授权。附带工具只依赖 Python 3.10+ 标准库，适用于 Windows、macOS、Linux。

先运行 `adb devices -l`，确认设备处于 `device` 状态。多台设备时明确指定 `--serial`，不可随机选择。读取型号与系统版本，并检查：

```text
adb -s SERIAL shell pm path com.oplus.postmanservice
```

先确认手机运行 ColorOS 17。包存在说明值得尝试此路径，不代表当前机型一定输出硬件信息；包不存在时说明此设备不适用默认检测路径。

## 默认流程：先捕获，再检测

1. 在电脑先启动附带采集脚本。Windows 使用 PowerShell 7，文本读写使用 UTF8；实际使用时把技能目录替换为当前目录。

```powershell
python "$HOME/.codex/skills/coloros17-memory-vendor/scripts/collect.py" --output-dir ./output/phone-hardware-check --timeout 180
```

macOS／Linux：

```bash
python3 ~/.codex/skills/coloros17-memory-vendor/scripts/collect.py --output-dir ./output/phone-hardware-check --timeout 180
```

多设备加 `--serial SERIAL`；ADB 不在 PATH 时加 `--adb` 及可执行文件路径。脚本输出“捕获已启动”后再开始手机检测。工具调用应允许进程后台运行，期间及时给用户进度，不要用长时间阻塞等待。

2. 手机解锁，进入 **手机管家 → 右上角菜单 → 手机诊断／常规检测**。确认有自动检测项“性能”。只勾选“性能”即可；如果已经全选，也可以在性能阶段结束后退出后续手动检测。需要用户点按时给出明确入口，不反复要求跑完全部检测。
3. 脚本会临时将 `log.tag.Postman-StorageHealthCheckItem` 与 `log.tag.StorageHealthInfoService` 设为 DEBUG，捕获目标日志，在成功、超时、Ctrl+C 或异常时停止自己的 logcat 并恢复原值。不会清空日志、启动售后服务或修改持久日志属性。
4. 成功后读取输出目录的 `hardware-result.json` 和 `hardware-evidence.txt`。默认只保存硬件相关字段，不保存完整 map 中的序列号等其他内容。仍需检查文件内容后再对外分享。

同一目录已有结果时脚本拒绝覆盖，请用新的输出目录。保留现有日志的离线解析方式：

```powershell
python "$HOME/.codex/skills/coloros17-memory-vendor/scripts/collect.py" --log ./local-capture.txt --output-dir ./output/phone-hardware-offline
```

离线模式不连接或修改手机；离线日志的设备归属由提供者负责确认。

## 判读规则

| 本机日志字段 | 含义 |
| --- | --- |
| `DDRDev` | RAM 类型、厂商标识及可能的颗粒标记、容量 |
| `MemoryDev` | **在已验证的 OPPO 接口中是 UFS**，通常包含完整料号与厂商 |
| `StorageDev` | 存储版本描述；保留原值，不擅自换算 UFS 版本 |
| `StorageSize` | 系统报告的存储容量；与 `/data` 分区大小分开报告 |

保留原始硬件字段，中文厂商名与推断分开。`Cxsh`／`CXSH` 对应 CXMT 的公开依据见[验证记录](references/verified-path.md)；其他未知缩写先查官方资料，不猜。

- `ro.product.manufacturer=OPPO` 是整机厂商，SoC 厂商也不是 RAM／UFS 厂商。
- 固件字符串或 QLC 支持名单只是支持范围，不能视为本机料号。
- 日志仅报 `DDR5` 时不能直接声称 LPDDR5X；`D1y` 不能直接换成纳米工艺；`2000` 不能直接判为 UFS 4.0／4.1。
- 完整 RAM 料号、实际速率未出现就明确未取得。单台结果不证明整个型号混用，也不证明性能差距。
- 只取得其中一项时报告部分成功，另一项未知；脚本退出码 0 表示取得至少一项有效厂商标识，仍应查看 `status`。

给用户简明结果表、证据来源和可点击的本地文件链接。结果来自实时检测、已有日志还是外部映射要说清楚。

## 无输出时排查

先核对手机是否锁屏、“性能”是否勾选、采集是否先于检测启动。ADB 手势可能被系统拒绝；截屏／UI XML 能读不代表自动点击也能生效，必要时请用户手动操作。

已确认先捕获再跑性能仍无结果时，不盲目重复相同检测。需要深入定位当前固件，阅读[验证记录与排障](references/verified-path.md)。普通 ADB 的直接 Binder 查询和硬件节点在验证机上被拒绝，不要把权限错误说成文件不存在。

本技能不授权解锁 bootloader、刷机、root、恢复出厂、维修写入、伪造售后认证、安装手机 APK 或向远程服务上传日志。查询遇到权限边界时，先完成现有只读路径，再说明边界。

## 分享与安装

分享整个 `coloros17-memory-vendor` 文件夹或它的 ZIP，保留 `SKILL.md`、`scripts/`、`references/`、`agents/` 和 `tests/`。不要放入个人 ADB 日志、bugreport、截图、设备序列号、从手机提取的 APK/JAR。

Codex 用户解压至 `~/.codex/skills/coloros17-memory-vendor/`（配置了 CODEX_HOME 时用该目录下的 `skills/`），新会话调用 `$coloros17-memory-vendor`。其他用户也可直接执行 `scripts/collect.py`，不依赖 Codex。
