# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
"""Topologia de disco no WINDOWS (F1 do SFS para Windows, desenho do Fable 02/10/2026).

Mesmo contrato das primitivas de `disks.py`; no Windows o próprio `disks.py`
troca as dele por estas (ver o fim daquele arquivo), e as funções genéricas
de lá — menu_labels, list_search_targets, removable_dest, path_needs_serial —
passam a enxergar letras de unidade sem mudar uma linha.

Modelo: a "tabela de montagens" é a lista de VOLUMES com letra:
    _Vol(dev, mp, fstype)   dev = r"\\\\.\\C:" (local) ou r"\\\\srv\\share" (rede)
                            mp  = "C:\\"
com atributos: drive_type, label, discos (PhysicalDriveN…), seek (True/False/
None), bus ("usb"/"sata"/…/""), readonly, unc. Toda função aceita `mounts=`
injetável (lista de _Vol) — é o que deixa 90% deste módulo testável no Linux.

ctypes só DENTRO das funções que falam com o SO; o import é limpo em qualquer
sistema. SEM chamada que acorda a rede durante a enumeração: unidade de rede
não passa por GetVolumeInformation (um share morto pendura ali), e o "está
vivo?" é só da sonda (mount_status), com prazo.
"""
from __future__ import annotations
import errno, ntpath, os, shutil, socket, threading, time

try:                                  # pacote (GUI) e flat (cli.py/testes)
    from . import disks as _L         # o disks.py genérico (DestCaps, IOProfile, …)
except ImportError:
    import disks as _L                # type: ignore

DRIVE_UNKNOWN, DRIVE_NO_ROOT, DRIVE_REMOVABLE, DRIVE_FIXED = 0, 1, 2, 3
DRIVE_REMOTE, DRIVE_CDROM, DRIVE_RAMDISK = 4, 5, 6

# STORAGE_BUS_TYPE (winioctl.h) — só os nomes que mudam política
_BUS = {1: "scsi", 2: "atapi", 3: "ata", 4: "1394", 5: "ssa", 6: "fibre", 7: "usb",
        8: "raid", 9: "iscsi", 10: "sas", 11: "sata", 12: "sd", 13: "mmc",
        14: "virtual", 15: "filebackedvirtual", 16: "spaces", 17: "nvme", 18: "scm", 19: "ufs"}


class _Vol(tuple):
    """Um volume com letra: 3-tupla (dev, mp, fstype) como as linhas do
    /proc/mounts do disks.py (desempacota igual), mais os atributos do Windows."""
    def __new__(cls, dev, mp, fstype, *, drive_type=DRIVE_FIXED, label="",
                discos=(), seek=None, bus="", readonly=False, unc=""):
        self = tuple.__new__(cls, (dev, mp, fstype))
        self.drive_type = drive_type
        self.label = label
        self.discos = tuple(discos)
        self.seek = seek              # IncursSeekPenalty: True = cabeçote; None = não sei
        self.bus = bus
        self.readonly = readonly
        self.unc = unc
        self.opts = ""                # compat com _Mount (o _backing_dev genérico lê)
        return self


# ------------------------------------------------------------------ ctypes
def _k32():
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = wintypes.HANDLE
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                              wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                  ctypes.c_void_p]
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    return k


_INVALID = -1
_SEM_FAILCRITICALERRORS, _SEM_NOOPENFILEERRORBOX = 0x0001, 0x8000


def _sem_dialogo():
    """Leitor de cartão vazio / CD sem mídia: sem isto o Windows abre a caixa
    'Insira um disco na unidade' e a enumeração espera um clique."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(_SEM_FAILCRITICALERRORS | _SEM_NOOPENFILEERRORBOX)
    except Exception:
        pass


def _abre(caminho):
    """Handle com acesso 0 (só consulta — não precisa de administrador)."""
    k = _k32()
    h = k.CreateFileW(caminho, 0, 0x1 | 0x2, None, 3, 0, None)   # SHARE_READ|WRITE, OPEN_EXISTING
    if h is None or h == _INVALID or h == 0xFFFFFFFFFFFFFFFF:
        return None, k
    return h, k


def _ioctl(h, k, code, inbuf=None, outsize=1024):
    import ctypes
    from ctypes import wintypes
    out = ctypes.create_string_buffer(outsize)
    n = wintypes.DWORD(0)
    ok = k.DeviceIoControl(h, code, inbuf, len(inbuf) if inbuf is not None else 0,
                           out, outsize, ctypes.byref(n), None)
    return out.raw[:n.value] if ok else None


_IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS = 0x00560000
_IOCTL_STORAGE_QUERY_PROPERTY = 0x002D1400


def _consulta_discos_do_volume(letra):
    """PhysicalDriveN que sustentam o volume (vários = volume estendido/Spaces).
    [] se o Windows não disser (sem admin em alguns sistemas — degrada pro serial)."""
    import struct
    h, k = _abre("\\\\.\\%s:" % letra)
    if h is None:
        return []
    try:
        raw = _ioctl(h, k, _IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS, outsize=8 + 24 * 32)
    finally:
        k.CloseHandle(h)
    if not raw or len(raw) < 8:
        return []
    n = struct.unpack_from("<I", raw, 0)[0]
    out = set()
    for i in range(n):
        off = 8 + 24 * i
        if off + 4 <= len(raw):
            out.add("PhysicalDrive%d" % struct.unpack_from("<I", raw, off)[0])
    return sorted(out)


def _consulta_disco(disco):
    """(seek, bus) do disco físico: IncursSeekPenalty (True/False/None) e o
    barramento ('usb', 'nvme', …, '' se não souber)."""
    import struct
    h, k = _abre("\\\\.\\" + disco)
    if h is None:
        return None, ""
    try:
        seek = None
        q = struct.pack("<II4x", 7, 0)          # StorageDeviceSeekPenaltyProperty, Standard
        raw = _ioctl(h, k, _IOCTL_STORAGE_QUERY_PROPERTY, q, 64)
        if raw and len(raw) >= 9:
            seek = bool(raw[8])
        bus = ""
        q = struct.pack("<II4x", 0, 0)          # StorageDeviceProperty
        raw = _ioctl(h, k, _IOCTL_STORAGE_QUERY_PROPERTY, q, 1024)
        if raw and len(raw) >= 32:
            bus = _BUS.get(struct.unpack_from("<I", raw, 28)[0], "")
        return seek, bus
    finally:
        k.CloseHandle(h)


def _unc_da_letra(letra):
    """\\\\servidor\\share por trás de uma letra mapeada ('' se não for)."""
    try:
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(1024)
        n = wintypes.DWORD(1024)
        r = ctypes.WinDLL("mpr").WNetGetConnectionW("%s:" % letra, buf, ctypes.byref(n))
        return buf.value if r == 0 else ""
    except Exception:
        return ""


def _enumera():
    """Volumes com letra, como _Vol. Unidade de rede NÃO é consultada (fstype
    'smb' fixo): GetVolumeInformation num share morto pendura sem prazo."""
    import ctypes
    from ctypes import wintypes
    _sem_dialogo()
    k32 = ctypes.windll.kernel32
    mask = k32.GetLogicalDrives()
    vols, cache_disco = [], {}
    for i in range(26):
        if not mask & (1 << i):
            continue
        letra = chr(ord("A") + i)
        raiz = letra + ":\\"
        tipo = k32.GetDriveTypeW(raiz)
        if tipo in (DRIVE_UNKNOWN, DRIVE_NO_ROOT):
            continue
        if tipo == DRIVE_REMOTE:
            unc = _unc_da_letra(letra)
            vols.append(_Vol(unc or "\\\\.\\%s:" % letra, raiz, "smb", drive_type=tipo,
                             label=unc, unc=unc))
            continue
        nome = ctypes.create_unicode_buffer(261)
        fs = ctypes.create_unicode_buffer(261)
        serial, maxc, flags = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
        if not k32.GetVolumeInformationW(raiz, nome, 261, ctypes.byref(serial), ctypes.byref(maxc),
                                         ctypes.byref(flags), fs, 261):
            continue                      # sem mídia (leitor de cartão vazio, CD vazio)
        discos = _consulta_discos_do_volume(letra) if tipo != DRIVE_CDROM else []
        seeks, buses = [], []
        for d in discos:
            if d not in cache_disco:
                cache_disco[d] = _consulta_disco(d)
            s, b = cache_disco[d]
            seeks.append(s); buses.append(b)
        # vários discos: a resposta do PIOR (regra do disks.py: um cabeçote
        # em qualquer lugar já é rotacional; SSD só se todos disserem)
        seek = True if True in seeks else (False if seeks and all(s is False for s in seeks) else None)
        if tipo == DRIVE_CDROM:
            seek = True
        bus = "usb" if "usb" in buses else (buses[0] if buses else "")
        vols.append(_Vol("\\\\.\\%s:" % letra, raiz, fs.value or "", drive_type=tipo,
                         label=nome.value, discos=discos, seek=seek, bus=bus,
                         readonly=bool(flags.value & 0x00080000)))   # FILE_READ_ONLY_VOLUME
    return vols


# Cache curto: o motor pergunta _mount_entry por raiz, e cada enumeração faz
# alguns IOCTLs. 2 s cobre uma busca; pendrive espetado aparece na próxima.
_cache_lock = threading.Lock()
_cache = (0.0, None)
_TTL = 2.0


def _read_mounts(src=None):
    """Volumes com letra (lista de _Vol). `src` = lista pronta (teste)."""
    global _cache
    if src is not None:
        return list(src)
    if os.name != "nt":
        return []                     # importado no Linux (testes): não há letras
    with _cache_lock:
        t, v = _cache
        if v is not None and time.monotonic() - t < _TTL:
            return list(v)
    v = _enumera()
    with _cache_lock:
        _cache = (time.monotonic(), v)
    return list(v)


# ------------------------------------------------------------------ caminhos
# Funções PURAS usam ntpath (regras de caminho do Windows) e não os.path: assim
# rodam iguais no Linux, onde os testes com tabelas sintéticas moram.
def _nc(p):
    """Forma de comparação: caixa e barra normalizadas (NTFS não distingue caixa)."""
    return ntpath.normcase(p)


def _unc_raiz(ap):
    """'\\\\srv\\share' de um caminho UNC, ou ''."""
    p = ap.replace("/", "\\")
    if not p.startswith("\\\\") or p.startswith("\\\\?\\") or p.startswith("\\\\.\\"):
        return ""
    partes = p[2:].split("\\")
    if len(partes) < 2 or not partes[0] or not partes[1]:
        return ""
    return "\\\\" + partes[0] + "\\" + partes[1]


def _mount_entry(ap, mounts=None):
    """(dev, mountpoint, fstype) do volume que contém `ap` — letra de unidade
    ou share UNC. ("", "", "") se não achar."""
    try:
        entradas = mounts if mounts is not None else _read_mounts()
    except OSError:
        entradas = []
    unc = _unc_raiz(ap)
    if unc:
        for v in entradas:            # share já mapeado numa letra: mesmo volume
            if v.unc and _nc(v.unc) == _nc(unc):
                return _Vol(v[0], unc + "\\", v[2], drive_type=DRIVE_REMOTE,
                            label=v.label, unc=v.unc)
        return _Vol(unc, unc + "\\", "smb", drive_type=DRIVE_REMOTE, label=unc, unc=unc)
    alvo = _nc(ap)
    best = ("", "", "")
    for v in entradas:
        mp = _nc(v[1])
        base = mp.rstrip("\\")
        if alvo == base or alvo == mp or alvo.startswith(base + "\\"):
            if len(v[1]) >= len(best[1]):
                best = v
    return best


def _backing_dev(entry, mounts=None):
    return entry[0]


def _dev_for_path(ap, mounts=None):
    return _mount_entry(ap, mounts)[0]


def _vol_do_dev(dev, mounts=None):
    try:
        entradas = mounts if mounts is not None else _read_mounts()
    except OSError:
        return None
    for v in entradas:
        if v[0] == dev:
            return v
    return None


def _sys_disks(dev, mounts=None):
    """Discos físicos (PhysicalDriveN) do volume `dev` — a chave de agrupamento
    do engine (_chave_de_disco). [] em rede ou se o Windows não disser."""
    v = _vol_do_dev(dev, mounts)
    return list(getattr(v, "discos", ()) or ()) if v is not None else []


def _sys_disk(dev):
    d = _sys_disks(dev)
    return d[0] if d else ""


def _le_rotational(disco):
    """'1'/'0'/None de um disco físico. Hook injetável (testes)."""
    seek, _bus = _consulta_disco(disco)
    return None if seek is None else ("1" if seek else "0")


def _rotational(dev, mounts=None):
    """'1'/'0'/None do volume — PIOR entre os discos, como no disks.py."""
    v = _vol_do_dev(dev, mounts)
    if v is None:
        return None
    if v.drive_type == DRIVE_CDROM:
        return "1"
    # `seek` já é o PIOR entre os discos do volume (medido na enumeração)
    return None if v.seek is None else ("1" if v.seek else "0")


def _unidade_do_sistema():
    return (os.environ.get("SystemDrive") or "C:").rstrip("\\") + "\\"


# "Disco do acervo" (o _under_mount do Linux, que é /mnt|/media): no Windows é
# qualquer volume que NÃO é o do sistema. Governa o `serialize` — HD externo e
# segundo disco serializam; o C:\ corre solto, como a / no Linux.
_MNT_PREFIXES = ()


def _under_mount(ap, mounts=None):
    mp = _mount_entry(ap, mounts)[1]
    return bool(mp) and _nc(mp) != _nc(_unidade_do_sistema())


def search_profile(path, mounts=None):
    """Perfil de I/O (mesmas classes do disks.py): network para letra de rede e
    UNC; rotational para HD/CD; ssd quando o Windows diz 'sem seek penalty'."""
    IOProfile = _L.IOProfile
    ap = ntpath.abspath(path)
    ent = _mount_entry(ap, mounts)
    dev, mp, fstype = ent
    if getattr(ent, "drive_type", None) == DRIVE_REMOTE or _unc_raiz(ap):
        return IOProfile("network", mp, fstype, serialize=False, is_network=True,
                         max_workers=_L.NET_WORKERS_PER_MOUNT, enumerate_default=True)
    if not dev:
        return IOProfile("unknown", mp, fstype, serialize=False, is_network=False,
                         max_workers=None, enumerate_default=True)
    acervo = _under_mount(ap, mounts)
    rot = _rotational(dev, mounts)
    if rot == "1":
        return IOProfile("rotational", mp, fstype, serialize=acervo, is_network=False,
                         max_workers=None, enumerate_default=True)
    if rot is None and acervo:
        return IOProfile("rotational", mp, fstype, serialize=True, is_network=False,
                         max_workers=None, enumerate_default=True)
    return IOProfile("ssd" if rot == "0" else "unknown", mp, fstype, serialize=False,
                     is_network=False, max_workers=None, enumerate_default=True)


def is_mountpoint(ap, mounts=None):
    """`ap` é a RAIZ de um volume (C:\\, \\\\srv\\share\\)."""
    ent = _mount_entry(ap, mounts)
    return bool(ent[1]) and _nc(ent[1]).rstrip("\\") == _nc(ap).rstrip("\\")


def is_mount_slot(ap):
    """Não há 'vaga de montagem' (/mnt/X) no Windows."""
    return False


def fstab_targets(src=None):
    """Letras mapeadas PERSISTENTES (HKCU\\Network\\<letra>) — o 'deveria estar
    montado' do Windows. Devolve as raízes ('Z:\\')."""
    if src is not None:
        return set(src)
    out = set()
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Network") as k:
            i = 0
            while True:
                try:
                    out.add(winreg.EnumKey(k, i).upper() + ":\\")
                except OSError:
                    break
                i += 1
    except (OSError, ImportError):
        pass
    return out


def volume_label(mp, mounts=None):
    """'Dados (D:)' — o nome que o Explorer mostra. Rede: o UNC."""
    ent = _mount_entry(mp, mounts)
    if not ent[1]:
        return None
    letra = ent[1].rstrip("\\")
    lbl = getattr(ent, "label", "")
    if getattr(ent, "drive_type", None) == DRIVE_REMOTE:
        return "%s (%s)" % (lbl, letra) if lbl and len(letra) == 2 else (lbl or None)
    return "%s (%s)" % (lbl, letra) if lbl else None


def mounts_under(root, mounts=None):
    """Volumes ESTRITAMENTE dentro de `root`. Sem pastas montadas (v2), só a
    raiz da árvore do Windows não contém outros volumes."""
    return []


def classifica_volumes(mounts=None):
    """{raiz: ("local"|"rede", fstype, dev)} — o classifica_montagens do engine.
    CD/DVD com mídia entra como local (é disco do usuário); RAM disk também."""
    try:
        entradas = mounts if mounts is not None else _read_mounts()
    except OSError:
        return {}
    out = {}
    for v in entradas:
        cl = "rede" if v.drive_type == DRIVE_REMOTE else "local"
        out[v[1]] = (cl, v[2], v[0])
    return out


# ------------------------------------------------------------- sonda de vida
# winerror que querem dizer "o servidor/volume não está lá" (o _DEAD_* do Linux)
_DEAD_WINERRORS = frozenset({
    53,    # ERROR_BAD_NETPATH
    59,    # ERROR_UNEXP_NET_ERR
    64,    # ERROR_NETNAME_DELETED
    67,    # ERROR_BAD_NET_NAME
    121,   # ERROR_SEM_TIMEOUT
    1222,  # ERROR_NO_NETWORK
    1231,  # ERROR_NETWORK_UNREACHABLE
    1232,  # ERROR_HOST_UNREACHABLE
    2250,  # ERROR_NOT_CONNECTED
    21,    # ERROR_NOT_READY (mídia removida)
})


def _porta_smb(servidor, timeout):
    """O servidor atende na 445? Barato e com prazo — antes de tocar o FS."""
    try:
        with socket.create_connection((servidor, 445), timeout=timeout):
            return True
    except OSError:
        return False


def _cancela_io(tid):
    """CancelSynchronousIo na thread presa: o que o Windows oferece para I/O
    síncrono sem resposta (a thread sai com erro e não fica pendurada)."""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenThread(0x0001, False, tid)          # THREAD_TERMINATE
        if h:
            k.CancelSynchronousIo(h)
            k.CloseHandle(h)
    except Exception:
        pass


def mount_status(mp, timeout=3.0, _stat=os.stat, _statvfs=shutil.disk_usage, _porta=None):
    """'alive' | 'no_response' | 'broken_mount' (mesmo contrato do Linux).

    Sem fork no Windows: (1) caminho de rede → a 445 do servidor responde no
    prazo? (2) stat + disk_usage numa thread; passou o prazo, CancelSynchronousIo
    nela e 'no_response'. `_stat`/`_statvfs`/`_porta` injetáveis (teste)."""
    unc = _unc_raiz(mp)
    if not unc:
        ent = _mount_entry(mp)
        unc = getattr(ent, "unc", "") if getattr(ent, "drive_type", None) == DRIVE_REMOTE else ""
    if unc:
        servidor = unc[2:].split("\\", 1)[0]
        if not (_porta or _porta_smb)(servidor, timeout):
            return "no_response"
    res = {}

    def _morto(e, conjunto_posix):
        # winerror real do Windows OU errno POSIX/WSA sem winerror (socket,
        # injeção de teste) — a mesma tabela do Linux, para o contrato bater
        w = getattr(e, "winerror", None)
        return w in _DEAD_WINERRORS or (w is None and e.errno in conjunto_posix)

    def sonda():
        res["tid"] = threading.get_ident()
        try:
            _stat(mp)
            try:
                _statvfs(mp)
            except OSError as e:
                if _morto(e, _L._DEAD_STATVFS_ERRNOS):
                    res["r"] = "broken_mount"; return
            res["r"] = "alive"
        except OSError as e:
            res["r"] = "broken_mount" if _morto(e, _L._DEAD_MOUNT_ERRNOS) else "alive"
        except BaseException:
            res["r"] = "alive"

    t = threading.Thread(target=sonda, daemon=True, name="sfs-sonda")
    t.start()
    t.join(timeout)
    if t.is_alive():
        tid = getattr(t, "native_id", None)
        if tid:
            _cancela_io(tid)
        return "no_response"
    return res.get("r", "no_response")


def mount_alive(mp, timeout=3.0, _stat=os.stat, _statvfs=shutil.disk_usage, _porta=None):
    return mount_status(mp, timeout=timeout, _stat=_stat, _statvfs=_statvfs, _porta=_porta) == "alive"


# --------------------------------------------------------- destino de cópia
def mount_ok(path):
    """O volume de destino existe agora? (letra de pendrive arrancado não existe)."""
    ent = _mount_entry(ntpath.abspath(path))
    return bool(ent[1]) and os.path.exists(ent[1])


_WIN_FS = {"ntfs": _L._NTFS, "fat32": _L._FAT, "fat": _L._FAT, "exfat": _L._EXFAT,
           "refs": _L._NTFS, "cdfs": None, "udf": None}


def _caps_win(fstype, drive_type):
    """Capacidades: o Win32 proíbe "*:<>?\\| , nomes reservados e ponto/espaço
    final em QUALQUER sistema de arquivos — não é o fs, é a API."""
    fk = (fstype or "").lower()
    if drive_type == DRIVE_REMOTE:
        base = dict(_L._NET_SMB)
    elif fk in ("cdfs", "udf") or drive_type == DRIVE_CDROM:
        return dict(max_file=None, symlinks=False, perms=False, times=False, charset=_L._DOS_BAD,
                    reserved=True, label=fstype or "CD", readonly=True)
    else:
        base = dict(_WIN_FS.get(fk) or _L._NTFS)
        if fk not in _WIN_FS:
            base["label"] = fstype or "?"
    base.update(charset=_L._DOS_BAD, reserved=True, symlinks=False, perms=False)
    base["utf8_only"] = False         # nome no Windows é UTF-16: não há byte quebrado
    return base


def dest_caps(path):
    ap = os.path.abspath(path)
    probe = ap
    while not os.path.exists(probe):
        pai = os.path.dirname(probe)
        if pai == probe:
            break
        probe = pai
    ent = _mount_entry(probe)
    dev, mp, fstype = ent
    caps = _caps_win(fstype, getattr(ent, "drive_type", DRIVE_FIXED))
    readonly = bool(caps.pop("readonly", False)) or bool(getattr(ent, "readonly", False))
    # namemax é em BYTES (fsencode = UTF-8 no Windows): 255 caracteres com
    # acento passariam de 255 bytes e o nome seria recusado à toa. O limite
    # real é maxchars (255 unidades UTF-16).
    return _L.DestCaps(fstype=fstype, mountpoint=mp, namemax=255 * 4, readonly=readonly,
                       via_gvfs=False, removable=is_removable(dev), link_mbits=None, **caps)


def is_removable(dev, mounts=None):
    """Pendrive/cartão (DRIVE_REMOVABLE) ou qualquer coisa no barramento USB
    (HD externo se diz FIXED — a mesma lição do Linux)."""
    v = _vol_do_dev(dev, mounts)
    return bool(v is not None and (v.drive_type == DRIVE_REMOVABLE or v.bus == "usb"))


def link_speed(dev):
    return None                       # v2 (Windows não expõe a velocidade sem WMI)


def luks_backing(dev, sysfs=None):
    return None


def eject_command(mountpoint, dev="", *, which=None, backing=None):
    return None                       # v2: CM_Request_Device_EjectW; sem passos, sem botão


def free_bytes(path):
    probe = os.path.abspath(path)
    while not os.path.exists(probe):
        pai = os.path.dirname(probe)
        if pai == probe:
            return 0
        probe = pai
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return 0


# O que o disks.py troca no Windows (o resto dele é genérico e fica).
EXPORTS = (
    "_MNT_PREFIXES", "_under_mount", "fstab_targets", "is_mountpoint", "is_mount_slot",
    "_read_mounts", "_mount_entry", "_backing_dev", "_dev_for_path", "volume_label",
    "_rotational", "_le_rotational", "search_profile", "mount_status", "mount_alive",
    "mounts_under", "mount_ok", "dest_caps", "is_removable", "_sys_disks", "_sys_disk",
    "link_speed", "luks_backing", "eject_command", "free_bytes", "classifica_volumes",
)

if os.name == "nt":                   # import circular: ver disks._aplica_windows
    _L._aplica_windows(__import__("sys").modules[__name__])
