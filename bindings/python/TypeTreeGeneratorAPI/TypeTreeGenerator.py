import ctypes
import json
import os
import platform
from dataclasses import dataclass
from typing import List, Literal, Optional, Tuple

TypeTreeBackend = Literal["AssetStudio", "AssetsTools", "AssetRipper"]


class TypeTreeNodeNative(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("m_Type", ctypes.c_char_p),
        ("m_Name", ctypes.c_char_p),
        ("m_Level", ctypes.c_int),
        ("m_MetaFlag", ctypes.c_int),
    ]


@dataclass
class TypeTreeNode:
    m_Type: str
    m_Name: str
    m_Level: int
    m_MetaFlag: int


DLL: ctypes.CDLL = None  # type: ignore


def init_dll(asm_path: Optional[str] = None):
    global DLL
    if DLL is not None:  # type: ignore
        return

    system = platform.system()
    LOCAL = os.path.dirname(os.path.realpath(__file__))
    if system == "Windows":
        fp = asm_path or os.path.join(LOCAL, "TypeTreeGeneratorAPI.dll")
        dll = ctypes.WinDLL(fp)
    elif system == "Linux":
        fp = asm_path or os.path.join(LOCAL, "libTypeTreeGeneratorAPI.so")
        dll = ctypes.CDLL(fp)
    elif system == "Darwin":
        fp = asm_path or os.path.join(LOCAL, "libTypeTreeGeneratorAPI.dylib")
        dll = ctypes.CDLL(fp)
    else:
        raise NotImplementedError(f"TypeTreeGenerator doesn't support {system}!")

    # set function types
    dll.TypeTreeGenerator_init.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    dll.TypeTreeGenerator_init.restype = ctypes.c_void_p
    dll.TypeTreeGenerator_loadDLL.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    dll.TypeTreeGenerator_loadIL2CPP.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    dll.TypeTreeGenerator_generateTreeNodesJson.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_char_p),
    ]
    dll.TypeTreeGenerator_generateTreeNodesRaw.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.POINTER(TypeTreeNodeNative)),
        ctypes.POINTER(ctypes.c_int),
    ]
    dll.TypeTreeGenerator_freeTreeNodesRaw.argtypes = [
        ctypes.POINTER(TypeTreeNodeNative),
        ctypes.c_int,
    ]
    dll.TypeTreeGenerator_getMonoBehaviorDefinitions.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_char_p)),
        ctypes.POINTER(ctypes.c_int),
    ]
    dll.TypeTreeGenerator_freeMonoBehaviorDefinitions.argtypes = [
        ctypes.POINTER(ctypes.c_char_p),
        ctypes.c_int,
    ]
    dll.TypeTreeGenerator_getLoadedDLLNames.argtypes = [ctypes.c_void_p]
    dll.TypeTreeGenerator_getLoadedDLLNames.restype = ctypes.c_void_p

    dll.TypeTreeGenerator_del.argtypes = [ctypes.c_void_p]
    dll.FreeCoTaskMem.argtypes = [ctypes.c_void_p]
    DLL = dll  # type: ignore


class TypeTreeGenerator:
    ptr = ctypes.c_void_p

    def __init__(
        self,
        unity_version: str,
        generator: TypeTreeBackend = "AssetStudio",
        asm_path: Optional[str] = None,
    ):
        init_dll(asm_path)
        self.ptr = DLL.TypeTreeGenerator_init(unity_version.encode("ascii"), generator.encode("ascii"))
        if not self.ptr:
            raise RuntimeError("Failed to initialize TypeTreeGenerator")

    def __del__(self):
        DLL.TypeTreeGenerator_del(self.ptr)

    def load_dll(self, dll: bytes):
        assert not DLL.TypeTreeGenerator_loadDLL(self.ptr, dll, len(dll)), "failed to load dll"

    def load_il2cpp(self, il2cpp: bytes, metadata: bytes):
        assert not DLL.TypeTreeGenerator_loadIL2CPP(self.ptr, il2cpp, len(il2cpp), metadata, len(metadata)), (
            "failed to load il2cpp"
        )

    def get_nodes_as_json(self, assembly: str, fullname: str) -> str:
        jsonPtr = ctypes.c_char_p()
        assert not DLL.TypeTreeGenerator_generateTreeNodesJson(
            self.ptr,
            assembly.encode("ascii"),
            fullname.encode("ascii"),
            ctypes.byref(jsonPtr),
        ), "failed to dump nodes as json"
        assert jsonPtr.value is not None, "didn't write json to ptr"
        json_str = jsonPtr.value.decode("utf8")
        DLL.FreeCoTaskMem(jsonPtr)
        return json_str

    def get_nodes(self, assembly: str, fullname: str) -> List[TypeTreeNode]:
        nodes_ptr = ctypes.POINTER(TypeTreeNodeNative)()
        nodes_count = ctypes.c_int()
        assert not DLL.TypeTreeGenerator_generateTreeNodesRaw(
            self.ptr,
            assembly.encode("ascii"),
            fullname.encode("ascii"),
            ctypes.byref(nodes_ptr),
            ctypes.byref(nodes_count),
        ), "failed to dump nodes raw"
        nodes_array = ctypes.cast(nodes_ptr, ctypes.POINTER(TypeTreeNodeNative * nodes_count.value)).contents
        nodes = [
            TypeTreeNode(
                m_Type=node.m_Type.decode("ascii"),
                m_Name=node.m_Name.decode("ascii"),
                m_Level=node.m_Level,
                m_MetaFlag=node.m_MetaFlag,
            )
            for node in nodes_array
        ]
        DLL.TypeTreeGenerator_freeTreeNodesRaw(nodes_ptr, nodes_count)
        return nodes

    def get_monobehavior_definitions(self) -> List[Tuple[str, str]]:
        names_ptr = ctypes.POINTER(ctypes.c_char_p)()
        names_cnt = ctypes.c_int()
        assert not DLL.TypeTreeGenerator_getMonoBehaviorDefinitions(
            self.ptr,
            ctypes.byref(names_ptr),
            ctypes.byref(names_cnt),
        ), "failed to get module exports"
        ptr_array = ctypes.cast(names_ptr, ctypes.POINTER(ctypes.c_char_p * names_cnt.value))
        names = [name.decode("utf-8") for name in ptr_array.contents]
        DLL.TypeTreeGenerator_freeMonoBehaviorDefinitions(names_ptr, names_cnt)
        return [(module, fullname) for module, fullname in zip(names[::2], names[1::2])]

    def get_loaded_dll_names(self) -> List[str]:
        names_ptr = DLL.TypeTreeGenerator_getLoadedDLLNames(self.ptr)
        if not names_ptr:
            return []
        names_ptr_c = ctypes.cast(names_ptr, ctypes.c_char_p)
        if not names_ptr_c.value:
            DLL.FreeCoTaskMem(names_ptr)
            return []
        names = json.loads(names_ptr_c.value)
        DLL.FreeCoTaskMem(names_ptr)
        return names


__all__ = ["TypeTreeGenerator", "TypeTreeNode", "TypeTreeNodeNative", "TypeTreeBackend"]
