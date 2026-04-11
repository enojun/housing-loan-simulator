const express = require("express");
const path = require("path");
const { spawn } = require("child_process");

const app = express();
app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

const PORT = process.env.PORT || 8080;
const MCP_SERVER_PATH = path.join(
  __dirname,
  "tax-law-mcp",
  "dist",
  "index.js"
);

// --- MCP Client via JSON-RPC over stdio ---

let mcpProcess = null;
let requestId = 0;
const pendingRequests = new Map();
let stdoutBuffer = "";
let initialized = false;

function startMcpServer() {
  console.log("Starting MCP server:", MCP_SERVER_PATH);
  mcpProcess = spawn("node", [MCP_SERVER_PATH], {
    stdio: ["pipe", "pipe", "pipe"],
    env: { ...process.env },
  });

  mcpProcess.stdout.on("data", (data) => {
    stdoutBuffer += data.toString();
    const lines = stdoutBuffer.split("\n");
    stdoutBuffer = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const msg = JSON.parse(line);
        if (msg.id !== undefined && pendingRequests.has(msg.id)) {
          const { resolve } = pendingRequests.get(msg.id);
          pendingRequests.delete(msg.id);
          resolve(msg);
        }
      } catch {
        // ignore non-JSON lines
      }
    }
  });

  mcpProcess.stderr.on("data", (data) => {
    console.error("[MCP stderr]", data.toString());
  });

  mcpProcess.on("close", (code) => {
    console.error("MCP server exited with code", code);
    initialized = false;
    // Reject all pending requests
    for (const [id, { reject }] of pendingRequests) {
      reject(new Error("MCP server process exited"));
      pendingRequests.delete(id);
    }
    // Auto-restart after 2 seconds
    setTimeout(() => {
      startMcpServer();
      initializeMcp();
    }, 2000);
  });
}

function sendRpc(method, params) {
  return new Promise((resolve, reject) => {
    const id = ++requestId;
    const msg = { jsonrpc: "2.0", id, method, params };
    pendingRequests.set(id, { resolve, reject });
    mcpProcess.stdin.write(JSON.stringify(msg) + "\n");
    // 120 second timeout for slow searches
    setTimeout(() => {
      if (pendingRequests.has(id)) {
        pendingRequests.delete(id);
        reject(new Error("MCP request timed out"));
      }
    }, 120000);
  });
}

async function initializeMcp() {
  try {
    const result = await sendRpc("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "tax-law-frontend", version: "1.0.0" },
    });
    console.log("MCP initialized:", JSON.stringify(result.result?.serverInfo));
    // Send initialized notification (no id)
    mcpProcess.stdin.write(
      JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) +
        "\n"
    );
    initialized = true;
  } catch (err) {
    console.error("MCP initialization failed:", err);
  }
}

// --- API Endpoints ---

app.get("/api/tools", async (req, res) => {
  try {
    if (!initialized) {
      return res.status(503).json({ error: "MCP server not ready" });
    }
    const result = await sendRpc("tools/list", {});
    res.json(result.result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/api/tools/call", async (req, res) => {
  try {
    if (!initialized) {
      return res.status(503).json({ error: "MCP server not ready" });
    }
    const { name, arguments: args } = req.body;
    if (!name) {
      return res.status(400).json({ error: "tool name is required" });
    }
    const result = await sendRpc("tools/call", {
      name,
      arguments: args || {},
    });
    if (result.error) {
      return res.status(400).json({ error: result.error });
    }
    res.json(result.result);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/health", (req, res) => {
  res.json({ status: initialized ? "ok" : "initializing" });
});

// --- Start ---

startMcpServer();
initializeMcp();

app.listen(PORT, () => {
  console.log(`Tax Law Frontend running on port ${PORT}`);
});
