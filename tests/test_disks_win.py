#!/usr/bin/env python3
"""disks_win (F1 do SFS para Windows, 02/10/2026) com volumes SINTÉTICOS.

Roda no Linux e no Windows: as funções puras recebem `mounts=` (lista de _Vol)
e usam ntpath, então a tabela de um PC com NVMe + HD + HD USB + pendrive +
letra de rede + UNC solto é testável sem Windows. O que fala com o SO de
verdade (IOCTL, GetVolumeInformation) é medido na VM/CI em test_disks_win_real
— aqui só o contrato e as regras.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import disks_win as W, disks as D

falhas = []
def ok(cond, nome):
    print(("ok    " if cond else "FALHA ") + nome)
    if not cond: falhas.append(nome)

V = W._Vol
PC = [
    V("\\\\.\\C:", "C:\\", "NTFS", label="Windows", discos=["PhysicalDrive0"], seek=False, bus="nvme"),
    V("\\\\.\\D:", "D:\\", "NTFS", label="Dados", discos=["PhysicalDrive1"], seek=True, bus="sata"),
    V("\\\\.\\E:", "E:\\", "exFAT", label="Backup", discos=["PhysicalDrive2"], seek=True, bus="usb"),
    V("\\\\.\\F:", "F:\\", "FAT32", label="PENDRIVE", drive_type=W.DRIVE_REMOVABLE,
      discos=["PhysicalDrive3"], seek=None, bus="usb"),
    V("\\\\.\\G:", "G:\\", "NTFS", label="Dados", discos=["PhysicalDrive1"], seek=True, bus="sata"),
    V("\\\\nas\\fotos", "Z:\\", "smb", drive_type=W.DRIVE_REMOTE, label="\\\\nas\\fotos",
      unc="\\\\nas\\fotos"),
    V("\\\\.\\R:", "R:\\", "CDFS", label="DVD", drive_type=W.DRIVE_CDROM, seek=True),
]

# ------------------------------------------------------------ contrato
faltam = [n for n in W.EXPORTS if not hasattr(W, n)]
ok(not faltam, f"disks_win exporta todo o contrato ({faltam})")
publicas_linux = {n for n in dir(D) if not n.startswith("_") and callable(getattr(D, n))}
sem_par = sorted(n for n in publicas_linux & set(W.EXPORTS) if not callable(getattr(W, n)))
ok(not sem_par, f"toda função trocada continua função ({sem_par})")

# ------------------------------------------------------------ _mount_entry
ok(W._mount_entry("C:\\Users\\luca\\doc.txt", PC)[1] == "C:\\", "arquivo em C: -> volume C:\\")
ok(W._mount_entry("c:/users/LUCA", PC)[1] == "C:\\", "caixa e barra '/' não importam (NTFS)")
ok(W._mount_entry("D:\\", PC)[0] == "\\\\.\\D:", "a própria raiz casa")
ok(W._mount_entry("Q:\\x", PC) == ("", "", ""), "letra que não existe -> vazio")
e = W._mount_entry("\\\\nas\\fotos\\2026\\a.jpg", PC)
ok(e[1] == "\\\\nas\\fotos\\" and e[2] == "smb" and e.drive_type == W.DRIVE_REMOTE,
   f"UNC de share mapeado -> volume de rede ({tuple(e)})")
e = W._mount_entry("\\\\outro\\docs\\x", PC)
ok(e[0] == "\\\\outro\\docs" and e.drive_type == W.DRIVE_REMOTE, "UNC solto vira volume de rede sintético")
ok(W._mount_entry("\\\\?\\C:\\x", PC)[1] == "", "\\\\?\\ não é tratado como UNC (o chamador tira o prefixo)")

# ------------------------------------------------------------ discos físicos
ok(W._sys_disks("\\\\.\\D:", PC) == ["PhysicalDrive1"], "D: -> PhysicalDrive1")
ok(W._sys_disks("\\\\.\\G:", PC) == W._sys_disks("\\\\.\\D:", PC),
   "duas partições no mesmo HD -> mesmo disco (engine agrupa num processo só)")
ok(W._sys_disks("\\\\nas\\fotos", PC) == [], "rede não tem disco físico")

# ------------------------------------------------------------ política de busca
p = W.search_profile("C:\\Users", PC)
ok(p.klass == "ssd" and not p.serialize, f"C: NVMe -> ssd, sem serializar ({p.klass})")
p = W.search_profile("D:\\Filmes", PC)
ok(p.klass == "rotational" and p.serialize, f"D: HD de dados -> rotational, serializa ({p})")
p = W.search_profile("E:\\", PC)
ok(p.klass == "rotational" and p.serialize, "HD USB (FIXED) -> rotational, serializa")
p = W.search_profile("F:\\fotos", PC)
ok(p.klass == "rotational" and p.serialize, "pendrive sem resposta de seek fora do C: -> conservador")
p = W.search_profile("Z:\\2026", PC)
ok(p.klass == "network" and p.is_network and p.max_workers == D.NET_WORKERS_PER_MOUNT,
   "letra de rede -> network com teto por montagem")
p = W.search_profile("\\\\outro\\docs", PC)
ok(p.klass == "network" and p.is_network, "UNC solto -> network")
p = W.search_profile("R:\\", PC)
ok(p.klass == "rotational", "CD/DVD -> rotational")
C_HD = [V("\\\\.\\C:", "C:\\", "NTFS", discos=["PhysicalDrive0"], seek=True, bus="sata")]
p = W.search_profile("C:\\Users", C_HD)
ok(p.klass == "rotational" and not p.serialize,
   "PC só com HD: C: é rotational mas NÃO serializa (é a / do Linux)")
C_NADA = [V("\\\\.\\C:", "C:\\", "NTFS", discos=["PhysicalDrive0"], seek=None)]
ok(W.search_profile("C:\\x", C_NADA).klass == "unknown", "C: sem resposta de seek -> unknown (não inventa)")

# ------------------------------------------------------------ removível, rótulos
ok(W.is_removable("\\\\.\\F:", PC), "pendrive é removível")
ok(W.is_removable("\\\\.\\E:", PC), "HD USB (se diz FIXED) é removível para o ritmo de escrita")
ok(not W.is_removable("\\\\.\\D:", PC), "HD SATA interno não é removível")
ok(W.volume_label("D:\\", PC) == "Dados (D:)", f"rótulo como o Explorer ({W.volume_label('D:', PC)})")
ok(W.volume_label("Z:\\x", PC) == "\\\\nas\\fotos (Z:)", "rede: UNC + letra")
lbl = D.menu_labels(["D:\\", "G:\\"], PC)
ok(lbl["D:\\"] != lbl["G:\\"], f"dois volumes 'Dados' ficam distintos no menu ({lbl})")
ok(W.is_mountpoint("C:\\", PC) and W.is_mountpoint("c:", PC) and not W.is_mountpoint("C:\\Users", PC),
   "is_mountpoint: só a raiz do volume")
ok(W.mounts_under("C:\\", PC) == [], "sem pastas montadas na v1")

# ------------------------------------------------------------ classifica (menu Discos/Rede)
cl = W.classifica_volumes(PC)
ok(cl["Z:\\"][0] == "rede" and cl["D:\\"][0] == "local" and cl["F:\\"][0] == "local",
   "classifica_volumes: rede vs local")

# ------------------------------------------------------------ capacidades de destino
c = D.DestCaps(fstype="FAT32", **W._caps_win("FAT32", W.DRIVE_REMOVABLE))
ok(c.max_file == (1 << 32) - 1, "FAT32: teto de 4 GiB")
ok(c.name_problem("CON.txt") == "reserved", "FAT32 no Windows: CON.txt é reservado")
c = D.DestCaps(fstype="exFAT", **W._caps_win("exFAT", W.DRIVE_FIXED))
ok(c.max_file is None and c.name_problem("aux.log") == "reserved",
   "exFAT no Windows: sem teto, mas nome reservado vale (é o Win32, não o fs)")
ok(c.name_problem("a:b.txt") == "charset" and c.name_problem("fim.") == "trailing",
   "':' proibido e ponto final recusado em qualquer fs")
c = D.DestCaps(fstype="NTFS", namemax=255 * 4, **W._caps_win("NTFS", W.DRIVE_FIXED))
ok(c.name_problem("ã" * 200 + ".txt") is None, "200 letras acentuadas cabem (limite é em caracteres)")
ok(c.name_problem("a" * 300) == "length", "300 caracteres não cabem")
c = D.DestCaps(fstype="smb", **W._caps_win("smb", W.DRIVE_REMOTE))
ok(c.net and c.name_problem("x?.txt") == "charset", "destino de rede: net=True e charset do SMB")
ok(W._caps_win("CDFS", W.DRIVE_CDROM).get("readonly"), "CD é somente leitura")

# ------------------------------------------------------------ sonda (injetada)
def morto(_p):
    e = OSError(64, "The specified network name is no longer available")
    e.winerror = 64
    raise e
ok(W.mount_status("\\\\nas\\fotos", _stat=morto, _porta=lambda s, t: True) == "broken_mount",
   "winerror 64 (share sumiu) -> broken_mount")
ok(W.mount_status("\\\\nas\\fotos", _porta=lambda s, t: False) == "no_response",
   "servidor não atende na 445 -> no_response, sem tocar o FS")
def lento(_p):
    import time; time.sleep(5)
ok(W.mount_status("\\\\nas\\fotos", timeout=0.3, _stat=lento, _porta=lambda s, t: True) == "no_response",
   "stat que não volta no prazo -> no_response")
def negado(_p):
    e = PermissionError(13, "Access is denied"); e.winerror = 5; raise e
ok(W.mount_status("\\\\nas\\fotos", _stat=negado, _porta=lambda s, t: True) == "alive",
   "acesso negado: o share RESPONDEU -> alive")
ok(W.mount_status("\\\\nas\\fotos", _stat=lambda p: None, _statvfs=lambda p: None,
                  _porta=lambda s, t: True) == "alive", "tudo responde -> alive")

# ------------------------------------------------------------ fstab do Windows
ok(W.fstab_targets(["Z:\\"]) == {"Z:\\"}, "fstab_targets aceita fonte injetada")
ok(W.is_mount_slot("C:\\mnt\\x") is False, "não há vaga de montagem")

print(f"\n{'FALHOU: ' + '; '.join(falhas) if falhas else 'todos os testes passaram'}")
sys.exit(1 if falhas else 0)
