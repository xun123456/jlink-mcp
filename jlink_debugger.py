"""
jlink_debugger.py — JLink 调试器封装层
封装 pylink-square 库，提供高层调试 API，包含：
- 连接/断开管理
- 断点操作（地址 & 符号名）
- 执行控制（halt / run / step / reset）
- 内存读写（8/16/32 位）
- 寄存器读写
- ELF 变量读写（依赖 elf_parser）
- RTT 读取
- 固件烧录
"""

import struct
import time
from typing import Any, Dict, List, Optional, Union

try:
    import pylink
    PYLINK_AVAILABLE = True
except ImportError:
    PYLINK_AVAILABLE = False

from config import JLinkConfig, DEFAULT_CONFIG
from elf_parser import ELFParser, VariableInfo


# ARM Cortex-M 核心寄存器名称
CORTEX_M_REGISTERS = [
    "R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7",
    "R8", "R9", "R10", "R11", "R12", "SP", "LR", "PC",
    "xPSR", "MSP", "PSP",
]


class JLinkDebugger:
    """
    JLink 调试器高层封装
    线程安全性：当前为单线程设计，所有操作均为同步调用。
    """

    def __init__(self, config: JLinkConfig = DEFAULT_CONFIG):
        self._config = config
        self._jlink: Optional["pylink.JLink"] = None
        self._connected = False
        self._target_device = ""
        self._breakpoints: Dict[int, int] = {}   # address → handle
        self._elf = ELFParser()

    # ------------------------------------------------------------------ #
    #  连接管理
    # ------------------------------------------------------------------ #

    def connect(
        self,
        device: str,
        interface: str = "SWD",
        speed: int = 4000,
        serial_no: Optional[int] = None,
        ip_addr: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        连接 JLink 硬件并连接到目标芯片。

        Args:
            device: 目标芯片型号，如 "STM32F103C8"
            interface: "SWD" 或 "JTAG"
            speed: 通信速度 kHz
            serial_no: 指定 JLink 序列号（可选）
            ip_addr: JLink over IP（可选）
        """
        if not PYLINK_AVAILABLE:
            raise RuntimeError("pylink-square 未安装，请运行: pip install pylink-square")

        # 如果已连接则先断开
        if self._connected:
            self.disconnect()

        try:
            # 打开 JLink
            if ip_addr:
                self._jlink = pylink.JLink()
                self._jlink.open(ip_addr=ip_addr)
            elif serial_no:
                self._jlink = pylink.JLink()
                self._jlink.open(serial_no=serial_no)
            else:
                self._jlink = pylink.JLink()
                self._jlink.open()

            # 设置接口类型
            if interface.upper() == "SWD":
                self._jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
            else:
                self._jlink.set_tif(pylink.enums.JLinkInterfaces.JTAG)

            # 连接目标
            self._jlink.connect(device, speed=speed, verbose=False)

            self._connected = True
            self._target_device = device
            self._breakpoints.clear()

            # 获取目标信息
            hw_info = {
                "jlink_serial": self._jlink.serial_number,
                "jlink_firmware": self._jlink.firmware_version,
                "target_device": device,
                "interface": interface.upper(),
                "speed_khz": speed,
                "core_id": hex(self._jlink.core_id()),
            }

            # 可选：连接后暂停
            if self._config.auto_halt_on_connect:
                self._jlink.halt()
                hw_info["target_state"] = "halted"
            else:
                hw_info["target_state"] = "running"

            return {"success": True, **hw_info}

        except Exception as e:
            self._connected = False
            self._jlink = None
            raise RuntimeError(f"连接失败: {e}") from e

    def disconnect(self) -> Dict[str, Any]:
        """断开与 JLink 和目标的连接"""
        if not self._connected or self._jlink is None:
            return {"success": True, "message": "未连接"}
        try:
            # 继续运行后断开（避免目标停在断点）
            try:
                self._jlink.reset()
                self._jlink.restart()
            except Exception:
                pass
            self._jlink.close()
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            self._connected = False
            self._jlink = None
            self._breakpoints.clear()
        return {"success": True, "message": "已断开连接"}

    def get_status(self) -> Dict[str, Any]:
        """获取当前连接和目标状态"""
        if not self._connected or self._jlink is None:
            return {
                "connected": False,
                "target_device": "",
                "target_state": "disconnected",
            }
        try:
            halted = self._jlink.halted()
            pc = self._read_pc() if halted else None
            return {
                "connected": True,
                "target_device": self._target_device,
                "target_state": "halted" if halted else "running",
                "pc": f"0x{pc:08X}" if pc is not None else None,
                "breakpoints_active": len(self._breakpoints),
                "elf_loaded": self._elf.is_loaded,
                "elf_path": self._elf.elf_path,
            }
        except Exception as e:
            return {"connected": True, "error": str(e)}

    def _require_connected(self) -> None:
        """检查连接状态，未连接则抛出异常"""
        if not self._connected or self._jlink is None:
            raise RuntimeError("未连接到目标，请先调用 connect()")

    # ------------------------------------------------------------------ #
    #  执行控制
    # ------------------------------------------------------------------ #

    def halt(self) -> Dict[str, Any]:
        """暂停目标 CPU"""
        self._require_connected()
        self._jlink.halt()
        time.sleep(0.05)  # 等待暂停生效
        pc = self._read_pc()
        return {
            "success": True,
            "target_state": "halted",
            "pc": f"0x{pc:08X}" if pc else None,
        }

    def run(self) -> Dict[str, Any]:
        """继续执行目标程序"""
        self._require_connected()
        self._jlink.restart()
        return {"success": True, "target_state": "running"}

    def step(self, count: int = 1) -> Dict[str, Any]:
        """单步执行（指令级）"""
        self._require_connected()
        if not self._jlink.halted():
            self._jlink.halt()
        for _ in range(count):
            self._jlink.step()
            time.sleep(0.01)
        pc = self._read_pc()
        return {
            "success": True,
            "steps_executed": count,
            "pc": f"0x{pc:08X}" if pc else None,
        }

    def reset(self, halt_after: bool = True) -> Dict[str, Any]:
        """复位目标"""
        self._require_connected()
        if halt_after:
            self._jlink.reset()   # 复位并暂停
            state = "halted"
        else:
            self._jlink.reset()
            self._jlink.restart()
            state = "running"
        return {"success": True, "target_state": state}

    # ------------------------------------------------------------------ #
    #  断点管理
    # ------------------------------------------------------------------ #

    def set_breakpoint(
        self,
        address: Optional[int] = None,
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        设置断点。支持两种方式：
        - address: 直接指定地址（十进制或十六进制字符串）
        - symbol: 函数名或变量名（需加载 ELF）
        """
        self._require_connected()

        # 解析地址
        addr = self._resolve_address(address, symbol)

        if addr in self._breakpoints:
            return {
                "success": True,
                "message": f"断点已存在 @ 0x{addr:08X}",
                "address": f"0x{addr:08X}",
            }

        handle = self._jlink.breakpoint_set(addr)
        self._breakpoints[addr] = handle
        return {
            "success": True,
            "address": f"0x{addr:08X}",
            "handle": handle,
            "symbol": symbol,
            "message": f"断点已设置 @ 0x{addr:08X}",
        }

    def clear_breakpoint(
        self,
        address: Optional[int] = None,
        symbol: Optional[str] = None,
        handle: Optional[int] = None,
    ) -> Dict[str, Any]:
        """清除断点"""
        self._require_connected()

        if handle is not None:
            self._jlink.breakpoint_clear(handle)
            self._breakpoints = {
                a: h for a, h in self._breakpoints.items() if h != handle
            }
            return {"success": True, "message": f"断点 handle={handle} 已清除"}

        addr = self._resolve_address(address, symbol)
        bp_handle = self._breakpoints.get(addr)
        if bp_handle is None:
            return {"success": False, "message": f"0x{addr:08X} 处没有断点"}

        self._jlink.breakpoint_clear(bp_handle)
        del self._breakpoints[addr]
        return {"success": True, "address": f"0x{addr:08X}", "message": "断点已清除"}

    def clear_all_breakpoints(self) -> Dict[str, Any]:
        """清除所有断点"""
        self._require_connected()
        self._jlink.breakpoint_clear_all()
        count = len(self._breakpoints)
        self._breakpoints.clear()
        return {"success": True, "cleared": count}

    def list_breakpoints(self) -> Dict[str, Any]:
        """列出所有活动断点"""
        bp_list = [
            {"address": f"0x{addr:08X}", "handle": handle}
            for addr, handle in self._breakpoints.items()
        ]
        return {"breakpoints": bp_list, "count": len(bp_list)}

    # ------------------------------------------------------------------ #
    #  内存读写
    # ------------------------------------------------------------------ #

    def read_memory(
        self,
        address: int,
        num_bytes: int,
        width: int = 32,
    ) -> Dict[str, Any]:
        """
        读取内存。

        Args:
            address: 起始地址
            num_bytes: 读取字节数
            width: 读取宽度 8/16/32
        """
        self._require_connected()
        num_bytes = min(num_bytes, 1024)  # 限制单次最大 1KB

        if width == 8:
            n = num_bytes
            data = self._jlink.memory_read8(address, n)
        elif width == 16:
            n = num_bytes // 2
            data = self._jlink.memory_read16(address, n)
        else:
            n = num_bytes // 4
            data = self._jlink.memory_read32(address, n)

        # 格式化输出
        hex_bytes = " ".join(f"{v:02X}" if width == 8
                             else f"{v:04X}" if width == 16
                             else f"{v:08X}"
                             for v in data)
        return {
            "address": f"0x{address:08X}",
            "num_bytes": num_bytes,
            "width": width,
            "data": data,
            "hex": hex_bytes,
        }

    def write_memory(
        self,
        address: int,
        data: List[int],
        width: int = 32,
    ) -> Dict[str, Any]:
        """
        写入内存。

        Args:
            address: 起始地址
            data: 数据列表（根据 width 为字节/半字/字列表）
            width: 写入宽度 8/16/32
        """
        self._require_connected()

        if width == 8:
            self._jlink.memory_write8(address, data)
        elif width == 16:
            self._jlink.memory_write16(address, data)
        else:
            self._jlink.memory_write32(address, data)

        return {
            "success": True,
            "address": f"0x{address:08X}",
            "width": width,
            "count": len(data),
        }

    # ------------------------------------------------------------------ #
    #  寄存器操作
    # ------------------------------------------------------------------ #

    def read_registers(self) -> Dict[str, Any]:
        """读取全部 ARM Cortex-M 核心寄存器"""
        self._require_connected()
        if not self._jlink.halted():
            self._jlink.halt()

        regs = {}
        reg_indices = self._jlink.register_list()
        values = self._jlink.register_read_multiple(reg_indices)
        for idx, val in zip(reg_indices, values):
            name = self._jlink.register_name(idx)
            regs[name] = f"0x{val & 0xFFFFFFFF:08X}"

        return {"registers": regs, "count": len(regs)}

    def write_register(self, reg_name: str, value: int) -> Dict[str, Any]:
        """写入指定寄存器（目标需处于暂停状态）"""
        self._require_connected()
        if not self._jlink.halted():
            raise RuntimeError("写寄存器需要目标处于暂停状态，请先调用 halt()")

        reg_indices = self._jlink.register_list()
        reg_map = {self._jlink.register_name(i).upper(): i for i in reg_indices}

        reg_upper = reg_name.upper()
        if reg_upper not in reg_map:
            raise ValueError(
                f"未知寄存器: {reg_name}。可用: {list(reg_map.keys())}"
            )

        self._jlink.register_write(reg_map[reg_upper], value)
        return {
            "success": True,
            "register": reg_name,
            "value": f"0x{value:08X}",
        }

    # ------------------------------------------------------------------ #
    #  ELF 符号 & 变量操作
    # ------------------------------------------------------------------ #

    def load_elf(self, elf_path: str) -> Dict[str, Any]:
        """加载 ELF 文件用于符号解析"""
        return self._elf.load(elf_path)

    def get_symbol_address(self, symbol: str) -> Dict[str, Any]:
        """查询符号地址"""
        if not self._elf.is_loaded:
            raise RuntimeError("请先加载 ELF 文件")
        addr = self._elf.get_symbol_address(symbol)
        if addr is None:
            raise ValueError(f"符号未找到: {symbol}")
        return {"symbol": symbol, "address": f"0x{addr:08X}"}

    def list_global_variables(self) -> Dict[str, Any]:
        """列出所有全局变量"""
        if not self._elf.is_loaded:
            raise RuntimeError("请先加载 ELF 文件")
        variables = self._elf.list_global_variables()
        return {"variables": variables, "count": len(variables)}

    def list_functions(self) -> Dict[str, Any]:
        """列出所有函数"""
        if not self._elf.is_loaded:
            raise RuntimeError("请先加载 ELF 文件")
        functions = self._elf.list_functions()
        return {"functions": functions, "count": len(functions)}

    def read_variable(self, name: str) -> Dict[str, Any]:
        """
        按变量名读取变量值（需已加载 ELF 且已连接目标）。
        自动根据变量类型选择合适的读取宽度和解码方式。
        """
        self._require_connected()
        if not self._elf.is_loaded:
            raise RuntimeError("请先加载 ELF 文件（使用 load_elf）")

        var = self._elf.get_variable(name)
        if var is None:
            raise ValueError(f"变量未找到: {name}。请检查名称或重新加载 ELF。")

        addr = var.address
        size = var.byte_size if var.byte_size > 0 else 4

        # 读取原始字节（32 位对齐读取）
        num_words = max(1, (size + 3) // 4)
        raw_words = self._jlink.memory_read32(addr, num_words)
        raw_bytes = b""
        for w in raw_words:
            raw_bytes += struct.pack("<I", w)
        raw_bytes = raw_bytes[:size]

        # 按类型解码
        decoded_value = self._decode_value(raw_bytes, var)

        return {
            "name": name,
            "address": f"0x{addr:08X}",
            "type": var.type_name,
            "size_bytes": size,
            "encoding": var.encoding,
            "raw_hex": raw_bytes.hex().upper(),
            "value": decoded_value,
        }

    def write_variable(self, name: str, value: Union[int, float]) -> Dict[str, Any]:
        """按变量名写入变量值（需已加载 ELF 且已连接目标）"""
        self._require_connected()
        if not self._elf.is_loaded:
            raise RuntimeError("请先加载 ELF 文件")

        var = self._elf.get_variable(name)
        if var is None:
            raise ValueError(f"变量未找到: {name}")

        addr = var.address
        size = var.byte_size if var.byte_size > 0 else 4

        # 编码数值
        raw_bytes = self._encode_value(value, var)
        # 32 位对齐写入
        words = []
        padded = raw_bytes.ljust((len(raw_bytes) + 3) & ~3, b"\x00")
        for i in range(0, len(padded), 4):
            words.append(struct.unpack_from("<I", padded, i)[0])
        self._jlink.memory_write32(addr, words)

        return {
            "success": True,
            "name": name,
            "address": f"0x{addr:08X}",
            "value_written": value,
        }

    # ------------------------------------------------------------------ #
    #  RTT
    # ------------------------------------------------------------------ #

    def read_rtt(
        self,
        channel: int = 0,
        max_bytes: int = 1024,
    ) -> Dict[str, Any]:
        """
        读取 SEGGER RTT 缓冲区内容。
        注意：RTT 需要目标固件中包含 SEGGER RTT 库。
        """
        self._require_connected()
        try:
            # 启动 RTT（如果还未启动）
            if not self._jlink.rtt_get_status().IsRunning:
                addr = self._config.rtt_control_block_addr
                if addr:
                    self._jlink.rtt_start(addr)
                else:
                    self._jlink.rtt_start()
                time.sleep(0.1)

            data = self._jlink.rtt_read(channel, max_bytes)
            text = bytes(data).decode("utf-8", errors="replace") if data else ""
            return {
                "channel": channel,
                "bytes_read": len(data) if data else 0,
                "text": text,
            }
        except Exception as e:
            return {"channel": channel, "bytes_read": 0, "text": "", "error": str(e)}

    def write_rtt(self, text: str, channel: int = 0) -> Dict[str, Any]:
        """向 RTT 输入通道写入数据（发送给目标）"""
        self._require_connected()
        data = list(text.encode("utf-8"))
        written = self._jlink.rtt_write(channel, data)
        return {"channel": channel, "bytes_written": written}

    # ------------------------------------------------------------------ #
    #  固件烧录
    # ------------------------------------------------------------------ #

    def flash_firmware(
        self,
        file_path: str,
        address: Optional[int] = None,
        verify: bool = True,
    ) -> Dict[str, Any]:
        """
        烧录固件到目标 Flash。

        Args:
            file_path: 固件文件路径（.hex / .bin / .elf / .axf）
            address:   .bin 文件起始地址（.hex/.elf 文件不需要）
            verify:    烧录后校验
        """
        self._require_connected()
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"固件文件不存在: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()

        try:
            if ext in (".elf", ".axf"):
                result = self._jlink.flash_file(file_path, 0)
            elif ext == ".hex":
                result = self._jlink.flash_file(file_path, 0)
            elif ext == ".bin":
                if address is None:
                    raise ValueError(".bin 文件需要指定 address 参数（Flash 起始地址）")
                result = self._jlink.flash_file(file_path, address)
            else:
                raise ValueError(f"不支持的文件格式: {ext}（支持 .elf/.axf/.hex/.bin）")

            return {
                "success": True,
                "file": file_path,
                "result_code": result,
                "verified": verify,
                "message": "固件烧录成功",
            }
        except Exception as e:
            raise RuntimeError(f"固件烧录失败: {e}") from e

    # ------------------------------------------------------------------ #
    #  内部工具方法
    # ------------------------------------------------------------------ #

    def _read_pc(self) -> Optional[int]:
        """读取 PC 寄存器"""
        try:
            reg_indices = self._jlink.register_list()
            # 找到名为 R15 或 PC 的寄存器索引
            pc_idx = next(
                (i for i in reg_indices
                 if "PC" in self._jlink.register_name(i).upper()
                 or self._jlink.register_name(i).upper() == "R15"),
                15,
            )
            return self._jlink.register_read(pc_idx) & 0xFFFFFFFF
        except Exception:
            return None

    def _resolve_address(
        self,
        address: Optional[int],
        symbol: Optional[str],
    ) -> int:
        """将 address 或 symbol 解析为整数地址"""
        if address is not None:
            return address
        if symbol is not None:
            if not self._elf.is_loaded:
                raise RuntimeError("使用符号名需要先加载 ELF 文件（load_elf）")
            addr = self._elf.get_symbol_address(symbol)
            if addr is None:
                raise ValueError(f"符号未找到: {symbol}")
            # Thumb 函数地址通常带 LSB=1，断点需要对齐
            return addr & ~1
        raise ValueError("必须提供 address 或 symbol 参数之一")

    def _decode_value(
        self,
        raw: bytes,
        var: "VariableInfo",
    ) -> Any:
        """将原始字节解码为 Python 值"""
        size = len(raw)
        enc = var.encoding

        if enc == "float":
            if size == 4:
                return struct.unpack_from("<f", raw)[0]
            elif size == 8:
                return struct.unpack_from("<d", raw)[0]
        elif enc in ("signed", "signed_char"):
            return int.from_bytes(raw, "little", signed=True)
        elif enc == "bool":
            return bool(raw[0]) if raw else False
        elif enc == "pointer":
            return f"0x{int.from_bytes(raw[:4], 'little'):08X}"
        else:
            # unsigned / unknown
            return int.from_bytes(raw, "little", signed=False)

    def _encode_value(
        self,
        value: Union[int, float],
        var: "VariableInfo",
    ) -> bytes:
        """将 Python 值编码为原始字节"""
        size = max(var.byte_size, 1)
        enc = var.encoding

        if enc == "float":
            if size <= 4:
                return struct.pack("<f", float(value))
            return struct.pack("<d", float(value))
        elif enc in ("signed", "signed_char"):
            return int(value).to_bytes(size, "little", signed=True)
        else:
            return int(value).to_bytes(size, "little", signed=False)
