// Donation channels. Fill in each one as the account is created; a channel left
// empty is hidden, and the whole section stays hidden while every channel is empty.
const DOACAO = {
  githubSponsors: "Thiopental1976", // github.com/sponsors/<this>
  koFi: "sombrerofilesearch",       // ko-fi.com/<this>
  liberapay: "sombrerofilesearch",  // liberapay.com/<this>
  pix: {
    chave: "30da3f55-b299-42c9-966a-26389819c345",  // RANDOM key (chave aleatória), never CPF/phone/e-mail on a public page
    nome: "RODRIGO ROCHA DE TOLEDO",  // receiver name as the bank shows it, up to 25 characters, no accents
    cidade: "PALMITOS",  // up to 15 characters, no accents, e.g. "SAO JOSE CEDRO"
  },
};

// Static Pix "copia e cola" (BR Code, EMV QRCPS) with CRC16-CCITT (poly 0x1021, init 0xFFFF).
function brCode({ chave, nome, cidade }) {
  const f = (id, v) => id + String(v.length).padStart(2, "0") + v;
  const limpa = (s, n) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase().slice(0, n);
  const conta = f("00", "br.gov.bcb.pix") + f("01", chave);
  let p = f("00", "01") + f("26", conta) + f("52", "0000") + f("53", "986") + f("58", "BR") +
          f("59", limpa(nome, 25)) + f("60", limpa(cidade, 15)) + f("62", f("05", "***")) + "6304";
  let crc = 0xFFFF;
  for (const ch of p) {
    crc ^= ch.charCodeAt(0) << 8;
    for (let i = 0; i < 8; i++) crc = (crc & 0x8000) ? ((crc << 1) ^ 0x1021) & 0xFFFF : (crc << 1) & 0xFFFF;
  }
  return p + crc.toString(16).toUpperCase().padStart(4, "0");
}

(() => {
  const sec = document.querySelector("section.donate");
  if (!sec) return;
  const links = {
    sponsors: DOACAO.githubSponsors && `https://github.com/sponsors/${DOACAO.githubSponsors}`,
    kofi: DOACAO.koFi && `https://ko-fi.com/${DOACAO.koFi}`,
    liberapay: DOACAO.liberapay && `https://liberapay.com/${DOACAO.liberapay}/donate`,
  };
  let algum = false;
  for (const [canal, url] of Object.entries(links)) {
    const card = sec.querySelector(`[data-canal="${canal}"]`);
    if (!card) continue;
    if (url) { card.querySelector("a").href = url; card.hidden = false; algum = true; }
  }
  const px = DOACAO.pix, card = sec.querySelector('[data-canal="pix"]');
  if (card && px.chave && px.nome && px.cidade) {
    const code = brCode(px);
    card.querySelector("[data-pix-code]").value = code;
    const qr = card.querySelector("[data-pix-qr]");
    if (window.qrcode && qr) {
      const q = qrcode(0, "M"); q.addData(code); q.make();
      qr.innerHTML = q.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
    }
    card.querySelector("[data-pix-copy]").addEventListener("click", async (e) => {
      const b = e.currentTarget, campo = card.querySelector("[data-pix-code]");
      try { await navigator.clipboard.writeText(code); } catch (_) { campo.select(); }
      const txt = b.textContent; b.textContent = b.dataset.ok; setTimeout(() => (b.textContent = txt), 1800);
    });
    card.hidden = false; algum = true;
  }
  const grade = sec.querySelector(".give");
  if (grade) grade.classList.toggle("impar", grade.querySelectorAll(":scope > :not([hidden])").length % 2 === 1);
  sec.hidden = !algum;
  document.querySelectorAll("[data-donate-link]").forEach(a => (a.hidden = !algum));
})();
