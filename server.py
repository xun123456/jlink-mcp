"""
server.py — JLink MCP Server 主入口
基于 FastMCP 构建，将 JLink 调试功能暴露为 MCP tools。
支持 Claude Desktop、Cursor、Cline 等 MCP 客户端。
"""

from typing import Any, Dict, List, Optional, Union
from mcp.server.fastmcp import FastMCP
from jlink_debugger import JLinkDebugger
from config import COMMON_DEVICES, JLinkConfig

# ─────────────────────────────────────────────
#  全局状态
# ─────────────────────────────────────────────
mcp = FastMCP(
    name="jlink-mcp",
    instructions=(
        "JLink 单片机调试服务器。提供连接、断点、执行控制、内存读写、"
        "变量读写、RTT 日志、固件烧录等调试功能。"
        "使用前请先调用 connect() 连接目标芯片，"
        "如需按变量名调试请先调用 load_elf() 加载 ELF 文件。"
    ),
)

_debugger = JLinkDebugger()


# ─────────────────────────────────────────────
#  辅助函数
# ─────────────────────────────────────────────
def _parse_address(addr_str: Union[str, int]) -> int:
    """将字符串地址（十六进制/十进制）或整数转换为 int"""
    if isinstance(addr_str, int):
        return addr_str
    s = addr_str.strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(s, 10)


def _fmt_error(e: Exception) -> Dict[str, Any]:
    return {"success": False, "error": str(e), "error_type": type(e).__name__}


# ═══════════════════════════════════════════════
#  🔌 连接管理 Tools
# ═══════════════════════════════════════════════

@mcp.tool()
def connect(
    device: str,
    interface: str = "SWD",
    speed: int = 4000,
    serial_no: Optional[int] = None,
    ip_addr: Optional[str] = None,
) -> Dict[str, Any]:
    """
    连接 JLink 调试器并连接到目标单片机。
    必须在其他调试操作之前调用此工具。

    Args:
        device: 目标芯片型号，例如 "STM32F103C8"、"nRF52832_xxAA"。
                使用 list_devices() 查看常用芯片型号。
        interface: 调试接口，"SWD"（推荐，默认）或 "JTAG"。
        speed: 通信速度（kHz），默认 4000（4MHz）。
        serial_no: 指定 JLink 序列号（连接多个 JLink 时使用，可选）。
        ip_addr: JLink over IP 地址，如 "192.168.1.100"（可选）。

    Returns:
        连接结果，包含 JLink 固件版本、目标芯片信息和当前状态。
    """
    try:
        return _debugger.connect(
            device=device,
            interface=interface,
            speed=speed,
            serial_no=serial_no,
            ip_addr=ip_addr,
        )
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def disconnect() -> Dict[str, Any]:
    """
    断开 JLink 与目标单片机的连接。
    断开前会自动让目标继续运行，避免停在断点。

    Returns:
        断开结果。
    """
    try:
        return _debugger.disconnect()
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def get_status() -> Dict[str, Any]:
    """
    获取当前调试状态。

    Returns:
        包含连接状态、目标芯片型号、目标运行状态（运行中/已暂停）、
        当前 PC 地址、活动断点数量、ELF 加载状态等信息。
    """
    try:
        return _debugger.get_status()
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def list_devices() -> Dict[str, Any]:
    """
    列出常用单片机型号供参考。

    Returns:
        常用芯片型号字典，键为芯片型号字符串（可直接用于 connect()），
        值为芯片描述。
    """
    return {"devices": COMMON_DEVICES}


# ═══════════════════════════════════════════════
#  ▶️ 执行控制 Tools
# ═══════════════════════════════════════════════

@mcp.tool()
def halt() -> Dict[str, Any]:
    """
    暂停目标 CPU 执行。
    暂停后可以读写内存、读写寄存器、单步执行。

    Returns:
        包含目标状态和当前 PC 地址。
    """
    try:
        return _debugger.halt()
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def run() -> Dict[str, Any]:
    """
    继续执行目标程序（从当前 PC 位置继续运行）。
    如果有断点，目标将在断点处自动停下。

    Returns:
        执行状态。
    """
    try:
        return _debugger.run()
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def step(count: int = 1) -> Dict[str, Any]:
    """
    单步执行指令（指令级单步，不是源码级）。
    如果目标正在运行会先自动暂停。

    Args:
        count: 单步执行次数，默认 1 次。

    Returns:
        执行的步数和新的 PC 地址。
    """
    try:
        return _debugger.step(count=count)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def reset(halt_after: bool = True) -> Dict[str, Any]:
    """
    复位目标单片机。

    Args:
        halt_after: True（默认）= 复位后保持暂停，方便从头调试；
                    False = 复位后立即运行。

    Returns:
        复位结果和目标状态。
    """
    try:
        return _debugger.reset(halt_after=halt_after)
    except Exception as e:
        return _fmt_error(e)


# ═══════════════════════════════════════════════
#  🔴 断点管理 Tools
# ═══════════════════════════════════════════════

@mcp.tool()
def set_breakpoint(
    address: Optional[str] = None,
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    在指定地址或函数名处设置断点。
    必须提供 address 或 symbol 之一。

    Args:
        address: 十六进制地址字符串，如 "0x08001234" 或 "0x08001234"。
        symbol:  函数名或全局变量名，如 "main"、"HAL_GPIO_WritePin"。
                 使用符号名需要先调用 load_elf() 加载 ELF 文件。

    Returns:
        断点设置结果，包含断点地址和句柄。
    """
    try:
        addr_int = _parse_address(address) if address else None
        return _debugger.set_breakpoint(address=addr_int, symbol=symbol)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def clear_breakpoint(
    address: Optional[str] = None,
    symbol: Optional[str] = None,
    handle: Optional[int] = None,
) -> Dict[str, Any]:
    """
    清除断点。可以通过地址、符号名或断点句柄来指定。

    Args:
        address: 断点地址（十六进制字符串）。
        symbol:  断点处的符号名（需已加载 ELF）。
        handle:  断点句柄（由 set_breakpoint() 返回）。

    Returns:
        清除结果。
    """
    try:
        addr_int = _parse_address(address) if address else None
        return _debugger.clear_breakpoint(
            address=addr_int, symbol=symbol, handle=handle
        )
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def clear_all_breakpoints() -> Dict[str, Any]:
    """
    清除所有已设置的断点。

    Returns:
        清除的断点数量。
    """
    try:
        return _debugger.clear_all_breakpoints()
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def list_breakpoints() -> Dict[str, Any]:
    """
    列出所有当前活动的断点。

    Returns:
        断点列表，每个断点包含地址和句柄。
    """
    try:
        return _debugger.list_breakpoints()
    except Exception as e:
        return _fmt_error(e)


# ═══════════════════════════════════════════════
#  🧠 内存读写 Tools
# ═══════════════════════════════════════════════

@mcp.tool()
def read_memory(
    address: str,
    num_bytes: int = 16,
    width: int = 32,
) -> Dict[str, Any]:
    """
    读取目标内存。

    常用地址范围参考（ARM Cortex-M）：
    - 0x08000000: Flash 起始（STM32）
    - 0x20000000: SRAM 起始
    - 0x40000000: 外设寄存器区域
    - 0xE0000000: CoreSight 调试区域

    Args:
        address:   起始地址，十六进制字符串如 "0x20000000"。
        num_bytes: 读取字节数，最大 1024，默认 16。
        width:     读取宽度，8（字节）、16（半字）、32（字，默认）。

    Returns:
        读取到的数据（整数列表）和十六进制显示字符串。
    """
    try:
        addr_int = _parse_address(address)
        return _debugger.read_memory(addr_int, num_bytes, width)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def write_memory(
    address: str,
    data: List[int],
    width: int = 32,
) -> Dict[str, Any]:
    """
    向目标内存写入数据。

    Args:
        address: 起始地址，十六进制字符串如 "0x20000100"。
        data:    要写入的数据列表。
                 width=8 时为字节列表，如 [0x01, 0xFF]；
                 width=16 时为半字列表，如 [0x1234]；
                 width=32 时为字列表，如 [0xDEADBEEF]。
        width:   写入宽度，8/16/32，默认 32。

    Returns:
        写入结果。
    """
    try:
        addr_int = _parse_address(address)
        return _debugger.write_memory(addr_int, data, width)
    except Exception as e:
        return _fmt_error(e)


# ═══════════════════════════════════════════════
#  📊 寄存器 Tools
# ═══════════════════════════════════════════════

@mcp.tool()
def read_registers() -> Dict[str, Any]:
    """
    读取 ARM Cortex-M CPU 所有核心寄存器。
    目标需处于暂停状态（不暂停会自动暂停）。

    Returns:
        寄存器名称到值的映射，包括 R0-R12、SP、LR、PC、xPSR 等。
    """
    try:
        return _debugger.read_registers()
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def write_register(reg_name: str, value: str) -> Dict[str, Any]:
    """
    写入指定 CPU 寄存器。目标必须处于暂停状态。

    Args:
        reg_name: 寄存器名，如 "PC"、"R0"、"SP"、"LR"（不区分大小写）。
        value:    写入值，十六进制字符串如 "0x08001234" 或十进制字符串如 "1024"。

    Returns:
        写入结果。
    """
    try:
        val_int = _parse_address(value)
        return _debugger.write_register(reg_name, val_int)
    except Exception as e:
        return _fmt_error(e)


# ═══════════════════════════════════════════════
#  📦 ELF 符号与变量 Tools
# ═══════════════════════════════════════════════

@mcp.tool()
def load_elf(elf_path: str) -> Dict[str, Any]:
    """
    加载 ELF/AXF 文件用于符号名解析。
    加载后可以使用变量名读写变量、使用函数名设置断点。

    Keil 生成路径示例：
      C:/Projects/MyProject/Objects/MyProject.axf
    CLion/CMake 生成路径示例：
      C:/Projects/MyProject/cmake-build-debug/MyProject.elf

    Args:
        elf_path: ELF 文件完整路径（.elf 或 .axf）。

    Returns:
        加载结果，包含符号数量、变量数量、是否包含 DWARF 调试信息。
    """
    try:
        return _debugger.load_elf(elf_path)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def get_symbol_address(symbol: str) -> Dict[str, Any]:
    """
    查询符号（函数/全局变量）的内存地址。
    需要先调用 load_elf() 加载 ELF 文件。

    Args:
        symbol: 符号名称，如 "main"、"SystemCoreClock"、"g_counter"。

    Returns:
        符号名称和对应的内存地址。
    """
    try:
        return _debugger.get_symbol_address(symbol)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def list_global_variables() -> Dict[str, Any]:
    """
    列出 ELF 文件中所有全局变量。
    需要先调用 load_elf() 加载 ELF 文件。

    Returns:
        全局变量列表，每个变量包含名称、地址、类型、大小。
    """
    try:
        return _debugger.list_global_variables()
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def list_functions() -> Dict[str, Any]:
    """
    列出 ELF 文件中所有函数符号。
    需要先调用 load_elf() 加载 ELF 文件。

    Returns:
        函数列表，每个函数包含名称和起始地址。
    """
    try:
        return _debugger.list_functions()
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def read_variable(name: str) -> Dict[str, Any]:
    """
    按变量名读取全局变量的当前值。
    需要先调用 load_elf() 和 connect()。
    目标可以处于运行或暂停状态（建议暂停以获得一致读数）。

    Args:
        name: 全局变量名，如 "g_counter"、"SystemCoreClock"、"g_state"。

    Returns:
        变量名、地址、类型、大小、原始十六进制值和解码后的值。
    """
    try:
        return _debugger.read_variable(name)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def write_variable(name: str, value: float) -> Dict[str, Any]:
    """
    按变量名修改全局变量的值。
    需要先调用 load_elf() 和 connect()。
    目标建议处于暂停状态，以确保写入一致性。

    Args:
        name:  全局变量名，如 "g_counter"、"g_mode"。
        value: 要写入的数值（整数或浮点数，系统会根据变量类型自动转换）。

    Returns:
        写入结果。
    """
    try:
        return _debugger.write_variable(name, value)
    except Exception as e:
        return _fmt_error(e)


# ═══════════════════════════════════════════════
#  📡 RTT Tools
# ═══════════════════════════════════════════════

@mcp.tool()
def read_rtt(channel: int = 0, max_bytes: int = 1024) -> Dict[str, Any]:
    """
    读取 SEGGER RTT（Real Time Transfer）缓冲区内容。
    RTT 是非侵入式实时日志通道，无需停止目标即可读取。
    需要目标固件中包含 SEGGER RTT 库并使用 SEGGER_RTT_printf() 输出。

    Args:
        channel:   RTT 通道号，默认 0（通常用于日志输出）。
        max_bytes: 最大读取字节数，默认 1024。

    Returns:
        读取到的 RTT 文本内容。
    """
    try:
        return _debugger.read_rtt(channel=channel, max_bytes=max_bytes)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def write_rtt(text: str, channel: int = 0) -> Dict[str, Any]:
    """
    向 RTT 输入通道发送数据（发送到目标单片机）。

    Args:
        text:    要发送的文本字符串。
        channel: RTT 通道号，默认 0。

    Returns:
        实际写入的字节数。
    """
    try:
        return _debugger.write_rtt(text=text, channel=channel)
    except Exception as e:
        return _fmt_error(e)


# ═══════════════════════════════════════════════
#  💾 固件烧录 Tools
# ═══════════════════════════════════════════════

@mcp.tool()
def flash_firmware(
    file_path: str,
    address: Optional[str] = None,
    verify: bool = True,
) -> Dict[str, Any]:
    """
    烧录固件到目标单片机 Flash。
    支持 .elf、.axf（Keil）、.hex（Intel HEX）、.bin 格式。

    Args:
        file_path: 固件文件完整路径。
                   Keil: .../Objects/MyProject.axf 或 .hex
                   CLion: .../cmake-build-debug/MyProject.elf
        address:   仅 .bin 文件需要，指定 Flash 起始地址，如 "0x08000000"。
                   .elf/.axf/.hex 文件不需要此参数（地址已包含在文件中）。
        verify:    烧录后是否校验，默认 True。

    Returns:
        烧录结果，包含成功/失败状态和错误信息（如有）。
    """
    try:
        addr_int = _parse_address(address) if address else None
        return _debugger.flash_firmware(
            file_path=file_path, address=addr_int, verify=verify
        )
    except Exception as e:
        return _fmt_error(e)


# ─────────────────────────────────────────────
#  启动入口
# ─────────────────────────────────────────────
def main():
    mcp.run()


if __name__ == "__main__":
    main()
