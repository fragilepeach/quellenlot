"use strict";

function createEvidenceGraph(nodes, edges, activate) {
  const canvas = element("div", "graph-canvas");
  const svg = (tag) => document.createElementNS("http://www.w3.org/2000/svg", tag);
  const connections = svg("svg");
  connections.classList.add("graph-connections");
  connections.setAttribute("aria-hidden", "true");
  const defs = svg("defs");
  const arrow = svg("marker");
  arrow.id = "graph-citation-arrow";
  arrow.setAttribute("viewBox", "0 0 8 8");
  arrow.setAttribute("refX", "8");
  arrow.setAttribute("refY", "4");
  arrow.setAttribute("markerWidth", "6");
  arrow.setAttribute("markerHeight", "6");
  arrow.setAttribute("orient", "auto");
  const tip = svg("path");
  tip.setAttribute("d", "M0 0 L8 4 L0 8 Z");
  arrow.append(tip);
  defs.append(arrow);
  connections.append(defs);
  canvas.append(connections);

  const byId = new Map();
  const paths = edges.map(({ from, to, kind }) => {
    const path = svg("path");
    path.dataset.kind = kind;
    if (kind === "citation") path.setAttribute("marker-end", "url(#graph-citation-arrow)");
    connections.append(path);
    return { from, to, path };
  });
  const padding = 12;
  const clamp = (value, min, max) => Math.min(Math.max(value, min), Math.max(min, max));

  function position(node, x, y) {
    const halfWidth = node.control.offsetWidth / 2;
    const halfHeight = node.control.offsetHeight / 2;
    node.x = clamp(x, halfWidth + padding, canvas.clientWidth - halfWidth - padding);
    node.y = clamp(y, halfHeight + padding, canvas.clientHeight - halfHeight - padding);
    node.control.style.left = node.x + "px";
    node.control.style.top = node.y + "px";
  }

  function boundary(node, dx, dy) {
    const scale = Math.min(
      (node.control.offsetWidth / 2 + 2) / Math.abs(dx),
      (node.control.offsetHeight / 2 + 2) / Math.abs(dy),
    );
    return [node.x + dx * scale, node.y + dy * scale];
  }

  function draw() {
    for (const { from, to, path } of paths) {
      const start = byId.get(from);
      const end = byId.get(to);
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      if (Math.hypot(dx, dy) < 1) {
        path.removeAttribute("d");
      } else if (path.dataset.kind === "citation" && Math.abs(dy) < 24) {
        const direction = Math.max(start.y, end.y) > canvas.clientHeight - 70 ? -1 : 1;
        const [, startY] = boundary(start, 0, direction);
        const [, endY] = boundary(end, 0, direction);
        const curve = (direction > 0 ? Math.max(startY, endY) : Math.min(startY, endY)) + direction * 29;
        path.setAttribute("d", `M ${start.x} ${startY} C ${start.x} ${curve} ${end.x} ${curve} ${end.x} ${endY}`);
      } else {
        const [x1, y1] = boundary(start, dx, dy);
        const [x2, y2] = boundary(end, -dx, -dy);
        path.setAttribute("d", `M ${x1} ${y1} L ${x2} ${y2}`);
      }
    }
  }

  function move(node, x, y) {
    position(node, x, y);
    node.manualPosition = [node.x / canvas.clientWidth, node.y / canvas.clientHeight];
    draw();
  }

  function addControls(node) {
    const { control } = node;
    let drag;
    let ignoreClick = false;
    control.addEventListener("pointerdown", (event) => {
      if (!event.isPrimary || event.button !== 0) return;
      ignoreClick = false;
      drag = { id: event.pointerId, x: event.clientX, y: event.clientY, originX: node.x, originY: node.y };
    });
    control.addEventListener("pointermove", (event) => {
      if (drag?.id !== event.pointerId) return;
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (!ignoreClick && Math.hypot(dx, dy) < 5) return;
      if (!ignoreClick) {
        ignoreClick = true;
        control.setPointerCapture(event.pointerId);
        control.classList.add("is-dragging");
      }
      move(node, drag.originX + dx, drag.originY + dy);
    });
    const endDrag = (event) => {
      if (drag?.id !== event.pointerId) return;
      drag = undefined;
      control.classList.remove("is-dragging");
    };
    control.addEventListener("pointerup", endDrag);
    control.addEventListener("pointercancel", endDrag);
    control.addEventListener("lostpointercapture", endDrag);
    control.addEventListener("pointerleave", (event) => {
      if (!control.hasPointerCapture(event.pointerId)) endDrag(event);
    });
    control.addEventListener("click", (event) => {
      if (ignoreClick && event.detail > 0) {
        ignoreClick = false;
        event.preventDefault();
        return;
      }
      activate(node);
    });
    control.addEventListener("keydown", (event) => {
      const directions = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
      if (!Object.hasOwn(directions, event.key)) return;
      event.preventDefault();
      const [dx, dy] = directions[event.key];
      move(node, node.x + dx * 12, node.y + dy * 12);
    });
  }

  for (const entry of nodes) {
    const control = button("", "graph-node");
    control.title = entry.label;
    control.dataset.kind = entry.kind;
    control.setAttribute("aria-pressed", "false");
    control.append(element("span", "graph-node-name", entry.label));
    if (entry.relation) control.append(relationBadge(entry.relation));
    if (entry.note) control.append(element("span", "graph-node-note", entry.note));
    const node = { ...entry, control };
    byId.set(node.id, node);
    canvas.append(control);
    addControls(node);
  }

  let lastWidth;
  const observer = new ResizeObserver(() => {
    const width = canvas.clientWidth;
    if (!width || width === lastWidth) return;
    lastWidth = width;
    const columns = Math.max(1, Math.min(5, Math.floor(width / 135)));
    const nodeWidth = Math.min(174, (width - 2 * padding) / columns - 8);
    const rowHeight = width < 540 ? 95 : 112;
    const rows = [];
    for (const kind of ["claim", "evidence", "source"]) {
      const group = [...byId.values()].filter((node) => node.kind === kind);
      for (let index = 0; index < group.length; index += columns) rows.push(group.slice(index, index + columns));
    }
    canvas.style.height = Math.max(260, rows.length * rowHeight + 28) + "px";
    canvas.style.setProperty("--node-width", nodeWidth + "px");
    rows.forEach((row, index) => row.forEach((node, column) => {
      const x = (column + 0.5) * width / row.length;
      const y = padding + (index + 0.5) * rowHeight;
      position(node, node.manualPosition ? node.manualPosition[0] * width : x,
        node.manualPosition ? node.manualPosition[1] * canvas.clientHeight : y);
    }));
    draw();
  });
  observer.observe(canvas);

  return {
    canvas,
    select(id) {
      for (const node of byId.values()) node.control.setAttribute("aria-pressed", String(node.id === id));
    },
    dispose() { observer.disconnect(); },
  };
}
