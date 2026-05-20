"""
elf_parser.py — ELF/DWARF 符号与变量解析器
支持从 Keil (.axf) 和 CLion (.elf) 生成的 ELF 文件中解析变量地址、大小和类型。
"""

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from elftools.elf.elffile import ELFFile
    from elftools.dwarf.descriptions import describe_form_class
    from elftools.dwarf.die import DIE
    ELFTOOLS_AVAILABLE = True
except ImportError:
    ELFTOOLS_AVAILABLE = False


@dataclass
class SymbolInfo:
    """符号信息"""
    name: str
    address: int
    size: int
    symbol_type: str   # "FUNC", "OBJECT", "NOTYPE" 等
    section: str


@dataclass
class VariableInfo:
    """变量信息（来自 DWARF 调试信息）"""
    name: str
    address: int
    type_name: str
    byte_size: int
    is_pointer: bool = False
    encoding: str = "unknown"   # "unsigned", "signed", "float", "bool" 等


class ELFParser:
    """
    ELF/DWARF 解析器
    - 从符号表获取函数/全局变量地址
    - 从 DWARF 调试信息获取变量类型和大小
    """

    def __init__(self):
        self._elf_path: Optional[str] = None
        self._symbols: Dict[str, SymbolInfo] = {}
        self._variables: Dict[str, VariableInfo] = {}
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def elf_path(self) -> Optional[str]:
        return self._elf_path

    def load(self, elf_path: str) -> Dict[str, Any]:
        """
        加载 ELF 文件，解析符号表和 DWARF 调试信息。
        返回加载结果摘要。
        """
        if not ELFTOOLS_AVAILABLE:
            raise RuntimeError(
                "pyelftools 未安装，请运行: pip install pyelftools"
            )

        path = Path(elf_path)
        if not path.exists():
            raise FileNotFoundError(f"ELF 文件不存在: {elf_path}")

        self._symbols.clear()
        self._variables.clear()
        self._loaded = False

        with open(elf_path, "rb") as f:
            elf = ELFFile(f)

            # 1. 解析符号表
            sym_count = self._parse_symbol_table(elf)

            # 2. 解析 DWARF 调试信息（变量类型）
            var_count = 0
            if elf.has_dwarf_info():
                var_count = self._parse_dwarf(elf)

        self._elf_path = elf_path
        self._loaded = True

        return {
            "elf_path": elf_path,
            "symbols_loaded": sym_count,
            "variables_loaded": var_count,
            "has_dwarf": var_count > 0,
        }

    def _parse_symbol_table(self, elf: "ELFFile") -> int:
        """从 .symtab 或 .dynsym 段解析符号"""
        count = 0
        for section in elf.iter_sections():
            from elftools.elf.sections import SymbolTableSection
            if not isinstance(section, SymbolTableSection):
                continue
            for sym in section.iter_symbols():
                if not sym.name:
                    continue
                info = SymbolInfo(
                    name=sym.name,
                    address=sym["st_value"],
                    size=sym["st_size"],
                    symbol_type=sym.entry["st_info"]["type"],
                    section=str(sym["st_shndx"]),
                )
                self._symbols[sym.name] = info
                count += 1
        return count

    def _parse_dwarf(self, elf: "ELFFile") -> int:
        """从 DWARF 调试信息解析全局变量类型"""
        dwarf = elf.get_dwarf_info()
        count = 0

        for CU in dwarf.iter_CUs():
            # 构建类型 DIE 映射（offset → type_name, byte_size）
            type_map: Dict[int, Tuple[str, int, str]] = {}
            self._build_type_map(CU.get_top_DIE(), type_map, CU.cu_offset)

            # 查找 DW_TAG_variable
            for DIE in CU.get_top_DIE().iter_children():
                var_info = self._extract_variable(DIE, type_map, CU.cu_offset)
                if var_info:
                    self._variables[var_info.name] = var_info
                    count += 1

        return count

    def _build_type_map(
        self,
        die: "DIE",
        type_map: Dict[int, Tuple[str, int, str]],
        cu_offset: int,
    ) -> None:
        """递归构建类型 offset → (name, byte_size, encoding) 映射"""
        tag = die.tag

        if tag in ("DW_TAG_base_type", "DW_TAG_typedef",
                   "DW_TAG_structure_type", "DW_TAG_union_type",
                   "DW_TAG_enumeration_type", "DW_TAG_pointer_type",
                   "DW_TAG_array_type"):
            name = ""
            byte_size = 0
            encoding = "unknown"

            if "DW_AT_name" in die.attributes:
                name = die.attributes["DW_AT_name"].value
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="replace")

            if "DW_AT_byte_size" in die.attributes:
                byte_size = die.attributes["DW_AT_byte_size"].value

            if "DW_AT_encoding" in die.attributes:
                enc = die.attributes["DW_AT_encoding"].value
                encoding = _ENCODING_MAP.get(enc, "unknown")

            if tag == "DW_TAG_pointer_type":
                name = name or "void*"
                encoding = "pointer"

            type_map[die.offset] = (name or tag, byte_size, encoding)

        for child in die.iter_children():
            self._build_type_map(child, type_map, cu_offset)

    def _extract_variable(
        self,
        die: "DIE",
        type_map: Dict[int, Tuple[str, int, str]],
        cu_offset: int,
    ) -> Optional[VariableInfo]:
        """从 DW_TAG_variable DIE 中提取变量信息"""
        if die.tag != "DW_TAG_variable":
            return None

        # 必须有名称
        if "DW_AT_name" not in die.attributes:
            return None
        name = die.attributes["DW_AT_name"].value
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")

        # 必须有位置（地址）
        if "DW_AT_location" not in die.attributes:
            return None

        address = self._extract_address(die)
        if address is None or address == 0:
            return None

        # 获取类型信息
        type_name = "unknown"
        byte_size = 0
        encoding = "unknown"
        is_pointer = False

        if "DW_AT_type" in die.attributes:
            type_offset = die.attributes["DW_AT_type"].value
            # type_offset 是相对 CU 的偏移，需要加上 CU 起始偏移
            # pyelftools 中的 value 已经是绝对偏移
            if type_offset in type_map:
                type_name, byte_size, encoding = type_map[type_offset]
                is_pointer = (encoding == "pointer")

        return VariableInfo(
            name=name,
            address=address,
            type_name=type_name,
            byte_size=byte_size,
            is_pointer=is_pointer,
            encoding=encoding,
        )

    def _extract_address(self, die: "DIE") -> Optional[int]:
        """从 DW_AT_location 属性提取变量内存地址"""
        try:
            loc_attr = die.attributes["DW_AT_location"]
            # 直接常量地址（DW_FORM_addr）
            if loc_attr.form in ("DW_FORM_addr", "DW_FORM_data4", "DW_FORM_data8"):
                return loc_attr.value
            # DW_OP_addr 表达式
            if loc_attr.form in ("DW_FORM_block1", "DW_FORM_block",
                                  "DW_FORM_exprloc"):
                expr = loc_attr.value
                if isinstance(expr, list) and len(expr) > 0:
                    # DW_OP_addr = 0x03，后跟 4 或 8 字节地址
                    if expr[0] == 0x03 and len(expr) >= 5:
                        return struct.unpack_from("<I", bytes(expr[1:5]))[0]
                    if expr[0] == 0x03 and len(expr) >= 9:
                        return struct.unpack_from("<Q", bytes(expr[1:9]))[0]
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ #
    #  公共查询 API
    # ------------------------------------------------------------------ #

    def get_symbol(self, name: str) -> Optional[SymbolInfo]:
        """按名称查询符号（函数/变量）"""
        return self._symbols.get(name)

    def get_variable(self, name: str) -> Optional[VariableInfo]:
        """按名称查询变量（含类型和地址）"""
        # 优先 DWARF，其次符号表
        var = self._variables.get(name)
        if var:
            return var
        sym = self._symbols.get(name)
        if sym and sym.symbol_type == "STT_OBJECT":
            return VariableInfo(
                name=name,
                address=sym.address,
                type_name="unknown",
                byte_size=sym.size,
            )
        return None

    def get_symbol_address(self, name: str) -> Optional[int]:
        """快速获取符号地址"""
        sym = self._symbols.get(name)
        if sym:
            return sym.address
        var = self._variables.get(name)
        if var:
            return var.address
        return None

    def list_global_variables(self) -> List[Dict[str, Any]]:
        """列出所有已知全局变量"""
        result = []
        for name, var in self._variables.items():
            result.append({
                "name": name,
                "address": f"0x{var.address:08X}",
                "type": var.type_name,
                "size_bytes": var.byte_size,
                "encoding": var.encoding,
            })
        # 补充仅在符号表中的 OBJECT 符号
        for name, sym in self._symbols.items():
            if name not in self._variables and sym.symbol_type == "STT_OBJECT":
                result.append({
                    "name": name,
                    "address": f"0x{sym.address:08X}",
                    "type": "unknown",
                    "size_bytes": sym.size,
                    "encoding": "unknown",
                })
        return sorted(result, key=lambda x: x["name"])

    def list_functions(self) -> List[Dict[str, Any]]:
        """列出所有函数符号"""
        return [
            {
                "name": sym.name,
                "address": f"0x{sym.address:08X}",
                "size_bytes": sym.size,
            }
            for sym in self._symbols.values()
            if sym.symbol_type == "STT_FUNC" and sym.address != 0
        ]

    def get_summary(self) -> Dict[str, Any]:
        """返回已加载 ELF 文件摘要"""
        if not self._loaded:
            return {"loaded": False}
        return {
            "loaded": True,
            "elf_path": self._elf_path,
            "total_symbols": len(self._symbols),
            "total_variables": len(self._variables),
            "total_functions": sum(
                1 for s in self._symbols.values() if s.symbol_type == "STT_FUNC"
            ),
        }


# DWARF ATE（基本类型编码）映射
_ENCODING_MAP = {
    0x01: "void",
    0x02: "bool",
    0x03: "complex_float",
    0x04: "float",
    0x05: "signed",
    0x06: "signed_char",
    0x07: "unsigned",
    0x08: "unsigned_char",
}
