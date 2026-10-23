# IB Equity-Pitch Practice with LiveKit

A real-time LiveKit voice roleplay for investment-banking equity-pitch practice. A junior analyst pitches a fictional stock to Nomura-san, a simulated institutional client.

---

## What It Does

- 🎤 Listens to client speech in real-time
- 💬 Responds as a simulated client avatar for analyst training
- 📊 Uses a fictional stock case with client-specific objectives and objections
- 📡 Broadcasts conversation to your frontend

---

## Quick Start

### 1. Install Dependencies

Use Python 3.11 or newer. From the project root, create and activate a virtual environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

In Command Prompt, activate with `.\.venv\Scripts\activate.bat` instead. On macOS or Linux, use `python3 -m venv .venv` and `source .venv/bin/activate`.

Then install the project dependencies from the included requirements file:

```bash
python -m pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env.local` in the project root, then replace the API key placeholders with your Groq and Deepgram API keys. The example uses local LiveKit development credentials:

```powershell
# Windows PowerShell
Copy-Item .env.example .env.local
```

On macOS or Linux, run `cp .env.example .env.local`.

Keep `.env.local` private; it is ignored by Git. The LiveKit URL and `devkey`/`secret` values are for the local development server below. For a hosted LiveKit project, use its URL, API key, and API secret instead.

### 3. Start the Three Services

Open three terminals in the project root and leave each process running:

**Terminal 1 — LiveKit server (Docker):**

```bash
docker run --rm -p 7880:7880 -p 7881:7881 -p 7882:7882/udp livekit/livekit-server --dev --bind 0.0.0.0 --node-ip 127.0.0.1
```

**Terminal 2 — Voice agent:**

```powershell
.\.venv\Scripts\Activate.ps1
python agent.py dev
```

**Terminal 3 — Streamlit app:**

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run app.py
```

Activate the virtual environment in both Python terminals. In Command Prompt use `.\.venv\Scripts\activate.bat`; on macOS or Linux use `source .venv/bin/activate`.

Open the local URL Streamlit prints (normally `http://localhost:8501`) and join the meeting. Allow microphone access in your browser if you want to speak; you can also type messages. Keep all three terminals running for the session.

The roleplay features Nomura-san and the fictional Asterion Grid Storage (AGS) equity case. The agent uses Groq for the language model and Deepgram for speech recognition and voice.

---

## Project Structure

```
.
├── agent.py              ← LiveKit voice agent
├── app.py                ← Streamlit call interface
├── knowledge_ib.py       ← Fictional IB stock-pitch roleplay
├── .env.example          ← Environment variable template
├── requirements.txt      ← Python dependencies
├── README.md
└── .gitignore
```

## Roleplay

- **Client:** Nomura-san, CIO at a regional public pension fund
- **Exercise:** Pitch Asterion Grid Storage (AGS), a fictional grid-scale battery company
- **Focus:** Discovery, thesis clarity, valuation, risk, and objection handling
- **Debrief:** Request a debrief or end the simulation to receive a score and feedback

The scenario, client profile, fictional case facts, and roleplay guidance are defined in `knowledge_ib.py`.

---

## 📡 Real-Time Features

### Transcript Broadcasting
- Client speech → logged + sent to frontend
- Agent speech → logged + sent to frontend
- Frontend receives via WebSocket data channel

### Voice Quality
- **STT**: Deepgram Nova-2 (high accuracy)
- **LLM**: Groq (model configurable with `GROQ_MODEL`)
- **TTS**: Deepgram Aura (natural sounding)
- **VAD**: Silero (detects when client is speaking)

---

## 🔧 Customization

Edit the IB scenario and roleplay guidance in `knowledge_ib.py`.

### Change LLM Model
Set `GROQ_MODEL` in `.env.local`:
```python
GROQ_MODEL=your-model-here
```

### Change Voice
Edit the TTS model setting in `agent.py`:
```python
tts=TranscriptCaptureTTS(model="your-voice-here")
```

---

## ⚠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| Can't connect to LiveKit | Confirm the Docker server is running and `.env.local` has `LIVEKIT_URL=ws://localhost:7880`, `LIVEKIT_API_KEY=devkey`, and `LIVEKIT_API_SECRET=secret` |
| Agent reports missing API keys | Set valid `GROQ_API_KEY` and `DEEPGRAM_API_KEY` values in `.env.local`, then restart the agent |
| Streamlit cannot join the room | Confirm the server and agent are running, check the LiveKit values in `.env.local`, and reload the app |
| Client not recognized | Verify client is in same room with unique identity |
| No transcript appearing | Check frontend is listening on "transcript" data channel |
| Poor speech quality | Adjust VAD parameters in `agent.py` entrypoint() |
| Agent is too slow | Check Groq API status |

---

## 📝 Environment Variables

| Variable | Required | Example |
|----------|----------|---------|
| `GROQ_API_KEY` | Yes | Your Groq API key |
| `DEEPGRAM_API_KEY` | Yes | Your Deepgram API key |
| `LIVEKIT_URL` | Yes | `ws://localhost:7880` |
| `LIVEKIT_API_KEY` | Yes | `devkey` for local development |
| `LIVEKIT_API_SECRET` | Yes | `secret` for local development |
| `GROQ_MODEL` | No | Model name used by Groq; defaults to the value configured in `agent.py` |

---

## 🎬 Production Checklist

- [ ] API keys configured (don't commit `.env.local`)
- [ ] LiveKit server running and reachable
- [ ] Dependencies installed (`python -m pip install -r requirements.txt`)
- [ ] Test connection with sample client
- [ ] Verify transcript reaches frontend
- [ ] Check logs for errors
- [ ] Use production LiveKit deployment

---

## 📚 File Breakdown

| File | Purpose |
|------|---------|
| `agent.py` | Main agent orchestration, speech processing, LiveKit integration |
| `app.py` | Streamlit browser interface for the roleplay |
| `knowledge_ib.py` | Fictional institutional client avatar and IB stock-pitch training case |
| `.env.example` | Safe template for local environment variables |
| `requirements.txt` | Python dependencies for pip installation |
| `.gitignore` | Excludes Python, logs, env files, IDE files |
| `README.md` | This file |

---

## 🤝 Support

For issues, check the logs:
```bash
# Agent logs to console + application logger
# Look for AGENT_SAID, USER_SAID, and error messages
```

---

**Ready to practice?** Set your `.env.local`, start the three services, and join the roleplay.
