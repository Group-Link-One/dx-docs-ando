(function () {
  const de = document.documentElement, root = de.dataset.root || "";
  let mermaidP = null;
  window.loadMermaid = function () {
    if (!mermaidP) mermaidP = new Promise((ok, no) => {
      const s = document.createElement("script");
      s.src = de.dataset.mermaid;
      s.onload = () => {
        mermaid.initialize({startOnLoad: false, securityLevel: "strict",
          theme: matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "default"});
        ok(mermaid);
      };
      s.onerror = no;
      document.head.appendChild(s);
    });
    return mermaidP;
  };
  window.renderMermaid = async function (def, id) {
    const m = await loadMermaid();
    try { return (await m.render(id, def)).svg; }
    finally { const x = document.getElementById("d" + id); if (x) x.remove(); }
  };
  const blocks = [...document.querySelectorAll("pre > code.language-mermaid")];
  blocks.forEach(async (code, i) => {
    const pre = code.parentElement;
    try {
      const svg = await renderMermaid(code.textContent, "m" + i);
      const d = document.createElement("div");
      d.className = "diagram";
      d.innerHTML = svg;
      pre.replaceWith(d);
    } catch (e) {
      pre.classList.add("mermaid-error");
      pre.title = "Mermaid could not render this block";
    }
  });
  const q = document.getElementById("q"), box = document.getElementById("results");
  let index = null;
  function load() {
    return new Promise(ok => {
      if (window.SEARCH) return ok();
      const s = document.createElement("script");
      s.src = root + "search.js";
      s.onload = ok;
      document.head.appendChild(s);
    });
  }
  const esc = t => t.replace(/[&<>]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[c]));
  q.addEventListener("input", async () => {
    const terms = q.value.toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) { box.style.display = "none"; return; }
    await load();
    index = index || window.SEARCH.map(p => ({...p, lt: p.title.toLowerCase(), lx: p.text.toLowerCase()}));
    const hits = [];
    for (const p of index) {
      if (!terms.every(t => p.lt.includes(t) || p.lx.includes(t))) continue;
      const score = terms.reduce((n, t) => n + (p.lt.includes(t) ? 10 : 0) + Math.min(p.lx.split(t).length - 1, 9), 0);
      const at = p.lx.indexOf(terms[0]);
      hits.push({p, score, snip: at < 0 ? "" : p.text.slice(Math.max(0, at - 40), at + 80)});
    }
    hits.sort((a, b) => b.score - a.score);
    box.innerHTML = hits.slice(0, 15).map(h =>
      `<a href="${root + h.p.path}">${esc(h.p.title)}<small>${esc(h.snip)}</small></a>`).join("") || "<small>No match</small>";
    box.style.display = "block";
  });
})();
