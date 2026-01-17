from flask import Flask, request
import os
import math
import re

app = Flask(__name__)

# SEADISTUS
LOG_FILE = "/root/vibe-trader/bot.log"
LINES_PER_PAGE = 100  # Näitame rohkem ridu, sest filtreerimine peidab paljud ära

def classify_log_line(line):
    """Määrab rea tüübi ja stiili"""
    lower_line = line.lower()
    
    # 1. TEHINGUD (Kõige tähtsamad)
    if "võitja" in lower_line or "ostame" in lower_line or "tehtud! ostetud" in lower_line:
        return "card-buy", "🚀 OST"
    if "kasum" in lower_line or "müün" in lower_line or "tehtud! müüdud" in lower_line:
        return "card-sell", "💰 MÜÜK"
    if "kahjum" in lower_line:
        return "card-loss", "🔻 STOP-LOSS"
    
    # 2. OLULINE INFO
    if "raha otsas" in lower_line:
        return "card-warning", "⚠️ HOIATUS"
    if "juba portfellis" in lower_line:
        return "card-info", "ℹ️ OLEMAS"
        
    # 3. MÜRA (Analüüsid jms)
    if "analüüsin" in lower_line or "ai hinne" in lower_line:
        return "card-noise", "🔍 ANALÜÜS"
    if "skanner" in lower_line or "filter" in lower_line or "portfell" in lower_line:
        return "card-noise", "⚙️ SÜSTEEM"
        
    return "card-noise", ""

@app.route("/")
def view_log():
    # Loeme faili
    lines = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except:
            with open(LOG_FILE, "r", encoding="latin-1") as f:
                lines = f.readlines()
        lines = lines[::-1] # Uusimad ees
    
    # Pagination
    total_lines = len(lines)
    total_pages = math.ceil(total_lines / LINES_PER_PAGE)
    if total_pages == 0: total_pages = 1
    
    page = request.args.get('page', 1, type=int)
    if page < 1: page = 1
    if page > total_pages: page = total_pages

    start = (page - 1) * LINES_PER_PAGE
    end = start + LINES_PER_PAGE
    current_page_lines = lines[start:end]

    # Renderdame sisu
    feed_html = ""
    for line in current_page_lines:
        clean_line = line.strip()
        if not clean_line: continue
        
        # Eraldame kellaaja
        timestamp = ""
        message = clean_line
        match = re.match(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.*)", clean_line)
        if match:
            timestamp = match.group(1)
            message = match.group(2)
        
        css_class, badge_text = classify_log_line(message)
        
        # HTML struktuur igale kaardile
        feed_html += f"""
        <div class="event {css_class}">
            <div class="time">{timestamp}</div>
            <div class="content">
                {'<span class="badge">' + badge_text + '</span>' if badge_text else ''}
                <div class="msg">{message}</div>
            </div>
        </div>
        """

    # Navigatsioonilingid
    prev_link = f'/?page={page-1}' if page > 1 else '#'
    next_link = f'/?page={page+1}' if page < total_pages else '#'
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Vibe Trader Feed</title>
        <meta http-equiv="refresh" content="30">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #0f172a;
                --sidebar: #1e293b;
                --card-bg: #1e293b;
                --text-main: #e2e8f0;
                --text-dim: #64748b;
                --accent: #38bdf8;
                --green: #10b981;
                --red: #ef4444;
                --gold: #f59e0b;
                --border: #334155;
            }}
            
            body {{ background-color: var(--bg); color: var(--text-main); font-family: 'Inter', sans-serif; margin: 0; padding: 0; }}
            
            /* Layout */
            .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
            
            /* Header & Filters */
            .header {{ 
                position: sticky; top: 0; z-index: 100;
                background: rgba(15, 23, 42, 0.95);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid var(--border);
                padding: 15px 0;
                margin-bottom: 30px;
            }}
            .header-content {{ display: flex; justify-content: space-between; align-items: center; max-width: 800px; margin: 0 auto; padding: 0 20px; }}
            h1 {{ margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.5px; }}
            .status-dot {{ display: inline-block; width: 8px; height: 8px; background: var(--green); border-radius: 50%; margin-right: 8px; box-shadow: 0 0 10px var(--green); }}
            
            /* Filter Buttons */
            .filters {{ display: flex; gap: 10px; }}
            .filter-btn {{
                background: var(--sidebar); border: 1px solid var(--border); color: var(--text-dim);
                padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; cursor: pointer; transition: 0.2s;
            }}
            .filter-btn.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
            .filter-btn:hover {{ border-color: var(--text-dim); }}

            /* Timeline Feed */
            .feed {{ position: relative; padding-left: 20px; border-left: 2px solid var(--border); margin-left: 10px; }}
            
            .event {{ position: relative; margin-bottom: 15px; padding: 15px; border-radius: 12px; background: var(--card-bg); border: 1px solid var(--border); transition: transform 0.2s; }}
            
            /* Timeline Dot */
            .event::before {{
                content: ''; position: absolute; left: -27px; top: 20px;
                width: 12px; height: 12px; border-radius: 50%; background: var(--border); border: 2px solid var(--bg);
            }}
            
            /* Styles for different event types */
            .card-buy {{ border-left: 4px solid var(--green); background: rgba(16, 185, 129, 0.1); }}
            .card-buy::before {{ background: var(--green); }}
            
            .card-sell {{ border-left: 4px solid var(--gold); background: rgba(245, 158, 11, 0.1); }}
            .card-sell::before {{ background: var(--gold); }}
            
            .card-loss {{ border-left: 4px solid var(--red); }}
            .card-loss::before {{ background: var(--red); }}
            
            /* Noise reduction */
            .card-noise {{ background: transparent; border: none; padding: 5px 0; margin-bottom: 5px; }}
            .card-noise .time {{ display: none; }} /* Peidame kellaaja müra jaoks */
            .card-noise::before {{ display: none; }} /* Peidame täpi */
            .card-noise .msg {{ color: var(--text-dim); font-size: 13px; font-family: 'JetBrains Mono', monospace; }}

            /* Content Typography */
            .time {{ font-size: 11px; color: var(--text-dim); margin-bottom: 4px; font-family: 'JetBrains Mono', monospace; }}
            .badge {{ 
                display: inline-block; padding: 2px 6px; border-radius: 4px; 
                font-size: 10px; font-weight: bold; text-transform: uppercase; margin-bottom: 6px;
            }}
            .card-buy .badge {{ background: var(--green); color: #fff; }}
            .card-sell .badge {{ background: var(--gold); color: #000; }}
            
            .msg {{ font-size: 14px; line-height: 1.5; }}

            /* Pagination */
            .nav {{ display: flex; justify-content: center; gap: 20px; margin-top: 40px; padding-bottom: 40px; }}
            .nav a {{ color: var(--accent); text-decoration: none; font-weight: 600; }}
            .nav a:hover {{ text-decoration: underline; }}

        </style>
        <script>
            function filterFeed(type) {{
                const events = document.querySelectorAll('.event');
                const buttons = document.querySelectorAll('.filter-btn');
                
                // Update buttons
                buttons.forEach(b => b.classList.remove('active'));
                document.getElementById('btn-' + type).classList.add('active');

                events.forEach(el => {{
                    if (type === 'all') {{
                        el.style.display = 'block';
                    }} else if (type === 'trades') {{
                        if (el.classList.contains('card-buy') || el.classList.contains('card-sell') || el.classList.contains('card-loss')) {{
                            el.style.display = 'block';
                        }} else {{
                            el.style.display = 'none';
                        }}
                    }}
                }});
            }}
        </script>
    </head>
    <body>
        <div class="header">
            <div class="header-content">
                <h1><span class="status-dot"></span>Vibe Trader</h1>
                <div class="filters">
                    <button id="btn-all" class="filter-btn active" onclick="filterFeed('all')">Kõik</button>
                    <button id="btn-trades" class="filter-btn" onclick="filterFeed('trades')">Ainult Tehingud</button>
                </div>
            </div>
        </div>

        <div class="container">
            <div class="feed">
                {feed_html}
            </div>
            
            <div class="nav">
                <a href="{prev_link}">← Uuemad</a>
                <span style="color: #64748b">Leht {page} / {total_pages}</span>
                <a href="{next_link}">Vanemad →</a>
            </div>
        </div>
    </body>
    </html>
    """
    return html

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)