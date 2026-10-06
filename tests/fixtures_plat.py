"""Ajudas de teste que valem nos dois SOs (F1 do SFS para Windows, 02/10/2026).

  ENV_CONFIG / ENV_CACHE   variável que plat.config_base()/cache_base() leem
                           (XDG_* no Linux, APPDATA/LOCALAPPDATA no Windows)
  deny_read / allow_read   tira/devolve a leitura de um caminho: chmod 000 no
                           Linux, icacls /deny no Windows (sem administrador)
  pode_negar_leitura()     False quando negar não tem efeito (root no Linux)
  so_linux(motivo)         True no Linux; no Windows imprime "~skip <motivo>" —
                           lacuna CONHECIDA, dita, nunca escondida
  arquivo_esparso(p, n)    arquivo de n bytes sem gastar disco (NTFS: FSCTL_SET_SPARSE)
  nome_de_bytes(b)         nome com codificação quebrada (Linux: byte não-UTF-8;
                           Windows: o mesmo str = UTF-16 inválido, que o NTFS aceita)
  NOMES_BYTES              nomes com byte não-UTF-8 existem? (só no Linux:
                           NTFS guarda UTF-16, não há byte quebrado)
"""
import os, subprocess

WIN = os.name == "nt"
ENV_CONFIG = "APPDATA" if WIN else "XDG_CONFIG_HOME"
ENV_CACHE = "LOCALAPPDATA" if WIN else "XDG_CACHE_HOME"
NOMES_BYTES = not WIN


_PODE_NEGAR = None


def pode_negar_leitura() -> bool:
    """Negar leitura TEM efeito aqui? Linux: não-root. Windows: MEDIDO — um
    administrador com privilégio de backup (sessão SSH elevada, runner do CI)
    lista pasta negada, como o root ignora chmod 000."""
    global _PODE_NEGAR
    if not WIN:
        return os.geteuid() != 0      # root lê tudo: chmod 000 não nega nada
    if _PODE_NEGAR is None:
        import shutil, tempfile
        d = tempfile.mkdtemp(prefix="sfs_sonda_acl_")
        try:
            deny_read(d)
            try:
                os.listdir(d)
                _PODE_NEGAR = False
            except PermissionError:
                _PODE_NEGAR = True
        except Exception:
            _PODE_NEGAR = False
        finally:
            try:
                allow_read(d)
            except Exception:
                pass
            shutil.rmtree(d, ignore_errors=True)
    return _PODE_NEGAR


def _icacls(*args, check=True):
    subprocess.run(["icacls", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=check)


def deny_read(path: str):
    """Tira a leitura (e a listagem, se pasta) do usuário atual."""
    if WIN:
        # só RD (ler dados / listar pasta): negar "R" inteiro tira também o
        # READ_CONTROL, e aí nem o icacls consegue desfazer (medido, exit 5)
        _icacls(path, "/deny", "%s:(RD)" % os.environ.get("USERNAME", "*S-1-1-0"))
    else:
        os.chmod(path, 0)


def allow_read(path: str, modo: int = 0o755):
    """Desfaz deny_read (para o tempdir poder ser apagado)."""
    if WIN:
        if os.path.lexists(path):     # limpeza: caminho já apagado não é erro
            _icacls(path, "/remove:d", os.environ.get("USERNAME", "*S-1-1-0"), check=False)
    elif os.path.lexists(path):
        os.chmod(path, modo)


def so_linux(motivo: str) -> bool:
    if WIN:
        print("~skip  [só Linux] " + motivo)
        return False
    return True


_PODE_LINK = None


def pode_symlink() -> bool:
    """Criar symlink funciona aqui? No Windows, usuário comum sem o "modo
    desenvolvedor" leva WinError 1314 — limitação do SO, não do programa."""
    global _PODE_LINK
    if _PODE_LINK is None:
        import shutil, tempfile
        d = tempfile.mkdtemp(prefix="sfs_sonda_link_")
        try:
            os.symlink(d, os.path.join(d, "l"), target_is_directory=True)
            _PODE_LINK = True
        except (OSError, NotImplementedError):
            _PODE_LINK = False
        finally:
            shutil.rmtree(d, ignore_errors=True)
    return _PODE_LINK


def arquivo_esparso(path: str, tamanho: int):
    """Cria `path` com `tamanho` bytes SEM gastar disco. No Linux o truncate já
    deixa buraco; no NTFS não: SetEndOfFile num arquivo comum ALOCA os 5 GiB
    (medido na VM: minutos de escrita, e o disco enche). Lá é preciso marcar o
    arquivo como esparso (FSCTL_SET_SPARSE) e estender ESCREVENDO o último
    byte: o f.truncate() do Python no Windows é o _chsize_s do CRT, que estende
    gravando zeros um bloco por vez — desfaz o esparso (medido)."""
    with open(path, "wb") as f:
        if not WIN or tamanho <= 0:
            f.truncate(max(tamanho, 0))
            return
        import ctypes, msvcrt
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p,
                                        wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        ret = wintypes.DWORD()
        FSCTL_SET_SPARSE = 0x000900C4
        k32.DeviceIoControl(msvcrt.get_osfhandle(f.fileno()), FSCTL_SET_SPARSE,
                            None, 0, None, 0, ctypes.byref(ret), None)
        f.seek(tamanho - 1)
        f.write(b"\0")


def nome_de_bytes(b: bytes) -> str:
    """O str que o Python usa para um nome com codificação QUEBRADA. Linux:
    os.fsdecode (bytes não-UTF-8 viram U+DC80..U+DCFF, surrogateescape).
    Windows: a MESMA string — lá ela é um nome UTF-16 inválido (substituto
    solitário) que o NTFS aceita e guarda; o os.fsdecode do Windows (UTF-8
    estrito/surrogatepass) recusaria os bytes, por isso a decodificação é à mão."""
    return b.decode("utf-8", "surrogateescape") if WIN else os.fsdecode(b)
