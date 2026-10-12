(function () {
  const B = window.BRIDGES, byId = Object.fromEntries(B.nodes.map(n => [n.id, n]));
  const sel = document.getElementById("sel"), out = document.getElementById("out");
  document.getElementById("nodes").innerHTML = B.nodes.map(n => `<option value="${n.id}">${n.kind}${n.project ? " / " + n.project : ""}</option>`).join("");
  const esc = t => String(t == null ? "" : t).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const link = id => `<a href="#${encodeURIComponent(id)}">${esc(id)}</a>`;
  function rows(edges, side) {
    if (!edges.length) return '<p class="muted">None.</p>';
    return "<table><tr><th>" + (side === "from" ? "Caller" : "Target") + "</th><th>Via</th><th>Name</th><th>Confidence</th><th>Evidence</th></tr>" +
      edges.map(e => `<tr><td>${link(side === "from" ? e.from : e.to)}</td><td>${esc(e.via)}</td><td><code>${esc(e.name)}</code></td>` +
        `<td><span class="badge ${esc(e.confidence)}">${esc(e.confidence)}</span></td><td>${(e.evidence || []).map(esc).join("<br>")}</td></tr>`).join("") + "</table>";
  }
  function graph(id, ups, downs, into) {
    const ids = [...new Set([id, ...ups.map(e => e.from), ...downs.map(e => e.to)])].slice(0, 30), idx = {};
    ids.forEach((n, i) => idx[n] = i);
    const lines = ["flowchart LR"];
    ids.forEach((n, i) => lines.push(`  n${i}["${n.replace(/"/g, "'")}"]`));
    [...ups, ...downs].forEach(e => {
      if (e.from in idx && e.to in idx) lines.push(`  n${idx[e.from]} -->|${String(e.via).replace(/[|"]/g, "")}| n${idx[e.to]}`);
    });
    into.innerHTML = ids.length === 30 ? '<p class="muted">Graph capped at 30 nodes. The tables list everything.</p>' : "";
    return mountDiagram(lines.join("\n"), w => into.prepend(w)).catch(() => {});
  }
  async function show(id) {
    const n = byId[id];
    if (!n) { out.innerHTML = '<p class="muted">Pick a service, workload, topic or external system.</p>'; return; }
    const ups = B.edges.filter(e => e.to === id), downs = B.edges.filter(e => e.from === id);
    out.innerHTML = `<h2>${esc(id)} <span class="badge">${esc(n.kind)}</span></h2>` +
      `<p class="muted">${[n.project && "project " + n.project, n.namespace && "namespace " + n.namespace].filter(Boolean).map(esc).join(" · ")}</p>` +
      `<div class="cols"><div><h3>Who calls or feeds it (${ups.length})</h3>${rows(ups, "from")}</div>` +
      `<div><h3>What it calls or feeds (${downs.length})</h3>${rows(downs, "to")}</div></div><div id="g"></div>`;
    graph(id, ups, downs, document.getElementById("g"));
  }
  function fromHash() { const id = decodeURIComponent(location.hash.slice(1)); sel.value = id; show(id); }
  sel.addEventListener("focus", () => { sel.dataset.prev = sel.value; sel.placeholder = sel.value || "Type a node name"; sel.value = ""; });
  sel.addEventListener("blur", () => { if (!sel.value) sel.value = sel.dataset.prev || ""; });
  sel.addEventListener("input", () => { if (byId[sel.value]) { location.hash = encodeURIComponent(sel.value); sel.blur(); } });
  addEventListener("hashchange", fromHash);
  fromHash();
})();
