#!/usr/bin/env python3
"""Menu "Discos ▾": Opção B + REDE à parte + sonda que não mente (22/09/2026).

1. Opção B (pareceres de julho): o disco de usuário é o que NÃO é de sistema, não
   o que mora num dos 4 prefixos — /data, /srv, ZFS (origem "pool/dataset"),
   mergerfs, disco dentro da home entram; /, /var, a pasta pessoal em si, o
   ZFS-raiz do Ubuntu, snaps, AppImage, contêineres, autofs e gvfs ficam fora.
2. REDE (NFS, SMB, sshfs, WebDAV, rclone) numa seção à parte do menu, FORA de
   "Todos os discos" (decisão do Rodrigo: busca local é o uso diário, custa menos).
3. mount_status fazia só stat() — medido com NFS real e o servidor desligado:
   "OK" em 0,0 s, do CACHE de atributos; a busca entrava no NAS morto e
   pendurava. Agora também statvfs, que vai ao servidor. Com o conserto, o mesmo
   cenário real: NAS pulado com aviso em 3,4 s. (O cenário real exige root e um
   servidor NFS; aqui ele é reproduzido com statvfs simulado.)
Rode:  python3 tests/test_montagens_opcao_b_2026_09_22.py
"""
from __future__ import annotations
import errno, os, sys, tempfile, time

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "lfs"))
import engine, disks                                          # noqa: E402

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)

TABELA = """/dev/mapper/root / btrfs rw 0 0
/dev/nvme0n1p3 /var btrfs rw 0 0
/dev/nvme0n1p3 /var/home btrfs rw 0 0
/dev/nvme0n1p3 /sysroot btrfs rw 0 0
/dev/nvme0n1p1 /boot/efi vfat rw 0 0
/dev/sda1 /var/mnt/Toledo ext4 rw 0 0
/dev/sdb1 /data ext4 rw 0 0
/dev/sdc1 /srv/acervo xfs rw 0 0
/dev/sdf1 /mnt ext4 rw 0 0
/dev/sdd1 /home/rodrigo/discos/HD\\040Velho ntfs3 rw 0 0
tank/fotos /tank/fotos zfs rw 0 0
rpool/ROOT/ubuntu / zfs rw 0 0
rpool/USERDATA/rodrigo /home/rodrigo zfs rw 0 0
rpool/var/log /var/log zfs rw 0 0
//nas/laudos /mnt/nas cifs rw 0 0
nas:/export/fotos /nfs/fotos nfs4 rw 0 0
127.0.0.1:/x /var/mnt/NAS-teste nfs rw 0 0
rodrigo@srv:/ /home/rodrigo/srv fuse.sshfs rw 0 0
b2:acervo /media/nuvem fuse.rclone rw 0 0
/dev/loop3 /snap/foo/12 squashfs ro 0 0
/dev/loop4 /run/media/rodrigo/ISO_WIN iso9660 ro 0 0
/dev/loop5 /tmp/.mount_App123 squashfs ro 0 0
disco1:disco2 /pool fuse.mergerfs rw 0 0
systemd-1 /mnt/auto autofs rw 0 0
overlay /var/lib/containers/storage/overlay/x/merged overlay rw 0 0
gvfsd-fuse /run/user/1000/gvfs fuse.gvfsd-fuse rw 0 0
tmpfs /tmp tmpfs rw 0 0
/dev/sde1 /run/media/rodrigo/PEN vfat rw 0 0""".splitlines(True)

LOCAIS = ["/data", "/home/rodrigo/discos/HD Velho", "/mnt", "/pool",
          "/run/media/rodrigo/ISO_WIN", "/run/media/rodrigo/PEN", "/srv/acervo",
          "/tank/fotos", "/var/mnt/Toledo"]
REDE = ["/home/rodrigo/srv", "/media/nuvem", "/mnt/nas", "/nfs/fotos", "/var/mnt/NAS-teste"]

# ------------------------------------------------------------- 1+2 classificação
loc, net = engine.user_mounts(TABELA), engine.network_mounts(TABELA)
ok(loc == LOCAIS, f"locais (Opção B) = {loc}")
ok(net == REDE, f"rede à parte = {net}")
for fora in ("/", "/var", "/var/home", "/sysroot", "/boot/efi", "/home/rodrigo", "/var/log",
             "/snap/foo/12", "/tmp/.mount_App123", "/mnt/auto",
             "/var/lib/containers/storage/overlay/x/merged", "/run/user/1000/gvfs", "/tmp"):
    ok(fora not in loc and fora not in net, f"de sistema/pseudo fica FORA: {fora}")
ok(not (set(loc) & set(net)), "nenhuma montagem é local E rede ao mesmo tempo")
# a lista de fs não-usuário é a DESTE módulo (o F12 tem um _PSEUDO_FS homônimo que a
# sobrescrevia no import — zram/overlay com origem /dev passavam como disco)
for l in ("/dev/zram0 /mnt/zram zram rw 0 0\n", "/dev/loop0 /media/o overlay rw 0 0\n",
          "/dev/sdz1 /mnt/tmp tmpfs rw 0 0\n"):
    mp = l.split()[1]
    ok(mp not in engine.user_mounts([l]), f"{l.split()[2]} com origem /dev fica FORA ({mp})")
ok("tmpfs" in engine._FS_NAO_USUARIO and "zram" in engine._FS_NAO_USUARIO,
   "_FS_NAO_USUARIO não é sobrescrito pelo _PSEUDO_FS do F12")

# planejar_raizes: raiz de REDE não leva stat antes da sonda (NAS congelado
# pendurava 150 s, 22/09/2026) — o stat do motor vira uma armadilha
chamados = []
orig_dev, orig_ident = engine._st_dev, engine._ident
engine._st_dev = lambda p: chamados.append(("st_dev", p)) or 1
engine._ident = lambda p: chamados.append(("ident", p)) or (1, 1)
try:
    mnt = [("//nas/c", "/var/mnt/NAS", "cifs"), ("/dev/sda1", "/var/mnt/HD", "ext4")]
    engine.planejar_raizes(["/var/mnt/NAS"], False, {}, mounts=mnt)
    ok(not any(p == "/var/mnt/NAS" for _k, p in chamados),
       f"raiz de rede: nenhum stat no plano ({chamados})")
    chamados.clear()
    engine.planejar_raizes(["/var/mnt/HD"], False, {}, mounts=mnt)
    ok(any(p == "/var/mnt/HD" for _k, p in chamados), "raiz local segue levando stat (bind/identidade)")
finally:
    engine._st_dev, engine._ident = orig_dev, orig_ident
ok(engine.user_mounts(["/dev/sdc1 /media/rodrigo/Backup\\040Externo ext4 rw 0 0\n"])
   == ["/media/rodrigo/Backup Externo"], "espaço escapado (\\040) segue decodificado")
ok(isinstance(engine.user_mounts(), list) and isinstance(engine.network_mounts(), list),
   "leitura real do /proc/mounts não explode")

# ------------------------------------------------------------- 3 sonda com statvfs
d = tempfile.mkdtemp(prefix="sfs_sonda_")
try:
    def eio(p):
        raise OSError(errno.EIO, "Input/output error")
    def eacces(p):
        raise OSError(errno.EACCES, "Permission denied")
    def trava(p):
        time.sleep(5)
    ok(disks.mount_status(d, timeout=2.0) == "alive", "dir real: stat + statvfs = viva")
    ok(disks.mount_status(d, timeout=2.0, _statvfs=eio) == "broken_mount",
       "stat do CACHE ok + statvfs EIO (servidor mudo) = MORTA (antes: 'alive')")
    for e in (errno.ETIMEDOUT, errno.EHOSTUNREACH, errno.ECONNREFUSED):
        def f(p, e=e):
            raise OSError(e, os.strerror(e))
        ok(disks.mount_status(d, timeout=2.0, _statvfs=f) == "broken_mount",
           f"statvfs {errno.errorcode[e]} = morta")
    ok(disks.mount_status(d, timeout=2.0, _statvfs=eacces) == "alive",
       "statvfs EACCES = respondeu (viva)")
    t0 = time.time()
    st = disks.mount_status(d, timeout=0.5, _statvfs=trava)
    ok(st == "no_response" and time.time() - t0 < 2.0,
       f"statvfs travado (NAS 'hard') -> no_response no prazo ({st}, {time.time()-t0:.1f}s)")
    ok(disks.mount_alive(d, timeout=2.0, _statvfs=eio) is False, "mount_alive repassa o _statvfs")
finally:
    os.rmdir(d)

# ------------------------------------------------------------- menu (GUI offscreen)
try:
    from PySide6.QtWidgets import QApplication, QMenu
except ImportError:
    print("--    (pulado) menu: sem PySide6")
else:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import app, i18n
    i18n.set_lang("en")
    qa = QApplication.instance() or QApplication([])
    orig = (engine.user_mounts, engine.network_mounts, engine.classifica_montagens)
    engine.user_mounts = lambda lines=None: ["/var/mnt/Toledo"]
    engine.network_mounts = lambda lines=None: ["/mnt/nas"]
    engine.classifica_montagens = lambda lines=None: {"/mnt/nas": ("rede", "cifs", "//nas/laudos")}
    try:
        menu, marcados = QMenu(), []
        estado = {"todos": None}
        app.preenche_menu_discos(menu, [], lambda mp, on: marcados.append((mp, on)),
                                 lambda on: estado.__setitem__("todos", on))
        textos = [a.text() for a in menu.actions() if not a.isSeparator()]
        ok(textos[0] == "All disks" and any("Toledo" in x for x in textos),
           f"menu: Todos + locais ({textos})")
        i_rede = next(i for i, x in enumerate(textos) if x.startswith("Network"))
        ok(any("🌐" in x and "nas" in x for x in textos[i_rede:]),
           "menu: seção Rede com 🌐 depois dos locais")
        cab = [a for a in menu.actions() if a.text().startswith("Network")][0]
        ok(not cab.isEnabled(), "cabeçalho da Rede não é clicável")
        nas = [a for a in menu.actions() if "🌐" in a.text()][0]
        ok("//nas/laudos" in nas.toolTip() and "cifs" in nas.toolTip(), "tooltip mostra origem e tipo")
        nas.setChecked(True)
        ok(marcados == [("/mnt/nas", True)], "marcar o NAS o põe no 'Em' (um a um)")
    finally:
        engine.user_mounts, engine.network_mounts, engine.classifica_montagens = orig
        i18n.set_lang(None)
    # "Todos os discos" da janela real marca só os LOCAIS
    app.save_cfg = lambda d: None
    engine.user_mounts = lambda lines=None: ["/var/mnt/Toledo"]
    engine.network_mounts = lambda lines=None: ["/mnt/nas"]
    try:
        w = app.MainWindow(); w.ed_path.setText("/home/x")
        w._toggle_all_disks(True)
        ok(w.ed_path.text() == "/home/x;/var/mnt/Toledo", f"Todos os discos NÃO inclui a rede ({w.ed_path.text()})")
        w.close()
    finally:
        engine.user_mounts, engine.network_mounts, engine.classifica_montagens = orig

if falhas:
    print(f"\n{len(falhas)} FALHA(S):"); [print("  -", f) for f in falhas]
    sys.stdout.flush(); os._exit(1)
print("\ntodos os testes passaram")
sys.stdout.flush(); os._exit(0)
