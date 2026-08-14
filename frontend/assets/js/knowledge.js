function knowledgeEscapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function healthScoreClass(score) {
  if (score >= 80) return "text-success";
  if (score >= 50) return "text-warning";
  return "text-danger";
}

function renderStatCards(health) {
  const cards = [
    { label: "Notes", value: health.note_count },
    { label: "Tags", value: health.tag_count },
    { label: "Links", value: health.link_count },
    { label: "Health score", value: `${health.health_score}%`, cls: healthScoreClass(health.health_score) },
    { label: "Duplicates", value: health.duplicates.length },
    { label: "Outdated", value: health.outdated.length },
    { label: "Broken links", value: health.broken_links.length },
    { label: "Orphan notes", value: health.orphan_notes.length },
    { label: "Gap analyses run", value: health.gaps_count },
    { label: "Knowledge updates", value: health.updates_count },
  ];
  return cards
    .map(
      (c) => `
    <div class="surface stat-card">
      <div class="stat-value ${c.cls || ""}">${c.value}</div>
      <div class="stat-label">${c.label}</div>
    </div>`
    )
    .join("");
}

function renderIssues(health) {
  const sections = [];

  if (health.duplicates.length) {
    sections.push(`
      <div class="knowledge-issue-section">
        <h6><i class="bi bi-files"></i> Duplicate notes</h6>
        ${health.duplicates
          .map(
            (d) => `
          <div class="knowledge-issue-row">
            <div class="issue-title">${knowledgeEscapeHtml(d.title_a)} &harr; ${knowledgeEscapeHtml(d.title_b)}</div>
            <div class="issue-detail">${d.reason} · ${Math.round(d.similarity * 100)}% similar · ${knowledgeEscapeHtml(d.path_a)} / ${knowledgeEscapeHtml(d.path_b)}</div>
          </div>`
          )
          .join("")}
      </div>`);
  }

  if (health.outdated.length) {
    sections.push(`
      <div class="knowledge-issue-section">
        <h6><i class="bi bi-hourglass-split"></i> Outdated notes</h6>
        ${health.outdated
          .map(
            (o) => `
          <div class="knowledge-issue-row">
            <div class="issue-title">${knowledgeEscapeHtml(o.title)}</div>
            <div class="issue-detail">Last updated ${o.days_since_update} days ago · ${knowledgeEscapeHtml(o.path)}</div>
          </div>`
          )
          .join("")}
      </div>`);
  }

  if (health.broken_links.length) {
    sections.push(`
      <div class="knowledge-issue-section">
        <h6><i class="bi bi-link-45deg"></i> Broken links</h6>
        ${health.broken_links
          .map(
            (b) => `
          <div class="knowledge-issue-row">
            <div class="issue-title">${knowledgeEscapeHtml(b.source_title)} &rarr; [[${knowledgeEscapeHtml(b.target_name)}]]</div>
            <div class="issue-detail">Target note not found · ${knowledgeEscapeHtml(b.source_path)}</div>
          </div>`
          )
          .join("")}
      </div>`);
  }

  if (health.orphan_notes.length) {
    sections.push(`
      <div class="knowledge-issue-section">
        <h6><i class="bi bi-slash-circle"></i> Orphan notes</h6>
        ${health.orphan_notes
          .map(
            (path) => `
          <div class="knowledge-issue-row">
            <div class="issue-title">${knowledgeEscapeHtml(path)}</div>
            <div class="issue-detail">No incoming or outgoing links</div>
          </div>`
          )
          .join("")}
      </div>`);
  }

  return sections.join("");
}

// A small deterministic force-directed layout (Fruchterman-Reingold-style):
// no external graphing library, no CDN — just enough physics to keep
// connected notes near each other and spread the rest out.
function layoutGraph(nodes, edges, width, height) {
  const n = nodes.length;
  if (n === 0) return [];
  const positions = nodes.map((node, i) => {
    const angle = (2 * Math.PI * i) / n;
    return {
      ...node,
      x: width / 2 + (Math.min(width, height) / 3) * Math.cos(angle),
      y: height / 2 + (Math.min(width, height) / 3) * Math.sin(angle),
    };
  });
  const indexByPath = new Map(positions.map((p, i) => [p.path, i]));
  const area = width * height;
  const k = Math.sqrt(area / Math.max(n, 1)) * 0.9;

  for (let iter = 0; iter < 200; iter++) {
    const disp = positions.map(() => ({ x: 0, y: 0 }));

    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let dx = positions[i].x - positions[j].x;
        let dy = positions[i].y - positions[j].y;
        let dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const force = (k * k) / dist;
        dx = (dx / dist) * force;
        dy = (dy / dist) * force;
        disp[i].x += dx;
        disp[i].y += dy;
        disp[j].x -= dx;
        disp[j].y -= dy;
      }
    }

    edges.forEach((e) => {
      const i = indexByPath.get(e.source);
      const j = indexByPath.get(e.target);
      if (i === undefined || j === undefined) return;
      let dx = positions[i].x - positions[j].x;
      let dy = positions[i].y - positions[j].y;
      let dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const force = (dist * dist) / k;
      dx = (dx / dist) * force;
      dy = (dy / dist) * force;
      disp[i].x -= dx;
      disp[i].y -= dy;
      disp[j].x += dx;
      disp[j].y += dy;
    });

    const temp = Math.max(width, height) * (1 - iter / 200) * 0.05;
    for (let i = 0; i < n; i++) {
      const d = Math.sqrt(disp[i].x ** 2 + disp[i].y ** 2) || 0.01;
      positions[i].x += (disp[i].x / d) * Math.min(d, temp);
      positions[i].y += (disp[i].y / d) * Math.min(d, temp);
      // Leave room on the right for the label text drawn to the right of
      // each node, so titles near the edge don't get clipped by the SVG.
      positions[i].x = Math.max(24, Math.min(width - 160, positions[i].x));
      positions[i].y = Math.max(24, Math.min(height - 24, positions[i].y));
    }
  }

  return positions;
}

function renderGraph(graph) {
  const svg = document.getElementById("knowledge-graph-svg");
  const wrap = document.getElementById("knowledge-graph-wrap");
  const emptyEl = document.getElementById("knowledge-graph-empty");
  document.getElementById("graph-node-count").textContent = graph.nodes.length
    ? `${graph.nodes.length} notes · ${graph.edges.length} links`
    : "";

  if (!graph.nodes.length) {
    wrap.classList.add("d-none");
    emptyEl.classList.remove("d-none");
    return;
  }
  wrap.classList.remove("d-none");
  emptyEl.classList.add("d-none");

  const width = wrap.clientWidth || 480;
  const height = 420;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const positions = layoutGraph(graph.nodes, graph.edges, width, height);
  const byPath = new Map(positions.map((p) => [p.path, p]));

  const edgeSvg = graph.edges
    .map((e) => {
      const a = byPath.get(e.source);
      const b = byPath.get(e.target);
      if (!a || !b) return "";
      return `<line class="graph-edge" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" />`;
    })
    .join("");

  const nodeSvg = positions
    .map(
      (p) => `
    <g class="graph-node" data-path="${knowledgeEscapeHtml(p.path)}">
      <circle cx="${p.x}" cy="${p.y}" r="7"><title>${knowledgeEscapeHtml(p.title)}</title></circle>
      <text x="${p.x + 10}" y="${p.y + 3}">${knowledgeEscapeHtml(p.title.length > 22 ? p.title.slice(0, 22) + "…" : p.title)}</text>
    </g>`
    )
    .join("");

  svg.innerHTML = edgeSvg + nodeSvg;

  svg.querySelectorAll(".graph-node").forEach((g) => {
    g.addEventListener("click", () => {
      window.location.href = `obsidian.html?note=${encodeURIComponent(g.dataset.path)}`;
    });
  });
}

async function loadKnowledgeUpdates() {
  const listEl = document.getElementById("knowledge-updates-list");
  const emptyEl = document.getElementById("knowledge-updates-empty");
  try {
    const res = await window.AIAgentApi.get("/history?type=knowledge_update&page_size=6");
    if (!res.items.length) {
      listEl.innerHTML = "";
      emptyEl.classList.remove("d-none");
      return;
    }
    emptyEl.classList.add("d-none");
    listEl.innerHTML = window.HistoryCommon.renderHistoryRows(res.items, { showProject: false });
  } catch (err) {
    window.AIAgentToast.show("Could not load recent knowledge updates.", "error");
  }
}

async function loadKnowledgeHealth() {
  const health = await window.AIAgentApi.get("/knowledge/health");
  document.getElementById("knowledge-stats").innerHTML = renderStatCards(health);

  const issuesHtml = renderIssues(health);
  document.getElementById("knowledge-issues").innerHTML = issuesHtml;
  document.getElementById("knowledge-issues-empty").classList.toggle("d-none", !!issuesHtml);
}

async function loadKnowledgeGraph() {
  const graph = await window.AIAgentApi.get("/knowledge/graph");
  renderGraph(graph);
}

async function refreshAll() {
  document.getElementById("knowledge-loading").classList.remove("d-none");
  document.getElementById("knowledge-body").classList.add("d-none");
  try {
    await Promise.all([loadKnowledgeHealth(), loadKnowledgeGraph(), loadKnowledgeUpdates()]);
    document.getElementById("knowledge-loading").classList.add("d-none");
    document.getElementById("knowledge-body").classList.remove("d-none");
  } catch (err) {
    window.AIAgentToast.show(err.message || "Could not load knowledge data.", "error");
    document.getElementById("knowledge-loading").classList.add("d-none");
  }
}

async function init() {
  const user = await window.AppShell.initAppShell("knowledge");
  if (!user) return;

  document.getElementById("knowledge-refresh-btn").addEventListener("click", refreshAll);
  await refreshAll();
}

init();
