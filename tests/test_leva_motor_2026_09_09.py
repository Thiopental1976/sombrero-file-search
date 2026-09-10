#!/usr/bin/env python3
"""Leva do motor 09/09/2026 — disco físico como CONJUNTO, não como um nome só.

Um volume pode ser sustentado por MAIS de um prato (VG do LVM em dois PVs, RAID
md, LUKS sobre LVM). O `_sys_disk` antigo descia dm-N pelo slaves[0] e parava
em 4 níveis: quem tinha dois discos embaixo era tratado como um só, e o
agrupamento por disco (F11) abria dois processos no MESMO prato ou juntava dois
pratos num só processo. Esta suíte trava o desenho novo:
  - disks._sys_disks(dev) devolve TODOS os discos (largura, sem ciclo infinito,
    sem teto de níveis), com fallback em [_sys_disk(dev)];
  - _rotational / is_removable / link_speed olham o CONJUNTO (política mais
    conservadora: qualquer rotacional → "1"; qualquer removível → True; menor
    velocidade USB);
  - engine._chave_de_disco vira ("disco", frozenset) e _grupos_por_disco FUNDE
    grupos cujos conjuntos se cruzam (união transitiva);
  - Query.rg_threads → ["--threads", N] no rg_flags_comuns;
  - _rodada particiona TAMBÉM no fallback Python (sem rg/fd);
  - search_boolean avalia a expressão POR GRUPO de disco e une os conjuntos.

Não toca em sysfs de verdade: os hooks (_slaves_de, _sys_disk, _le_rotational,
_disco_removivel, _velocidade_do_disco, _sys_disks, _chave_de_disco) são
substituídos por dict-lookup e restaurados no `finally`. As buscas de ponta a
ponta usam árvores temporárias reais, pequenas.
"""
import inspect, os, shutil, sys, tempfile, threading
from dataclasses import replace
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lfs import engine as E, boolean as B, disks as D

falhas = []
def ok(cond, nome):
    print(("ok    " if cond else "FALHA ") + nome)
    if not cond: falhas.append(nome)


# ---------------------------------------------------------------- disks._sys_disks
# Topologia fingida (nomes em /sys/block e seus slaves):
#   dm-0  → nvme0n1p2                (LVM simples, Mint/Ubuntu padrão)
#   dm-3  → sda2, sdb1               (VG em DOIS PVs)
#   dm-5  → dm-3                     (LUKS sobre o LVM acima)
#   md0   → sdc1, sdd1               (RAID1)
#   dm-9  → dm-9                     (ciclo artificial: não pode travar)
_SLAVES = {"dm-0": ["nvme0n1p2"], "dm-3": ["sda2", "sdb1"], "dm-5": ["dm-3"],
           "md0": ["sdc1", "sdd1"], "dm-9": ["dm-9"]}
# folhas → disco inteiro (o que o _sys_disk real faria lendo /sys/block)
_FOLHAS = {"/dev/nvme0n1p2": "nvme0n1", "/dev/sda2": "sda", "/dev/sdb1": "sdb",
           "/dev/sdc1": "sdc", "/dev/sdd1": "sdd", "/dev/vda3": "vda"}


def _com_topologia_fingida(fn):
    """Roda fn() com _slaves_de e _sys_disk fingidos; restaura sempre."""
    orig = (D._slaves_de, D._sys_disk)
    D._slaves_de = lambda base: list(_SLAVES.get(base, []))
    D._sys_disk = lambda dev: _FOLHAS.get(dev, "")
    try:
        return fn()
    finally:
        D._slaves_de, D._sys_disk = orig


def test_sys_disks_desce_pelos_slaves():
    def corpo():
        ok(D._sys_disks("/dev/dm-0") == ["nvme0n1"],
           "(a) dm-0 → [nvme0n1p2] → ['nvme0n1'] (LVM simples continua um disco só)")
        ok(D._sys_disks("/dev/dm-3") == ["sda", "sdb"],
           "(b) VG em 2 PVs: dm-3 → [sda2, sdb1] → ['sda', 'sdb'] (os DOIS pratos)")
        ok(D._sys_disks("/dev/dm-5") == ["sda", "sdb"],
           "(c) LUKS sobre LVM: dm-5 → [dm-3] → [sda2, sdb1] (dois níveis, sem teto)")
        ok(D._sys_disks("/dev/md0") == ["sdc", "sdd"],
           "(d) RAID: md0 → [sdc1, sdd1] → ['sdc', 'sdd'] (md* desce como dm-*)")
        ok(D._sys_disks("/dev/vda3") == ["vda"],
           "(f) sem slaves: cai em [_sys_disk(dev)] → ['vda']")
        ok(D._sys_disks("/dev/naoexiste") == [],
           "dev desconhecido (sem slaves, _sys_disk vazio): lista vazia, sem ''")
        # ordenado e sem repetição mesmo se o mesmo disco entrar por dois ramos
        D._slaves_de = lambda base: {"dm-7": ["sdb1", "sda2", "sdb1"]}.get(base, list(_SLAVES.get(base, [])))
        ok(D._sys_disks("/dev/dm-7") == ["sda", "sdb"],
           "ordenado e sem repetição (slaves fora de ordem / repetidos)")
    _com_topologia_fingida(corpo)


def test_sys_disks_ciclo_nao_trava():
    """(e) dm-9 → [dm-9]: a descida em largura tem de marcar o visitado; sem
    isso o laço é infinito. Roda numa thread com teto para o teste não ficar
    refém do bug que ele existe para pegar."""
    caixa = {}
    def corpo():
        def alvo():
            try:
                caixa["res"] = D._sys_disks("/dev/dm-9")
            except BaseException as e:      # noqa: reporta o erro no thread principal
                caixa["exc"] = e
        t = threading.Thread(target=alvo, daemon=True)
        t.start(); t.join(timeout=5)
        ok(not t.is_alive(), "(e) ciclo dm-9 → dm-9 não trava a descida (teto 5 s)")
        if "exc" in caixa:
            raise caixa["exc"]
        ok(caixa.get("res") == [], f"(e) ciclo devolve [] (fallback filtra '') — deu {caixa.get('res')!r}")
    _com_topologia_fingida(corpo)


def test_sys_disk_um_nome_continua():
    """Contrato antigo: _sys_disk(dev) continua existindo e devolvendo UM nome
    (str) — outros testes e o composefs mockam esse ponto."""
    ok(callable(getattr(D, "_sys_disk", None)), "disks._sys_disk continua existindo")
    ok(isinstance(D._sys_disk("/dev/naoexiste"), str), "_sys_disk devolve str ('' se não sabe)")
    ok(callable(getattr(D, "_slaves_de", None)), "disks._slaves_de existe (hook injetável)")
    ok(D._slaves_de("nao_existe_em_sys_block") == [],
       "_slaves_de de nome inexistente devolve [] (não levanta)")


# ---------------------------------------------------------------- políticas sobre o conjunto
def _com_conjunto(discos, fn, **hooks):
    """_sys_disks fingido devolvendo `discos`; hooks extras (_le_rotational…)."""
    nomes = ["_sys_disks"] + list(hooks)
    orig = {n: getattr(D, n) for n in nomes}
    D._sys_disks = lambda dev: list(discos)
    for n, h in hooks.items():
        setattr(D, n, h)
    try:
        return fn()
    finally:
        for n, v in orig.items():
            setattr(D, n, v)


def test_rotational_conjunto():
    rot = {"sda": "1", "sdb": "0", "nvme0n1": "0", "sdz": None}
    le = lambda nome: rot.get(nome)
    r = lambda discos: _com_conjunto(discos, lambda: D._rotational("/dev/x"), _le_rotational=le)
    ok(r(["nvme0n1"]) == "0", "um SSD só → '0'")
    ok(r(["sda"]) == "1", "um mecânico só → '1'")
    ok(r(["sdb", "nvme0n1"]) == "0", "'0' SÓ se TODOS forem '0'")
    ok(r(["sdb", "sda"]) == "1", "QUALQUER rotacional no conjunto → '1' (política conservadora)")
    ok(r([]) is None, "sem disco → None (desconhecido)")
    ok(r(["sdb", "sdz"]) is None, "um '0' e um desconhecido → None (não promete SSD)")
    ok(r(["sda", "sdz"]) == "1", "um '1' e um desconhecido → '1' (o rotacional manda)")


def test_is_removable_conjunto():
    rem = {"sda": False, "sdb": True}
    h = lambda nome: rem.get(nome, False)
    r = lambda discos: _com_conjunto(discos, lambda: D.is_removable("/dev/x"), _disco_removivel=h)
    ok(r(["sda"]) is False, "interno → False")
    ok(r(["sdb"]) is True, "removível → True")
    ok(r(["sda", "sdb"]) is True, "qualquer removível no conjunto → True")
    ok(r([]) is False, "sem disco → False")


def test_link_speed_conjunto():
    vel = {"sda": None, "sdb": 5000.0, "sdc": 480.0}
    h = lambda nome: vel.get(nome)
    r = lambda discos: _com_conjunto(discos, lambda: D.link_speed("/dev/x"), _velocidade_do_disco=h)
    ok(r(["sdb"]) == 5000.0, "um USB 3 → 5000")
    ok(r(["sdb", "sdc"]) == 480.0, "dois USB → a MENOR velocidade (gargalo)")
    ok(r(["sda", "sdb"]) == 5000.0, "interno + USB → a do USB (o interno não tem)")
    ok(r(["sda"]) is None, "só interno → None")
    ok(r([]) is None, "sem disco → None")


# ---------------------------------------------------------------- engine._chave_de_disco
def test_chave_de_disco_conjunto():
    """A chave passa a carregar o CONJUNTO de discos (frozenset) — é ela que
    permite a fusão transitiva em _grupos_por_disco. ZFS e o reserva por
    st_dev ficam como eram."""
    orig = (D._sys_disks, D._mount_entry)
    vistos = []
    D._sys_disks = lambda dev: (vistos.append(dev), ["sda", "sdb"])[1]
    try:
        ok(E._chave_de_disco("/") == ("disco", frozenset({"sda", "sdb"})),
           f"chave = ('disco', frozenset) quando o disks sabe — deu {E._chave_de_disco('/')!r}")
        ok(vistos and vistos[0].startswith("/dev/"),
           f"_chave_de_disco consulta disks._sys_disks com o nó de bloco — deu {vistos[:1]}")
        # ZFS: pool, não disco (decidido antes de olhar o sysfs)
        D._mount_entry = lambda ap, mounts=None: D._Mount("tank/home", "/", "zfs")
        ok(E._chave_de_disco("/") == ("zpool", "tank"), "ZFS continua ('zpool', pool)")
        # disks não sabe (conjunto vazio): reserva por st_dev
        D._mount_entry = orig[1]
        D._sys_disks = lambda dev: []
        ok(E._chave_de_disco("/tmp") == ("dev", os.stat("/tmp").st_dev),
           "sem disco conhecido: reserva ('dev', st_dev) inalterado")
    finally:
        D._sys_disks, D._mount_entry = orig


# ---------------------------------------------------------------- _grupos_por_disco: união transitiva
def _com_chaves(mapa, fn):
    """_chave_de_disco fingido por caminho (prefixo), como o teste F11 faz."""
    real = E._chave_de_disco
    def fake(p):
        ap = os.path.abspath(p)
        for r, k in mapa.items():
            if ap == r or ap.startswith(r.rstrip("/") + "/"):
                return k
        return real(p)
    E._chave_de_disco = fake
    try:
        return fn()
    finally:
        E._chave_de_disco = real


def test_grupos_fundem_conjuntos_que_se_cruzam():
    S = lambda *n: ("disco", frozenset(n))
    # A{sda,sdb}, B{sdb,sdc}, C{sdc} → UM grupo (cadeia); D{sdz} fica só
    mapa = {"/A": S("sda", "sdb"), "/B": S("sdb", "sdc"), "/C": S("sdc"), "/D": S("sdz")}
    g = _com_chaves(mapa, lambda: E._grupos_por_disco(["/A", "/D", "/B", "/C"]))
    ok(g == [["/A", "/B", "/C"], ["/D"]],
       f"A{{sda,sdb}} B{{sdb,sdc}} C{{sdc}} viram UM grupo; D separado; ordem de 1ª aparição — deu {g}")
    # ponte tardia: X{sda} e Y{sdc} nasceram separados, Z{sda,sdc} os une
    mapa = {"/X": S("sda"), "/Y": S("sdc"), "/Z": S("sda", "sdc")}
    g = _com_chaves(mapa, lambda: E._grupos_por_disco(["/X", "/Y", "/Z"]))
    ok(g == [["/X", "/Y", "/Z"]],
       f"ponte tardia (Z une X e Y já separados) → um grupo só, na ordem — deu {g}")
    # conjuntos disjuntos NÃO se fundem
    mapa = {"/P": S("sda"), "/Q": S("sdb")}
    g = _com_chaves(mapa, lambda: E._grupos_por_disco(["/P", "/Q"]))
    ok(g == [["/P"], ["/Q"]], f"conjuntos disjuntos continuam grupos distintos — deu {g}")
    # chaves de outro tipo agrupam por IGUALDADE e não se misturam com 'disco'
    mapa = {"/z1": ("zpool", "tank"), "/z2": ("zpool", "tank"), "/d1": ("dev", 42),
            "/d2": ("dev", 43), "/s": S("sda")}
    g = _com_chaves(mapa, lambda: E._grupos_por_disco(["/z1", "/d1", "/z2", "/s", "/d2"]))
    ok(g == [["/z1", "/z2"], ["/d1"], ["/s"], ["/d2"]],
       f"zpool/dev agrupam por igualdade, sem cruzar com 'disco' — deu {g}")
    # o contrato do F11 continua: mesmo conjunto → mesmo grupo
    mapa = {"/a": S("sda"), "/a2": S("sda"), "/b": S("sdb")}
    g = _com_chaves(mapa, lambda: E._grupos_por_disco(["/a", "/b", "/a2"]))
    ok(g == [["/a", "/a2"], ["/b"]], f"subvolumes do mesmo prato no mesmo grupo (F11) — deu {g}")


def test_grupo_inacessivel_continua():
    real = E._chave_de_disco
    E._chave_de_disco = lambda p: (_ for _ in ()).throw(OSError()) if p == "/sumiu" else real(p)
    try:
        g = E._grupos_por_disco(["/sumiu", "/tmp"])
    finally:
        E._chave_de_disco = real
    ok(len(g) == 2, "root sem stat continua virando grupo próprio")


# ---------------------------------------------------------------- Query.rg_threads
def test_rg_threads():
    q = E.Query(paths=["/"])
    ok(getattr(q, "rg_threads", "ausente") is None, "Query.rg_threads existe e é None por padrão")
    flags = E.rg_flags_comuns(q)
    ok("--threads" not in flags, "rg_threads=None: nenhum --threads nas flags")
    q3 = E.Query(paths=["/"], rg_threads=3)
    flags = E.rg_flags_comuns(q3)
    i = flags.index("--threads") if "--threads" in flags else -1
    ok(i >= 0 and flags[i + 1] == "3", f"rg_threads=3 → ['--threads', '3'] — deu {flags}")
    ok(flags.count("--threads") == 1, "--threads entra UMA vez")
    q1 = E.Query(paths=["/"], rg_threads=1)
    flags = E.rg_flags_comuns(q1, matching=False)
    ok("1" in flags and "--threads" in flags, "matching=False (universo do NOT) também leva --threads")
    ok(E.Query(**q3.__dict__).rg_threads == 3, "Query(**q.__dict__) continua funcionando com o campo novo")
    ok(replace(q3, rg_threads=None).rg_threads is None, "dataclasses.replace respeita o campo")


# ---------------------------------------------------------------- árvores temporárias
def _arvore(prefixo, arquivos):
    d = tempfile.mkdtemp(prefix=prefixo)
    for nome, texto in arquivos.items():
        fp = os.path.join(d, nome)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w") as f:
            f.write(texto)
    return d


def _duas_raizes():
    r1 = _arvore("lfs_leva_r1_", {"a1.txt": "alfa\n", "a2.txt": "alfa beta\n",
                                  "g1.txt": "gama\n", "sub/n1.log": "nada\n"})
    r2 = _arvore("lfs_leva_r2_", {"b1.txt": "alfa\n", "b2.txt": "beta\n",
                                  "g2.txt": "gama alfa\n", "sub/n2.log": "beta gama\n"})
    return r1, r2


def _sem_motores(fn):
    """Fallback Python puro: sem rg, sem fd, sem rga."""
    orig = (E.RG, E.FD, E.RGA)
    E.RG = E.FD = E.RGA = None
    try:
        return fn()
    finally:
        E.RG, E.FD, E.RGA = orig


def _caminhos(q):
    out = []
    E.search(q, out.append, stats={})
    return {m.path for m in out}


# ---------------------------------------------------------------- _rodada particiona no fallback
def test_fallback_python_particiona():
    """Sem rg/fd, duas raízes em discos distintos passam por _iter_particionado
    (uma thread por disco também no os.walk) e o resultado é o MESMO da busca
    raiz a raiz."""
    r1, r2 = _duas_raizes()
    mapa = {r1: ("disco", frozenset({"sda"})), r2: ("disco", frozenset({"sdb"}))}
    chamadas = []
    orig_ip = E._iter_particionado
    def espiao(*a, **k):
        chamadas.append(True)
        return orig_ip(*a, **k)
    try:
        def corpo():
            E._iter_particionado = espiao
            try:
                # por NOME
                qn = E.Query(paths=[r1, r2], name_patterns=["*.txt"])
                juntos = _caminhos(qn)
                chamou_nome = bool(chamadas); chamadas.clear()
                E._iter_particionado = orig_ip
                separados = _caminhos(replace(qn, paths=[r1])) | _caminhos(replace(qn, paths=[r2]))
                ok(chamou_nome, "fallback por NOME com 2 discos passa por _iter_particionado")
                ok(juntos == separados and len(juntos) == 6,
                   f"fallback por nome: particionado == raiz a raiz ({len(juntos)} vs {len(separados)})")
                # por CONTEÚDO
                E._iter_particionado = espiao
                qc = E.Query(paths=[r1, r2], content="alfa")
                juntos = _caminhos(qc)
                chamou_cont = bool(chamadas); chamadas.clear()
                E._iter_particionado = orig_ip
                separados = _caminhos(replace(qc, paths=[r1])) | _caminhos(replace(qc, paths=[r2]))
                ok(chamou_cont, "fallback por CONTEÚDO com 2 discos passa por _iter_particionado")
                ok(juntos == separados and len(juntos) == 4,
                   f"fallback por conteúdo: particionado == raiz a raiz ({len(juntos)} vs {len(separados)})")
                ok({os.path.basename(p) for p in juntos} == {"a1.txt", "a2.txt", "b1.txt", "g2.txt"},
                   "os achados de conteúdo são os esperados (alfa nos dois discos)")
            finally:
                E._iter_particionado = orig_ip
        _com_chaves(mapa, lambda: _sem_motores(corpo))
    finally:
        E._iter_particionado = orig_ip
        shutil.rmtree(r1, ignore_errors=True); shutil.rmtree(r2, ignore_errors=True)


# ---------------------------------------------------------------- booleano por grupo de disco
def _bool(q, expr):
    out = []
    B.search_boolean(q, expr, out.append, stats={})
    return {m.path for m in out}


def _roda_booleano(r1, r2, expr, particionado):
    """Roda a expressão com os dois roots no mesmo grupo (particionado=False)
    ou em grupos distintos; devolve (conjunto de caminhos, conjuntos de q.paths
    vistos pelo _eval)."""
    if particionado:
        mapa = {r1: ("disco", frozenset({"sda"})), r2: ("disco", frozenset({"sdb"}))}
    else:
        mapa = {r1: ("disco", frozenset({"sda"})), r2: ("disco", frozenset({"sda"}))}
    vistos = set()
    orig_eval = B._eval
    def espiao(node, q, *a, **k):
        vistos.add(tuple(q.paths))
        return orig_eval(node, q, *a, **k)
    B._eval = espiao
    try:
        res = _com_chaves(mapa, lambda: _bool(E.Query(paths=[r1, r2]), expr))
    finally:
        B._eval = orig_eval
    return res, vistos


def _test_booleano_por_grupo(rotulo):
    r1, r2 = _duas_raizes()
    try:
        esperado = {
            "alfa AND NOT beta": {"a1.txt", "b1.txt", "g2.txt"},
            "alfa OR gama": {"a1.txt", "a2.txt", "g1.txt", "b1.txt", "g2.txt", "n2.log"},
            "(alfa OR gama) AND NOT beta": {"a1.txt", "g1.txt", "b1.txt", "g2.txt"},
        }
        for expr, nomes in esperado.items():
            um, vistos1 = _roda_booleano(r1, r2, expr, particionado=False)
            dois, vistos2 = _roda_booleano(r1, r2, expr, particionado=True)
            ok(um == dois, f"[{rotulo}] '{expr}': por grupo == grupo único ({len(dois)} vs {len(um)})")
            ok({os.path.basename(p) for p in dois} == nomes,
               f"[{rotulo}] '{expr}': achados corretos — deu {sorted(os.path.basename(p) for p in dois)}")
            ok(len(vistos1) == 1, f"[{rotulo}] '{expr}': grupo único → _eval viu 1 conjunto de paths ({len(vistos1)})")
            ok(len(vistos2) == 2 and all(len(t) == 1 for t in vistos2),
               f"[{rotulo}] '{expr}': particionado → _eval viu 2 conjuntos, 1 raiz cada — deu {sorted(vistos2)}")
    finally:
        shutil.rmtree(r1, ignore_errors=True); shutil.rmtree(r2, ignore_errors=True)


def test_booleano_por_grupo_rg():
    if not E.RG:
        print("~pula booleano rg (sem rg)"); return
    _test_booleano_por_grupo("rg")


def test_booleano_por_grupo_fallback():
    _sem_motores(lambda: _test_booleano_por_grupo("python"))


# ---------------------------------------------------------------- contrato público não quebra
def test_assinaturas_publicas():
    sb = list(inspect.signature(B.search_boolean).parameters)
    ok(sb[:3] == ["q", "expr", "on_result"] and
       {"cancel", "on_progress", "on_phase", "stats", "on_event"} <= set(sb),
       f"search_boolean mantém a assinatura pública — deu {sb}")
    se = list(inspect.signature(E.search).parameters)
    ok(se[:2] == ["q", "on_result"] and {"cancel", "on_progress", "stats", "on_event"} <= set(se),
       f"engine.search mantém a assinatura pública — deu {se}")
    q = E.Query(paths=["/tmp"], content="x", max_results=5)
    q2 = E.Query(**q.__dict__)
    ok(q2 == q, "Query(**q.__dict__) reconstrói a query (o boolean depende disto)")
    ok(E.Query(**{**q.__dict__, "content": "y"}).content == "y",
       "Query(**{**q.__dict__, 'content': t}) — o _files_with_term_py faz isto")


TESTES = (test_sys_disks_desce_pelos_slaves, test_sys_disks_ciclo_nao_trava,
          test_sys_disk_um_nome_continua,
          test_rotational_conjunto, test_is_removable_conjunto, test_link_speed_conjunto,
          test_chave_de_disco_conjunto,
          test_grupos_fundem_conjuntos_que_se_cruzam, test_grupo_inacessivel_continua,
          test_rg_threads,
          test_fallback_python_particiona,
          test_booleano_por_grupo_rg, test_booleano_por_grupo_fallback,
          test_assinaturas_publicas)

for fn in TESTES:
    print(f"--- {fn.__name__}")
    try:
        fn()
    except Exception as e:                 # implementação ausente não esconde os outros
        print(f"ERRO  {fn.__name__}: {type(e).__name__}: {e}")
        falhas.append(f"{fn.__name__} ({type(e).__name__})")
print(f"\n{'FALHOU: ' + ', '.join(falhas) if falhas else 'todos os testes passaram'}")
sys.exit(1 if falhas else 0)
