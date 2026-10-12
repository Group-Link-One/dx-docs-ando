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
  let seq = 0;
  window.mountDiagram = async function (def, place) {
    const wrap = document.createElement("div"), bar = document.createElement("div"), view = document.createElement("div");
    wrap.className = "dg"; bar.className = "dgbar"; view.className = "dv";
    const dirRe = /^(\s*(?:flowchart|graph)\s+)(LR|RL|TB|TD|BT)\b/m, hasDir = dirRe.test(def);
    const btn = (label, title, fn) => { const b = document.createElement("button"); b.textContent = label; b.title = title; b.type = "button"; b.onclick = fn; bar.appendChild(b); return b; };
    let cur = def, svg, w, h, x = 0, y = 0, k = 1;
    const apply = () => { svg.style.transform = `translate(${x}px,${y}px) scale(${k})`; };
    const fit = () => {
      const cw = view.clientWidth, full = wrap.classList.contains("full");
      const vh = full ? wrap.clientHeight - bar.offsetHeight : Math.min(Math.max(h * cw / w, 220), innerHeight * 0.75);
      view.style.height = vh + "px";
      k = Math.min(cw / w, vh / h); x = (cw - w * k) / 2; y = (vh - h * k) / 2; apply();
    };
    const zoom = (f, cx, cy) => {
      cx = cx == null ? view.clientWidth / 2 : cx; cy = cy == null ? view.clientHeight / 2 : cy;
      const nk = Math.min(Math.max(k * f, 0.05), 8);
      x = cx - (cx - x) * nk / k; y = cy - (cy - y) * nk / k; k = nk; apply();
    };
    const draw = async () => {
      view.innerHTML = await renderMermaid(cur, "m" + (seq++));
      svg = view.querySelector("svg");
      const vb = svg.viewBox.baseVal;
      w = vb.width; h = vb.height;
      svg.removeAttribute("style");
      svg.setAttribute("width", w); svg.setAttribute("height", h);
      svg.style.transformOrigin = "0 0"; svg.style.maxWidth = "none";
      fit();
    };
    btn("+", "Zoom in", () => zoom(1.3)); btn("\u2212", "Zoom out", () => zoom(1 / 1.3)); btn("Fit", "Fit to view", fit);
    if (hasDir) btn("Rotate", "Flip the layout direction and re-render", async () => {
      cur = cur.replace(dirRe, (_, a, d) => a + (d === "LR" || d === "RL" ? "TB" : "LR"));
      try { await draw(); } catch (e) { /* keep the previous drawing */ }
    });
    const exp = btn("Expand", "Full screen (Esc to close)", () => {
      wrap.classList.toggle("full"); exp.textContent = wrap.classList.contains("full") ? "Close" : "Expand"; fit();
    });
    bar.appendChild(Object.assign(document.createElement("span"), {className: "muted", textContent: "Drag to pan, Ctrl+scroll to zoom"}));
    wrap.append(bar, view);
    place(wrap);
    try { await draw(); } catch (e) { wrap.remove(); throw e; }
    let drag = null;
    view.addEventListener("pointerdown", e => { drag = {x: e.clientX - x, y: e.clientY - y}; view.setPointerCapture(e.pointerId); view.classList.add("grab"); });
    view.addEventListener("pointermove", e => { if (drag) { x = e.clientX - drag.x; y = e.clientY - drag.y; apply(); } });
    view.addEventListener("pointerup", () => { drag = null; view.classList.remove("grab"); });
    view.addEventListener("wheel", e => {
      if (!(e.ctrlKey || e.metaKey || wrap.classList.contains("full"))) return;
      e.preventDefault();
      const r = view.getBoundingClientRect();
      zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
    }, {passive: false});
    addEventListener("keydown", e => { if (e.key === "Escape" && wrap.classList.contains("full")) exp.click(); });
    addEventListener("resize", () => { if (wrap.isConnected) fit(); });
    return wrap;
  };
  document.querySelectorAll("pre > code.language-mermaid").forEach(code => {
    const pre = code.parentElement;
    mountDiagram(code.textContent, w => pre.replaceWith(w)).catch(() => {
      pre.classList.add("mermaid-error");
      pre.title = "Mermaid could not render this block";
    });
  });
  const menu = document.getElementById("menu");
  try { if (localStorage.getItem("ando-nav") === "off") document.body.classList.add("nav-off"); } catch (e) {}
  menu.addEventListener("click", () => {
    const off = document.body.classList.toggle("nav-off");
    try { localStorage.setItem("ando-nav", off ? "off" : "on"); } catch (e) {}
    window.dispatchEvent(new Event("resize"));
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
