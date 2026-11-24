#!/usr/bin/env python3
"""Auditoria de 23/11/2026 (achados da Vega, conferidos): quatro furos no contrato
"se não consegui olhar, eu aviso" e na fila por disco.

  1. stderr com caminho não-UTF-8 não pode zerar a contabilidade de erros (_reap);
  2. erro GRAVE depois de o funil encher (200 entradas) continua valendo como grave;
  3. exceção no on_espera (ou no cancel) não deixa o ticket preso na fila do disco;
  4. o vigia do cancelamento olha o cancel() ANTES da sonda: sonda travada numa
     montagem morta não segura o Cancelar.
"""
from __future__ import annotations
import os, sys, threading, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lfs"))
import engine as E
import vez as V

falhas = []
def ok(cond, msg):
    print(("ok  " if cond else "FALHOU: ") + "  " + msg)
    if not cond:
        falhas.append(msg)


class ProcMorto:
    returncode = 0
    def poll(self): return 0
    def wait(self, t=None): return 0
    def terminate(self): pass
    def kill(self): pass

# 1. stderr com byte fora do UTF-8
errf = E._arquivo_de_erros()
os.write(errf.fileno(), b"rg: /mnt/x/arq\xff.txt: Permission denied (os error 13)\n"
                        b"rg: /mnt/y/pasta: Permission denied (os error 13)\n")
st = {}
E._reap(ProcMorto(), errf, st)
ok(st.get("denied") == 2, "stderr com nome não-UTF-8: as 2 pastas negadas são contadas (denied=%r)" % st.get("denied"))
ok(any(e["motivo"] == "permission_denied" for e in st.get("incompleto", [])),
   "stderr com nome não-UTF-8: a busca sai marcada como incompleta")

# 2. grave depois do funil cheio
st = {}
for i in range(E._INCOMPLETO_MAX + 50):
    E.anota_incompleto(st, "permission_denied", onde=f"/mnt/d/pasta{i}")
grave, _ = E.resumo_incompleto(st)
ok(not grave, "funil cheio só de avisos leves: não é grave")
E.anota_incompleto(st, "read_error", onde="/mnt/morto", detalhe="x", grave=True)
grave, linhas = E.resumo_incompleto(st)
ok(grave, "erro GRAVE depois do funil cheio continua grave")
ok(any("/mnt/morto" in l for l in linhas), "o erro grave tardio aparece nas linhas do resumo")
motivo_grave = next(iter(E.MOTIVOS_GRAVES))
st = {}
for i in range(E._INCOMPLETO_MAX):
    E.anota_incompleto(st, "permission_denied", onde=f"/mnt/d/pasta{i}")
E.anota_incompleto(st, motivo_grave, onde="/mnt/outro")
ok(E.resumo_incompleto(st)[0], "motivo da lista de graves (%s) depois do funil cheio continua grave" % motivo_grave)

# 3. exceção no on_espera / no cancel não prende a fila
A = V.discos_de(("disco", frozenset({"sda"})))
for nome, kw in (("on_espera", dict(on_espera=lambda *a: (_ for _ in ()).throw(RuntimeError("objeto Qt destruído")))),
                 ("cancel", dict(cancel=lambda: (_ for _ in ()).throw(RuntimeError("cancel quebrou"))))):
    V._reset()
    seg = V.pedir(A, "aba1")
    erro = []
    def tenta():
        try:
            V.pedir(A, "aba2", **kw)
        except Exception as ex:
            erro.append(type(ex).__name__)
    th = threading.Thread(target=tenta); th.start(); th.join(3)
    ok(erro == ["RuntimeError"], f"{nome} que lança: a exceção sobe para quem pediu ({erro})")
    V.soltar(seg)
    tomou = []
    th = threading.Thread(target=lambda: tomou.append(V.pedir(A, "aba3")), daemon=True); th.start(); th.join(2)
    ok(bool(tomou), f"{nome} que lança: o próximo da fila toma o disco (sem ticket preso)")
    if tomou:
        V.soltar(tomou[0])

# 4. vigia: cancel antes da sonda
class ProcVivo:
    def __init__(self): self.terminado = threading.Event()
    def poll(self): return 0 if self.terminado.is_set() else None
    def terminate(self): self.terminado.set()

class SondaTravada:
    def __init__(self): self.solta = threading.Event()
    def tick(self, forca=False): self.solta.wait(30)      # montagem morta: isdir() não volta

p, s = ProcVivo(), SondaTravada(); pedido = []
fim = E._vigia_cancel(p, lambda: bool(pedido), intervalo=0.05, sonda=s)
time.sleep(0.4); pedido.append(1)            # cancela DEPOIS de a sonda já estar pendurada
ok(p.terminado.wait(1.5), "sonda travada em montagem morta: o Cancelar ainda mata o processo")
fim.set(); s.solta.set()

class SondaQuebrada:
    def tick(self, forca=False): raise OSError("stat falhou")
p = ProcVivo(); pedido = []
fim = E._vigia_cancel(p, lambda: bool(pedido), intervalo=0.05, sonda=SondaQuebrada())
time.sleep(0.3); pedido.append(1)
ok(p.terminado.wait(1.5), "sonda que lança exceção não derruba o vigia: cancelar depois ainda funciona")
fim.set()

# 4b. a sonda descobre "é pasta?" pelo /proc, sem tocar o disco
import progresso as P, subprocess, tempfile
if not sys.platform.startswith("linux"):
    print("~pula 4b: /proc/<pid>/fdinfo e O_DIRECTORY so existem no Linux")
else:
  with tempfile.TemporaryDirectory() as d:
      sub = os.path.join(d, "a", "b"); os.makedirs(sub)
      arq = os.path.join(sub, "f.txt"); open(arq, "w").write("x")
      filho = subprocess.Popen([sys.executable, "-c",
          "import os,sys,time; os.open(sys.argv[1], os.O_RDONLY|os.O_DIRECTORY); f=open(sys.argv[2]); print('ok', flush=True); time.sleep(20)",
          os.path.join(d, "a"), arq], stdout=subprocess.PIPE)
      filho.stdout.readline()
      real = os.path.isdir
      def proibido(c):
          raise AssertionError("isdir tocou o disco: " + c)
      os.path.isdir = proibido
      try:
          achou = P.pasta_atual_linux(filho.pid, [d])
      except AssertionError as ex:
          achou = str(ex)
      finally:
          os.path.isdir = real
          filho.kill(); filho.wait()
      ok(achou == sub, "pasta atual sai do fdinfo, sem isdir no disco (arquivo aberto -> a pasta dele): %s" % achou)

# revisão da Vega (23/11): a marca de grave omitido atravessa a fusão como marca,
# e fd fechado na corrida não leva a sonda ao disco
dst = {}
E._funde_stats(dst, {"incompleto_grave_omitido": True}); E._funde_stats(dst, {"incompleto_grave_omitido": True})
ok(dst.get("incompleto_grave_omitido") is True and E.resumo_incompleto(dst)[0],
   "fusão de workers: incompleto_grave_omitido continua True (não vira contador) e a busca é grave")
real = os.path.isdir
os.path.isdir = lambda c: (_ for _ in ()).throw(AssertionError("isdir tocou o disco"))
try:
    r = P._fd_eh_pasta("/proc", os.getpid(), 987654, "/mnt/qualquer")
except AssertionError as ex:
    r = str(ex)
finally:
    os.path.isdir = real
if sys.platform.startswith("linux"):          # a sonda por /proc é só-Linux
    ok(r is False, "fd já fechado (fdinfo sumiu): sem isdir no disco (%r)" % (r,))

print("\n" + ("TUDO OK" if not falhas else "%d FALHA(S)" % len(falhas)))
sys.exit(1 if falhas else 0)
