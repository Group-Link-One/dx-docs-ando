(function () {
  const BASE = window.MAP, root = document.documentElement.dataset.root || "";
  const NS = "http://www.w3.org/2000/svg";
  const byId = Object.fromEntries(BASE.nodes.map(n => [n.id, n]));
  // the same map with each part (a task, a job) of a service drawn as its own node
  const SPLIT = (() => {
    const nodes = new Map(BASE.nodes.map(n => [n.id, n])), edges = new Map();
    const end = (id, part) => {
      if (!part) return id;
      const pid = id + "#" + part, o = byId[id];
      if (!nodes.has(pid)) { const n = {id: pid, label: part, kind: "part", parent: id, group: o.group, namespace: o.namespace}; nodes.set(pid, n); byId[pid] = n; }
      return pid;
    };
    BASE.edges.forEach(e => e.items.forEach(it => {
      const a = end(e.from, it.from_part), b = end(e.to, it.to_part), k = [a, b, e.via, e.config].join("|");
      if (!edges.has(k)) edges.set(k, {...e, from: a, to: b, items: []});
      edges.get(k).items.push(it);
    }));
    return {...BASE, nodes: [...nodes.values()], edges: [...edges.values()], any: nodes.size > BASE.nodes.length};
  })();
  let M = BASE;
  const stage = document.getElementById("stage"), panel = document.getElementById("panel"), bar = document.getElementById("mapbar");
  const esc = t => String(t == null ? "" : t).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const FAM = {msg: "Topics and queues", call: "Calls", store: "Stores"};
  const isChannel = n => n.kind === "topic" || n.kind === "queue";
  const isHub = n => n.kind === "store";
  const groups = [...new Set(M.nodes.map(n => n.group).filter(Boolean))];
  const hue = g => (groups.indexOf(g) * 67 + 205) % 360;

  const st = {fam: {msg: true, call: false, store: false}, config: false, orphan: true, split: true, sel: null, trace: null, dir: "LR"};
  try { Object.assign(st, JSON.parse(localStorage.getItem("ando-map") || "{}"), {sel: null, trace: null}); } catch (e) {}
  const save = () => { try { localStorage.setItem("ando-map", JSON.stringify({fam: st.fam, config: st.config, orphan: st.orphan, split: st.split, dir: st.dir})); } catch (e) {} };

  function visible() {
    M = st.split && SPLIT.any ? SPLIT : BASE;
    let edges = M.edges.filter(e => st.fam[e.fam] && (st.config || !e.config));
    if (!st.orphan) edges = edges.filter(e => !byId[e.to].orphan);
    if (st.trace && st.trace.how === "near") {
      // one hop, but a topic or queue is followed through to the service on its other side
      const id = st.trace.id, via = new Set();
      edges.forEach(e => { if (e.from === id && isChannel(byId[e.to])) via.add(e.to); if (e.to === id && isChannel(byId[e.from])) via.add(e.from); });
      edges = edges.filter(e => e.from === id || e.to === id || via.has(e.from) || via.has(e.to));
    }
    else if (st.trace) {
      const keep = new Set([st.trace.id]);
      const walk = (start, fwd) => {
        const queue = [start];
        while (queue.length) {
          const id = queue.pop();
          for (const e of edges) {
            const hops = [];
            if ((fwd ? e.from : e.to) === id) hops.push(fwd ? e.to : e.from);
            if (e.both && (fwd ? e.to : e.from) === id) hops.push(fwd ? e.from : e.to);
            for (const nx of hops) {
              if (keep.has(nx)) continue;
              keep.add(nx);
              // a shared store links everything to everything, so a trace ends there
              if (!isHub(byId[nx])) queue.push(nx);
            }
          }
        }
      };
      if (st.trace.how !== "up") walk(st.trace.id, true);
      if (st.trace.how !== "down") walk(st.trace.id, false);
      edges = edges.filter(e => keep.has(e.from) && keep.has(e.to) &&
        (st.trace.how === "both" || !isHub(byId[st.trace.how === "down" ? e.from : e.to]) || e.from === st.trace.id || e.to === st.trace.id));
    }
    const ids = new Set();
    edges.forEach(e => { ids.add(e.from); ids.add(e.to); });
    return {nodes: M.nodes.filter(n => ids.has(n.id)), edges};
  }

  let pos = {};
  try { pos = JSON.parse(localStorage.getItem("ando-map-pos") || "{}"); } catch (e) {}
  // dragged positions only make sense for the exact set of things on screen
  const key = () => [st.dir, st.split, st.fam.msg, st.fam.call, st.fam.store, st.config, st.orphan, st.trace ? st.trace.id + st.trace.how : "", M.nodes.length].join("|");
  const savePos = () => { try { localStorage.setItem("ando-map-pos", JSON.stringify(pos)); } catch (e) {} reset.hidden = !Object.keys(pos[key()] || {}).length; };
  function route(a, b) {
    if (st.dir === "LR") {
      const f = b.x >= a.x ? 1 : -1, sx = a.x + f * a.w / 2, ex = b.x - f * b.w / 2, c = Math.max(40, Math.abs(ex - sx) / 2);
      return {d: `M${sx},${a.y}C${sx + f * c},${a.y} ${ex - f * c},${b.y} ${ex},${b.y}`, mid: {x: (sx + ex) / 2, y: (a.y + b.y) / 2}};
    }
    const f = b.y >= a.y ? 1 : -1, sy = a.y + f * a.h / 2, ey = b.y - f * b.h / 2, c = Math.max(40, Math.abs(ey - sy) / 2);
    return {d: `M${a.x},${sy}C${a.x},${sy + f * c} ${b.x},${ey - f * c} ${b.x},${ey}`, mid: {x: (a.x + b.x) / 2, y: (sy + ey) / 2}};
  }
  function reroute(de) {
    const r = route(drawn.nodes.get(de.e.from), drawn.nodes.get(de.e.to));
    de.hit.setAttribute("d", r.d); de.line.setAttribute("d", r.d);
    if (de.lab) de.lab.setAttribute("transform", `translate(${r.mid.x},${r.mid.y})`);
  }

  const meas = document.createElement("canvas").getContext("2d");
  function size(n) {
    meas.font = (isChannel(n) ? "500 12px " : "600 13px ") + "system-ui,sans-serif";
    const w = Math.max(meas.measureText(n.label).width + (isChannel(n) ? 34 : 30), 80);
    if (n.kind === "part") return {w: Math.ceil(Math.max(w, meas.measureText(byId[n.parent].label).width * 0.8 + 30)), h: 46};
    return {w: Math.ceil(w), h: n.kind === "store" ? 54 : isChannel(n) ? 30 : 40};
  }

  const el = (tag, attrs, parent) => {
    const x = document.createElementNS(NS, tag);
    for (const k in attrs) x.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(x);
    return x;
  };
  let svg, world, drawn = {nodes: new Map(), edges: []}, x = 0, y = 0, k = 1, gw = 1, gh = 1;
  const apply = () => world.setAttribute("transform", `translate(${x},${y}) scale(${k})`);
  function fit(ids) {
    const cw = stage.clientWidth, ch = stage.clientHeight;
    let x0 = 0, y0 = 0, x1 = gw, y1 = gh;
    if (ids && ids.size) {
      x0 = y0 = 1e9; x1 = y1 = -1e9;
      ids.forEach(id => { const d = drawn.nodes.get(id); if (!d) return; x0 = Math.min(x0, d.x - d.w / 2); x1 = Math.max(x1, d.x + d.w / 2); y0 = Math.min(y0, d.y - d.h / 2); y1 = Math.max(y1, d.y + d.h / 2); });
      if (x0 > x1) return;
    }
    const pad = ids ? 120 : 24;
    k = Math.min((cw - pad) / (x1 - x0), (ch - pad) / (y1 - y0), ids ? 1.4 : 1.2);
    x = cw / 2 - (x0 + x1) / 2 * k; y = ch / 2 - (y0 + y1) / 2 * k; apply();
  }
  function zoom(f, cx, cy) {
    cx = cx == null ? stage.clientWidth / 2 : cx; cy = cy == null ? stage.clientHeight / 2 : cy;
    const nk = Math.min(Math.max(k * f, 0.05), 4);
    x = cx - (cx - x) * nk / k; y = cy - (cy - y) * nk / k; k = nk; apply();
  }

  function shape(g, n, w, h) {
    if (n.kind === "store") {
      const r = 8;
      el("path", {class: "body", d: `M${-w / 2},${-h / 2 + r} a${w / 2},${r} 0 0 1 ${w},0 v${h - 2 * r} a${w / 2},${r} 0 0 1 ${-w},0 z`}, g);
      el("path", {class: "rim", d: `M${-w / 2},${-h / 2 + r} a${w / 2},${r} 0 0 0 ${w},0`}, g);
    } else if (isChannel(n)) {
      el("rect", {class: "body", x: -w / 2, y: -h / 2, width: w, height: h, rx: h / 2}, g);
      el("path", {class: "rim", d: `M${w / 2 - 12},${-h / 2 + 3} a7,${h / 2 - 3} 0 0 0 0,${h - 6}`}, g);
    } else {
      el("rect", {class: "body", x: -w / 2, y: -h / 2, width: w, height: h, rx: 6}, g);
      if (n.group && n.kind !== "external" && n.kind !== "unknown") el("rect", {x: -w / 2, y: -h / 2, width: 5, height: h, rx: 2, fill: `hsl(${hue(n.group)} 60% 50%)`}, g);
    }
    if (n.kind === "part") el("text", {class: "cap", x: 3, y: -8, "text-anchor": "middle"}, g).textContent = byId[n.parent].label;
    const t = el("text", {x: n.kind === "store" ? 0 : isChannel(n) ? -4 : 3, y: n.kind === "store" ? 8 : n.kind === "part" ? 11 : 4, "text-anchor": "middle"}, g);
    t.textContent = n.label;
  }

  // each connected part is laid out alone, then the parts are packed into the shape of the screen
  function layout(v) {
    const comp = new Map(v.nodes.map(n => [n.id, n.id]));
    const top = id => { while (comp.get(id) !== id) id = comp.get(id); return id; };
    v.edges.forEach(e => comp.set(top(e.from), top(e.to)));
    const parts = new Map();
    v.nodes.forEach(n => { const t = top(n.id); if (!parts.has(t)) parts.set(t, {nodes: [], edges: []}); parts.get(t).nodes.push(n); });
    v.edges.forEach((e, i) => parts.get(top(e.from)).edges.push([e, i]));
    const boxes = [...parts.values()].map(part => {
      const g = new dagre.graphlib.Graph({multigraph: true});
      g.setGraph({rankdir: st.dir, nodesep: 10, ranksep: 46, edgesep: 6, marginx: 0, marginy: 0, ranker: "network-simplex"});
      g.setDefaultEdgeLabel(() => ({}));
      part.nodes.forEach(n => { const s = size(n); g.setNode(n.id, {width: s.w, height: s.h}); });
      part.edges.forEach(([e, i]) => g.setEdge(e.from, e.to, {}, "e" + i));
      dagre.layout(g);
      return {g, part, w: g.graph().width || 1, h: g.graph().height || 1};
    }).sort((a, b) => b.h - a.h || b.w - a.w);
    const gap = 36, cw = stage.clientWidth || 1200, ch = stage.clientHeight || 800, widest = Math.max(...boxes.map(b => b.w));
    const pack = W => {
      let px = 0, py = 0, row = 0, w = 0;
      const at = boxes.map(b => {
        if (px && px + b.w > W) { px = 0; py += row + gap; row = 0; }
        const o = {x: px, y: py};
        px += b.w + gap; row = Math.max(row, b.h); w = Math.max(w, px - gap);
        return o;
      });
      return {at, w, h: py + row};
    };
    let best = null;
    for (let f = 1; f <= 4; f += 0.25) {
      const t = pack(widest * f), sc = Math.min(cw / t.w, ch / t.h);
      if (!best || sc > best.sc) best = {...t, sc};
    }
    const pos = new Map(), pts = [];
    boxes.forEach((b, j) => {
      const o = best.at[j];
      b.part.nodes.forEach(n => { const p = b.g.node(n.id); pos.set(n.id, {x: p.x + o.x + 20, y: p.y + o.y + 20, width: p.width, height: p.height}); });
      b.part.edges.forEach(([e, i]) => { pts[i] = b.g.edge(e.from, e.to, "e" + i).points.map(q => ({x: q.x + o.x + 20, y: q.y + o.y + 20})); });
    });
    return {pos, pts, w: best.w + 40, h: best.h + 40};
  }

  function draw(keepView) {
    const v = visible();
    const L = layout(v);
    gw = L.w; gh = L.h;
    stage.innerHTML = "";
    svg = el("svg", {width: "100%", height: "100%"}, stage);
    const defs = el("defs", {}, svg);
    ["msg", "call", "store", "hot"].forEach(f => {
      [["a-", "M0,0 L8,4 L0,8 z", 7], ["b-", "M8,0 L0,4 L8,8 z", 1]].forEach(([p, d, rx]) => {
        const m = el("marker", {id: p + f, class: "mk " + f, viewBox: "0 0 8 8", refX: rx, refY: 4, markerWidth: 7, markerHeight: 7, orient: "auto"}, defs);
        el("path", {d}, m);
      });
    });
    world = el("g", {}, svg);
    const eg = el("g", {}, world), ng = el("g", {}, world);
    drawn = {nodes: new Map(), edges: []};
    const moved = pos[key()] || {};
    v.nodes.forEach(n => {
      const p = L.pos.get(n.id), m = moved[n.id];
      drawn.nodes.set(n.id, {x: m ? m[0] : p.x, y: m ? m[1] : p.y, w: p.width, h: p.height});
    });
    v.edges.forEach((e, i) => {
      const pts = L.pts[i];
      let d = `M${pts[0].x},${pts[0].y}`;
      if (pts.length === 2) d += `L${pts[1].x},${pts[1].y}`;
      for (let j = 1; j < pts.length - 1; j++) {
        const end = j === pts.length - 2 ? pts[j + 1] : {x: (pts[j].x + pts[j + 1].x) / 2, y: (pts[j].y + pts[j + 1].y) / 2};
        d += `Q${pts[j].x},${pts[j].y} ${end.x},${end.y}`;
      }
      let mid = pts[Math.floor(pts.length / 2)];
      if (moved[e.from] || moved[e.to]) { const r = route(drawn.nodes.get(e.from), drawn.nodes.get(e.to)); d = r.d; mid = r.mid; }
      const grp = el("g", {class: `edge ${e.fam}${e.config ? " config" : ""}`}, eg);
      const hit = el("path", {class: "hit", d}, grp);
      const line = el("path", {class: "line", d, "marker-end": `url(#a-${e.fam})`}, grp);
      if (e.both) line.setAttribute("marker-start", `url(#b-${e.fam})`);
      const n = e.items.length;
      let lab = null;
      if (e.fam !== "msg" && n > 1) {
        lab = el("g", {class: "elab", transform: `translate(${mid.x},${mid.y})`}, grp);
        el("rect", {x: -11, y: -8, width: 22, height: 16, rx: 8}, lab);
        el("text", {y: 4, "text-anchor": "middle"}, lab).textContent = n;
      }
      grp.addEventListener("click", ev => { ev.stopPropagation(); if (!wasDrag) select({edge: e}); });
      drawn.edges.push({e, grp, line, hit, lab});
    });
    v.nodes.forEach(n => {
      const p = drawn.nodes.get(n.id);
      const grp = el("g", {class: `node k-${n.kind}${n.orphan ? " orphan" : ""}`, transform: `translate(${p.x},${p.y})`}, ng);
      shape(grp, n, p.w, p.h);
      el("title", {}, grp).textContent = n.orphan ? n.label + " (no known consumer)" : n.label;
      grp.addEventListener("click", ev => { ev.stopPropagation(); if (!wasDrag) select({node: n.id}); });
      grp.addEventListener("dblclick", ev => { ev.stopPropagation(); trace(n.id, "near"); });
      grp.addEventListener("pointerdown", ev => { if (!ev.button) { ev.stopPropagation(); wasDrag = false; nodeDrag = {id: n.id, d: p, sx: ev.clientX, sy: ev.clientY, ox: p.x, oy: p.y}; } });
      p.grp = grp;
    });
    if (keepView) apply(); else fit();
    paint(); reset.hidden = !Object.keys(moved).length;
    count.textContent = `${v.nodes.length} nodes, ${v.edges.length} links`;
  }

  function paint() {
    const id = st.sel && st.sel.node, se = st.sel && st.sel.edge;
    const near = new Set();
    drawn.edges.forEach(({e, grp, line}) => {
      const hot = se ? e === se : id && !st.trace ? e.from === id || e.to === id : false;
      if (hot) { near.add(e.from); near.add(e.to); }
      grp.classList.toggle("hot", hot);
      grp.classList.toggle("dim", !st.trace && !!(id || se) && !hot);
      line.setAttribute("marker-end", `url(#a-${hot ? "hot" : e.fam})`);
      if (e.both) line.setAttribute("marker-start", `url(#b-${hot ? "hot" : e.fam})`);
    });
    drawn.nodes.forEach((d, nid) => {
      d.grp.classList.toggle("sel", nid === id);
      d.grp.classList.toggle("dim", !st.trace && !!(id || se) && nid !== id && !near.has(nid));
    });
  }

  const link = id => `<a href="#${encodeURIComponent(id)}" data-id="${esc(id)}">${esc(byId[id].label)}</a>`;
  const evidence = it => (it.evidence || []).map(x => `<code>${esc(x)}</code>`).join("<br>");
  function itemRows(items) {
    return "<table>" + items.map(it => `<tr><td><code>${esc(it.name)}</code>${[it.from_part, it.to_part].filter(Boolean).map(x => ` <span class="badge part">${esc(x)}</span>`).join("")}${it.access ? ` <span class="badge">${it.access}</span>` : ""}` +
      `<span class="badge ${esc(it.confidence)}">${esc(it.confidence)}</span>${it.note ? `<div class="muted">${esc(it.note)}</div>` : ""}<div class="ev">${evidence(it)}</div></td></tr>`).join("") + "</table>";
  }
  function side(title, list, other) {
    if (!list.length) return "";
    return `<h3>${title} (${list.length})</h3>` + list.map(e =>
      `<details><summary>${link(e[other])} <span class="via ${e.fam}">${esc(e.via)}</span>${e.config ? ' <span class="badge config">config</span>' : ""}` +
      `${e.items.length > 1 ? ` <span class="muted">${e.items.length}</span>` : !isChannel(byId[e[other]]) ? ` <code>${esc(e.items[0].name)}</code>` : ""}</summary>${itemRows(e.items)}</details>`).join("");
  }
  function showPanel() {
    const s = st.sel;
    if (!s) { panel.hidden = true; return; }
    let h = '<button class="x" type="button" title="Close">&times;</button>';
    if (s.edge) {
      const e = s.edge;
      h += `<h2>${link(e.from)} ${e.both ? "&harr;" : "&rarr;"} ${link(e.to)}</h2><p><span class="via ${e.fam}">${esc(e.via)}</span>` +
        `${e.config ? ' <span class="badge config">config</span> seen only in deploy env: it proves wiring, not direction.' : ""}</p>${itemRows(e.items)}`;
    } else {
      const n = byId[s.node], all = M.edges;
      const ins = all.filter(e => e.to === n.id || (e.both && e.from === n.id)), outs = all.filter(e => e.from === n.id || (e.both && e.to === n.id));
      const doc = M.docs && M.docs[n.group];
      h += `<h2>${esc(n.label)}</h2><p><span class="badge">${esc(n.kind)}</span>${n.via ? ` <span class="via ${isChannel(n) ? "msg" : "store"}">${esc(n.via)}</span>` : ""}` +
        `${n.orphan ? ' <span class="badge stale">no known consumer</span>' : ""}</p>` +
        `<p class="muted">${[n.parent && "part of " + link(n.parent), n.group && "project " + esc(n.group), n.namespace && "namespace " + esc(n.namespace)].filter(Boolean).join(" · ")}` +
        `${doc ? ` · <a href="${root + doc}">docs</a>` : ""}</p>` +
        `<p class="acts"><button data-t="near" type="button">Focus</button><button data-t="up" type="button">Trace upstream</button><button data-t="down" type="button">Trace downstream</button><button data-t="both" type="button">Both</button></p>` +
        side(isChannel(n) ? "Produced by" : isHub(n) ? "Written by" : "Fed or called by", ins, "from") +
        side(isChannel(n) ? "Consumed by" : isHub(n) ? "Read by" : "Feeds or calls", outs, "to");
    }
    panel.innerHTML = h; panel.hidden = false;
  }

  function select(s, quiet) {
    st.sel = s;
    if (s && s.node && !quiet) history.replaceState(null, "", "#" + encodeURIComponent(s.node));
    if (!s && !quiet) history.replaceState(null, "", location.pathname + location.search);
    paint(); showPanel();
  }
  function trace(id, how) {
    st.trace = id ? {id, how} : null;
    chip.hidden = !id;
    if (id) chip.innerHTML = `${how === "up" ? "Upstream of" : how === "down" ? "Downstream of" : how === "near" ? "Direct links of" : "Everything around"} <b>${esc(byId[id].label)}</b> &times;`;
    draw();
    if (id) select({node: id});
  }
  function go(id, zoomTo) {
    if (!byId[id]) return;
    if (!drawn.nodes.has(id)) {
      const es = (byId[id].kind === "part" ? SPLIT : BASE).edges.filter(e => e.from === id || e.to === id);
      st.trace = null; chip.hidden = true;
      es.forEach(e => { st.fam[e.fam] = true; });
      if (es.length && es.every(e => e.config)) st.config = true;
      if (byId[id].orphan) st.orphan = true;
      st.split = byId[id].kind === "part";
      sync(); draw();
    }
    select({node: id});
    if (zoomTo) {
      const ids = new Set([id]);
      drawn.edges.forEach(({e}) => { if (e.from === id || e.to === id) { ids.add(e.from); ids.add(e.to); } });
      fit(ids);
    }
  }

  const mk = (tag, props, parent) => { const x = Object.assign(document.createElement(tag), props); (parent || bar).appendChild(x); return x; };
  const find = mk("input", {type: "search", placeholder: "Find a service, topic or store", autocomplete: "off"});
  find.setAttribute("list", "mapnodes");
  mk("datalist", {id: "mapnodes", innerHTML: SPLIT.nodes.map(n => `<option value="${esc(n.label)}">${esc(n.kind)}${n.parent ? " of " + esc(n.parent) : n.group ? " / " + esc(n.group) : ""}</option>`).join("")});
  const pick = () => { const q = find.value.trim().toLowerCase(); const n = SPLIT.nodes.find(n => n.label.toLowerCase() === q) || (q && SPLIT.nodes.find(n => n.label.toLowerCase().includes(q))); if (n) { go(n.id, true); find.blur(); } };
  find.addEventListener("change", pick);
  find.addEventListener("keydown", e => { if (e.key === "Enter") pick(); });
  const toggles = [];
  const toggle = (label, cls, title, get, set) => {
    const b = mk("button", {type: "button", className: "tg " + cls, textContent: label, title});
    b.onclick = () => { set(!get()); sync(); save(); draw(); };
    toggles.push(() => b.classList.toggle("on", get()));
  };
  Object.keys(FAM).forEach(f => toggle(FAM[f], f, "Show or hide " + FAM[f].toLowerCase(), () => st.fam[f], v => { st.fam[f] = v; }));
  toggle("Deploy wiring", "cfg", "Links seen only in deploy env (KAFKA_BROKERS, REDIS_CONN, *_URL). They prove wiring, not direction.", () => st.config, v => { st.config = v; });
  toggle("Unconsumed topics", "orph", "Topics that something produces and nothing tracked consumes", () => st.orphan, v => { st.orphan = v; });
  if (SPLIT.any) toggle("Parts", "prt", "Draw each task or job inside a service as its own box, so a topic shows which one owns it", () => st.split, v => { st.split = v; st.sel = null; st.trace = null; chip.hidden = true; panel.hidden = true; });
  const sync = () => toggles.forEach(f => f());
  const chip = mk("button", {type: "button", className: "chip", hidden: true, title: "Back to the whole map"});
  chip.onclick = () => trace(null);
  const right = mk("span", {className: "right"});
  const count = mk("span", {className: "muted"}, right);
  mk("button", {type: "button", textContent: "Rotate", title: "Flip the layout direction", onclick: () => { st.dir = st.dir === "LR" ? "TB" : "LR"; save(); draw(); }}, right);
  mk("button", {type: "button", textContent: "−", title: "Zoom out", onclick: () => zoom(1 / 1.3)}, right);
  mk("button", {type: "button", textContent: "+", title: "Zoom in", onclick: () => zoom(1.3)}, right);
  mk("button", {type: "button", textContent: "Fit", title: "Fit the map. With a node selected: redraw only that node and its direct links, close together", onclick: () => {
    const id = st.sel && st.sel.node;
    if (id && !(st.trace && st.trace.id === id)) trace(id, "near"); else fit();
  }}, right);

  const reset = mk("button", {type: "button", textContent: "Reset layout", title: "Forget the positions you dragged", hidden: true, onclick: () => { delete pos[key()]; savePos(); draw(); }}, right);
  right.insertBefore(reset, right.children[1]);
  let drag = null, wasDrag = false, nodeDrag = null;
  stage.addEventListener("pointerdown", e => { if (!e.button) { drag = {x: e.clientX - x, y: e.clientY - y, sx: e.clientX, sy: e.clientY}; wasDrag = false; } });
  addEventListener("pointermove", e => {
    if (nodeDrag) {
      const dx = e.clientX - nodeDrag.sx, dy = e.clientY - nodeDrag.sy;
      if (Math.abs(dx) + Math.abs(dy) > 4) wasDrag = true;
      if (!wasDrag) return;
      const d = nodeDrag.d;
      d.x = nodeDrag.ox + dx / k; d.y = nodeDrag.oy + dy / k;
      d.grp.setAttribute("transform", `translate(${d.x},${d.y})`);
      drawn.edges.forEach(de => { if (de.e.from === nodeDrag.id || de.e.to === nodeDrag.id) reroute(de); });
      return;
    }
    if (!drag) return;
    if (Math.abs(e.clientX - drag.sx) + Math.abs(e.clientY - drag.sy) > 4) wasDrag = true;
    if (wasDrag) { stage.classList.add("grab"); x = e.clientX - drag.x; y = e.clientY - drag.y; apply(); }
  });
  addEventListener("pointerup", () => {
    if (nodeDrag && wasDrag) { (pos[key()] = pos[key()] || {})[nodeDrag.id] = [Math.round(nodeDrag.d.x), Math.round(nodeDrag.d.y)]; savePos(); }
    nodeDrag = null; drag = null; stage.classList.remove("grab");
  });
  stage.addEventListener("click", () => { if (!wasDrag) select(null); });
  stage.addEventListener("wheel", e => {
    e.preventDefault();
    const r = stage.getBoundingClientRect();
    if (e.ctrlKey || e.metaKey || !e.deltaX && Math.abs(e.deltaY) >= 50) zoom(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)), e.clientX - r.left, e.clientY - r.top);
    else { x -= e.deltaX; y -= e.deltaY; apply(); }
  }, {passive: false});
  panel.addEventListener("click", e => {
    const a = e.target.closest("a[data-id]"), t = e.target.closest("button[data-t]");
    if (a) { e.preventDefault(); go(a.dataset.id, true); }
    else if (t) trace(st.sel.node, t.dataset.t);
    else if (e.target.closest(".x")) select(null);
  });
  addEventListener("keydown", e => {
    if (e.key === "Escape") { if (st.sel) select(null); else if (st.trace) trace(null); }
    if (e.key === "/" && document.activeElement !== find) { e.preventDefault(); find.focus(); }
  });
  addEventListener("resize", () => { if (svg) fit(); });
  addEventListener("hashchange", () => go(decodeURIComponent(location.hash.slice(1)), true));

  sync(); draw(); savePos();
  if (location.hash.length > 1) go(decodeURIComponent(location.hash.slice(1)), true);
})();
