"""
test_full.py — JLink MCP Server 完整功能测试
目标: STM32H7B0VB (Cortex-M7, SWD)
"""
import sys
import time
sys.stdout.reconfigure(encoding='utf-8')

# 直接导入调试器模块
from jlink_debugger import JLinkDebugger
from config import JLinkConfig

cfg = JLinkConfig(
    interface="SWD",
    speed=4000,
    auto_halt_on_connect=True,
)
dbg = JLinkDebugger(cfg)

PASS = "[PASS]"
FAIL = "[FAIL]"
INFO = "[INFO]"
SEP  = "-" * 55

def banner(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

# ─────────────────────────────────────────────
print("=" * 55)
print("  JLink MCP Server — STM32H7B0VB 测试")
print("=" * 55)

# 1. 连接
banner("STEP 1: 连接目标 (STM32H7B0VB, SWD 4MHz)")
try:
    result = dbg.connect(
        device="STM32H7B0VB",
        interface="SWD",
        speed=4000,
    )
    print(f"{PASS} 连接成功")
    print(f"       JLink S/N   : {result.get('jlink_serial')}")
    print(f"       固件版本    : {result.get('jlink_firmware')}")
    print(f"       Core ID     : {result.get('core_id')}")
    print(f"       目标状态    : {result.get('target_state')}")
except Exception as e:
    print(f"{FAIL} 连接失败: {e}")
    sys.exit(1)

# 2. 暂停
banner("STEP 2: 暂停目标 CPU")
try:
    r = dbg.halt()
    print(f"{PASS} halt() 成功 — 状态: {r.get('target_state')}")
    print(f"       当前 PC: {r.get('pc')}")
except Exception as e:
    print(f"{FAIL} halt() 失败: {e}")

# 3. 读取寄存器
banner("STEP 3: 读取 CPU 寄存器")
try:
    r = dbg.read_registers()
    regs = r.get("registers", {})
    print(f"{PASS} 读取 {r.get('count')} 个寄存器成功")
    # 打印关键寄存器
    key_regs = ["R0", "R1", "R2", "R3", "PC", "SP", "LR"]
    for name in key_regs:
        # 寄存器名可能有不同格式，做模糊匹配
        val = next((v for k, v in regs.items() if name in str(k).upper()), "N/A")
        print(f"       {name:5s}: {val}")
except Exception as e:
    print(f"{FAIL} 读取寄存器失败: {e}")

# 4. 读取 SRAM 内存
banner("STEP 4: 读取 SRAM 内存 (0x24000000)")
# STM32H7B0VB SRAM 起始地址 (AXI SRAM)
SRAM_ADDR = 0x24000000
try:
    r = dbg.read_memory(SRAM_ADDR, num_bytes=32, width=32)
    print(f"{PASS} read_memory(0x{SRAM_ADDR:08X}, 32 bytes) 成功")
    print(f"       HEX: {r.get('hex')}")
    print(f"       数据: {r.get('data')}")
except Exception as e:
    print(f"{FAIL} 读取内存失败: {e}")

# 5. 写入 + 回读内存验证
banner("STEP 5: 写入/读回内存验证")
TEST_ADDR = 0x24000100   # SRAM 偏移 256 字节
TEST_DATA = [0xDEADBEEF, 0xCAFEBABE, 0x12345678, 0xAABBCCDD]
try:
    dbg.write_memory(TEST_ADDR, TEST_DATA, width=32)
    r = dbg.read_memory(TEST_ADDR, num_bytes=16, width=32)
    read_back = r.get("data", [])
    if read_back == TEST_DATA:
        print(f"{PASS} 写入/读回验证通过")
        print(f"       写入: {[hex(x) for x in TEST_DATA]}")
        print(f"       读回: {[hex(x) for x in read_back]}")
    else:
        print(f"{FAIL} 数据不匹配!")
        print(f"       期望: {[hex(x) for x in TEST_DATA]}")
        print(f"       实际: {[hex(x) for x in read_back]}")
except Exception as e:
    print(f"{FAIL} 写内存失败: {e}")

# 6. 断点测试（在当前 PC 设置断点）
banner("STEP 6: 断点操作测试")
try:
    # 获取当前 PC
    r_regs = dbg.read_registers()
    regs = r_regs.get("registers", {})
    pc_val = next((v for k, v in regs.items() if "PC" in str(k).upper()), None)
    
    if pc_val:
        pc_int = int(pc_val, 16) & ~1   # 对齐到偶数
        bp_addr = pc_int + 4             # 在 PC+4 设置断点
        
        r_set = dbg.set_breakpoint(address=bp_addr)
        print(f"{PASS} set_breakpoint(0x{bp_addr:08X}) — handle={r_set.get('handle')}")
        
        r_list = dbg.list_breakpoints()
        print(f"       当前断点数: {r_list.get('count')}")
        
        r_clr = dbg.clear_all_breakpoints()
        print(f"{PASS} clear_all_breakpoints() — 清除 {r_clr.get('cleared')} 个")
    else:
        print(f"{INFO} 无法获取 PC，跳过断点测试")
except Exception as e:
    print(f"{FAIL} 断点测试失败: {e}")

# 7. 单步执行
banner("STEP 7: 单步执行 (step x3)")
try:
    r_before = dbg.read_registers()
    regs_before = r_before.get("registers", {})
    pc_before = next((v for k, v in regs_before.items() if "PC" in str(k).upper()), "?")
    
    r_step = dbg.step(count=3)
    
    r_after = dbg.read_registers()
    regs_after = r_after.get("registers", {})
    pc_after = next((v for k, v in regs_after.items() if "PC" in str(k).upper()), "?")
    
    print(f"{PASS} step(3) 完成")
    print(f"       执行前 PC: {pc_before}")
    print(f"       执行后 PC: {pc_after}")
    if pc_before != pc_after:
        print(f"       PC 已推进，单步正常工作")
except Exception as e:
    print(f"{FAIL} 单步失败: {e}")

# 8. get_status
banner("STEP 8: 状态查询")
try:
    r = dbg.get_status()
    print(f"{PASS} get_status() 成功")
    print(f"       连接状态 : {r.get('connected')}")
    print(f"       目标设备 : {r.get('target_device')}")
    print(f"       运行状态 : {r.get('target_state')}")
    print(f"       PC       : {r.get('pc')}")
    print(f"       断点数量 : {r.get('breakpoints_active')}")
except Exception as e:
    print(f"{FAIL} 状态查询失败: {e}")

# 9. 恢复运行
banner("STEP 9: 恢复运行")
try:
    r = dbg.run()
    print(f"{PASS} run() — 目标已继续运行")
    time.sleep(0.2)
    r_status = dbg.get_status()
    print(f"       运行状态: {r_status.get('target_state')}")
except Exception as e:
    print(f"{FAIL} run() 失败: {e}")

# 10. 断开
banner("STEP 10: 断开连接")
try:
    r = dbg.disconnect()
    print(f"{PASS} disconnect() — {r.get('message')}")
except Exception as e:
    print(f"{FAIL} 断开失败: {e}")

print(f"\n{'=' * 55}")
print("  测试完成！")
print(f"{'=' * 55}\n")
