# ColorOS 17 Memory Vendor

通过 ADB 和手机管家“性能”检测日志，查询 ColorOS 17 手机的 RAM、UFS 厂商、料号与容量。

本项目既可作为 Codex skill 使用，也可直接运行 Python 脚本。已在一台 OPPO Find X10 Pro Max（PMX110，Android 17）上验证成功；不同 ColorOS 17 机型与固件的日志输出可能不同。

## 运行查询

需要 Python 3.10+、Android Platform Tools（`adb` 在 PATH 中）。脚本只使用 Python 标准库，支持 Windows、macOS、Linux。手机需要开启 USB 调试并允许电脑连接。

在项目目录运行：

```sh
adb devices -l
python scripts/collect.py --output-dir ./output/my-phone --timeout 180
```

macOS／Linux 如 `python` 不指向 Python 3，可使用 `python3`。Windows 推荐使用 PowerShell 7。

等待终端提示“捕获已启动”，随后在手机操作：

1. 解锁手机，打开手机管家。
2. 进入右上角菜单 → 手机诊断／常规检测。
3. 勾选自动检测项“性能”，点击“开始检测”。

脚本捕获到厂商字段后自动结束，在指定目录写入：

- `hardware-result.json`：结构化结果。
- `hardware-evidence.txt`：可复核的硬件字段。

脚本临时开启两个目标日志标签，在成功、超时、异常或 Ctrl+C 时恢复原值。输出不保存完整 map 中的设备序列号，也不会清空日志、解锁手机或执行维修操作。强杀进程或连接中断可能导致恢复失败，终端会打印原值，按[排障说明](references/verified-path.md)恢复。

多台设备时明确指定序列号：

```sh
python scripts/collect.py --serial SERIAL --output-dir ./output/my-phone
```

ADB 不在 PATH 中时使用 `--adb /path/to/adb`。已有结果的目录不能覆盖，请为每次查询选择新的输出目录。

解析已有本地 UTF8 日志，不连接手机：

```sh
python scripts/collect.py --log ./local-capture.txt --output-dir ./output/offline-check
```

## 安装为 Codex skill

将本项目放入 `~/.codex/skills/coloros17-memory-vendor/`。配置了 `CODEX_HOME` 时，使用该目录下的 `skills/`。

在新会话输入：

> 使用 $coloros17-memory-vendor 查询已连接 ColorOS 17 手机的内存和闪存厂商。

完整 agent 工作流程见 [SKILL.md](SKILL.md)。

## 如何判读

| 字段 | 含义 |
| --- | --- |
| `DDRDev` | RAM 厂商标识、类型及可能的颗粒标记 |
| `MemoryDev` | 此接口中的 **UFS 闪存**厂商和料号 |
| `StorageDev` | 系统报告的存储版本字符串 |
| `StorageSize` | 系统报告的存储容量 |

结果保留原始字段。`status=complete` 表示 RAM、UFS 均取得厂商标识，`partial` 表示只取得其中一项；退出码 0 表示至少取得一项。未知项不按容量或跑分推测。

系统仅报告 `DDR5`、`D1y` 或 `2000` 时，不能据此断言 LPDDR5X、具体纳米工艺或 UFS 4.x。`Cxsh` 与 CXMT 的名称映射依据、已验证示例及底层接口说明见[验证记录](references/verified-path.md)。单台结果不证明同型号是否混用，也不量化性能差异。

## 验证与贡献

```sh
python -m unittest discover -s tests -v
```

测试覆盖日志解析、部分结果、私人字段排除、不覆盖已有文件、临时属性恢复、超时与取消；测试本身不连接手机。欢迎提交 ColorOS 17 机型兼容记录，注明型号、系统版本、检测入口和去除个人标识的相关字段。

不要提交原始 bugreport、完整个人日志、设备序列号、截图或从手机提取的 APK/JAR。查询输出和 Python 缓存已加入 `.gitignore`。

## 许可证

[MIT](LICENSE)。
