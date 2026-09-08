#!/usr/bin/env python3
"""Classificação de disco em topologias que NÃO existem no ServidorCedro.

A 3a revisão (Fable 5.1, 08/09/2026) mostrou que o prefixo /mnt|/media estava
fazendo papel de "disco do acervo": um HDD em /home caía em 'unknown' e ficava
sem política nenhuma. Vale aqui, onde todo HDD está em /mnt; falha no desktop
mais comum do Linux. Esta suíte injeta tabelas de montagem sintéticas para que
a máquina do Rodrigo pare de ser a única topologia testada.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import disks, engine as E

falhas = []
def ok(cond, nome):
    print(("ok    " if cond else "FALHA ") + nome)
    if not cond: falhas.append(nome)

# rotational injetável: não depende do /sys desta máquina
REAL = disks._rotational
MAPA = {"/dev/sda2": "1", "/dev/sdb1": "1", "/dev/nvme0n1p2": "0",
        "/dev/mapper/vg-root": "0", "/dev/vda1": "1"}
disks._rotational = lambda dev: MAPA.get(dev)

def perfil(path, mounts):
    pr = disks.search_profile(path, mounts=mounts)
    return pr.klass, E._jobs_para_classe([pr.klass])

try:
    # 1) desktop comum: SSD na raiz, HDD em /home  (o caso que estava errado)
    M = [("/dev/nvme0n1p2", "/", "ext4"), ("/dev/sda2", "/home", "ext4")]
    ok(perfil("/home/joao/x", M) == ("rotational", 1),
       "desktop: HDD em /home ganha politica de disco mecanico (nao 'unknown')")
    ok(perfil("/etc", M) == ("ssd", None), "desktop: raiz em SSD fica solta")

    # 2) o MESMO disco em dois prefixos tem a MESMA classe
    M2 = M + [("/dev/sda2", "/mnt/acervo", "ext4")]
    ok(perfil("/home/joao/x", M2)[1] == perfil("/mnt/acervo/x", M2)[1],
       "mesmo disco fisico, mesma politica, em qualquer prefixo")

    # 3) Ubuntu/Mint LVM: /dev/mapper na raiz
    M3 = [("/dev/mapper/vg-root", "/", "ext4")]
    ok(perfil("/usr", M3) == ("ssd", None), "LVM sobre NVMe nao vira 'unknown'")

    # 4) Fedora btrfs @/@home: um dev, dois subvolumes -> um disco
    M4 = [("/dev/nvme0n1p2", "/", "btrfs"), ("/dev/nvme0n1p2", "/home", "btrfs")]
    ok(perfil("/home/x", M4) == ("ssd", None), "btrfs subvolume herda o disco de baixo")

    # 5) NAS: politica de rede vem do disks, nao do motor
    M5 = [("servidor:/export", "/mnt/nas", "nfs4")]
    k, j = perfil("/mnt/nas/x", M5)
    ok(k == "network" and j == disks.NET_WORKERS_PER_MOUNT,
       "montagem de rede usa NET_WORKERS_PER_MOUNT")

    # 6) celular MTP: latencia de rede, nao de bloco
    M6 = [("jmtpfs", "/run/user/1000/tel", "fuse.jmtpfs")]
    pr = disks.search_profile("/run/user/1000/tel/DCIM", mounts=M6)
    ok(pr.klass == "gvfs" and pr.enumerate_default is False,
       "MTP: pool de rede e fora do 'buscar em tudo'")

    # 7) VM: sem ramo especial — o kernel diz 1, a gente acredita
    M7 = [("/dev/vda1", "/", "ext4")]
    ok(perfil("/usr", M7) == ("rotational", 1),
       "disco de VM que se diz rotacional e tratado como tal (sem palpite)")

    # 8) fstype desconhecido sem no de bloco, fora de /mnt: nao estrangula
    M8 = [("overlay", "/", "overlay")]
    ok(perfil("/usr", M8) == ("unknown", None),
       "container/overlay: 'unknown' de verdade nao leva politica de HDD")
finally:
    disks._rotational = REAL

print(f"\n{'FALHOU: ' + '; '.join(falhas) if falhas else 'todos os testes passaram'}")
sys.exit(1 if falhas else 0)
