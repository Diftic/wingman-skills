/* SC_LogReader DevKit — Real-time Dashboard */

const MAX_FEED_ITEMS = 200;

const readerFeed = document.getElementById("reader-feed");
const eventFeed = document.getElementById("event-feed");
const ruleFeed = document.getElementById("rule-feed");
const stateGrid = document.getElementById("state-grid");
const connStatus = document.getElementById("connection-status");
const readerCount = document.getElementById("reader-count");
const eventCount = document.getElementById("event-count");
const ruleCount = document.getElementById("rule-count");

let readerTotal = 0;
let eventTotal = 0;
let ruleTotal = 0;
let autoScroll = { reader: true, events: true, rules: true };

// State grouping for the monitor panel
const STATE_GROUPS = {
    "Location": ["location", "location_name", "star_system", "jurisdiction"],
    "Ship": ["ship", "ship_owner", "own_ship"],
    "Zones": ["in_armistice", "in_monitored_space", "in_restricted_area"],
    "Mission": [
        "current_objective", "last_contract_accepted",
        "last_contract_accepted_id", "last_contract_completed",
        "last_contract_completed_id", "last_contract_failed",
        "last_contract_failed_id",
    ],
    "Session": ["player_name", "player_geid", "server"],
    "Health": [],  // Dynamic injury keys added at runtime
};

const knownStateKeys = new Set(
    Object.values(STATE_GROUPS).flat()
);

const states = {};

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
            const packet = JSON.parse(e.data);
            handlePacket(packet);
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
            states[key] = value;
        }
        renderStates();
    } catch (err) {
        console.error("Failed to load initial states:", err);
    }
}

// ── Packet Router ───────────────────────────────────────────────────────

function handlePacket(packet) {
    const { layer, type, data, ts } = packet;
    const time = formatTime(ts);

    if (layer === "parser" && type === "raw_event") {
        addReaderItem(time, data);
    } else if (layer === "parser" && type === "state_change") {
        handleStateChange(data);
    } else if (layer === "logic" && type === "derived_event") {
        addEventItem(time, data);
    } else if (layer === "logic" && type === "rule_fired") {
        addRuleItem(time, data);
    }
}

// ── Panel 1: Log Reader ─────────────────────────────────────────────────

function addReaderItem(time, data) {
    readerTotal++;
    readerCount.textContent = readerTotal;

    const item = document.createElement("div");
    item.className = "feed-item flash";

    const eventType = data.event_type || "unknown";
    const tagClass = getEventTagClass(eventType);
    const rawLine = data.raw_line || "";
    const extracted = data.data || {};
    const dataStr = Object.keys(extracted).length > 0
        ? Object.entries(extracted).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join("  ")
        : "";

    item.innerHTML = `
        <span class="feed-ts">${time}</span>
        <span class="feed-tag ${tagClass}">${eventType}</span>
        <div class="feed-msg">
            ${escapeHtml(rawLine.substring(0, 120))}
            ${dataStr ? `<div class="feed-data">${escapeHtml(dataStr)}</div>` : ""}
        </div>
    `;

    appendToFeed(readerFeed, item, "reader");
}

// ── Panel 2: State Monitor ──────────────────────────────────────────────

function handleStateChange(data) {
    const { key, new: newVal } = data;
    states[key] = newVal;

    // Add dynamic keys (e.g., injury_*) to Health group
    if (key.startsWith("injury_") && !knownStateKeys.has(key)) {
        knownStateKeys.add(key);
        STATE_GROUPS["Health"].push(key);
    } else if (!knownStateKeys.has(key)) {
        knownStateKeys.add(key);
        if (!STATE_GROUPS["Other"]) STATE_GROUPS["Other"] = [];
        STATE_GROUPS["Other"].push(key);
    }

    renderStates();

    // Flash the changed row
    const row = document.getElementById(`state-${key}`);
    if (row) {
        row.classList.remove("changed");
        void row.offsetWidth; // Force reflow
        row.classList.add("changed");
    }
}

function renderStates() {
    stateGrid.innerHTML = "";

    for (const [group, keys] of Object.entries(STATE_GROUPS)) {
        // Skip empty groups
        const activeKeys = keys.filter(k => states[k] !== undefined);
        if (activeKeys.length === 0) continue;

        const groupDiv = document.createElement("div");
        groupDiv.className = "state-group";

        const header = document.createElement("div");
        header.className = "state-group-header";
        header.textContent = group;
        groupDiv.appendChild(header);

        for (const key of activeKeys) {
            const value = states[key];
            const row = document.createElement("div");
            row.className = "state-row";
            row.id = `state-${key}`;

            const dotClass = getDotClass(value);
            const valClass = getValueClass(value);
            const displayVal = formatStateValue(value);

            row.innerHTML = `
                <span class="state-dot ${dotClass}"></span>
                <span class="state-key">${key}</span>
                <span class="state-value ${valClass}">${escapeHtml(displayVal)}</span>
            `;
            groupDiv.appendChild(row);
        }

        stateGrid.appendChild(groupDiv);
    }
}

// ── Panel 3: Event Stream ───────────────────────────────────────────────

function addEventItem(time, data) {
    eventTotal++;
    eventCount.textContent = eventTotal;

    const item = document.createElement("div");
    item.className = "feed-item flash";

    const eventType = data.event_type || "unknown";
    const message = data.message || "";
    const tagClass = `tag-${eventType}`;

    item.innerHTML = `
        <span class="feed-ts">${time}</span>
        <span class="feed-tag tag-derived">${eventType}</span>
        <span class="feed-msg">${escapeHtml(message)}</span>
    `;

    appendToFeed(eventFeed, item, "events");
}

// ── Panel 4: Rules ──────────────────────────────────────────────────────

function addRuleItem(time, data) {
    ruleTotal++;
    ruleCount.textContent = ruleTotal;

    const item = document.createElement("div");
    item.className = "feed-item flash";

    const ruleName = data.rule || "unknown";
    const message = data.message || "";
    const conditions = data.conditions || [];
    const condStr = conditions
        .map(c => `${c.key} ${c.op} ${JSON.stringify(c.expected)} → ${JSON.stringify(c.actual)}`)
        .join(", ");

    item.innerHTML = `
        <span class="feed-ts">${time}</span>
        <span class="feed-tag tag-rule">${ruleName}</span>
        <div class="feed-msg">
            ${escapeHtml(message)}
            ${condStr ? `<div class="feed-data">${escapeHtml(condStr)}</div>` : ""}
        </div>
    `;

    appendToFeed(ruleFeed, item, "rules");
}

// ── Utilities ───────────────────────────────────────────────────────────

function appendToFeed(container, item, feedKey) {
    const isAtBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 20;

    container.appendChild(item);

    // Trim old items
    while (container.children.length > MAX_FEED_ITEMS) {
        container.removeChild(container.firstChild);
    }

    // Auto-scroll if user was at bottom
    if (isAtBottom) {
        container.scrollTop = container.scrollHeight;
    }
}

function formatTime(isoStr) {
    if (!isoStr) return "--:--:--";
    const parts = isoStr.split("T");
    if (parts.length < 2) return isoStr;
    return parts[1].substring(0, 12);
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function getDotClass(value) {
    if (value === true) return "on";
    if (value === false || value === null || value === undefined) return "off";
    return "on";
}

function getValueClass(value) {
    if (value === true) return "val-true";
    if (value === false) return "val-false";
    if (value === null || value === undefined) return "val-null";
    return "val-string";
}

function formatStateValue(value) {
    if (value === null || value === undefined) return "null";
    if (value === true) return "TRUE";
    if (value === false) return "FALSE";
    return String(value);
}

function getEventTagClass(eventType) {
    if (eventType.includes("armistice") || eventType.includes("monitored") || eventType.includes("restricted") || eventType.includes("jurisdiction")) return "tag-zone";
    if (eventType.includes("channel") || eventType.includes("hangar")) return "tag-ship";
    if (eventType.includes("location") || eventType.includes("quantum") || eventType.includes("station_departed")) return "tag-location";
    if (eventType.includes("contract") || eventType.includes("objective") || eventType.includes("mission")) return "tag-mission";
    if (eventType.includes("injury") || eventType.includes("med_bed") || eventType.includes("emergency")) return "tag-health";
    if (eventType.includes("shop") || eventType.includes("commodity") || eventType.includes("reward") || eventType.includes("refinery")) return "tag-trade";
    return "tag-parser";
}

// ── Start ───────────────────────────────────────────────────────────────

connect();
