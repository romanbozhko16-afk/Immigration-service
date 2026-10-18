// Minimal client. All server text is inserted with textContent, never as HTML.
"use strict";

const $ = (id) => document.getElementById(id);
const STORE = window.sessionStorage; // the token lives until the tab is closed
let token = null;
let role = null;
let caseId = null;
let lastDocument = null;

function save(key, value) { try { STORE.setItem(key, value); } catch (_) { /* private mode */ } }
function load(key) { try { return STORE.getItem(key); } catch (_) { return null; } }
function drop(key) { try { STORE.removeItem(key); } catch (_) { /* ignore */ } }

async function api(method, path, body) {
  const options = { method, headers: { Authorization: "Bearer " + token } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  if (response.status === 204) return null;
  const type = response.headers.get("content-type") || "";
  const data = type.includes("json") ? await response.json() : await response.blob();
  if (!response.ok) {
    const error = new Error((data && data.detail) || "error " + response.status);
    error.status = response.status;
    throw error;
  }
  return data;
}

function language() { return $("language").value; }
function show(element, text) { element.textContent = text; }

// --- login -------------------------------------------------------------------------------

async function detectRole(candidate) {
  token = candidate;
  try { return (await api("GET", "/api/me")).role; }
  catch (e) { if (e.status === 401) return null; throw e; }
}

async function login(candidate) {
  show($("login-msg"), "");
  try {
    role = await detectRole(candidate);
  } catch (_) {
    show($("login-msg"), "Service unavailable.");
    return;
  }
  if (!role) { token = null; show($("login-msg"), "Invalid token."); return; }
  save("token", candidate);
  $("login").hidden = true;
  $("app").hidden = false;
  $("lawyer-tab").hidden = role !== "lawyer";
  if (role === "lawyer") { selectTab("lawyer"); refreshCases(); } else { selectTab("interview"); }
}

function logout() {
  drop("token"); drop("case"); token = null; role = null; caseId = null;
  $("app").hidden = true; $("login").hidden = false; $("token").value = "";
}

// --- tabs --------------------------------------------------------------------------------

function selectTab(name) {
  for (const button of document.querySelectorAll("#tabs button")) {
    button.setAttribute("aria-selected", String(button.dataset.tab === name));
  }
  for (const id of ["interview", "chat", "lawyer"]) { $(id).hidden = id !== name; }
}

// --- interview ---------------------------------------------------------------------------

async function loadPrompt() {
  if (!caseId) { show($("prompt"), ""); return; }
  try {
    const data = await api("GET", `/api/cases/${caseId}/interview?language=${language()}`);
    show($("prompt"), data.prompt);
  } catch (e) { show($("prompt"), e.message); }
}

async function newCase() {
  const data = await api("POST", "/api/cases");
  caseId = data.case_id; save("case", caseId);
  show($("case-line"), "Case: " + caseId);
  show($("reply"), ""); show($("flags"), "");
  await loadPrompt();
}

async function sendAnswer() {
  const message = $("answer").value;
  if (!caseId || !message.trim()) return;
  try {
    const data = await api("POST", `/api/cases/${caseId}/interview`, { language: language(), message });
    $("answer").value = "";
    show($("reply"), data.message === data.next_prompt ? "" : data.message);
    show($("prompt"), data.next_prompt);
  } catch (e) { show($("reply"), e.message); }
}

async function showFlags() {
  if (!caseId) return;
  try {
    const data = await api("GET", `/api/cases/${caseId}/flags`);
    const lines = [];
    if (!data.application_built) lines.push("The form cannot be checked yet: the interview is not finished.");
    for (const f of data.flags) lines.push(`[${f.severity}] Item ${f.item}: ${f.message}\n    Source: ${f.source}`);
    show($("flags"), lines.join("\n\n") || "No checks to show.");
  } catch (e) { show($("flags"), e.message); }
}

async function deleteCase() {
  if (!caseId || !confirm("Delete this case and all its data permanently?")) return;
  await api("DELETE", `/api/cases/${caseId}`);
  caseId = null; drop("case");
  show($("case-line"), "Case deleted."); show($("prompt"), ""); show($("reply"), ""); show($("flags"), "");
}

// --- reference chat ----------------------------------------------------------------------

async function ask() {
  const message = $("chat-question").value;
  if (!message.trim()) return;
  try {
    const data = await api("POST", "/api/chat", { language: language(), message });
    show($("chat-answer"), data.message);
  } catch (e) { show($("chat-answer"), e.message); }
}

// --- attorney ----------------------------------------------------------------------------

async function refreshCases() {
  const cases = await api("GET", "/api/lawyer/cases");
  const select = $("lawyer-case");
  select.replaceChildren();
  for (const c of cases) {
    const option = document.createElement("option");
    option.value = c.case_id;
    option.textContent = `${c.created_at.slice(0, 16).replace("T", " ")}  ${c.status}  ${c.case_id.slice(0, 8)}`;
    select.appendChild(option);
  }
}

async function openCase() {
  const id = $("lawyer-case").value;
  if (!id) return;
  try {
    const data = await api("GET", `/api/lawyer/cases/${id}/review`);
    show($("lawyer-summary"), data.summary); show($("lawyer-audit"), data.audit_log);
    show($("lawyer-msg"), "");
  } catch (e) { show($("lawyer-msg"), e.message); }
}

async function lawyerAction(fn) {
  const id = $("lawyer-case").value;
  if (!id) return;
  try { show($("lawyer-msg"), (await fn(id)) || "Saved."); await openCase(); }
  catch (e) { show($("lawyer-msg"), e.message); }
}

function parseValue(text) {
  if (text === "true") return true;
  if (text === "false") return false;
  return text;
}

async function fillPdf() {
  const id = $("lawyer-case").value;
  if (!id) return;
  try {
    const data = await api("POST", `/api/lawyer/cases/${id}/fill`);
    const blob = await api("GET", `/api/lawyer/cases/${id}/documents/${data.document_id}`);
    if (lastDocument) URL.revokeObjectURL(lastDocument);
    lastDocument = URL.createObjectURL(blob);
    const link = $("download");
    link.href = lastDocument; link.download = "I-765_draft.pdf"; link.hidden = false;
    show($("lawyer-msg"), `Draft filled: ${data.filled_fields} fields; ${data.skipped} held back for an attorney decision.`);
  } catch (e) { show($("lawyer-msg"), e.message); }
}

// --- wiring ------------------------------------------------------------------------------

$("login-btn").addEventListener("click", () => login($("token").value.trim()));
$("token").addEventListener("keydown", (e) => { if (e.key === "Enter") login($("token").value.trim()); });
$("logout-btn").addEventListener("click", logout);
$("tabs").addEventListener("click", (e) => { if (e.target.dataset.tab) selectTab(e.target.dataset.tab); });
$("language").addEventListener("change", loadPrompt);
$("new-case").addEventListener("click", newCase);
$("send").addEventListener("click", sendAnswer);
$("answer").addEventListener("keydown", (e) => { if (e.key === "Enter") sendAnswer(); });
$("show-flags").addEventListener("click", showFlags);
$("delete-case").addEventListener("click", deleteCase);
$("chat-send").addEventListener("click", ask);
$("chat-question").addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
$("lawyer-refresh").addEventListener("click", refreshCases);
$("lawyer-open").addEventListener("click", openCase);
$("att-save").addEventListener("click", () => lawyerAction(async (id) => {
  await api("POST", `/api/lawyer/cases/${id}/attorney-data`, { path: $("att-path").value.trim(), value: parseValue($("att-value").value) });
}));
$("decision-save").addEventListener("click", () => lawyerAction(async (id) => {
  await api("POST", `/api/lawyer/cases/${id}/decision`, { decision: $("decision").value, note: $("decision-note").value });
}));
$("fill").addEventListener("click", fillPdf);

const saved = load("token");
if (saved) { caseId = load("case"); login(saved).then(() => { if (caseId) { show($("case-line"), "Case: " + caseId); loadPrompt(); } }); }
