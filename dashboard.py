from flask import Flask
import os
import re

app = Flask(__name__)
LOG_FILE = "bot.log"

def get_log_content():
    if not os.path.exists(LOG_FILE):
        return []
    
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        return [[{"ts": "ERROR", "msg": f"Ei saanud logi lugeda: {e}", "class": "msg-error"}]]
    
    cycles = []
    current_cycle = []
    
    for line in reversed(lines):
        clean_line = line.strip()
        if not clean_line: continue
        
        match = re.match(r'^\[(.*?)] (.*)', clean_line)
        if match:
            ts = match.group(1)
            msg = match.group(2)
        else:
            ts = "-"
            msg = clean_line

        if "========== TSÜKKEL START ==========" in msg:
            if current_cycle:
                cycles.append(current_cycle)
                current_cycle = []
            continue
            
        if "========== TSÜKKEL LÕPP ==========" in msg:
            continue

        row_class = "msg-info"
        if "TEGIJA: Ostame" in msg or "TEHTUD! Ostetud" in msg: row_class = "msg-buy"
        elif "Müün" in msg or "STOP HIT" in msg: row_class = "msg-sell"
        elif "VÕITJA" in msg: row_class = "msg-winner"
        elif "RISK-FREE" in msg: row_class = "msg-riskfree"
        elif "UUDIS" in msg: row_class = "msg-news"
        elif "[SKIP]" in msg: row_class = "msg-skip"
        elif "Failed" in msg or "Error" in msg or "Traceback" in msg: row_class = "msg-error"
        elif "LEID:" in msg: row_class = "msg-hot"

        try:
            msg = re.sub(r'(https?://\S+)', r'<a href="\1" target="_blank">LINK ↗</a>', msg)
        except: pass
        
        current_cycle.append({"ts": ts, "msg": msg, "class": row_class})
            
    if current_cycle:
        cycles.append(current_cycle)
        
    return cycles

@app.route('/')
def index():
    try:
        cycles = get_log_content()
    except Exception as e:
        return f"<h1>VIGA DASHBOARDI LAADIMISEL</h1><p>{e}</p>"
    
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Vibe Trader 2.2</title>
        <meta http-equiv="refresh" content="5">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { 
                background: #0f172a; 
                color: #cbd5e1; 
                font-family: 'Consolas', 'Monaco', monospace; 
                padding: 20px; 
                max-width: 1100px; 
                margin: 0 auto; 
                font-size: 13px; 
            }
            h1 { color: #38bdf8; text-align: center; margin-bottom: 20px; font-family: sans-serif; }
            .cycle-box {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                margin-bottom: 20px;
                padding: 5px 0;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
            }
            .row { display: flex; padding: 3px 15px; border-bottom: 1px solid #253045; }
            .row:last-child { border-bottom: none; }
            .row:hover { background: #28364d; }
            .ts { color: #64748b; min-width: 140px; font-size: 11px; margin-right: 15px; display: flex; align-items: center; }
            .msg { word-break: break-word; line-height: 1.4; width: 100%; }
            a { color: #38bdf8; text-decoration: none; border-bottom: 1px dotted #38bdf8; }
            
            .msg-info { color: #94a3b8; }
            .msg-buy { color: #10b981; font-weight: bold; background: rgba(16, 185, 129, 0.1); padding: 2px 5px; border-radius: 3px;}
            .msg-sell { color: #f59e0b; font-weight: bold; background: rgba(245, 158, 11, 0.1); padding: 2px 5px; border-radius: 3px;}
            .msg-winner { color: #d8b4fe; font-weight: bold; border-bottom: 1px solid #a855f7; }
            .msg-riskfree { color: #60a5fa; font-weight: bold; }
            .msg-hot { color: #f472b6; }
            .msg-news { color: #e2e8f0; font-style: italic; }
            .msg-skip { color: #475569; font-size: 11px; }
            .msg-error { color: #ef4444; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>🤖 VIBE TRADER LIVE</h1>
    """
    
    if not cycles:
        html += "<p style='text-align:center; color:#64748b;'>Logi on tühi. Bot käivitub...</p>"
    
    for cycle in cycles:
        html += '<div class="cycle-box">'
        for row in cycle:
            html += f"""<div class="row"><div class="ts">{row['ts']}</div><div class="msg {row['class']}">{row['msg']}</div></div>"""
        html += '</div>'

    html += "</body></html>"
    return html

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)