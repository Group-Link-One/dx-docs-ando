(function () {
  const de = document.documentElement, root = de.dataset.root || "";
  let mermaidP = null;
  window.loadMermaid = function () {
    if (!mermaidP) mermaidP = new Promise((ok, no) => {
      const s = document.createElement("script");
      s.src = de.dataset.mermaid;
      s.onload = () => {
        mermaid.initialize({startOnLoad: false, securityLevel: "strict", flowchart: {htmlLabels: false},
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
  const san = t => t.replace(/[^A-Za-z0-9_]/g, "_");
  const norm = t => t.replace(/\s+/g, " ").trim();
  function copyText(t) {
    if (navigator.clipboard && isSecureContext) return navigator.clipboard.writeText(t);
    const ta = Object.assign(document.createElement("textarea"), {value: t});
    ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } finally { ta.remove(); }
    return Promise.resolve();
  }
  function download(name, blob) {
    const a = Object.assign(document.createElement("a"), {href: URL.createObjectURL(blob), download: name});
    a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  function bridgesReady() {
    if (window.BRIDGES) return Promise.resolve();
    return new Promise(ok => {
      const s = document.createElement("script");
      s.src = root + "bridges-data.js"; s.onload = ok; s.onerror = ok;
      document.head.appendChild(s);
    });
  }
  async function explorerHref(label, id) {
    await bridgesReady();
    if (!window.BRIDGES) return null;
    const n = BRIDGES.nodes.find(n => n.id === label || san(n.id) === id);
    return n ? root + "explorer.html#" + encodeURIComponent(n.id) : null;
  }
  window.mountDiagram = async function (def, place, opts) {
    opts = opts || {};
    const resolve = opts.resolve || explorerHref;
    const wrap = document.createElement("div"), bar = document.createElement("div"), view = document.createElement("div");
    wrap.className = "dg"; bar.className = "dgbar"; view.className = "dv";
    bar.title = "Drag to pan. Ctrl+scroll to zoom. Click a node to highlight its links. Double-click to focus.";
    const dirRe = /^(\s*(?:flowchart|graph)\s+)(LR|RL|TB|TD|BT)\b/m, isFlow = dirRe.test(def);
    const btn = (label, title, fn) => { const b = document.createElement("button"); b.textContent = label; b.title = title; b.type = "button"; b.onclick = fn; bar.appendChild(b); return b; };
    let cur = def, svg, w, h, x = 0, y = 0, k = 1, model = null, selId = null, moved = 0;
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
    const focusOn = ids => {
      const vr = view.getBoundingClientRect();
      let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
      model.nodes.filter(n => ids.has(n.id)).forEach(n => {
        const r = n.el.getBoundingClientRect();
        x0 = Math.min(x0, (r.left - vr.left - x) / k); y0 = Math.min(y0, (r.top - vr.top - y) / k);
        x1 = Math.max(x1, (r.right - vr.left - x) / k); y1 = Math.max(y1, (r.bottom - vr.top - y) / k);
      });
      if (x0 > x1) return;
      const bw = x1 - x0, bh = y1 - y0, cw = view.clientWidth, vh = view.clientHeight;
      k = Math.min(cw / (bw * 1.3), vh / (bh * 1.3), 3);
      x = cw / 2 - (x0 + bw / 2) * k; y = vh / 2 - (y0 + bh / 2) * k; apply();
    };
    const dimTo = (nodeOk, edgeOk) => {
      model.nodes.forEach(n => n.el.classList.toggle("dim", !nodeOk(n)));
      model.edges.forEach(e => { const off = !edgeOk(e); e.el.classList.toggle("dim", off); if (e.label) e.label.classList.toggle("dim", off); });
    };
    const neigh = id => {
      const s = new Set([id]);
      model.edges.forEach(e => { if (e.src === id) s.add(e.dst); if (e.dst === id) s.add(e.src); });
      return s;
    };
    const openA = Object.assign(document.createElement("a"), {className: "dgopen", hidden: true});
    const find = Object.assign(document.createElement("input"), {type: "search", placeholder: "Find node"});
    const select = id => {
      selId = id; openA.hidden = true;
      if (!id) { dimTo(() => true, () => true); return; }
      const ns = neigh(id);
      dimTo(n => ns.has(n.id), e => e.src === id || e.dst === id);
      const n = model.nodes.find(n => n.id === id);
      Promise.resolve(resolve(n.label, id)).then(href => {
        if (href && selId === id) { openA.href = href; openA.textContent = "Open in explorer: " + n.label; openA.hidden = false; }
      });
    };
    const bind = () => {
      const nodes = [...svg.querySelectorAll("g.node")].map(el => {
        const m = /^flowchart-(.+)-\d+$/.exec(el.id);
        return m && {el, id: m[1], label: norm(el.textContent)};
      }).filter(Boolean);
      const labels = svg.querySelectorAll("g.edgeLabel");
      const ids = new Set(nodes.map(n => n.id));
      const ends = el => {
        const c = el.getAttribute("class") || "", ls = /LS-(\S+)/.exec(c), le = /LE-(\S+)/.exec(c);
        if (ls && le) return [ls[1], le[1]];
        const rest = (/^L_(.+)_\d+$/.exec(el.id) || [])[1] || "";
        for (const id of ids) if (rest.startsWith(id + "_") && ids.has(rest.slice(id.length + 1))) return [id, rest.slice(id.length + 1)];
        return [];
      };
      const edges = [...svg.querySelectorAll("path.flowchart-link")].map((el, i) => {
        const [src, dst] = ends(el);
        return {el, src, dst, label: labels[i]};
      });
      model = {nodes, edges}; selId = null; find.value = "";
    };
    const draw = async () => {
      view.innerHTML = await renderMermaid(cur, "m" + (seq++));
      svg = view.querySelector("svg");
      const vb = svg.viewBox.baseVal;
      w = vb.width; h = vb.height;
      svg.removeAttribute("style");
      svg.setAttribute("width", w); svg.setAttribute("height", h);
      svg.style.transformOrigin = "0 0"; svg.style.maxWidth = "none";
      if (isFlow) bind();
      fit();
    };
    const svgText = () => {
      const c = svg.cloneNode(true);
      c.removeAttribute("style"); c.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      c.querySelectorAll(".dim").forEach(n => n.classList.remove("dim"));
      return new XMLSerializer().serializeToString(c);
    };
    const flash = (b, t) => { const o = b.dataset.t || b.textContent; b.dataset.t = o; b.textContent = t; setTimeout(() => { b.textContent = o; }, 1500); };
    btn("+", "Zoom in", () => zoom(1.3)); btn("−", "Zoom out", () => zoom(1 / 1.3)); btn("Fit", "Fit to view", () => { fit(); });
    if (isFlow) btn("Rotate", "Flip the layout direction and re-render", async () => {
      cur = cur.replace(dirRe, (_, a, d) => a + (d === "LR" || d === "RL" ? "TB" : "LR"));
      try { await draw(); } catch (e) { /* keep the previous drawing */ }
    });
    const exp = btn("Expand", "Full screen (Esc to close)", () => {
      wrap.classList.toggle("full"); exp.textContent = wrap.classList.contains("full") ? "Close" : "Expand"; fit();
    });
    if (isFlow) {
      bar.appendChild(find); bar.appendChild(openA);
      find.addEventListener("input", () => {
        const q = find.value.trim().toLowerCase();
        if (!q) { select(selId); return; }
        const hit = id => (model.nodes.find(n => n.id === id) || {label: ""}).label.toLowerCase().includes(q);
        dimTo(n => hit(n.id), e => hit(e.src) || hit(e.dst));
      });
      find.addEventListener("keydown", e => {
        if (e.key !== "Enter") return;
        const q = find.value.trim().toLowerCase();
        focusOn(new Set(model.nodes.filter(n => n.label.toLowerCase().includes(q)).map(n => n.id)));
      });
    }
    const right = document.createElement("span");
    right.className = "dgright";
    bar.appendChild(right);
    const rbtn = (label, title, fn) => { const b = btn(label, title, () => fn(b)); right.appendChild(b); };
    rbtn("SVG", "Download as SVG", () => download("diagram.svg", new Blob([svgText()], {type: "image/svg+xml"})));
    rbtn("PNG", "Download as PNG", b => {
      const img = new Image(), c = document.createElement("canvas");
      c.width = w * 2; c.height = h * 2;
      img.onload = () => {
        try {
          const g = c.getContext("2d");
          g.fillStyle = getComputedStyle(document.body).backgroundColor; g.fillRect(0, 0, c.width, c.height);
          g.drawImage(img, 0, 0, c.width, c.height);
          c.toBlob(bl => download("diagram.png", bl));
        } catch (e) { flash(b, "PNG failed"); }
      };
      img.onerror = () => flash(b, "PNG failed");
      img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svgText());
    });
    rbtn("Copy source", "Copy the Mermaid source", b => copyText(cur).then(() => flash(b, "Copied")));
    wrap.append(bar, view);
    place(wrap);
    try { await draw(); } catch (e) { wrap.remove(); throw e; }
    const nodeAt = e => { const g = e.target.closest && e.target.closest("g.node"); return g && model && model.nodes.find(n => n.el === g); };
    let drag = null;
    view.addEventListener("pointerdown", e => {
      if (e.button) return;
      drag = {x: e.clientX - x, y: e.clientY - y, sx: e.clientX, sy: e.clientY}; moved = 0;
    });
    addEventListener("pointermove", e => {
      if (!drag) return;
      moved = Math.max(moved, Math.abs(e.clientX - drag.sx) + Math.abs(e.clientY - drag.sy));
      if (moved > 4) { view.classList.add("grab"); x = e.clientX - drag.x; y = e.clientY - drag.y; apply(); }
    });
    addEventListener("pointerup", () => { drag = null; view.classList.remove("grab"); });
    view.addEventListener("click", e => {
      if (moved > 4 || e.detail > 1 || !isFlow) return;
      const n = nodeAt(e);
      select(n && n.id !== selId ? n.id : null);
    });
    view.addEventListener("dblclick", e => {
      if (!isFlow) { fit(); return; }
      const n = nodeAt(e);
      if (!n) { select(null); fit(); return; }
      select(n.id); focusOn(neigh(n.id));
    });
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
  document.querySelectorAll("main h1[id],main h2[id],main h3[id],main h4[id]").forEach(h => {
    const a = Object.assign(document.createElement("a"), {className: "hl", href: "#" + h.id, textContent: "#", title: "Copy link"});
    a.addEventListener("click", e => {
      e.preventDefault();
      history.replaceState(null, "", "#" + h.id);
      copyText(location.href.split("#")[0] + "#" + h.id).then(() => { a.textContent = "copied"; setTimeout(() => { a.textContent = "#"; }, 1200); });
    });
    h.appendChild(a);
  });
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
