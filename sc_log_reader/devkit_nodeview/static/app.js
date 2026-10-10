/* SC_LogReader DevKit NodeView — Dynamic Node Graph
 *
 * Each event type, state key, rule, and output is its own node.
 * Edges are discovered dynamically from the data flow.
 * Animated particles trace the live data path.
 *
 * Author: Mallachi
 */

const SVG_NS = "http://www.w3.org/2000/svg";

// ── Colors per column ───────────────────────────────────────────────────

const COLORS = {
    events: { css: "event",  hex: "#d29922" },
    states: { css: "state",  hex: "#58a6ff" },
    rules:  { css: "rule",   hex: "#39d2c0" },
    output: { css: "output", hex: "#3fb950" },
};

// ── DOM refs ────────────────────────────────────────────────────────────

const connStatus = document.getElementById("connection-status");
const canvasWrap = document.getElementById("canvas-wrap");
const edgeSvg    = document.getElementById("edge-svg");
const columns = {
    events: document.getElementById("col-events"),
    states: document.getElementById("col-states"),
    rules:  document.getElementById("col-rules"),
    output: document.getElementById("col-output"),
};
const colCounts = {
    events: document.getElementById("count-events"),
    states: document.getElementById("count-states"),
    rules:  document.getElementById("count-rules"),
    output: document.getElementById("count-output"),
};

// ── Registries ──────────────────────────────────────────────────────────

// nodeMap["events:location_change"] = { el, column, name, hits, value }
const nodeMap = {};

// edgeMap["events:location_change->states:location"] = { pathEl, arrowEl, sourceId, targetId, color }
const edgeMap = {};

// Current state values
const stateValues = {};

// Pipeline context — tracks current data flow for edge discovery
let pendingRawEventType = null;
let pendingRawEventTimer = null;
let lastRuleName = null;
let lastRuleEventType = null;

// Debounce edge redraw
let redrawTimer = null;

// ── Node Management ─────────────────────────────────────────────────────

function getOrCreateNode(column, name, initialValue) {
    const id = `${column}:${name}`;
    if (nodeMap[id]) return nodeMap[id];

    const el = document.createElement("div");
    el.className = `node node-${COLORS[column].css}`;
    el.id = `node-${column}-${safeId(name)}`;

    const nameSpan = document.createElement("div");
    nameSpan.className = "node-name";
    nameSpan.textContent = name;
    el.appendChild(nameSpan);

    // Value line for states and outputs
    if (column === "states" || column === "output") {
        const valSpan = document.createElement("div");
        valSpan.className = "node-value";
        valSpan.textContent = initialValue != null ? formatValue(initialValue) : "";
        el.appendChild(valSpan);
    }

    // Hit counter
    const hitBadge = document.createElement("span");
    hitBadge.className = "node-hits";
    hitBadge.textContent = "0";
    el.appendChild(hitBadge);

    columns[column].appendChild(el);

    const entry = { el, column, name, id, hits: 0, valueEl: el.querySelector(".node-value"), hitBadge };
    nodeMap[id] = entry;

    // Update column count
    updateColCount(column);

    // Schedule edge redraw (new node may need edges repositioned)
    scheduleRedraw();

    return entry;
}

function updateColCount(column) {
    const count = Object.values(nodeMap).filter(n => n.column === column).length;
    colCounts[column].textContent = count;
}

function hitNode(node) {
    node.hits++;
    node.hitBadge.textContent = node.hits;
}

function pulseNode(node) {
    const cls = `pulse-${COLORS[node.column].css}`;
    node.el.classList.remove(cls);
    void node.el.offsetWidth; // force reflow
    node.el.classList.add(cls);
    setTimeout(() => node.el.classList.remove(cls), 800);
}

function updateNodeValue(node, value) {
    if (!node.valueEl) return;
    node.valueEl.textContent = formatValue(value);
    node.valueEl.className = "node-value " + getValueClass(value);
}

// ── Edge Management ─────────────────────────────────────────────────────

function getOrCreateEdge(sourceId, targetId) {
    const edgeId = `${sourceId}->${targetId}`;
    if (edgeMap[edgeId]) return edgeMap[edgeId];

    const sourceNode = nodeMap[sourceId];
    const targetNode = nodeMap[targetId];
    if (!sourceNode || !targetNode) return null;

    // Determine color from target column
    const colorHex = COLORS[targetNode.column].hex;
    const colorCss = COLORS[targetNode.column].css;

    // Create SVG path (will be positioned by redrawAllEdges)
    const pathEl = document.createElementNS(SVG_NS, "path");
    pathEl.classList.add("edge-path");
    pathEl.id = `edge-${safeId(edgeId)}`;
    edgeSvg.appendChild(pathEl);

    // Arrow marker
    const arrowEl = document.createElementNS(SVG_NS, "polygon");
    arrowEl.classList.add(`arrow-dim`);
    arrowEl.id = `arrow-${safeId(edgeId)}`;
    edgeSvg.appendChild(arrowEl);

    const entry = { pathEl, arrowEl, sourceId, targetId, colorHex, colorCss, edgeId };
    edgeMap[edgeId] = entry;

    // Position it
    positionEdge(entry);

    return entry;
}

function discoverEdge(sourceId, targetId) {
    // Only create if both nodes exist
    if (!nodeMap[sourceId] || !nodeMap[targetId]) return null;
    return getOrCreateEdge(sourceId, targetId);
}

function positionEdge(edge) {
    const sourceNode = nodeMap[edge.sourceId];
    const targetNode = nodeMap[edge.targetId];
    if (!sourceNode || !targetNode) return;

    const from = getAnchor(sourceNode.el, "right");
    const to   = getAnchor(targetNode.el, "left");

    const pathD = buildBezier(from, to);
    edge.pathEl.setAttribute("d", pathD);

    // Arrow at target
    const arrowPts = buildArrow(to, "left");
    edge.arrowEl.setAttribute("points", arrowPts);
}

function redrawAllEdges() {
    for (const edge of Object.values(edgeMap)) {
        positionEdge(edge);
    }
}

function scheduleRedraw() {
    clearTimeout(redrawTimer);
    redrawTimer = setTimeout(() => {
        updateSvgSize();
        redrawAllEdges();
    }, 50);
}

function updateSvgSize() {
    const h = Math.max(canvasWrap.scrollHeight, canvasWrap.clientHeight);
    const w = Math.max(canvasWrap.scrollWidth, canvasWrap.clientWidth);
    edgeSvg.style.width = w + "px";
    edgeSvg.style.height = h + "px";
    edgeSvg.setAttribute("viewBox", `0 0 ${w} ${h}`);
}

// ── Edge Animation ──────────────────────────────────────────────────────

function animateEdge(edge) {
    if (!edge) return;

    // Pulse the path
    const activeCls = `active-${edge.colorCss}`;
    edge.pathEl.classList.add(activeCls);
    edge.arrowEl.classList.remove("arrow-dim");
    edge.arrowEl.classList.add(`arrow-${edge.colorCss}`);
    setTimeout(() => {
        edge.pathEl.classList.remove(activeCls);
        edge.arrowEl.classList.remove(`arrow-${edge.colorCss}`);
        edge.arrowEl.classList.add("arrow-dim");
    }, 700);

    // Animated particle
    const pathEl = edge.pathEl;
    const totalLen = pathEl.getTotalLength();
    if (totalLen < 1) return;

    const circle = document.createElementNS(SVG_NS, "circle");
    circle.setAttribute("r", "5");
    circle.setAttribute("fill", edge.colorHex);
    circle.setAttribute("filter", "url(#glow)");
    edgeSvg.appendChild(circle);

    const duration = 450;
    const startTime = performance.now();

    function step(now) {
        const t = Math.min((now - startTime) / duration, 1);
        const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic
        const pt = pathEl.getPointAtLength(eased * totalLen);
        circle.setAttribute("cx", pt.x);
        circle.setAttribute("cy", pt.y);

        if (t < 1) {
            requestAnimationFrame(step);
        } else {
            circle.remove();
        }
    }

    requestAnimationFrame(step);
}

// ── SSE Connection ──────────────────────────────────────────────────────

function connect() {
    const evtSource = new EventSource("/api/events");

    evtSource.onopen = () => {
        connStatus.textContent = "Connected";
        connStatus.className = "status connected";
        loadInitialStates();
    };

    evtSource.onmessage = (e) => {
        try {
            handlePacket(JSON.parse(e.data));
        } catch (err) {
            console.error("Parse error:", err);
        }
    };

    evtSource.onerror = () => {
        connStatus.textContent = "Disconnected";
        connStatus.className = "status disconnected";
        evtSource.close();
        setTimeout(connect, 2000);
    };
}

async function loadInitialStates() {
    try {
        const resp = await fetch("/api/states");
        const data = await resp.json();
        for (const [key, value] of Object.entries(data.states || {})) {
            stateValues[key] = value;
            const node = getOrCreateNode("states", key, value);
            updateNodeValue(node, value);
        }
    } catch (err) {
        console.error("Failed to load states:", err);
    }
}

// ── Packet Router ───────────────────────────────────────────────────────

function handlePacket(packet) {
    const { layer, type, data } = packet;

    if (layer === "parser" && type === "raw_event") {
        onRawEvent(data);
    } else if (layer === "parser" && type === "state_change") {
        onStateChange(data);
    } else if (layer === "logic" && type === "rule_fired") {
        onRuleFired(data);
    } else if (layer === "logic" && type === "derived_event") {
        onDerivedEvent(data);
    }
}

// ── Handlers ────────────────────────────────────────────────────────────

function onRawEvent(data) {
    const eventType = data.event_type || "unknown";

    // Create/activate event node
    const node = getOrCreateNode("events", eventType);
    hitNode(node);
    pulseNode(node);

    // Track for edge discovery: next state_changes came from this event
    pendingRawEventType = eventType;
    clearTimeout(pendingRawEventTimer);
    pendingRawEventTimer = setTimeout(() => { pendingRawEventType = null; }, 500);
}

function onStateChange(data) {
    const { key, new: newVal } = data;
    stateValues[key] = newVal;

    // Create/activate state node
    const node = getOrCreateNode("states", key, newVal);
    hitNode(node);
    pulseNode(node);
    updateNodeValue(node, newVal);

    // Discover edge: raw event → this state
    if (pendingRawEventType) {
        const sourceId = `events:${pendingRawEventType}`;
        const targetId = `states:${key}`;
        const edge = discoverEdge(sourceId, targetId);
        if (edge) animateEdge(edge);
    }
}

function onRuleFired(data) {
    const ruleName = data.rule || "unknown";
    const conditions = data.conditions || [];
    const eventType = data.event_type || "unknown";

    // Create/activate rule node
    const node = getOrCreateNode("rules", ruleName);
    hitNode(node);
    pulseNode(node);

    // Track for derived event edge discovery
    lastRuleName = ruleName;
    lastRuleEventType = eventType;

    // Discover edges: condition states → this rule
    for (const cond of conditions) {
        if (cond.key) {
            const sourceId = `states:${cond.key}`;
            const targetId = `rules:${ruleName}`;
            // Ensure state node exists
            if (!nodeMap[sourceId] && stateValues[cond.key] !== undefined) {
                getOrCreateNode("states", cond.key, stateValues[cond.key]);
            }
            const edge = discoverEdge(sourceId, targetId);
            if (edge) {
                setTimeout(() => animateEdge(edge), 100);
            }
        }
    }
}

function onDerivedEvent(data) {
    const eventType = data.event_type || "unknown";
    const message = data.message || "";

    // Create/activate output node
    const node = getOrCreateNode("output", eventType, message);
    hitNode(node);
    pulseNode(node);
    updateNodeValue(node, message);

    // Discover edge: rule → this output
    if (lastRuleName) {
        const sourceId = `rules:${lastRuleName}`;
        const targetId = `output:${eventType}`;
        const edge = discoverEdge(sourceId, targetId);
        if (edge) {
            setTimeout(() => animateEdge(edge), 200);
        }
    }

    // Also try direct event → output if no rule (passthrough events)
    if (pendingRawEventType && !lastRuleName) {
        const sourceId = `events:${pendingRawEventType}`;
        const targetId = `output:${eventType}`;
        const edge = discoverEdge(sourceId, targetId);
        if (edge) {
            setTimeout(() => animateEdge(edge), 100);
        }
    }

    // Clear rule context after derived event completes the pipeline
    lastRuleName = null;
    lastRuleEventType = null;
}

// ── Geometry Helpers ────────────────────────────────────────────────────

function getAnchor(el, side) {
    const rect = el.getBoundingClientRect();
    const canvasRect = canvasWrap.getBoundingClientRect();
    const scrollX = canvasWrap.scrollLeft;
    const scrollY = canvasWrap.scrollTop;

    // Translate to canvas-relative coordinates (accounting for scroll)
    const relX = rect.left - canvasRect.left + scrollX;
    const relY = rect.top - canvasRect.top + scrollY;

    if (side === "right") {
        return { x: relX + rect.width, y: relY + rect.height / 2 };
    } else { // "left"
        return { x: relX, y: relY + rect.height / 2 };
    }
}

function buildBezier(from, to) {
    const dx = Math.abs(to.x - from.x);
    const tension = Math.max(50, dx * 0.4);

    const cp1x = from.x + tension;
    const cp2x = to.x - tension;

    return `M ${from.x} ${from.y} C ${cp1x} ${from.y}, ${cp2x} ${to.y}, ${to.x} ${to.y}`;
}

function buildArrow(tip, side) {
    const size = 6;
    if (side === "left") {
        return `${tip.x},${tip.y} ${tip.x - size},${tip.y - size / 2} ${tip.x - size},${tip.y + size / 2}`;
    }
    // "right" fallback
    return `${tip.x},${tip.y} ${tip.x + size},${tip.y - size / 2} ${tip.x + size},${tip.y + size / 2}`;
}

// ── Utility ─────────────────────────────────────────────────────────────

function safeId(str) {
    return str.replace(/[^a-zA-Z0-9_-]/g, "_");
}

function formatValue(val) {
    if (val == null) return "null";
    if (val === true) return "TRUE";
    if (val === false) return "FALSE";
    const s = String(val);
    return s.length > 40 ? s.substring(0, 40) + "..." : s;
}

function getValueClass(val) {
    if (val === true) return "val-true";
    if (val === false) return "val-false";
    if (val == null) return "val-null";
    return "";
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// ── Init ────────────────────────────────────────────────────────────────

window.addEventListener("resize", scheduleRedraw);

updateSvgSize();
connect();
