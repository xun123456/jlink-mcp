# JLink MCP Server

> 🔌 让 AI 直接调试你的单片机 — 基于 Model Context Protocol (MCP)

通过本项目，**Claude、Cursor** 等 AI 助手可以直接通过 JLink 调试器控制单片机，实现：设置断点、单步执行、读写内存、读取变量、查看寄存器、RTT 日志、烧录固件等完整调试功能。

已在 **STM32H7B0VB (Cortex-M7)** 上完成真机验证，全部功能正常。

---

## 功能特性

- ✅ **连接管理** — 支持 SWD / JTAG，支持多 JLink、JLink over IP
- ✅ **断点控制** — 按地址或函数名设置/清除断点
- ✅ **执行控制** — 暂停、继续、单步、复位
- ✅ **内存读写** — 支持 8/16/32 位宽度，最大单次 1KB
- ✅ **寄存器读写** — 读写全部 CPU 核心寄存器（R0-R15、PC、SP、LR、xPSR 等）
- ✅ **变量调试** — 按变量名读写全局变量（自动解析 ELF/DWARF 调试信息）
- ✅ **符号解析** — 加载 `.elf` / `.axf` 获取函数地址、变量地址
- ✅ **RTT 日志** — 读写 SEGGER RTT 实时通道
- ✅ **固件烧录** — 支持 `.elf` / `.axf` / `.hex` / `.bin` 格式
- ✅ **兼容 Keil MDK 和 CLion/CMake** 工作流

---

## 目录结构

```
jlink-mcp/
├── server.py              # MCP 服务器主入口（25 个工具）
├── jlink_debugger.py      # JLink 操作封装（基于 pylink-square）
├── elf_parser.py          # ELF/DWARF 解析（变量名 → 地址 + 类型）
├── config.py              # 配置类 + 常用芯片型号表
├── requirements.txt       # Python 依赖
├── pyproject.toml         # 项目元数据
├── claude_desktop_config.json  # Claude Desktop 配置模板
├── test_jlink.py          # JLink 硬件检测脚本
├── test_full.py           # 完整功能测试脚本
└── README.md              # 本文档
```

---

## 环境要求

| 依赖 | 说明 |
|---|---|
| **SEGGER J-Link 驱动** | [下载](https://www.segger.com/downloads/jlink/) — 必须安装，提供 `JLinkARM.dll` |
| **Python 3.10+** | [python.org](https://www.python.org/) |
| **JLink 调试器硬件** | J-Link BASE / EDU / PLUS / OB 均可 |

---

## 安装

```powershell
# 进入项目目录
cd "jlink-mcp"

# 安装依赖（国内使用清华镜像）
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
```

**requirements.txt 内容：**
```
mcp[cli]>=1.0.0
pylink-square>=0.12.0
pyelftools>=0.31
```

---

## MCP 工具列表（25 个）

### 🔌 连接管理
| 工具 | 参数 | 说明 |
|---|---|---|
| `connect` | `device`, `interface="SWD"`, `speed=4000` | 连接 JLink 和目标芯片 |
| `disconnect` | — | 断开连接（自动恢复目标运行） |
| `get_status` | — | 查询连接状态、目标状态、PC、断点数 |
| `list_devices` | — | 列出常用芯片型号（用于 connect 参数参考） |

### ▶️ 执行控制
| 工具 | 参数 | 说明 |
|---|---|---|
| `halt` | — | 暂停目标 CPU |
| `run` | — | 继续运行 |
| `step` | `count=1` | 单步执行（指令级，支持多步） |
| `reset` | `halt_after=True` | 复位（默认复位后保持暂停） |

### 🔴 断点管理
| 工具 | 参数 | 说明 |
|---|---|---|
| `set_breakpoint` | `address` 或 `symbol` | 设置断点（地址或函数名） |
| `clear_breakpoint` | `address` 或 `symbol` 或 `handle` | 清除指定断点 |
| `clear_all_breakpoints` | — | 清除全部断点 |
| `list_breakpoints` | — | 列出所有活动断点 |

### 🧠 内存读写
| 工具 | 参数 | 说明 |
|---|---|---|
| `read_memory` | `address`, `num_bytes=16`, `width=32` | 读内存（最大 1KB） |
| `write_memory` | `address`, `data[]`, `width=32` | 写内存 |

### 📊 寄存器
| 工具 | 参数 | 说明 |
|---|---|---|
| `read_registers` | — | 读取全部 CPU 寄存器（R0-R15、PC、SP、LR 等） |
| `write_register` | `reg_name`, `value` | 写入指定寄存器 |

### 📦 符号与变量（需加载 ELF）
| 工具 | 参数 | 说明 |
|---|---|---|
| `load_elf` | `elf_path` | 加载 `.elf` 或 `.axf` 文件 |
| `get_symbol_address` | `symbol` | 查询符号地址 |
| `list_global_variables` | — | 列出所有全局变量（含地址、类型、大小） |
| `list_functions` | — | 列出所有函数符号 |
| `read_variable` | `name` | 按变量名读取值（自动类型解码） |
| `write_variable` | `name`, `value` | 按变量名写入值 |

### 📡 RTT 实时日志
| 工具 | 参数 | 说明 |
|---|---|---|
| `read_rtt` | `channel=0`, `max_bytes=1024` | 读取 SEGGER RTT 日志 |
| `write_rtt` | `text`, `channel=0` | 向目标发送 RTT 数据 |

### 💾 固件烧录
| 工具 | 参数 | 说明 |
|---|---|---|
| `flash_firmware` | `file_path`, `address`（仅.bin需要）, `verify=True` | 烧录固件 |

---

## 配置 AI 客户端

### Claude Desktop

编辑：`%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "jlink-mcp": {
      "command": "python",
      "args": ["C:\\path\\to\\jlink-mcp\\server.py"]
    }
  }
}
```

> **注意**：将路径替换为实际的 `server.py` 路径，然后**重启 Claude Desktop**。

### Cursor

Settings → Features → MCP Servers → Add Server：

```json
{
  "jlink-mcp": {
    "type": "stdio",
    "command": "python",
    "args": ["C:\\path\\to\\jlink-mcp\\server.py"]
  }
}
```

### VS Code (Cline / Continue)

`.vscode/mcp.json`：

```json
{
  "servers": {
    "jlink-mcp": {
      "type": "stdio",
      "command": "python",
      "args": ["C:\\path\\to\\jlink-mcp\\server.py"]
    }
  }
}
```

---

## 使用示例

### 基础调试流程

```
用户: 连接 STM32H7B0VB，SWD 接口
AI  → connect(device="STM32H7B0VB", interface="SWD")
   ← JLink S/N: 601012469, Core ID: 0x6ba02477, 已暂停

用户: 读取当前所有寄存器
AI  → read_registers()
   ← R0=0x00000000, PC=0x9008B598, SP=0x20006DD8...

用户: 在 main 函数设置断点，然后复位运行
AI  → load_elf("C:/Project/Debug/app.elf")
   → set_breakpoint(symbol="main")
   → reset(halt_after=False)
   ← 程序运行中，等待命中断点...

用户: 读取全局变量 g_counter 的值
AI  → read_variable(name="g_counter")
   ← name="g_counter", address=0x24000100, type="uint32_t", value=42

用户: 单步执行 5 次，查看 PC 变化
AI  → step(count=5)
   ← PC: 0x9008B598 → 0x9008B5A6

用户: 查看 RTT 日志输出
AI  → read_rtt()
   ← "[INFO] System init OK\r\n[INFO] Main loop start\r\n"
```

### Keil MDK 工作流

1. Keil 编译项目（生成 `.axf` 和 `.hex`）
2. **关闭 Keil 调试会话**（释放 JLink）
3. 对 AI 说：
   - `"加载 ELF: C:\Keil_Projects\MyProject\Objects\MyProject.axf"`
   - `"连接 STM32F103C8"`
   - `"在 HAL_GPIO_WritePin 设置断点，运行"`

### CLion / CMake 工作流

1. CLion 构建项目（生成 `.elf`）
2. **停止 CLion 调试会话**（释放 JLink）
3. 对 AI 说：
   - `"加载 ELF: C:\Projects\MyApp\cmake-build-debug\MyApp.elf"`
   - `"连接 STM32F407VG"`

---

## 常用芯片型号参考

| 型号字符串 | 芯片 |
|---|---|
| `STM32F103C8` | STM32F103C8T6 (Blue Pill), Cortex-M3 |
| `STM32F407VG` | STM32F407VGT6, Cortex-M4F |
| `STM32H7B0VB` | STM32H7B0VBT6, Cortex-M7 ✅ 已验证 |
| `STM32H743ZI` | STM32H743ZIT6, Cortex-M7 |
| `STM32G071RB` | STM32G071RBT6, Cortex-M0+ |
| `nRF52832_xxAA` | nRF52832, Cortex-M4F, BLE5 |
| `nRF52840_xxAA` | nRF52840, Cortex-M4F |
| `GD32F103C8` | GD32F103C8T6, STM32 兼容 |

---

## 真机测试结果

**测试设备：** STM32H7B0VB + J-Link V11 (S/N: 601012469)

| 测试项 | 结果 |
|---|---|
| 连接 JLink + 目标 (SWD 4MHz) | ✅ PASS |
| halt() 暂停 CPU | ✅ PASS |
| read_registers() — 115 个寄存器 | ✅ PASS |
| read_memory(0x24000000, 32B) | ✅ PASS |
| write_memory + 读回验证 | ✅ PASS (0xDEADBEEF 等精确一致) |
| set_breakpoint / clear_all_breakpoints | ✅ PASS |
| step(count=3) 单步 — PC 正确推进 | ✅ PASS |
| get_status() | ✅ PASS |
| run() 恢复运行 | ✅ PASS |
| disconnect() | ✅ PASS |

---

## 常见问题

**Q: 连接失败 "Cannot connect to J-Link"**
> 确认 JLink USB 已插好，SEGGER J-Link 驱动已安装，目标板已供电。

**Q: 找不到 JLinkARM.dll**
> 安装 [SEGGER J-Link Software Pack](https://www.segger.com/downloads/jlink/)。
> 默认路径：`C:\Program Files\SEGGER\JLink\JLinkARM.dll`

**Q: 变量读取提示"变量未找到"**
> 1. 确认已调用 `load_elf()` 加载了 ELF 文件
> 2. 确认是**全局变量**（局部变量需要目标暂停在特定帧才能读取）
> 3. 确认编译时开启了调试信息（Keil: Debug，CLion: Debug 配置）

**Q: Keil 和本工具能同时使用吗？**
> ❌ 不能，JLink 同一时间只能被一个程序独占。使用本工具前请关闭 Keil 的调试会话。

**Q: 支持 JTAG 吗？**
> 支持，`connect()` 时传入 `interface="JTAG"` 即可。

**Q: RTT 读取没有输出？**
> 目标固件需要集成 SEGGER RTT 库，并调用 `SEGGER_RTT_printf()` 输出数据。

---

## 依赖说明

| 库 | 版本 | 用途 |
|---|---|---|
| `mcp[cli]` | ≥1.0.0 | MCP 协议服务器框架 (FastMCP) |
| `pylink-square` | ≥0.12.0 | JLink DLL Python 封装 |
| `pyelftools` | ≥0.31 | ELF/DWARF 解析，变量符号解析 |

---

## License

MIT License — 可自由使用、修改和分发。

---

## 开发信息

- **开发语言**: Python 3.10+
- **MCP 框架**: FastMCP (mcp[cli])
- **JLink 接口**: pylink-square → JLinkARM.dll
- **符号解析**: pyelftools (ELF/DWARF)
- **支持平台**: Windows（JLinkARM.dll）

## License

MIT — 详见 [LICENSE](LICENSE)。

