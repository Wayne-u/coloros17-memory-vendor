# 验证记录与排障

## 已验证范围

2026-10-04，在一台 OPPO Find X10 Pro Max（PMX110，mt6995，Android 17，OTA `PMX110_11.A.55_0550_202609270158`）上成功。下面是去除个人标识的硬件示例，不是其他手机的默认答案：

```text
DDRDev=Device version:DDR5|Device manufacture:Cxsh|D1y|16G|
MemoryDev=Device version:KLUFG8RHKF-F0H1 |Device manufacture:SAMSUNG |
StorageDev=Device version:2000|Device manufacture:SAMSUNG |
StorageSize=512
```

成功路径是临时开启两个目标日志标签，先实时捕获，再由用户运行手机管家常规检测的“性能”项。在检测开始后的数秒内出现：

```text
Postman-StorageHealthCheckItem: health info map : { ... }
```

ColorOS 17 的机型与固件输出可能不同，查询结果以本机日志为准。

## 非直观的接口映射

从本机系统 JAR 与 APK 字节码核对：

- `StorageHealthInfoService.getDDRDeviceVersion()` 调用 `android.os.PerformanceManager.getDevinfoDDRInfo()`，结果写到 `DDRDev`。
- `getMemoryDeviceVersion()` 调用 `getDevinfoUfsInfo()`，结果写到 `MemoryDev`；名字含 Memory，但这里指闪存。
- `getStorageDevInfo()` 调用 `getDevinfoUfsVersionInfo()`，写到 `StorageDev`。
- `PostmanService.apk` 的 `assets/self_category_item_config.xml` 在性能分类 `cat_software` 下配置 `ItemStorageHealthCheck`，`diagnosis_id=180201`。内部 key 为 `item_memory_ram`，同样不要被 ram 名字误导。
- `ItemStorageHealthCheck.getHealthInfoMap()` 调用 `StorageHealthInfoManager.getStorageHealthInfoMap()`，将整个 map 输出到 `Postman-StorageHealthCheckItem` 的 DEBUG 日志。
- 原始 map 还包含序列号、健康计数等信息。附带脚本只保留已明确用于硬件判读的字段。

## 厂商名称映射的依据

技嘉官方 BIOS 更新说明使用 **“CXSH (CXMT)”**，提供 CXSH 与 CXMT 的对应；CXMT 官网为长鑫存储。

- [技嘉官方支持页](https://www.gigabyte.com/lt/Motherboard/B650E-AORUS-STEALTH-ICE/support)
- [长鑫存储官网](https://www.cxmt.com/?lang=zh-hans)

这是外部名称映射，手机日志本身只显示 `Cxsh`。此依据不证明 LPDDR 具体代际、速率或工艺，也不是手机完整料号对照表。引用时如页面变化应重新核实。

## 已尝试的权限边界

普通 shell 在验证机上无法读：

```text
/proc/devinfo/ddr
/proc/devinfo/ddr_type
/proc/devinfo/ufs
/sys/block/sdc/device/vendor
/sys/block/sdc/device/model
/sys/block/sdc/device/rev
/sys/devices/platform/soc/16810000.ufshci/device_descriptor/manufacturer_id
/sys/devices/platform/soc/16810000.ufshci/string_descriptors/manufacturer_name
/sys/devices/platform/soc/16810000.ufshci/string_descriptors/product_name
```

这些是验证机路径示例。查询时只读发现当前设备的控制器地址、盘符及节点布局。Permission denied 不能证明 leaf 存在或不存在。

getprop、工程软件版本页、初始 bugreport 均没给出可用厂商值。bugreport 内容很多且含个人日志，不作为默认第一步。软件版本页没有 RAM／UFS 字段，也不应反复要求用户滚动。

`IStorageHealthInfoService` 在这版系统中的只读事务：1=`getstrStorageHealthInfo()`，2=`getStorageHealthInfoItem()`，3=`getStorageOriginalInfo()`。1、3 对普通 shell 明确返回无权限；2 只给字段名，不能当成字段值。服务按调用 UID 限制，允许 qualityprotect、engineermode、postmanservice 的系统应用，普通 `pm grant` 不解决 UID 校验。

底层服务名 `vendor.oplus.hardware.performance.IPerformance/default`，这版 proxy 中 28=`getDevinfoUfsInfo()`、29=`getDevinfoDDRInfo()`、30=`getDevinfoUfsVersionInfo()`。普通 shell 即使 `service check` 显示存在，`service call` 仍可因访问策略返回 does not exist。

以上事务编号只用于理解这次调查。不同版本必须先从本机接口确认签名／事务号，禁止试探未知编号：相邻事务可能写入系统。

手机管家诊断 Activity 受厂商权限保护，普通 `am start` 被拒绝。用户从已授权的手机管家 UI 进入，才能由诊断应用调用接口。`ConnectionService` 虽可由 shell 启动，本次核对发现 PC 诊断命令要求厂商签名认证，未发送检测请求，随后停止服务；不作为本技能的采集路径。

## 排障与结束条件

1. 没有对应包／入口：说明当前系统不适用，尝试已有只读硬件节点。
2. 没日志：确认启动顺序与勾选项；至多做一次纠正后的重试，避免让用户反复跑全套检测。
3. 日志有 map 但 DDRDev 或 MemoryDev 为 null／unknown：报告缺失，不以示例填充。脚本保留有值的部分。
4. DEBUG 标签设置被拒绝：脚本报错并恢复已改标签；不要改持久属性或系统安全开关绕过。
5. 捕获进程异常／超时：查看退出信息，确认标签恢复。进程强杀、断开 USB 或电脑关机可能阻断 finally；只能在再次连上同一设备后依据启动时打印的原值恢复，不能一律清空。

手动恢复示例，空原值使用 Android shell 的空字符串：

```text
adb -s SERIAL shell "setprop log.tag.Postman-StorageHealthCheckItem ''"
adb -s SERIAL shell "setprop log.tag.StorageHealthInfoService ''"
```

非空原值用实际原值替换 `''`。不要 `adb kill-server`，不要杀掉其他人的 logcat，也不要清空全局日志缓冲区。
