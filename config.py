"""
config.py — JLink MCP Server 配置
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class JLinkConfig:
    """JLink 连接与调试配置"""

    # --- 接口配置 ---
    interface: str = "SWD"          # "SWD" 或 "JTAG"
    speed: int = 4000               # 通信速度 kHz，4000 = 4 MHz
    device: str = ""                # 目标芯片型号，如 "STM32F103C8"

    # --- JLink 硬件选择 ---
    serial_no: Optional[int] = None      # 指定 JLink 序列号（多个 JLink 时使用）
    ip_addr: Optional[str] = None        # JLink over IP 地址（如 "192.168.1.100"）

    # --- 调试配置 ---
    auto_halt_on_connect: bool = True    # 连接后自动暂停目标
    reset_on_connect: bool = False       # 连接时复位目标

    # --- ELF 文件 ---
    elf_path: Optional[str] = None       # 默认 ELF 文件路径（用于符号解析）

    # --- RTT 配置 ---
    rtt_enabled: bool = True
    rtt_control_block_addr: Optional[int] = None  # RTT 控制块地址（None=自动搜索）
    rtt_search_start: int = 0x20000000   # RTT 搜索起始地址（RAM 起始）
    rtt_search_size: int = 0x10000       # RTT 搜索范围（64KB）

    # --- Flash 配置 ---
    flash_speed: int = 4000              # Flash 烧录速度 kHz


# 全局默认配置实例
DEFAULT_CONFIG = JLinkConfig()


# 常用芯片型号参考（供 AI 提示使用）
COMMON_DEVICES = {
    # STMicroelectronics
    "STM32F103C8": "STM32F103C8T6 (Blue Pill), Cortex-M3, 64KB Flash",
    "STM32F103RB": "STM32F103RBT6, Cortex-M3, 128KB Flash",
    "STM32F407VG": "STM32F407VGT6, Cortex-M4F, 1MB Flash",
    "STM32F411CE": "STM32F411CEU6, Cortex-M4F, 512KB Flash",
    "STM32F429ZI": "STM32F429ZIT6, Cortex-M4F, 2MB Flash",
    "STM32G071RB": "STM32G071RBT6, Cortex-M0+, 128KB Flash",
    "STM32H743ZI": "STM32H743ZIT6, Cortex-M7, 2MB Flash",
    "STM32L432KC": "STM32L432KCU6, Cortex-M4, 256KB Flash (低功耗)",
    # Nordic Semiconductor
    "nRF52832_xxAA": "nRF52832, Cortex-M4F, BLE5, 512KB Flash",
    "nRF52840_xxAA": "nRF52840, Cortex-M4F, BLE5+USB, 1MB Flash",
    "nRF5340_xxAA": "nRF5340, Dual Cortex-M33, BLE5.2",
    # NXP
    "LPC1768": "LPC1768, Cortex-M3, 512KB Flash",
    "MIMXRT1062": "i.MX RT1062 (Teensy 4.x), Cortex-M7",
    # GigaDevice (GD32 常见国产 STM32 兼容)
    "GD32F103C8": "GD32F103C8T6, Cortex-M3, STM32 兼容",
    "GD32F303RE": "GD32F303RET6, Cortex-M4, STM32 兼容",
    # Espressif (需要特殊支持)
    # RP2040: 不支持标准 JLink
}
