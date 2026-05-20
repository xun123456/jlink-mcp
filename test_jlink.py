"""
test_jlink.py — JLink 连接检测脚本
运行此脚本检测 JLink 硬件和目标设备基本信息
"""
import pylink

print("=" * 50)
print("  JLink MCP Server — 硬件检测")
print("=" * 50)

jlink = pylink.JLink()

# 1. 打开 JLink
print("\n[1] 尝试打开 JLink...")
try:
    jlink.open()
    print(f"    ✅ JLink 已连接")
    print(f"    序列号  : {jlink.serial_number}")
    print(f"    固件版本: {jlink.firmware_version}")
    print(f"    硬件版本: {jlink.hardware_version}")
except Exception as e:
    print(f"    ❌ 打开失败: {e}")
    print("\n    请检查：")
    print("    - JLink USB 是否插好")
    print("    - SEGGER J-Link 驱动是否已安装")
    exit(1)

# 2. 尝试 SWD 接口扫描目标
print("\n[2] 设置 SWD 接口，扫描目标...")
try:
    jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
    jlink.set_speed(4000)
    
    # 读取 SWD IDCODE
    # 先尝试 SWD 的基本连接
    print("    SWD 接口设置成功")
    
    # 获取目标核心 ID（不需要 device 名称）
    try:
        core_id = jlink.core_id()
        print(f"    ✅ 目标响应！Core ID = 0x{core_id:08X}")
        
        # 分析 ARM IDCODE
        designer = (core_id >> 1) & 0x7FF
        part_no  = (core_id >> 12) & 0xFFFF
        version  = (core_id >> 28) & 0xF
        print(f"    设计商代码 : 0x{designer:03X}")
        print(f"    Part No    : 0x{part_no:04X}")
        print(f"    版本       : {version}")
        
        # 尝试识别常见芯片
        if part_no == 0x0BA0:
            print("    推测芯片族 : ARM Cortex-M0")
        elif part_no == 0x0BA1:
            print("    推测芯片族 : ARM Cortex-M1")
        elif part_no == 0x0BA3:
            print("    推测芯片族 : ARM Cortex-M3")
        elif part_no == 0x0BA4:
            print("    推测芯片族 : ARM Cortex-M4")
        elif part_no == 0x0BA7:
            print("    推测芯片族 : ARM Cortex-M7")
        elif part_no == 0x0BD2:
            print("    推测芯片族 : ARM Cortex-M33")
            
    except Exception as e:
        print(f"    ⚠️  读取 Core ID 失败: {e}")
        print("    (需要在 connect() 时指定正确的 device 型号)")

except Exception as e:
    print(f"    ❌ SWD 设置失败: {e}")

# 3. 读取目标电压
print("\n[3] 测量目标供电电压...")
try:
    voltage = jlink.target_voltage()
    print(f"    目标电压: {voltage} mV ({voltage/1000:.2f} V)")
    if voltage < 1500:
        print("    ⚠️  电压偏低，请检查目标板供电")
    elif voltage > 4000:
        print("    ⚠️  电压偏高，请确认接线")
    else:
        print("    ✅ 电压正常")
except Exception as e:
    print(f"    ⚠️  读取电压失败: {e}")

print("\n" + "=" * 50)
print("  检测完成！请告诉我你的芯片型号，")
print("  例如：STM32F103C8、STM32F407VG 等")
print("  然后我将调用 connect() 进行完整连接测试")
print("=" * 50)

jlink.close()
