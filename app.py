"""Streamlit front end for the Nomura-san client-avatar simulation.

What this app does
------------------
* Shows the analyst's case sheet (the fictional company facts from knowledge_ib.py).
* Embeds a call console that joins the same LiveKit room your agent.py worker serves.
* Mic is OFF by default. The analyst unmutes with the mic button (or Space) to talk,
  and mutes again when done, like a normal meeting.
* The analyst can also type a message instead of speaking.
* "End and get debrief" sends "End simulation" so the avatar gives its scored debrief.

Run:
    pip install -e .
    streamlit run app.py

Needs in .env.local (same file your agent uses):
    LIVEKIT_URL=wss://<your-project>.livekit.cloud
    LIVEKIT_API_KEY=...
    LIVEKIT_API_SECRET=...

Keep the agent worker running in another terminal:
    python agent.py dev
"""

from __future__ import annotations

import importlib
import json
import os
import uuid
from datetime import timedelta

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv()  # also honour a plain .env

KNOWLEDGE_MODULE = os.getenv("KNOWLEDGE_MODULE", "knowledge_ib")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")

st.set_page_config(
    page_title="Pitch practice with Nomura-san",
    page_icon="📞",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container { padding-top: 2rem; padding-bottom: 1rem; max-width: 1400px; }
      h1 { font-size: 1.9rem !important; letter-spacing: -0.01em; }
      .case-note { color: #5B6B82; font-size: 0.9rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Load the scenario
# --------------------------------------------------------------------------- #
@st.cache_resource
def load_scenario(module_name: str) -> dict:
    module = importlib.import_module(module_name)
    return module.MISSION_CONTEXT


try:
    scenario = load_scenario(KNOWLEDGE_MODULE)
except Exception as exc:  # pragma: no cover - surfaced in the UI
    st.error(f"Could not load `{KNOWLEDGE_MODULE}`: {exc}")
    st.stop()

if scenario.get("scenario_type") != "ib_client_roleplay":
    st.error(
        f"`{KNOWLEDGE_MODULE}` is not an `ib_client_roleplay` cartridge. "
        "This UI is built for the equity-pitch simulation. Set KNOWLEDGE_MODULE=knowledge_ib."
    )
    st.stop()

avatar = scenario["avatar"]
stock = scenario["stock_case"]

missing = [
    name
    for name, value in {
        "LIVEKIT_URL": LIVEKIT_URL,
        "LIVEKIT_API_KEY": LIVEKIT_API_KEY,
        "LIVEKIT_API_SECRET": LIVEKIT_API_SECRET,
    }.items()
    if not value
]
if missing:
    st.error(f"Add {', '.join(missing)} to `.env.local`, then reload this page.")
    st.stop()

try:
    from livekit import api as lk_api
except ImportError:
    st.error("Missing dependency. Run `pip install -e .` or `pip install livekit streamlit` and restart Streamlit.")
    st.stop()


# --------------------------------------------------------------------------- #
# Session / token
# --------------------------------------------------------------------------- #
def new_session() -> None:
    """Create a fresh room and join token for this browser session."""
    room_name = f"ib-sim-{uuid.uuid4().hex[:10]}"
    identity = f"analyst-{uuid.uuid4().hex[:6]}"
    token = (
        lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name("Analyst")
        .with_grants(
            lk_api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_ttl(timedelta(hours=1))
        .to_jwt()
    )
    st.session_state.room_name = room_name
    st.session_state.token = token
    st.session_state.session_no = st.session_state.get("session_no", 0) + 1


if "token" not in st.session_state:
    new_session()


# --------------------------------------------------------------------------- #
# The call console (HTML + LiveKit JS client, rendered in an iframe)
# --------------------------------------------------------------------------- #
CONSOLE_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600&family=Public+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/livekit-client@2/dist/livekit-client.umd.min.js"></script>
<style>
  :root {
    --ink: #14213d;
    --muted: #5b6b82;
    --line: #d9e0ea;
    --paper: #ffffff;
    --wash: #f3f6fa;
    --client: #e8eef7;
    --analyst: #14213d;
    --live: #d62839;
    --ok: #1f7a5c;
    --warn: #b7791f;
    --ui: "Public Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
    --read: "Newsreader", Georgia, "Times New Roman", serif;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    font-family: var(--ui); color: var(--ink); background: transparent;
    font-size: 14px; line-height: 1.45;
  }
  button, input { font: inherit; color: inherit; }
  :focus-visible { outline: 2px solid #2f6fdb; outline-offset: 2px; }

  .shell {
    position: relative; height: 100%; display: grid;
    grid-template-rows: auto 1fr auto;
    background: var(--paper); border: 1px solid var(--line); border-radius: 14px;
    overflow: hidden;
  }

  /* header */
  .head {
    display: flex; align-items: center; gap: 12px; padding: 12px 16px;
    border-bottom: 1px solid var(--line); background: var(--wash);
  }
  .avatar {
    width: 40px; height: 40px; border-radius: 50%; flex: none;
    display: grid; place-items: center; background: var(--ink); color: #fff;
    font-family: var(--read); font-weight: 600; font-size: 16px; position: relative;
  }
  .avatar.speaking::after {
    content: ""; position: absolute; inset: -4px; border-radius: 50%;
    border: 2px solid var(--ok); animation: halo 1.4s ease-out infinite;
  }
  @keyframes halo { from { transform: scale(.92); opacity: 1; } to { transform: scale(1.18); opacity: 0; } }
  .who { min-width: 0; flex: 1; }
  .who b { font-family: var(--read); font-size: 17px; font-weight: 600; display: block; }
  .who span { color: var(--muted); font-size: 12.5px; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pills { display: flex; gap: 8px; align-items: center; flex: none; }
  .pill {
    display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
    border: 1px solid var(--line); border-radius: 999px; background: var(--paper);
    font-size: 12.5px; color: var(--muted); white-space: nowrap;
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #9aa6b8; }
  .pill.listening .dot { background: var(--ok); }
  .pill.thinking .dot { background: var(--warn); animation: blink 1s infinite; }
  .pill.speaking .dot { background: var(--ok); animation: blink .7s infinite; }
  @keyframes blink { 50% { opacity: .3; } }
  #timer { font-variant-numeric: tabular-nums; }

  /* transcript */
  .log { overflow-y: auto; padding: 18px 16px 8px; display: flex; flex-direction: column; gap: 12px; scroll-behavior: smooth; }
  .msg { max-width: min(82%, 640px); display: flex; flex-direction: column; gap: 3px; }
  .msg .meta { font-size: 11.5px; color: var(--muted); }
  .msg .body {
    font-family: var(--read); font-size: 16.5px; line-height: 1.5;
    padding: 9px 14px; border-radius: 14px; white-space: pre-wrap; overflow-wrap: anywhere;
  }
  .msg.client { align-self: flex-start; }
  .msg.client .body { background: var(--client); border-top-left-radius: 4px; }
  .msg.analyst { align-self: flex-end; align-items: flex-end; }
  .msg.analyst .body { background: var(--analyst); color: #fff; border-top-right-radius: 4px; }
  .msg.system { align-self: center; max-width: 90%; }
  .msg.system .body {
    font-family: var(--ui); font-size: 12.5px; color: var(--muted);
    background: transparent; padding: 2px 8px; text-align: center;
  }
  .tag { border: 1px solid var(--line); border-radius: 4px; padding: 0 5px; margin-left: 6px; font-size: 11px; }
  .score {
    display: inline-flex; align-items: baseline; gap: 4px; margin-bottom: 6px;
    padding: 4px 12px; border-radius: 8px; background: var(--paper); border: 1px solid var(--line);
    font-family: var(--ui);
  }
  .score b { font-size: 24px; font-weight: 600; }
  .score span { color: var(--muted); }
  .typing { align-self: flex-start; display: inline-flex; gap: 4px; padding: 10px 14px; background: var(--client); border-radius: 14px; }
  .typing i { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); animation: blink 1s infinite; }
  .typing i:nth-child(2) { animation-delay: .15s; }
  .typing i:nth-child(3) { animation-delay: .3s; }
  .hidden { display: none !important; }

  /* composer */
  .composer { border-top: 1px solid var(--line); padding: 12px 16px 12px; background: var(--paper); }
  .row { display: flex; align-items: center; gap: 12px; }
  .mic {
    --lvl: 0; flex: none; width: 60px; height: 60px; border-radius: 50%;
    border: 1.5px solid var(--line); background: var(--wash); cursor: pointer;
    display: grid; place-items: center; transition: background .15s, border-color .15s;
    box-shadow: 0 0 0 calc(var(--lvl) * 16px) rgba(214, 40, 57, .22);
  }
  .mic svg { width: 26px; height: 26px; }
  .mic:hover:not(:disabled) { border-color: var(--ink); }
  .mic:disabled { opacity: .45; cursor: not-allowed; }
  .mic.live { background: var(--live); border-color: var(--live); color: #fff; }
  .mic.finishing { background: #f6d7db; border-color: var(--live); color: var(--live); }
  .mic .slash { display: block; }
  .mic.live .slash, .mic.finishing .slash { display: none; }
  .field { flex: 1; display: flex; gap: 8px; min-width: 0; }
  .field input {
    flex: 1; min-width: 0; padding: 12px 14px; border: 1px solid var(--line);
    border-radius: 10px; background: var(--paper); font-size: 14.5px;
  }
  .field input:disabled { background: var(--wash); }
  .btn {
    padding: 10px 14px; border-radius: 10px; border: 1px solid var(--line);
    background: var(--paper); cursor: pointer; white-space: nowrap; font-weight: 500;
  }
  .btn:hover:not(:disabled) { border-color: var(--ink); }
  .btn:disabled { opacity: .45; cursor: not-allowed; }
  .btn.primary { background: var(--ink); border-color: var(--ink); color: #fff; }
  .btn.quiet { border-color: transparent; color: var(--muted); padding: 6px 10px; font-weight: 400; }
  .btn.quiet:hover:not(:disabled) { color: var(--ink); border-color: var(--line); }
  .sub { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-top: 8px; }
  #micHint { color: var(--muted); font-size: 12.5px; }
  #micHint.live { color: var(--live); font-weight: 500; }
  .tools { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
  .switch { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); font-size: 12.5px; cursor: pointer; padding: 6px 10px; }
  .switch input { accent-color: var(--ink); }
  #notice { color: var(--live); font-size: 12.5px; min-height: 18px; margin-top: 4px; }

  /* join overlay */
  .overlay {
    position: absolute; inset: 0; z-index: 5; display: grid; place-items: center; padding: 24px;
    background: rgba(243, 246, 250, .96); text-align: center;
  }
  .overlay .card { max-width: 440px; }
  .overlay h2 { font-family: var(--read); font-size: 24px; margin: 0 0 8px; font-weight: 600; }
  .overlay p { color: var(--muted); margin: 0 0 18px; font-size: 14.5px; }
  .overlay .btn.primary { padding: 12px 26px; font-size: 15px; }
  .overlay ul { text-align: left; color: var(--muted); font-size: 13.5px; margin: 0 auto 20px; padding-left: 18px; max-width: 360px; }

  @media (max-width: 640px) {
    .pills .pill:first-child { display: none; }
    .msg { max-width: 94%; }
    .row { flex-wrap: wrap; }
    .field { flex-basis: 100%; order: 3; }
  }
  @media (prefers-reduced-motion: reduce) {
    * { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
  }
</style>
</head>
<body>
<div class="shell">
  <header class="head">
    <div class="avatar" id="avatar" aria-hidden="true"></div>
    <div class="who"><b id="clientName"></b><span id="clientRole"></span></div>
    <div class="pills">
      <span class="pill" id="statePill"><i class="dot"></i><span id="stateText">Not connected</span></span>
      <span class="pill" id="timer" title="Call length">00:00</span>
    </div>
  </header>

  <main class="log" id="log" aria-live="polite"></main>

  <footer class="composer">
    <div class="row">
      <button class="mic" id="mic" disabled aria-pressed="false" aria-label="Unmute microphone" title="Click to unmute (Space)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <rect x="9" y="3" width="6" height="11" rx="3"></rect>
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3"></path>
          <path class="slash" d="M4 4l16 16" stroke="#d62839"></path>
        </svg>
      </button>
      <div class="field">
        <input id="text" type="text" placeholder="Type your reply instead of speaking" autocomplete="off" disabled aria-label="Type a message to Nomura-san">
        <button class="btn primary" id="send" disabled>Send</button>
      </div>
    </div>
    <div class="sub">
      <span id="micHint">Your mic is off.</span>
      <div class="tools">
        <label class="switch"><input type="checkbox" id="voice" checked> Hear Nomura-san's voice</label>
        <button class="btn quiet" id="download" disabled>Save transcript</button>
        <button class="btn" id="debrief" disabled>End and get debrief</button>
        <button class="btn quiet" id="leave" disabled>Leave</button>
      </div>
    </div>
    <div id="notice" role="status"></div>
  </footer>

  <div class="overlay" id="overlay">
    <div class="card">
      <h2 id="ovTitle">Ready when you are</h2>
      <p id="ovText">Nomura-san has about ten minutes before the next meeting.</p>
      <ul id="ovList">
        <li>Your mic starts off. Click the mic button or press Space to talk, and click again to mute.</li>
        <li>You can type instead of speaking at any time.</li>
        <li>When you finish, choose End and get debrief for your score.</li>
      </ul>
      <button class="btn primary" id="join">Join meeting</button>
    </div>
  </div>
</div>

<script>
(function () {
  const CFG = __CONFIG__;
  const $ = (id) => document.getElementById(id);
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const MIC_TAIL_MS = 900;   // keep sending silence briefly after mute so the agent can detect end of speech
  const MERGE_MS = 2500;     // merge sentence-by-sentence agent chunks into one bubble

  const S = {
    room: null, micOn: false, micBusy: false, agentState: "initializing",
    messages: [], joinedAt: null, timerId: null, lvl: 0, connected: false, ended: false,
  };
  const audioEls = [];

  $("clientName").textContent = CFG.clientName;
  $("clientRole").textContent = CFG.clientRole;
  $("avatar").textContent = CFG.initials;

  /* ---------- helpers ---------- */
  const norm = (t) => t.toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
  const hhmm = (d) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const isAgent = (p) => !!p && (p.isAgent === true ||
    (window.LivekitClient && LivekitClient.ParticipantKind && p.kind === LivekitClient.ParticipantKind.AGENT) ||
    String(p.identity || "").startsWith("agent"));
  const agentPresent = () => !!S.room && [...S.room.remoteParticipants.values()].some(isAgent);

  let noticeTimer = null;
  function notice(text) {
    $("notice").textContent = text;
    clearTimeout(noticeTimer);
    if (text) noticeTimer = setTimeout(() => ($("notice").textContent = ""), 6000);
  }

  /* ---------- transcript ---------- */
  function addMessage(role, text, opts = {}) {
    text = (text || "").trim();
    if (!text) return;
    const now = Date.now();
    const recent = S.messages.slice(-6);
    if (role !== "system" && recent.some((m) => m.role === role && norm(m.text) === norm(text) && now - m.t < 10000)) return;

    const last = S.messages[S.messages.length - 1];
    if (role === "client" && last && last.role === "client" && now - last.t < MERGE_MS) {
      last.text += " " + text;
      last.t = now;
    } else {
      S.messages.push({
        role,
        text,
        t: now,
        at: new Date(),
        typed: !!opts.typed,
        speaker: opts.speaker || null,
      });
    }
    render();
  }

  function render() {
    const log = $("log");
    log.innerHTML = "";
    S.messages.forEach((m) => {
      const wrap = document.createElement("div");
      wrap.className = "msg " + m.role;
      if (m.role !== "system") {
        const meta = document.createElement("div");
        meta.className = "meta";
        const speakerLabel = m.speaker || (m.role === "client" ? CFG.clientName : "You");
        meta.textContent = speakerLabel + "  " + hhmm(m.at);
        if (m.typed) {
          const tag = document.createElement("span");
          tag.className = "tag"; tag.textContent = "typed";
          meta.appendChild(tag);
        }
        wrap.appendChild(meta);
      }
      const body = document.createElement("div");
      body.className = "body";
      const score = m.role === "client" && m.text.match(/Analyst score:\s*(\d{1,3})\s*\/\s*100/i);
      if (score) {
        const chip = document.createElement("div");
        chip.className = "score";
        chip.innerHTML = "<b></b><span>/ 100</span>";
        chip.querySelector("b").textContent = score[1];
        body.appendChild(chip);
        body.appendChild(document.createElement("br"));
      }
      body.appendChild(document.createTextNode(m.text));
      wrap.appendChild(body);
      log.appendChild(wrap);
    });
    if (S.agentState === "thinking") {
      const t = document.createElement("div");
      t.className = "typing";
      t.innerHTML = "<i></i><i></i><i></i>";
      log.appendChild(t);
    }
    log.scrollTop = log.scrollHeight;
  }

  /* ---------- agent state ---------- */
  function setAgentState(s) {
    S.agentState = s;
    const pill = $("statePill");
    pill.className = "pill " + s;
    const labels = {
      initializing: "Nomura-san is joining", idle: "Listening", listening: "Listening",
      thinking: "Thinking", speaking: "Speaking",
    };
    $("stateText").textContent = labels[s] || s;
    $("avatar").classList.toggle("speaking", s === "speaking");
    render();
  }

  function refreshPresence() {
    if (!S.connected) return;
    if (!agentPresent()) {
      $("stateText").textContent = "Waiting for Nomura-san";
      $("statePill").className = "pill";
    } else if (S.agentState === "initializing") {
      setAgentState("listening");
    }
  }

  /* ---------- mic (mute / unmute, like a normal meeting) ---------- */
  function updateMicUI() {
    const mic = $("mic"), hint = $("micHint");
    mic.classList.toggle("live", S.micOn);
    mic.classList.toggle("finishing", !S.micOn && S.micBusy);
    mic.setAttribute("aria-pressed", String(S.micOn));
    mic.disabled = !S.connected || S.ended || (S.micBusy && !S.micOn);
    mic.setAttribute("aria-label", S.micOn ? "Mute microphone" : "Unmute microphone");
    mic.title = S.micOn ? "Click to mute (Space)" : "Click to unmute (Space)";
    hint.classList.toggle("live", S.micOn);
    if (S.micOn) hint.textContent = "Mic is live. Click the mic to mute when you finish.";
    else if (S.micBusy) hint.textContent = "Finishing your last words...";
    else hint.textContent = "Your mic is off. Click the mic or press Space to talk.";
    if (!S.micOn) mic.style.setProperty("--lvl", 0);
  }

  async function setMic(on) {
    if (!S.room || S.micBusy) return;
    S.micBusy = true;
    try {
      if (on) {
        await S.room.localParticipant.setMicrophoneEnabled(true);
        S.micOn = true;
      } else {
        S.micOn = false;
        updateMicUI();
        await sleep(MIC_TAIL_MS);
        await S.room.localParticipant.setMicrophoneEnabled(false);
      }
    } catch (e) {
      S.micOn = false;
      notice("Could not access the microphone. Allow mic access in your browser, or type your reply instead.");
    } finally {
      S.micBusy = false;
      updateMicUI();
    }
  }

  function levelLoop() {
    if (S.micOn && S.room) {
      const target = Math.min(1, (S.room.localParticipant.audioLevel || 0) * 2.2);
      S.lvl += (target - S.lvl) * 0.25;
      $("mic").style.setProperty("--lvl", S.lvl.toFixed(3));
    }
    requestAnimationFrame(levelLoop);
  }

  /* ---------- sending typed text ---------- */
  async function sendTyped() {
    const input = $("text");
    const text = input.value.trim();
    if (!text || !S.room) return;
    input.value = "";
    addMessage("analyst", text, { typed: true });
    try {
      await S.room.localParticipant.sendText(text, { topic: "lk.chat" });
    } catch (e) {
      notice("Message did not send. Check your connection and try again.");
    }
  }

  /* ---------- connect ---------- */
  function setConnectedUI(on) {
    S.connected = on;
    ["text", "send", "debrief", "leave", "download"].forEach((id) => ($(id).disabled = !on));
    updateMicUI();
  }

  async function join() {
    if (typeof LivekitClient === "undefined") {
      notice("The LiveKit client script did not load. Check your internet connection and reload.");
      return;
    }
    const { Room, RoomEvent, Track } = LivekitClient;
    $("join").disabled = true;
    $("join").textContent = "Connecting...";
    const room = new Room({ adaptiveStream: true, dynacast: true });
    S.room = room;

    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) {
        const el = track.attach();
        el.muted = !$("voice").checked;
        el.style.display = "none";
        document.body.appendChild(el);
        audioEls.push(el);
      }
    });
    room.on(RoomEvent.TrackUnsubscribed, (track) => track.detach());

    room.on(RoomEvent.DataReceived, (payload, participant, kind, topic) => {
      if (topic !== "transcript") return;
      try {
        const msg = JSON.parse(new TextDecoder().decode(payload));
        const type = msg.type || "system";
        const role = type === "agent_response" ? "client" : type === "user_input" ? "analyst" : "system";
        const speaker = msg.speaker || (role === "client" ? CFG.clientName : "You");
        if (role === "system") {
          addMessage("system", msg.text || "Transcript update");
        } else {
          addMessage(role, msg.text, { speaker });
        }
      } catch (e) { /* ignore malformed packets */ }
    });

    room.on(RoomEvent.ParticipantAttributesChanged, (participant, changedAttributes) => {
      if (isAgent(participant) && changedAttributes && Object.prototype.hasOwnProperty.call(changedAttributes, "lk.agent.state")) {
        setAgentState(changedAttributes["lk.agent.state"]);
      }
    });
    room.on(RoomEvent.ParticipantConnected, (p) => {
      if (isAgent(p)) { setAgentState("listening"); addMessage("system", "Nomura-san joined the call."); }
    });
    room.on(RoomEvent.ParticipantDisconnected, (p) => {
      if (isAgent(p)) { addMessage("system", "Nomura-san left the call."); refreshPresence(); }
    });
    room.on(RoomEvent.Disconnected, () => finish("The call has ended."));

    try {
      await room.connect(CFG.url, CFG.token);
      await room.startAudio();
    } catch (e) {
      $("join").disabled = false;
      $("join").textContent = "Join meeting";
      notice("Could not connect: " + (e && e.message ? e.message : "unknown error") + ". Is your LiveKit URL correct?");
      return;
    }

    setConnectedUI(true);
    $("overlay").classList.add("hidden");
    S.joinedAt = Date.now();
    S.timerId = setInterval(() => {
      const s = Math.floor((Date.now() - S.joinedAt) / 1000);
      $("timer").textContent = String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
    }, 1000);
    addMessage("system", "You joined with your mic off. Waiting for Nomura-san to pick up.");
    room.remoteParticipants.forEach((p) => {
      if (isAgent(p)) setAgentState(p.attributes && p.attributes["lk.agent.state"] || "listening");
    });
    refreshPresence();
    $("text").focus();
  }

  function finish(message) {
    if (S.ended) return;
    S.ended = true;
    clearInterval(S.timerId);
    setConnectedUI(false);
    $("download").disabled = S.messages.length === 0;
    S.micOn = false; updateMicUI();
    $("stateText").textContent = "Call ended";
    $("statePill").className = "pill";
    $("avatar").classList.remove("speaking");
    addMessage("system", message);
    $("ovTitle").textContent = "Call ended";
    $("ovText").textContent = "Save your transcript below, or start a new session from the sidebar to try again.";
    $("ovList").classList.add("hidden");
    $("join").classList.add("hidden");
    if (!$("saveEnd")) {
      const b = document.createElement("button");
      b.className = "btn primary"; b.id = "saveEnd"; b.textContent = "Save transcript";
      b.onclick = downloadTranscript;
      const v = document.createElement("button");
      v.className = "btn quiet"; v.textContent = "Review the conversation";
      v.onclick = () => $("overlay").classList.add("hidden");
      $("overlay").querySelector(".card").append(b, document.createTextNode(" "), v);
    }
    $("overlay").classList.remove("hidden");
  }

  async function endAndDebrief() {
    if (!S.room) return;
    if (S.micOn) await setMic(false);
    addMessage("system", "You asked for the debrief.");
    try {
      await S.room.localParticipant.sendText("End simulation. Please give me my debrief.", { topic: "lk.chat" });
    } catch (e) {
      notice("Could not request the debrief. Check your connection and try again.");
    }
  }

  function downloadTranscript() {
    const lines = S.messages.map((m) => {
      const who = m.role === "client" ? CFG.clientName : m.role === "analyst" ? "Analyst" : "Note";
      return "[" + hhmm(m.at) + "] " + who + (m.typed ? " (typed)" : "") + ": " + m.text;
    });
    const blob = new Blob([lines.join("\n\n")], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "pitch-practice-transcript.txt";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  /* ---------- wiring ---------- */
  $("join").onclick = join;
  $("mic").onclick = () => setMic(!S.micOn);
  $("send").onclick = sendTyped;
  $("text").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendTyped(); } });
  $("debrief").onclick = endAndDebrief;
  $("leave").onclick = async () => { if (S.micOn) await setMic(false); S.room && S.room.disconnect(); };
  $("download").onclick = downloadTranscript;
  $("voice").onchange = () => audioEls.forEach((el) => (el.muted = !$("voice").checked));
  document.addEventListener("keydown", (e) => {
    if (e.code !== "Space" || e.repeat || !S.connected) return;
    const tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "BUTTON") return;
    e.preventDefault();
    setMic(!S.micOn);
  });
  window.addEventListener("beforeunload", () => { try { S.room && S.room.disconnect(); } catch (e) {} });

  updateMicUI();
  requestAnimationFrame(levelLoop);
})();
</script>
</body>
</html>
"""


def render_console(token: str, height: int = 780) -> None:
    cfg = {
        "url": LIVEKIT_URL,
        "token": token,
        "clientName": avatar["name"],
        "clientRole": avatar["role"],
        "initials": "".join(part[0] for part in avatar["name"].split()[:2]).upper(),
    }
    payload = json.dumps(cfg).replace("</", "<\\/")
    components.html(CONSOLE_HTML.replace("__CONFIG__", payload), height=height, scrolling=False)


# --------------------------------------------------------------------------- #
# Page layout
# --------------------------------------------------------------------------- #
def pretty(key: str) -> str:
    return key.replace("_", " ").capitalize()


with st.sidebar:
    st.header("Session")
    st.caption(f"Room: `{st.session_state.room_name}`")
    if st.button("Start a new session", use_container_width=True):
        new_session()
        st.rerun()
    st.divider()
    st.markdown(
        "**Before you join**\n\n"
        "- Run `python agent.py dev` so Nomura-san can pick up.\n"
        "- Use Chrome, Edge or Safari. Mic access needs `localhost` or HTTPS.\n"
        "- Your mic stays off until you click it."
    )

st.title("Pitch practice with " + avatar["name"])
st.caption(f"{avatar['role']}. Practice discovery and a balanced pitch. Everything in this case is fictional.")

left, right = st.columns([2, 3], gap="large")

with left:
    st.subheader("Your case sheet")
    st.markdown(f"**{stock['company']}**  \n{stock['ticker']}")
    st.write(stock["business"])
    st.markdown(f"**Thesis.** {stock['investment_thesis']}")

    with st.container(border=True):
        for key, value in stock["fictional_case_facts"].items():
            c1, c2 = st.columns([2, 3])
            c1.markdown(f"<span class='case-note'>{pretty(key)}</span>", unsafe_allow_html=True)
            c2.write(value)

    with st.expander("Catalysts"):
        for item in stock["potential_catalysts"]:
            st.markdown(f"- {item}")
    with st.expander("Risks to be ready for"):
        for item in stock["material_risks"]:
            st.markdown(f"- {item}")
    with st.expander("What a good pitch does"):
        st.write(stock["balanced_pitch_expectation"])

with right:
    # The token lives in session_state, so this HTML is identical across reruns and the call is not reset.
    render_console(st.session_state.token)