#!/usr/bin/env python3
# Sombrero File Search — Copyright (C) 2026 Rodrigo Toledo
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob
# os termos da GNU General Public License, versão 3 ou posterior (ver LICENSE).
# Distribuído na esperança de ser útil, mas SEM QUALQUER GARANTIA.
"""Sombrero File Search — disk topology (F7).

Extracted from boolean.py so that both the search (which SERIALIZES scans on
rotational disks) and the copy engine (which must know what the DESTINATION
filesystem can actually hold) share one source of truth. No Qt here, and no
dependency beyond the stdlib — this module is imported by the headless tests.

Three jobs:
  1. Which device/filesystem backs a path (`/proc/mounts`, longest prefix).
  2. Should scans on it be serialized (SMR/USB seek thrash) — `path_needs_serial`.
  3. **What the destination filesystem supports** — `dest_caps`. The copy engine
     targets pendrives, external disks and media players, which are very often
     exFAT/FAT32/NTFS/MTP: no symlinks, no POSIX permissions, a 4 GiB file limit
     on FAT32 and a restricted filename charset. Copying an 8 GiB video to FAT32
     fails at byte 4294967296, not at the start, so we check BEFORE writing.
"""
from __future__ import annotations
import os, re

try:                        # pacote (GUI) e flat (cli.py/testes)
    from . import engine
except ImportError:
    import engine


# ------------------------------------------------------------------ topologia
# Pontos de montagem onde discos SMR/USB do acervo costumam viver: seek concorrente
# os castiga, então buscas AQUI são SERIALIZADAS (1 processo por vez).
_MNT_PREFIXES = ("/mnt", "/media", "/run/media")


def _under_mount(ap: str) -> bool:
    return any(ap == pre or ap.startswith(pre + os.sep) for pre in _MNT_PREFIXES)


def _read_mounts(src="/proc/mounts"):
    """/proc/mounts como lista de (dev, mountpoint, fstype). `src` pode ser um
    caminho OU um iterável de linhas — é o que torna testável o casamento de
    caminho com montagens que NÃO têm nó em /dev/ (MTP, gvfs, sshfs)."""
    linhas = open(src, encoding="utf-8").readlines() if isinstance(src, str) else list(src)
    out = []
    for line in linhas:
        parts = line.split()
        if len(parts) < 3:
            continue
        # espaço no ponto de montagem vem escapado como \040 no /proc/mounts
        out.append((parts[0], parts[1].replace("\\040", " "), parts[2]))
    return out


def _mount_entry(ap: str, mounts=None):
    """(dev, mountpoint, fstype) do mount de prefixo MAIS LONGO que cobre `ap`.
    ("", "", "") se não achar.

    NÃO exige source em /dev/: um telefone via MTP/gvfs aparece como
    `gvfsd-fuse /run/user/1000/gvfs fuse.gvfsd-fuse`, sem nó de bloco. Filtrar por
    /dev/ fazia o casamento subir até `/` e classificar o celular como o disco de
    sistema ext4 — o pior erro possível para uma cópia (sem aviso, sem ritmo). O
    dev fica "" nesses casos, e is_removable/rotational lidam bem com isso."""
    best = ("", "", "")
    try:
        entradas = mounts if mounts is not None else _read_mounts()
    except OSError:
        return ("", "", "")
    for dev, mp, fstype in entradas:
        if ap == mp or mp == "/" or ap.startswith(mp.rstrip("/") + "/"):
            if len(mp) >= len(best[1]):               # prefixo mais específico vence
                best = (dev, mp, fstype)
    return best


def _dev_for_path(ap: str) -> str:
    """Nó de dispositivo (/dev/...) que sustenta `ap`. "" se não achar (então
    tratamos como desconhecido)."""
    return _mount_entry(ap)[0]


def _rotational(dev: str):
    """'1'/'0' de /sys/block/<disco>/queue/rotational p/ o disco que sustenta o nó
    `dev` (sobe da partição p/ o disco inteiro). None se desconhecido."""
    if not dev:
        return None
    name = os.path.basename(dev)                       # sdb1, nvme0n1p1...
    try:
        real = os.path.realpath("/sys/class/block/" + name)
        parent = os.path.basename(os.path.dirname(real))
        base = name if parent == "block" else parent   # disco inteiro se for partição
        with open("/sys/block/%s/queue/rotational" % base, encoding="ascii") as f:
            return f.read().strip()
    except OSError:
        return None


def path_needs_serial(ap: str) -> bool:
    """Serializa se o caminho está sob /mnt (etc.) E o disco que o sustenta é
    rotacional ou desconhecido. SSD/NVMe confirmado (rotational=0) libera o
    paralelismo mesmo sob /mnt — refinamento do parecer v3 (Fable 5)."""
    if not _under_mount(ap):
        return False
    return _rotational(_dev_for_path(ap)) != "0"       # None (desconhecido) => serializa


def mount_ok(path: str) -> bool:
    """O destino de uma cópia está numa montagem REAL? Sob /mnt|/media|/run/media,
    um ponto de montagem desmontado continua existindo como diretório vazio no
    disco de sistema: copiar 300 GB para lá encheria o NVMe silenciosamente.
    Fora desses prefixos (home, /tmp) não há o que checar."""
    ap = os.path.abspath(path)
    if not _under_mount(ap):
        return True
    mp = _mount_entry(ap)[1]
    if not mp or not _under_mount(mp):
        return False                     # coberto só por / (ou nada): não montado
    return mp in engine.user_mounts()


# ------------------------------------------------------------------ capacidades do destino
# O que cada família de sistema de arquivos aceita. Só listamos os que RESTRINGEM;
# o padrão (ext4/xfs/btrfs/zfs/f2fs/nfs...) aceita tudo que o Linux aceita.
#
#   max_file  — maior arquivo, em bytes (None = sem limite prático)
#   symlinks  — suporta link simbólico
#   perms     — suporta modo/uid/gid POSIX
#   times     — suporta ajustar mtime (utime)
#   charset   — caracteres PROIBIDOS no nome
#   reserved  — nomes reservados do DOS (CON, PRN, LPT1…) são inválidos
#   utf8_only — o nome precisa ser UTF-8 VÁLIDO. O vfat/exfat/ntfs guardam nomes
#               em UTF-16 e o kernel converte na hora de escrever; um nome com
#               byte inválido (foto de câmera, arquivo vindo de outro sistema)
#               volta EINVAL. Não é teoria: o pendrive de verdade recusou
#               'camera_\xff\xfe.jpg' que a imagem FAT32 em loop tinha aceitado
#               — a diferença é o iocharset com que o udisks monta o removível.
#   maxchars  — limite de nome em CARACTERES (não bytes). FAT/exFAT/NTFS contam
#               255 unidades UTF-16, mas o statvfs do vfat responde f_namemax
#               =1530 (255x6, o pior caso do UTF-8): confiar nele fazia a
#               pré-checagem aprovar um nome de 300 caracteres que o kernel
#               recusa com ENAMETOOLONG na hora de escrever. Medido em FAT32
#               real: 254 caracteres passam, 259 não.
_DOS_BAD = '"*:<>?\\|'
_FAT = dict(max_file=(1 << 32) - 1, symlinks=False, perms=False, times=True,
            charset=_DOS_BAD, reserved=True, label="FAT32", maxchars=255, utf8_only=True)
_EXFAT = dict(max_file=None, symlinks=False, perms=False, times=True,
              charset=_DOS_BAD, reserved=False, label="exFAT", maxchars=255, utf8_only=True)
_NTFS = dict(max_file=None, symlinks=False, perms=False, times=True,
             charset=_DOS_BAD, reserved=True, label="NTFS", maxchars=255, utf8_only=True)
_MTP = dict(max_file=None, symlinks=False, perms=False, times=False,
            charset=_DOS_BAD, reserved=False, label="MTP", maxchars=255, utf8_only=True)

_FS_CAPS = {
    "vfat": _FAT, "fat": _FAT, "msdos": _FAT, "umsdos": _FAT,
    "exfat": _EXFAT, "fuse.exfat": _EXFAT, "exfat-fuse": _EXFAT,
    "ntfs": _NTFS, "ntfs3": _NTFS, "fuseblk": _NTFS, "fuse.ntfs-3g": _NTFS,
    # celular/câmera: não é sistema de arquivos de verdade (sem mtime confiável)
    "fuse.jmtpfs": _MTP, "fuse.simple-mtpfs": _MTP, "fuse.go-mtpfs": _MTP,
    "mtpfs": _MTP, "fuse.gvfsd-fuse": _MTP, "gvfsd-fuse": _MTP,
    # ISO/UDF montados são somente-leitura; tratados como erro na pré-checagem
    "iso9660": dict(max_file=None, symlinks=True, perms=False, times=False,
                    charset="", reserved=False, label="ISO9660", readonly=True),
}

_DEFAULT_CAPS = dict(max_file=None, symlinks=True, perms=True, times=True,
                     charset="", reserved=False, label="POSIX")

def _has_broken_bytes(name: str) -> bool:
    """O nome carrega bytes que não formam UTF-8 válido? São os substitutos do
    surrogateescape, que o Python usa para representar bytes indecodificáveis."""
    return any(0xDC80 <= ord(c) <= 0xDCFF for c in name)


def _fix_broken_bytes(name: str) -> str:
    """Troca cada byte indecodificável por '%XX' — o valor original fica legível
    no nome, então dá para saber de que arquivo veio sem consultar a origem."""
    return "".join("%%%02X" % (ord(c) - 0xDC00) if 0xDC80 <= ord(c) <= 0xDCFF else c
                   for c in name)


_RESERVED = ({"CON", "PRN", "AUX", "NUL"} |
             {"COM%d" % i for i in range(1, 10)} |
             {"LPT%d" % i for i in range(1, 10)})


class DestCaps:
    """O que o sistema de arquivos de destino aceita. `fstype` vazio = não
    identificado -> assumimos POSIX (otimista), mas `namemax` do statvfs ainda
    vale, então nomes longos demais continuam sendo pegos."""

    def __init__(self, fstype="", mountpoint="", namemax=255, readonly=False, **caps):
        self.fstype = fstype
        self.mountpoint = mountpoint
        self.namemax = namemax or 255
        self.readonly = readonly
        self.max_file = caps.get("max_file")
        self.symlinks = caps.get("symlinks", True)
        self.perms = caps.get("perms", True)
        self.times = caps.get("times", True)
        self.charset = caps.get("charset", "")
        self.maxchars = caps.get("maxchars")             # limite em CARACTERES (UTF-16)
        self.utf8_only = bool(caps.get("utf8_only"))     # nome precisa ser UTF-8 válido
        # Removível: pendrive/cartão/gaveta USB. Não muda o QUE pode ser escrito
        # (isso é o resto da tabela) — muda o RITMO com que se escreve.
        self.removable = bool(caps.get("removable"))
        # Velocidade negociada do link USB (Mbit/s), quando aplicável. Explica
        # sozinha a maior parte das cópias "lentas demais".
        self.link_mbits = caps.get("link_mbits")
        self.reserved = caps.get("reserved", False)
        self.label = caps.get("label", "POSIX")

    @property
    def restrictive(self) -> bool:
        """Precisa avisar o usuário antes de copiar?"""
        return bool(self.charset or self.max_file or not self.symlinks
                    or self.namemax < 255)

    def name_problem(self, name: str):
        """Por que `name` não pode existir no destino? None se pode.
        Devolve chave estável ('charset'|'length'|'reserved'|'trailing'), que a
        GUI traduz — o módulo não fala com o usuário (i18n mora na borda)."""
        if self.charset and any(c in self.charset for c in name):
            return "charset"
        if self.charset and any(ord(c) < 32 for c in name):
            return "charset"             # \n, \t: ilegais em FAT/exFAT/NTFS
        if self.utf8_only and _has_broken_bytes(name):
            return "encoding"            # nome que não é UTF-8: EINVAL no vfat
        if len(os.fsencode(name)) > self.namemax:
            return "length"
        if self.maxchars and len(name) > self.maxchars:
            return "length"                  # FAT/exFAT/NTFS: 255 unidades UTF-16
        if self.reserved and os.path.splitext(name)[0].upper() in _RESERVED:
            return "reserved"
        if self.charset and (name.endswith(" ") or name.endswith(".")):
            return "trailing"            # FAT/NTFS descartam espaço/ponto final
        return None

    def sanitize(self, name: str) -> str:
        """Nome adaptado ao destino, preservando a extensão. Só é usado quando o
        usuário escolhe 'adaptar nomes' — nunca automaticamente."""
        if self.utf8_only:
            name = _fix_broken_bytes(name)
        out = "".join("_" if (c in self.charset or ord(c) < 32) else c for c in name)
        if self.reserved and os.path.splitext(out)[0].upper() in _RESERVED:
            stem, ext = os.path.splitext(out)
            out = stem + "_" + ext
        out = out.rstrip(" .") or "_"
        # corta o RADICAL preservando a extensão. O limite é em BYTES (não chars):
        # fsencode/fsdecode com surrogateescape roundtripa nome não-UTF-8 sem perder.
        stem, ext = os.path.splitext(out)
        eb = os.fsencode(ext)
        if len(eb) >= self.namemax:                   # extensão absurda: corta tudo
            return os.fsdecode(os.fsencode(out)[:self.namemax])
        room = self.namemax - len(eb)
        sb = os.fsencode(stem)
        if len(sb) > room:
            stem = os.fsdecode(sb[:room]) or "_"
        if self.maxchars:                             # e o limite em CARACTERES
            stem = stem[:max(1, self.maxchars - len(ext))]
        return (stem + ext).rstrip(" .") or "_"


def is_removable(dev: str) -> bool:
    """O dispositivo é removível (pendrive, cartão, HD USB)?

    Lê /sys/block/<disco>/removable, e trata USB como removível mesmo quando a
    flag é 0 — gaveta USB com disco comum responde 0, e o que nos interessa aqui
    não é "pode arrancar", é "escrever nisso é lento e o cache de página do
    kernel vira uma bomba-relógio"."""
    disco = _sys_disk(dev)
    if not disco:
        return False
    d = "/sys/block/%s" % disco
    try:
        with open(d + "/removable") as f:
            if f.read().strip() == "1":
                return True
    except OSError:
        return False
    try:                                   # barramento USB: caminho tem /usb
        return "/usb" in os.path.realpath(d + "/device")
    except OSError:
        return False


def _sys_disk(dev: str) -> str:
    """Nome em /sys/block do DISCO inteiro que sustenta o nó `dev` (sobe de
    partição para disco e de dm-N para o disco físico). "" se não der."""
    base = os.path.basename(os.path.realpath(dev or ""))
    if not base:
        return ""
    for _ in range(4):
        if not base.startswith("dm-"):
            break
        try:
            base = sorted(os.listdir("/sys/block/%s/slaves" % base))[0]
        except (OSError, IndexError):
            return ""
    disco = re.sub(r"(p?\d+)$", "", base) if not base.startswith("sd") else base.rstrip("0123456789")
    return disco if os.path.isdir("/sys/block/%s" % disco) else ""


def link_speed(dev: str):
    """Velocidade NEGOCIADA do barramento, em Mbit/s, ou None se não for USB.

    Vale a pena mostrar porque explica a maior parte das decepções com pendrive:
    o mesmo SanDisk que faz 100 MB/s numa porta USB 3 faz 30 numa USB 2, e o
    usuário não tem como saber em qual porta o filho espetou. 480 = USB 2.0,
    5000 = USB 3.0, 10000 = 3.1 Gen2, 20000 = 3.2 Gen2x2.

    É o teto do LINK, não do dispositivo: um pendrive lento em porta rápida
    continua lento. Serve para dizer "não adianta trocar de porta" ou o
    contrário."""
    disco = _sys_disk(dev)
    if not disco:
        return None
    caminho = os.path.realpath("/sys/block/%s/device" % disco)
    # sobe a árvore até achar o nó USB que carrega 'speed'
    for _ in range(8):
        alvo = os.path.join(caminho, "speed")
        if os.path.isfile(alvo):
            try:
                with open(alvo) as f:
                    return float(f.read().strip())
            except (OSError, ValueError):
                return None
        pai = os.path.dirname(caminho)
        if pai == caminho or pai == "/sys":
            return None
        caminho = pai
    return None


def link_label(mbits) -> str:
    """'USB 2.0 (480 Mb/s)' — o nome que o usuário reconhece, com o número."""
    if not mbits:
        return ""
    nome = {480: "USB 2.0", 5000: "USB 3.0", 10000: "USB 3.1", 20000: "USB 3.2",
            12: "USB 1.1", 1.5: "USB 1.0"}.get(mbits, "USB")
    return f"{nome} ({mbits:g} Mb/s)"


def dest_caps(path: str) -> DestCaps:
    """Capacidades do sistema de arquivos que sustenta `path` (ou o ancestral
    existente mais próximo, se o diretório ainda vai ser criado)."""
    ap = os.path.abspath(path)
    probe = ap
    while probe != "/" and not os.path.exists(probe):
        probe = os.path.dirname(probe)
    dev, mp, fstype = _mount_entry(probe)
    caps = dict(_FS_CAPS.get(fstype.lower(), _DEFAULT_CAPS))
    readonly = bool(caps.pop("readonly", False))
    namemax = 255
    try:
        st = os.statvfs(probe)
        namemax = int(st.f_namemax) or 255
        # ST_RDONLY = 1; montagem só-leitura vira erro claro na pré-checagem
        readonly = readonly or bool(getattr(st, "f_flag", 0) & 1)
    except OSError:
        pass
    return DestCaps(fstype=fstype, mountpoint=mp, namemax=namemax,
                    readonly=readonly, removable=is_removable(dev),
                    link_mbits=link_speed(dev), **caps)


def free_bytes(path: str) -> int:
    """Bytes livres no destino (0 se não der para saber)."""
    probe = os.path.abspath(path)
    while probe != "/" and not os.path.exists(probe):
        probe = os.path.dirname(probe)
    try:
        st = os.statvfs(probe)
        return st.f_bavail * st.f_frsize
    except OSError:
        return 0
