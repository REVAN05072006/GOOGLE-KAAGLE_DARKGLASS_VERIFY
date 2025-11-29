# app.py
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv
load_dotenv()

from sessions import session_store
from agents import GeneratorAgent, ValidatorAgent

app = Flask(__name__, static_folder="static", static_url_path="/static")
generator = GeneratorAgent()
validator = ValidatorAgent()

INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>DARKGLASS VERIFY</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">

  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">

  <style>
    :root {
      --bg: #0d0f17;
      --glass-bg: rgba(255, 255, 255, 0.06);
      --glass-border: rgba(255, 255, 255, 0.12);
      --primary: #4e8cff;
      --primary-glow: rgba(78, 140, 255, 0.6);
      --text: #e5e7ef;
      --text-dim: #9aa0b8;
    }

    /* NEW — Fully center page */
    body {
      margin: 0;
      padding: 0;
      background: radial-gradient(circle at top, #151823, #0d0f17);
      font-family: 'Inter', sans-serif;
      color: var(--text);
      min-height: 100vh;

      display: flex;
      justify-content: center;
      align-items: center;
    }

    /* Wrapper centered by flex — no auto margins */
    .wrapper {
      max-width: 960px;
      width: 100%;
      padding: 20px;
      text-align: center;
    }

    .title {
      font-size: 34px;
      font-weight: 700;
      margin-bottom: 8px;
      background: linear-gradient(90deg, #4e8cff, #8ab5ff);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }

    .subtitle {
      font-size: 15px;
      color: var(--text-dim);
      margin-bottom: 26px;
    }

    .card {
      backdrop-filter: blur(16px) saturate(140%);
      -webkit-backdrop-filter: blur(16px) saturate(140%);
      background: var(--glass-bg);
      border-radius: 18px;
      border: 1px solid var(--glass-border);
      box-shadow: 0 10px 40px rgba(0,0,0,0.5);
      padding: 28px;
      animation: fadeIn 0.35s ease;
      text-align: left;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(10px); }
      to   { opacity: 1; transform: translateY(0); }
    }

    .control-row {
      display: flex;
      gap: 12px;
      margin-bottom: 12px;
      justify-content: flex-start;
      align-items: center;
      flex-wrap: wrap;
    }

    button {
      background: transparent;
      border: 1px solid var(--primary);
      color: var(--text);
      padding: 10px 14px;
      font-size: 14px;
      font-weight: 600;
      border-radius: 12px;
      cursor: pointer;
      transition: 0.22s ease;
      box-shadow: 0 0 10px rgba(78,140,255,0.08);
    }

    button:hover {
      background: var(--primary);
      color: white;
      box-shadow: 0 0 18px var(--primary-glow);
      transform: translateY(-2px);
    }

    input[type=text] {
      width: 100%;
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid var(--glass-border);
      background: rgba(255,255,255,0.03);
      color: var(--text);
      margin-top: 12px;
    }

    input[type=text]:focus {
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 10px var(--primary-glow);
    }

    .instructions {
      border-left: 4px solid var(--primary);
      padding: 14px;
      background: rgba(255,255,255,0.03);
      border-radius: 10px;
      font-size: 14px;
      margin-bottom: 14px;
      color: var(--text-dim);
    }

    .shapes { display:flex; gap:10px; flex-wrap:wrap; margin-top: 12px; }
    .shape {
      padding: 12px 16px;
      border-radius: 12px;
      background: rgba(255,255,255,0.03);
      border: 1px solid var(--glass-border);
      cursor: pointer;
      color: var(--text);
      font-weight: 700;
      transition: 0.15s;
    }
    .shape:hover { background: rgba(78,140,255,0.12); }
    .shape.selected { background: rgba(78,140,255,0.28); box-shadow: 0 0 14px var(--primary-glow); border-color: var(--primary); }

    canvas, img.color-box {
      border-radius: 14px;
      border: 1px solid var(--glass-border);
      margin-top: 12px;
      max-width: 100%;
      display: block;
    }

    audio { width: 100%; margin-top: 12px; }

    .result {
      margin-top: 14px;
      font-size: 15px;
      font-weight: 600;
      color: var(--text);
    }

    .small { font-size: 13px; color: var(--text-dim); margin-top:6px }
  </style>
</head>

<body>
  <div class="wrapper">
    <div class="title">DARKGLASS VERIFY</div>
    <div class="subtitle">See. Hear. Solve. Prove You’re Human.</div>

    <div class="card">

      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
        <div class="control-row" style="margin:0;flex:1 1 auto;">
          <button id="newSessionBtn">New Session</button>
          <button id="genBtn">Generate CAPTCHA</button>
        </div>

        <div style="flex:0 0 auto;text-align:right;">
          <div id="sessionLabel" class="small"></div>
        </div>
      </div>

      <div id="captchaArea" style="margin-top:18px"></div>
      <div id="result" class="result"></div>
    </div>
  </div>

<script>
/* JS FULLY WORKING — SAME AS LAST VERSION */

let sessionId = null;

document.getElementById("newSessionBtn").onclick = async () => {
  try {
    const r = await fetch("/session", {method:"POST"});
    const j = await r.json();
    sessionId = j.session_id;
    document.getElementById("sessionLabel").innerText = "Session: " + sessionId;
    document.getElementById("captchaArea").innerHTML = "";
    document.getElementById("result").innerText = "";
  } catch (err) {
    console.error(err);
    alert("Failed to create session");
  }
};

document.getElementById("genBtn").onclick = async () => {
  if(!sessionId){ alert("Create a session first."); return; }
  try {
    const r = await fetch(`/captcha/${sessionId}`);
    const j = await r.json();
    if(j.error){ alert("Error: " + j.error); return; }
    renderCaptcha(j);
  } catch (err) {
    console.error(err);
    alert("Failed to generate captcha");
  }
};

function renderCaptcha(data){
  const area = document.getElementById("captchaArea");
  area.innerHTML = "";

  const inst = document.createElement("div");
  inst.className = "instructions";
  inst.innerText = data.instructions || "";
  area.appendChild(inst);

  const type = data.captcha_type;
  const ui = data.ui_data || {};

  // IMAGE CAPTCHA
  if(type === "image"){
    const img = new Image();
    img.src = ui.image_base64;
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = img.width;
      canvas.height = img.height;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0);
      canvas.onclick = (ev)=>{
        const r = canvas.getBoundingClientRect();
        const x = Math.round((ev.clientX - r.left) * (canvas.width / r.width));
        const y = Math.round((ev.clientY - r.top) * (canvas.height / r.height));
        ctx.drawImage(img, 0, 0);
        ctx.beginPath(); ctx.arc(x,y,8,0,Math.PI*2);
        ctx.strokeStyle="#4e8cff"; ctx.lineWidth=3; ctx.stroke();
        verify({x,y});
      };
      area.appendChild(canvas);
    };
    return;
  }

  // AUDIO CAPTCHA
  if(type === "audio"){
    const a=document.createElement("audio");
    a.controls=true;
    a.src=ui.audio_base64;
    area.appendChild(a);
    renderInput(area, ui.hint || "Type what you hear", verify);
    return;
  }

  // PATTERN CAPTCHA
// -------------------------------------------------------------
// PATTERN CAPTCHA (Option A — Show selected order dynamically)
// -------------------------------------------------------------
// -------------------------------------------------------------
// PATTERN CAPTCHA (Displays required order + shows user clicks)
// -------------------------------------------------------------
if(type === "pattern"){
    const clueBox = document.createElement("div");
    clueBox.className = "instructions";
    clueBox.innerText = "Click in order: " + (ui.clue || "(missing clue)");
    area.appendChild(clueBox);

    const wrap = document.createElement("div");
    wrap.className = "shapes";

    let seq = [];

    (ui.shapes || []).forEach((shape, index) => {
        const el = document.createElement("div");
        el.className = "shape";
        el.innerText = shape;
        el.dataset.index = index;

        el.onclick = () => {
            if (!el.classList.contains("selected")) {
                el.classList.add("selected");
                seq.push(index);
                updateSeq();
            }
        };

        wrap.appendChild(el);
    });

    area.appendChild(wrap);

    const seqDisplay = document.createElement("div");
    seqDisplay.className = "small";
    seqDisplay.style.marginTop = "12px";
    seqDisplay.innerText = "Your selection: (none)";
    area.appendChild(seqDisplay);

    function updateSeq() {
        seqDisplay.innerText =
            seq.length === 0 ? "Your selection: (none)"
                              : "Your selection: " + seq.join(" → ");
    }

    renderButton(area, "Verify", () => verify(seq));
    return;
}


  // COLOR CAPTCHA
  if(type === "color"){
    const img=new Image();
    img.className="color-box";
    img.src=ui.image_base64;
    area.appendChild(img);
    renderInput(area, ui.hint || "Enter color name or hex", verify);
    return;
  }

  // TEXT / MATH CAPTCHA
  if(type==="text"||type==="math"){
    const q=document.createElement("div");
    q.className="small";
    q.innerText=ui.question;
    area.appendChild(q);
    renderInput(area, ui.hint||"Enter answer", verify);
    return;
  }
}

function renderInput(area, placeholder, cb){
  const input=document.createElement("input");
  input.type="text"; input.placeholder=placeholder;
  area.appendChild(input);
  renderButton(area,"Verify",()=>cb(input.value));
}

function renderButton(area,label,cb){
  const btn=document.createElement("button");
  btn.innerText=label;
  btn.style.marginTop="12px";
  btn.onclick=cb;
  area.appendChild(btn);
}

async function verify(answer){
  document.getElementById("result").innerText = "Verifying...";
  try{
    const r=await fetch(`/validate/${sessionId}`,{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({answer})
    });
    const j=await r.json();
    if(j.success){
      document.getElementById("result").style.color="#2ecc71";
      document.getElementById("result").innerText="✔ "+(j.message||"Correct");
    } else {
      document.getElementById("result").style.color="#ff6b6b";
      document.getElementById("result").innerText="✘ "+(j.error||j.message||"Incorrect");
    }
  } catch(e){
    document.getElementById("result").innerText="✘ Verification failed";
  }
}
</script>

</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML)

@app.route("/session", methods=["POST"])
def create_session():
    sid = session_store.create()
    return jsonify({"session_id": sid})

@app.route("/captcha/<session_id>", methods=["GET"])
def get_captcha(session_id):
    result = generator.run(session_id)
    return jsonify(result)

@app.route("/validate/<session_id>", methods=["POST"])
def validate(session_id):
    payload = request.get_json() or {}
    answer = payload.get("answer")
    result = validator.run(session_id, answer)
    return jsonify(result)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
