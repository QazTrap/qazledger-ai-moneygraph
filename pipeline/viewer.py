from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


HTML_TEMPLATE = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>QazLedger MoneyGraph Viewer</title>
<style>
:root{
  --bg:#f7f8fa;
  --panel:#ffffff;
  --text:#16181d;
  --muted:#667085;
  --line:#d9dee7;
  --accent:#2563eb;
}
*{box-sizing:border-box}
body{
  margin:0;
  font-family:Inter,Segoe UI,Arial,sans-serif;
  background:var(--bg);
  color:var(--text);
}
.wrap{max-width:1500px;margin:0 auto;padding:20px}
.header{
  display:flex;justify-content:space-between;align-items:flex-start;gap:16px;flex-wrap:wrap
}
h1{margin:0 0 4px;font-size:24px}
.sub{color:var(--muted);margin-bottom:16px}
.lang-switch{
  display:flex;gap:4px;background:var(--panel);border:1px solid var(--line);
  padding:4px;border-radius:10px
}
.lang-btn{
  padding:7px 11px;border:0;border-radius:7px;background:transparent;
  color:#475467;font-weight:700;cursor:pointer
}
.lang-btn.active{background:var(--accent);color:#fff}
.toolbar{
  display:flex;gap:10px;flex-wrap:wrap;align-items:center;
  background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px;
}
input{
  min-width:320px;flex:1;padding:11px 12px;border:1px solid var(--line);
  border-radius:10px;font-size:15px;
}
button{
  padding:11px 16px;border:0;border-radius:10px;background:var(--accent);
  color:#fff;font-weight:600;cursor:pointer;
}
button.secondary{background:#eef2f7;color:#1f2937;border:1px solid var(--line)}
.status{color:var(--muted);font-size:13px}
.grid{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-top:16px}
.card{
  background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;
  min-width:0;
}
.card h2{font-size:16px;margin:0 0 10px}
#graphWrap{overflow:auto;min-height:700px}
svg{display:block;width:100%;min-width:820px;height:700px;background:#fff;border-radius:10px}
.node{cursor:pointer}
.node text{pointer-events:none;font-size:11px;font-weight:600;fill:#111827}
.edge-label{font-size:9px;fill:#6b7280}
.metric{display:grid;grid-template-columns:1fr auto;gap:6px;border-bottom:1px solid #eef1f5;padding:7px 0}
.metric:last-child{border-bottom:0}
.metric span:first-child{color:var(--muted)}
.evidence{margin-top:10px;padding:10px;background:#f8fafc;border-radius:10px;line-height:1.45}
.legend{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 12px}
.legend-item{display:flex;align-items:center;gap:5px;font-size:12px;color:#475467}
.dot{width:11px;height:11px;border-radius:50%;display:inline-block}
.list{max-height:250px;overflow:auto;border-top:1px solid #eef1f5}
.row{
  display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;
  padding:8px 0;border-bottom:1px solid #eef1f5;font-size:12px;
}
.gidbtn{background:none;color:#1d4ed8;padding:0;border:0;text-align:left;font-weight:600;cursor:pointer}
.small{font-size:12px;color:var(--muted)}
.badge{display:inline-block;padding:3px 8px;border-radius:999px;background:#eef2ff;font-size:12px}
@media(max-width:980px){
  .grid{grid-template-columns:1fr}
  input{min-width:220px}
}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div>
      <h1>QazLedger MoneyGraph Viewer</h1>
      <div class="sub" id="subtitle"></div>
    </div>
    <div class="lang-switch" aria-label="Language">
      <button class="lang-btn" id="langRu" type="button">RU</button>
      <button class="lang-btn" id="langEn" type="button">EN</button>
    </div>
  </div>

  <div class="toolbar">
    <input id="gidInput" inputmode="numeric">
    <button id="searchBtn"></button>
    <button id="topBtn" class="secondary"></button>
    <span id="status" class="status"></span>
  </div>

  <div class="legend" id="legend"></div>

  <div class="grid">
    <div class="card">
      <h2 id="graphTitle"></h2>
      <div id="graphWrap">
        <svg id="graph" viewBox="0 0 1100 700" role="img">
          <defs>
            <marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto" markerUnits="strokeWidth">
              <path d="M0,0 L0,6 L9,3 z" fill="#98a2b3"></path>
            </marker>
          </defs>
          <g id="edgesLayer"></g>
          <g id="nodesLayer"></g>
        </svg>
      </div>
      <div class="small" id="graphNote"></div>
    </div>

    <div class="card">
      <h2 id="selectedHeading"></h2>
      <div id="details"></div>

      <h2 id="incomingHeading" style="margin-top:18px"></h2>
      <div id="incoming" class="list"></div>

      <h2 id="outgoingHeading" style="margin-top:18px"></h2>
      <div id="outgoing" class="list"></div>
    </div>
  </div>
</div>

<script>
const NODES = __NODES_JSON__;
const EDGES = __EDGES_JSON__;
const TOP_GIDS = __TOP_GIDS_JSON__;

const ROLE_STYLE = {
  coordinator:  {fill:"#7c3aed"},
  consolidator: {fill:"#2563eb"},
  distributor:  {fill:"#ea580c"},
  transit:      {fill:"#0891b2"},
  terminal:     {fill:"#16a34a"},
  peripheral:   {fill:"#94a3b8"}
};

const ROLE_NAMES = {
  ru: {
    coordinator:"Координатор",
    consolidator:"Консолидатор",
    distributor:"Распределитель",
    transit:"Транзит",
    terminal:"Конечный получатель",
    peripheral:"Периферия",
    unknown:"Неизвестно"
  },
  en: {
    coordinator:"Coordinator",
    consolidator:"Consolidator",
    distributor:"Distributor",
    transit:"Transit",
    terminal:"Terminal",
    peripheral:"Peripheral",
    unknown:"Unknown"
  }
};

const T = {
  ru: {
    subtitle:"Поиск GID, роль, кластер, приоритет и прямые транзакционные связи.",
    placeholder:"Введите полный GID",
    find:"Найти GID",
    top:"Открыть узел №1 из Top-20",
    network:"Сеть",
    selectedNode:"Выбранный узел",
    choose:"Выберите GID для просмотра.",
    incoming:"Входящие связи",
    outgoing:"Исходящие связи",
    role:"Роль",
    roleScore:"Уверенность в роли",
    priorityScore:"Приоритет проверки",
    cluster:"Кластер",
    evidence:"Обоснование",
    noLinks:"В предоставленном графе прямых связей нет.",
    sameCluster:"тот же кластер, что и выбранный",
    selected:"ВЫБРАН",
    tx:"транз.",
    found:"Найден",
    notFound:"GID не найден в nodes_roles.csv",
    directAround:"Прямые связи узла",
    showing:"Показано",
    neighbors:"соседних узлов",
    directLinks:"прямых связей",
    hiddenPrefix:"Ещё",
    hiddenSuffix:"связей с меньшим объёмом скрыты на схеме для читаемости, но остаются в списке справа.",
    graphAria:"Транзакционная сеть вокруг выбранного GID"
  },
  en: {
    subtitle:"Search a GID, inspect its role, cluster, priority and direct transaction links.",
    placeholder:"Enter full GID",
    find:"Find GID",
    top:"Open #1 Top-20 Node",
    network:"Network",
    selectedNode:"Selected node",
    choose:"Choose a GID to inspect.",
    incoming:"Incoming links",
    outgoing:"Outgoing links",
    role:"Role",
    roleScore:"Role score",
    priorityScore:"Priority score",
    cluster:"Cluster",
    evidence:"Evidence",
    noLinks:"No direct links in the provided graph.",
    sameCluster:"same cluster as selected",
    selected:"SELECTED",
    tx:"tx",
    found:"Found",
    notFound:"GID not found in nodes_roles.csv",
    directAround:"Direct network around",
    showing:"Showing",
    neighbors:"neighboring nodes",
    directLinks:"direct links",
    hiddenPrefix:"",
    hiddenSuffix:"lower-volume links are omitted from the diagram for readability; they remain listed on the right.",
    graphAria:"Transaction network around selected GID"
  }
};

const nodeMap = new Map(NODES.map(n => [n.gid, n]));
const incomingMap = new Map();
const outgoingMap = new Map();

for (const e of EDGES) {
  if (!outgoingMap.has(e.src)) outgoingMap.set(e.src, []);
  if (!incomingMap.has(e.dst)) incomingMap.set(e.dst, []);
  outgoingMap.get(e.src).push(e);
  incomingMap.get(e.dst).push(e);
}

for (const arr of incomingMap.values()) arr.sort((a,b)=>b.sum_kzt-a.sum_kzt);
for (const arr of outgoingMap.values()) arr.sort((a,b)=>b.sum_kzt-a.sum_kzt);

const $ = id => document.getElementById(id);
const svgNS = "http://www.w3.org/2000/svg";
let currentGid = null;
let currentLang = localStorage.getItem("moneygraph_lang") || "ru";
if (!["ru","en"].includes(currentLang)) currentLang = "ru";

function tr(key) {
  return T[currentLang][key] || key;
}

function roleName(role, withCode=false) {
  const name = (ROLE_NAMES[currentLang] || ROLE_NAMES.en)[role] || role;
  if (currentLang === "ru" && withCode) return `${name} (${role})`;
  return name;
}

function shortRoleName(role) {
  if (currentLang === "en") return role;
  const m = {
    coordinator:"координатор",
    consolidator:"консолид.",
    distributor:"распред.",
    transit:"транзит",
    terminal:"конечный",
    peripheral:"периферия"
  };
  return m[role] || role;
}

function money(v) {
  const locale = currentLang === "ru" ? "ru-RU" : "en-US";
  const suffix = currentLang === "ru" ? " ₸" : " KZT";
  return new Intl.NumberFormat(locale, {maximumFractionDigits:0}).format(Number(v || 0)) + suffix;
}

function compactMoney(v) {
  const locale = currentLang === "ru" ? "ru-RU" : "en-US";
  return new Intl.NumberFormat(locale,{notation:"compact",maximumFractionDigits:1}).format(v);
}

function shortGid(gid) {
  const s = String(gid);
  return "…" + s.slice(-6);
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, ch => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[ch]));
}

function roleColor(role) {
  return (ROLE_STYLE[role] || {fill:"#64748b"}).fill;
}

function evidenceForLanguage(raw) {
  const s = String(raw ?? "");
  if (currentLang === "ru") return s;

  let m;
  if ((m = s.match(/^Высокая центральность: in=(\d+), out=(\d+); связывает несколько направлений потока\.$/))) {
    return `High centrality: in=${m[1]}, out=${m[2]}; connects multiple flow directions.`;
  }
  if ((m = s.match(/^Получает средства от (\d+) узлов; входящий поток (.+) KZT\.$/))) {
    return `Receives funds from ${m[1]} nodes; incoming flow ${m[2]} KZT.`;
  }
  if ((m = s.match(/^Распределяет средства на (\d+) получателей; исходящий поток (.+) KZT\.$/))) {
    return `Distributes funds to ${m[1]} recipients; outgoing flow ${m[2]} KZT.`;
  }
  if ((m = s.match(/^Сквозной поток: out\/in=([0-9.]+); in=(.+), out=(.+) KZT\.$/))) {
    return `Pass-through flow: out/in=${m[1]}; in=${m[2]}, out=${m[3]} KZT.`;
  }
  if ((m = s.match(/^Средства в основном остаются: in=(.+), out=(.+) KZT; depth=(\d+)\.$/))) {
    return `Most funds are retained: in=${m[1]}, out=${m[2]} KZT; depth=${m[3]}.`;
  }
  if (s === "Периферия: depth=4 — граница выгрузки, поэтому отсутствие исходящих не доказывает terminal.") {
    return "Peripheral: depth=4 is the extraction boundary, so missing outgoing links do not prove a terminal role.";
  }
  if ((m = s.match(/^Выраженной роли нет: in_degree=(\d+), out_degree=(\d+)\.$/))) {
    return `No strong functional role: in_degree=${m[1]}, out_degree=${m[2]}.`;
  }
  return s;
}

function buildLegend() {
  $("legend").innerHTML = Object.keys(ROLE_STYLE)
    .map(role => `<div class="legend-item"><span class="dot" style="background:${ROLE_STYLE[role].fill}"></span>${esc(roleName(role, currentLang === "ru"))}</div>`)
    .join("") + `<div class="legend-item"><span style="width:14px;height:14px;border:3px solid #111827;border-radius:50%;display:inline-block"></span>${esc(tr("sameCluster"))}</div>`;
}

function setStatus(msg) {
  $("status").textContent = msg;
}

function renderList(containerId, arr, direction) {
  const el = $(containerId);
  if (!arr || !arr.length) {
    el.innerHTML = `<div class="small" style="padding:8px 0">${esc(tr("noLinks"))}</div>`;
    return;
  }

  el.innerHTML = arr.slice(0, 30).map(e => {
    const other = direction === "in" ? e.src : e.dst;
    const n = nodeMap.get(other);
    return `<div class="row">
      <div>
        <button class="gidbtn" data-gid="${esc(other)}">${esc(other)}</button>
        <div class="small">${n ? esc(roleName(n.role, currentLang === "ru")) + " · " + esc(tr("cluster").toLowerCase()) + " " + esc(n.cluster_id) : ""}</div>
      </div>
      <div style="text-align:right">
        <strong>${esc(money(e.sum_kzt))}</strong>
        <div class="small">${esc(e.n_tx)} ${esc(tr("tx"))}</div>
      </div>
    </div>`;
  }).join("");

  el.querySelectorAll(".gidbtn").forEach(btn => {
    btn.addEventListener("click", () => selectGid(btn.dataset.gid));
  });
}

function renderDetails(n) {
  $("details").innerHTML = `
    <div class="metric"><span>GID</span><strong>${esc(n.gid)}</strong></div>
    <div class="metric"><span>${esc(tr("role"))}</span><strong><span class="badge">${esc(roleName(n.role, currentLang === "ru"))}</span></strong></div>
    <div class="metric"><span>${esc(tr("roleScore"))}</span><strong>${Number(n.role_score).toFixed(4)}</strong></div>
    <div class="metric"><span>${esc(tr("priorityScore"))}</span><strong>${Number(n.priority_score).toFixed(4)}</strong></div>
    <div class="metric"><span>${esc(tr("cluster"))}</span><strong>${esc(n.cluster_id)}</strong></div>
    <div class="evidence"><strong>${esc(tr("evidence"))}</strong><br>${esc(evidenceForLanguage(n.evidence))}</div>
  `;
}

function makeSvg(tag, attrs={}) {
  const el = document.createElementNS(svgNS, tag);
  for (const [k,v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
}

function renderGraph(gid) {
  const center = nodeMap.get(gid);
  const ins = (incomingMap.get(gid) || []);
  const outs = (outgoingMap.get(gid) || []);

  const merged = [];
  for (const e of ins) merged.push({edge:e, other:e.src, dir:"in"});
  for (const e of outs) merged.push({edge:e, other:e.dst, dir:"out"});
  merged.sort((a,b)=>b.edge.sum_kzt-a.edge.sum_kzt);

  const MAX_NEIGHBORS = 24;
  const shown = merged.slice(0, MAX_NEIGHBORS);
  const unique = [];
  const seen = new Set();
  for (const item of shown) {
    if (!seen.has(item.other)) {
      seen.add(item.other);
      unique.push(item);
    }
  }

  const edgesLayer = $("edgesLayer");
  const nodesLayer = $("nodesLayer");
  edgesLayer.innerHTML = "";
  nodesLayer.innerHTML = "";

  const cx = 550, cy = 350;
  const radius = unique.length <= 8 ? 235 : 270;
  const positions = new Map([[gid, {x:cx,y:cy}]]);

  unique.forEach((item, i) => {
    const a = (-Math.PI/2) + (2*Math.PI*i/Math.max(unique.length,1));
    positions.set(item.other, {x:cx + radius*Math.cos(a), y:cy + radius*Math.sin(a)});
  });

  const maxSum = Math.max(1, ...shown.map(x => Number(x.edge.sum_kzt || 0)));

  for (const item of shown) {
    if (!positions.has(item.other)) continue;
    const e = item.edge;
    const from = positions.get(e.src);
    const to = positions.get(e.dst);
    if (!from || !to) continue;

    const dx = to.x-from.x, dy = to.y-from.y;
    const len = Math.max(1, Math.hypot(dx,dy));
    const ux = dx/len, uy = dy/len;
    const startPad = e.src === gid ? 44 : 32;
    const endPad = e.dst === gid ? 48 : 36;

    const x1 = from.x + ux*startPad;
    const y1 = from.y + uy*startPad;
    const x2 = to.x - ux*endPad;
    const y2 = to.y - uy*endPad;

    const width = 1 + 5*Math.sqrt(Number(e.sum_kzt || 0)/maxSum);
    const line = makeSvg("line", {
      x1,y1,x2,y2, stroke:"#98a2b3", "stroke-width":width,
      "stroke-opacity":"0.65", "marker-end":"url(#arrow)"
    });
    edgesLayer.appendChild(line);

    if (unique.length <= 12) {
      const tx = (x1+x2)/2, ty=(y1+y2)/2;
      const t = makeSvg("text", {x:tx,y:ty,"text-anchor":"middle",class:"edge-label"});
      t.textContent = compactMoney(e.sum_kzt);
      edgesLayer.appendChild(t);
    }
  }

  function drawNode(nid, x, y, selected=false) {
    const n = nodeMap.get(nid) || {gid:nid,role:"unknown",cluster_id:"?"};
    const group = makeSvg("g", {class:"node"});
    group.dataset.gid = nid;

    const sameCluster = center && String(n.cluster_id) === String(center.cluster_id);
    const circle = makeSvg("circle", {
      cx:x, cy:y, r:selected ? 43 : 31,
      fill:roleColor(n.role),
      "fill-opacity":selected ? "1" : "0.86",
      stroke:selected ? "#111827" : (sameCluster ? "#111827" : "#ffffff"),
      "stroke-width":selected ? "5" : (sameCluster ? "3" : "2")
    });
    group.appendChild(circle);

    const t1 = makeSvg("text", {x:x,y:y-3,"text-anchor":"middle"});
    t1.setAttribute("fill","#ffffff");
    t1.setAttribute("font-size", selected && currentLang === "ru" ? "9" : "11");
    t1.textContent = selected ? tr("selected") : shortGid(nid);
    group.appendChild(t1);

    const t2 = makeSvg("text", {x:x,y:y+13,"text-anchor":"middle"});
    t2.setAttribute("fill","#ffffff");
    t2.setAttribute("font-size","9");
    t2.textContent = selected ? shortGid(nid) : shortRoleName(n.role);
    group.appendChild(t2);

    group.addEventListener("click", () => selectGid(String(nid)));
    nodesLayer.appendChild(group);
  }

  for (const item of unique) {
    const p = positions.get(item.other);
    drawNode(item.other, p.x, p.y, false);
  }
  drawNode(gid, cx, cy, true);

  $("graphTitle").textContent = `${tr("directAround")} ${gid}`;
  const hidden = Math.max(0, merged.length - shown.length);

  if (currentLang === "ru") {
    $("graphNote").textContent =
      `${tr("showing")} ${unique.length} ${tr("neighbors")} и ${shown.length} ${tr("directLinks")}.` +
      (hidden ? ` ${tr("hiddenPrefix")} ${hidden} ${tr("hiddenSuffix")}` : "");
  } else {
    $("graphNote").textContent =
      `${tr("showing")} ${unique.length} ${tr("neighbors")} and ${shown.length} ${tr("directLinks")}.` +
      (hidden ? ` ${hidden} ${tr("hiddenSuffix")}` : "");
  }
}

function selectGid(gid) {
  gid = String(gid).trim();
  const n = nodeMap.get(gid);
  if (!n) {
    setStatus(tr("notFound"));
    return;
  }

  currentGid = gid;
  $("gidInput").value = gid;
  setStatus(`${tr("found")} · ${tr("role").toLowerCase()} ${roleName(n.role, currentLang === "ru")} · ${tr("cluster").toLowerCase()} ${n.cluster_id}`);
  renderDetails(n);
  renderList("incoming", incomingMap.get(gid) || [], "in");
  renderList("outgoing", outgoingMap.get(gid) || [], "out");
  renderGraph(gid);
}

function applyLanguage() {
  document.documentElement.lang = currentLang;
  $("subtitle").textContent = tr("subtitle");
  $("gidInput").placeholder = tr("placeholder");
  $("searchBtn").textContent = tr("find");
  $("topBtn").textContent = tr("top");
  $("selectedHeading").textContent = tr("selectedNode");
  $("incomingHeading").textContent = tr("incoming");
  $("outgoingHeading").textContent = tr("outgoing");
  $("graph").setAttribute("aria-label", tr("graphAria"));

  $("langRu").classList.toggle("active", currentLang === "ru");
  $("langEn").classList.toggle("active", currentLang === "en");

  buildLegend();

  if (currentGid && nodeMap.has(currentGid)) {
    selectGid(currentGid);
  } else {
    $("graphTitle").textContent = tr("network");
    $("details").innerHTML = `<div class="small">${esc(tr("choose"))}</div>`;
    $("incoming").innerHTML = "";
    $("outgoing").innerHTML = "";
    setStatus("");
  }
}

function setLanguage(lang) {
  currentLang = lang;
  localStorage.setItem("moneygraph_lang", lang);
  applyLanguage();
}

$("searchBtn").addEventListener("click", () => selectGid($("gidInput").value));
$("gidInput").addEventListener("keydown", e => {
  if (e.key === "Enter") selectGid($("gidInput").value);
});
$("topBtn").addEventListener("click", () => {
  if (TOP_GIDS.length) selectGid(TOP_GIDS[0]);
});
$("langRu").addEventListener("click", () => setLanguage("ru"));
$("langEn").addEventListener("click", () => setLanguage("en"));

applyLanguage();
if (TOP_GIDS.length) selectGid(TOP_GIDS[0]);
</script>
</body>
</html>
"""


def load_data(data_dir: Path, out_dir: Path):
    edges_path = data_dir / "edges.parquet"
    roles_path = out_dir / "nodes_roles.csv"
    top_path = out_dir / "top_nodes.csv"

    missing = [p for p in (edges_path, roles_path, top_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Не найдены необходимые файлы: "
            + ", ".join(str(p) for p in missing)
            + "\nСначала запустите pipeline.py."
        )

    edges = pd.read_parquet(edges_path)
    roles = pd.read_csv(roles_path)
    top = pd.read_csv(top_path)

    for c in ("src", "dst"):
        edges[c] = edges[c].astype("int64")
    roles["gid"] = roles["gid"].astype("int64")
    top["gid"] = top["gid"].astype("int64")

    return edges, roles, top


def build_html(edges: pd.DataFrame, roles: pd.DataFrame, top: pd.DataFrame) -> str:
    # GID MUST be serialized as strings: values are larger than JS safe integers.
    nodes_records = []
    for r in roles.itertuples(index=False):
        nodes_records.append(
            {
                "gid": str(int(r.gid)),
                "role": str(r.role),
                "role_score": float(r.role_score),
                "cluster_id": int(r.cluster_id),
                "priority_score": float(r.priority_score),
                "evidence": str(r.evidence),
            }
        )

    edge_records = []
    for r in edges.itertuples(index=False):
        edge_records.append(
            {
                "src": str(int(r.src)),
                "dst": str(int(r.dst)),
                "sum_kzt": float(r.sum_kzt),
                "n_tx": int(getattr(r, "n_tx", 1)),
            }
        )

    top_gids = [
        str(int(g))
        for g in top.sort_values("rank")["gid"].tolist()
    ]

    html = HTML_TEMPLATE
    html = html.replace(
        "__NODES_JSON__",
        json.dumps(nodes_records, ensure_ascii=False, separators=(",", ":")),
    )
    html = html.replace(
        "__EDGES_JSON__",
        json.dumps(edge_records, ensure_ascii=False, separators=(",", ":")),
    )
    html = html.replace(
        "__TOP_GIDS_JSON__",
        json.dumps(top_gids, ensure_ascii=False, separators=(",", ":")),
    )
    return html


def main():
    ap = argparse.ArgumentParser(
        description="QazLedger MoneyGraph: generate self-contained local GID viewer"
    )
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="output")
    ap.add_argument("--file", default="viewer.html")
    args = ap.parse_args()

    data_dir = Path(args.data)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    edges, roles, top = load_data(data_dir, out_dir)
    html = build_html(edges, roles, top)

    target = out_dir / args.file
    target.write_text(html, encoding="utf-8")

    print("QazLedger MoneyGraph Viewer generated / Viewer создан")
    print(f"file: {target}")
    print(f"nodes: {len(roles)}")
    print(f"edges: {len(edges)}")
    print("Open output/viewer.html in a browser. RU is default; use RU/EN switch in the top-right corner.")


if __name__ == "__main__":
    main()
