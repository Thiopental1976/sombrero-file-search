# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
"""Integração com o shell do Windows (F2) — o contrato de xdg.py, no Windows.

Mesmas perguntas que o xdg.py responde no Linux ("o que é este arquivo",
"quem sabe abri-lo", "abra com este"), mais as duas que no Windows têm API
própria e melhor do que imitar o freedesktop:

  reveal(paths)      Explorer aberto na pasta COM os itens selecionados
                     (SHOpenFolderAndSelectItems — o ShowItems do Windows).
  choose_app(path)   a caixa nativa "Abrir com… / Escolher outro aplicativo".

"Abrir com" usa SHAssocEnumHandlers, a mesma lista que o Explorer mostra no
submenu — inclusive apps da Loja (Fotos, Media Player), que não têm linha de
comando no registro e só abrem por IAssocHandler::Invoke.

Só ctypes (nenhuma dependência nova no pacote). Somente leitura, como o
xdg.py: nada aqui escreve, move ou apaga arquivo.
"""
from __future__ import annotations
import ctypes, mimetypes, os, subprocess, uuid
from ctypes import POINTER, byref, c_void_p, c_ulong, c_wchar_p, wintypes

if os.name == "nt":
    _ole32 = ctypes.OleDLL("ole32")
    _ole32_w = ctypes.WinDLL("ole32")              # CoTaskMemFree é void
    _shell32 = ctypes.OleDLL("shell32")
    _shell32_w = ctypes.WinDLL("shell32")          # funções que não devolvem HRESULT
    _HRESULT_FN = ctypes.WINFUNCTYPE
else:                                              # importável no Linux (testes)
    _ole32 = _ole32_w = _shell32 = _shell32_w = None
    _HRESULT_FN = ctypes.CFUNCTYPE


_HRESULT = getattr(ctypes, "HRESULT", ctypes.c_long)   # só existe no Windows


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


def _guid(s: str) -> _GUID:
    return _GUID.from_buffer_copy(uuid.UUID(s).bytes_le)


IID_IShellItemArray = _guid("b63ea76d-1f85-456f-a19c-48159efa858b")
IID_IDataObject = _guid("0000010e-0000-0000-c000-000000000046")
BHID_DataObject = _guid("b8c0bd9f-ed24-455c-83e6-d5390c4fe8c4")

ASSOC_FILTER_RECOMMENDED = 0x1
COINIT_APARTMENTTHREADED = 0x2
OAIF_ALLOW_REGISTRATION = 0x1
OAIF_EXEC = 0x4


# ------------------------------------------------------------ COM em ctypes
def _vt(obj: c_void_p, idx: int, *argtypes, restype=_HRESULT):
    """Método `idx` da vtable de `obj` (já ligado ao this). HRESULT de falha vira
    OSError pelo próprio ctypes."""
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    fn = _HRESULT_FN(restype, c_void_p, *argtypes)(vtbl[idx])
    return lambda *a: fn(obj, *a)


def _release(obj) -> None:
    if obj:
        _vt(obj, 2, restype=c_ulong)()             # IUnknown::Release


def _com_init() -> None:
    """STA na thread atual. A thread da GUI já vem com OLE iniciado pelo Qt
    (S_FALSE) ou noutro modelo (RPC_E_CHANGED_MODE): os dois servem."""
    try:
        _ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    except OSError:
        pass


def _take_str(p: c_wchar_p) -> str:
    s = p.value or ""
    _ole32_w.CoTaskMemFree(p)
    return s


def _pidl(path: str) -> c_void_p:
    f = _shell32_w.ILCreateFromPathW
    f.argtypes, f.restype = [c_wchar_p], c_void_p
    return c_void_p(f(os.path.abspath(path)))


def _ilfree(p) -> None:
    if p:
        f = _shell32_w.ILFree
        f.argtypes, f.restype = [c_void_p], None
        f(p)


# ------------------------------------------------------------- o que é isto
def mime_for(path: str) -> str:
    """Tipo MIME (o `mimetypes` do Windows já lê o Content Type do registro)."""
    if os.path.isdir(path):
        return "inode/directory"
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


# ------------------------------------------------------------- abrir com
class WinApp:
    """Um manipulador de "Abrir com". `key` é o GetName do IAssocHandler (o
    caminho do .exe, ou a identidade do app da Loja) — estável entre duas
    enumerações, é por ele que launch() reencontra o manipulador."""

    terminal = False

    def __init__(self, key: str, name: str, ext: str):
        self.key, self.name, self.ext = key, name, ext
        self.desktop_id = key                      # paridade com DesktopApp

    def __repr__(self):
        return "WinApp(%r)" % self.name


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def _enum_handlers(ext: str):
    """Gera (IAssocHandler*, key, ui_name). Quem recebe o ponteiro o libera."""
    _com_init()
    enum = c_void_p()
    try:
        _shell32.SHAssocEnumHandlers(c_wchar_p(ext), ASSOC_FILTER_RECOMMENDED,
                                     byref(enum))
    except OSError:
        return
    try:
        nxt = _vt(enum, 3, c_ulong, POINTER(c_void_p), POINTER(c_ulong))
        while True:
            h, got = c_void_p(), c_ulong(0)
            try:
                nxt(1, byref(h), byref(got))
            except OSError:
                return
            if not got.value or not h:
                return
            try:
                pn, pu = c_wchar_p(), c_wchar_p()
                _vt(h, 3, POINTER(c_wchar_p))(byref(pn))     # GetName
                key = _take_str(pn)
                _vt(h, 4, POINTER(c_wchar_p))(byref(pu))     # GetUIName
                name = _take_str(pu)
            except OSError:
                _release(h)
                continue
            yield h, key, name
    finally:
        _release(enum)


def apps_for(path: str, limit: int = 12):
    """Os aplicativos que o Explorer recomenda para este tipo, o padrão
    primeiro. Lista vazia é legítima (sem extensão, tipo desconhecido) — a GUI
    cai no "Escolher outro aplicativo…"."""
    ext = _ext(path)
    if not ext or os.name != "nt":
        return []
    out, seen = [], set()
    for h, key, name in _enum_handlers(ext):
        _release(h)
        if key.lower() in seen or not name:
            continue
        seen.add(key.lower())
        out.append(WinApp(key, name, ext))
        if len(out) >= limit:
            break
    return out


def _data_object(paths):
    """IDataObject* com todos os `paths` (um player recebe a seleção inteira
    numa chamada só, como no Explorer). None se algum caminho não resolve."""
    pidls = [_pidl(p) for p in paths]
    try:
        if not all(p.value for p in pidls):
            return None
        arr_t = c_void_p * len(pidls)
        arr = arr_t(*[p.value for p in pidls])
        sia = c_void_p()
        _shell32.SHCreateShellItemArrayFromIDLists(len(pidls), arr, byref(sia))
        try:
            dobj = c_void_p()
            _vt(sia, 3, c_void_p, POINTER(_GUID), POINTER(_GUID),
                POINTER(c_void_p))(None, byref(BHID_DataObject),
                                   byref(IID_IDataObject), byref(dobj))
            return dobj
        finally:
            _release(sia)
    except OSError:
        return None
    finally:
        for p in pidls:
            _ilfree(p.value)


def launch(app, paths) -> bool:
    """Abre `paths` com `app` (um WinApp de apps_for)."""
    paths = [os.path.abspath(p) for p in paths]
    if not paths or os.name != "nt" or not isinstance(app, WinApp):
        return False
    alvo = None
    for h, key, _name in _enum_handlers(app.ext):
        if alvo is None and key.lower() == app.key.lower():
            alvo = h
        else:
            _release(h)
    if alvo is None:
        return False
    try:
        dobj = _data_object(paths)
        if not dobj:
            return False
        try:
            _vt(alvo, 8, c_void_p)(dobj)                     # Invoke
            return True
        except OSError:
            return False
        finally:
            _release(dobj)
    finally:
        _release(alvo)


class _OPENASINFO(ctypes.Structure):
    _fields_ = [("pcszFile", c_wchar_p), ("pcszClass", c_wchar_p),
                ("oaifInFlags", ctypes.c_int)]


def choose_app(path: str, hwnd: int = 0) -> bool:
    """A caixa nativa "Abrir com" do Windows ("Escolher outro aplicativo"),
    que já abre o arquivo com o que o usuário escolher. Modal."""
    if os.name != "nt":
        return False
    info = _OPENASINFO(os.path.abspath(path), None,
                       OAIF_ALLOW_REGISTRATION | OAIF_EXEC)
    try:
        _shell32.SHOpenWithDialog(wintypes.HWND(hwnd or 0), byref(info))
        return True
    except OSError:                                # inclui o usuário cancelar
        return False


def launch_command(cmdline: str, paths) -> bool:
    """"Outro comando…": o usuário digitou um comando; os caminhos vão no fim,
    com as aspas do Windows. Processo destacado: sobrevive ao fechar o SFS."""
    if not cmdline.strip():
        return False
    full = cmdline.strip() + " " + subprocess.list2cmdline(
        [os.path.abspath(p) for p in paths])
    try:
        subprocess.Popen(full, close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                         | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        return True
    except OSError:
        return False


# ------------------------------------------------------- mostrar na pasta
def reveal(paths) -> bool:
    """Explorer na pasta de cada item, COM os itens selecionados. Agrupa por
    pasta (uma janela por pasta, na ordem em que aparecem). True se ao menos
    uma janela abriu; False → a GUI cai em abrir a pasta sem seleção."""
    if os.name != "nt":
        return False
    grupos: dict = {}
    for p in paths:
        p = os.path.abspath(p)
        grupos.setdefault(os.path.dirname(p), []).append(p)
    _com_init()
    find_last = _shell32_w.ILFindLastID
    find_last.argtypes, find_last.restype = [c_void_p], c_void_p
    abriu = False
    for pasta, itens in grupos.items():
        pf = _pidl(pasta)
        filhos = [_pidl(i) for i in itens]
        try:
            vivos = [f.value for f in filhos if f.value]
            if not pf.value or not vivos:
                continue
            rel = (c_void_p * len(vivos))(*[find_last(v) for v in vivos])
            _shell32.SHOpenFolderAndSelectItems(pf, len(vivos), rel, 0)
            abriu = True
        except OSError:
            pass
        finally:
            _ilfree(pf.value)
            for f in filhos:
                _ilfree(f.value)
    return abriu


# ------------------------------------------- paridade com o contrato xdg.py
def default_file_manager():
    """No Windows o gerenciador é o Explorer, via reveal(); nada a escolher."""
    return None


def implements_showitems(app) -> bool:
    return False
