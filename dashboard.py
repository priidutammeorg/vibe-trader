from flask import Flask, request
import os
import math

app = Flask(__name__)

# SEADISTUS
LOG_FILE = "/root/vibe-trader/bot.log"
LINES_PER_PAGE = 100

def classify_log_line(line):
    """Määrab rea tüübi ja stiili"""
    lower_line = line.lower()
    
    # 1. TEHINGUD
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
        
    # 3. MÜRA
    if "analüüsin" in lower_line or "ai hinne" in lower_line:
        return "card-noise", "🔍 ANALÜÜS"
    if "skanner" in lower_line or "filter" in lower_line or "portfell" in lower_line:
        return "card-noise", "⚙️ SÜSTEEM"
        
    return "card-noise", ""

@app.route("/")
def view_log():
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
        
        # --- PARANDATUD AJATEMPLI LUGEMINE ---
        # Eeldame formaati: [2026-01-17 15:00:00] Sõnum
        timestamp = ""
        message = clean_line
        
        if clean_line.startswith("[") and "]" in clean_line:
            # Leiame esimese ] märgi asukoha
            end_bracket = clean_line.find("]")
            # Võtame kõik, mis on [ ja ] vahel
            potential_time = clean_line[1:end_bracket]
            
            # Kontrollime, kas see näeb välja nagu kellaaeg (sisaldab koolonit)
            if ":" in potential_time:
                timestamp = potential_time
                message = clean_line[end_bracket+1:].strip()
            else:
                # Kui ei ole kellaaeg, siis on see lihtsalt mingi muu tekst nurksulgudes
                timestamp = "" 
        
        if not timestamp:
            timestamp = "---" # Vana logi ilma ajata

        css_class, badge_text = classify_log_line(message)
        
        feed_html += f"""
        <div class="event {css_class}">
            <div class="meta">
                <span class="time">{timestamp}</span>
                {'<span class="badge">' + badge_text + '</span>' if badge_text else ''}
            </div>
            <div class="msg">{message}</div>
        </div>
        """

    # Navigatsioon
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
                --card-bg: #1e293b;
                --text-main: #e2e8f0;
                --text-dim: #94a3b8;
                --accent: #38bdf8;
                --green: #10b981;
                --red: #ef4444;
                --gold: #f59e0b;
                --border: #334155;
            }}
            body {{ background-color: var(--bg); color: var(--text-main); font-family: 'Inter', sans-serif; margin: 0; padding: 0; }}
            .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
            
            /* Header */
            .header {{ 
                position: sticky; top: 0; z-index: 100;
                background: rgba(15, 23, 42, 0.95);
                backdrop-filter: blur(10px);
                border-bottom: 1px solid var(--border);
                padding: 15px 0; margin-bottom: 30px;
            }}
            .header-content {{ display: flex; justify-content: space-between; align-items: center; max-width: 800px; margin: 0 auto; padding: 0 20px; }}
            h1 {{ margin: 0; font-size: 18px; font-weight: 700; }}
            .status-dot {{ display: inline-block; width: 8px; height: 8px; background: var(--green); border-radius: 50%; margin-right: 8px; }}

            /* Filters */
            .filters button {{
                background: var(--card-bg); border: 1px solid var(--border); color: var(--text-dim);
                padding: 5px 10px; border-radius: 15px; font-size: 12px; cursor: pointer;
            }}
            .filters button.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

            /* Feed Item */
            .event {{ 
                margin-bottom: 12px; padding: 12px; border-radius: 8px; 
                background: var(--card-bg); border: 1px solid var(--border); 
            }}
            
            /* Meta row (Time + Badge) */
            .meta {{ display: flex; align-items: center; margin-bottom: 6px; gap: 10px; }}
            
            .time {{ 
                font-family: 'JetBrains Mono', monospace; 
                font-size: 12px; 
                color: var(--accent); /* Teeme kellaaja helesiniseks, et paistaks välja */
                opacity: 0.8;
                min-width: 140px;
            }}
            
            .badge {{ 
                padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold; text-transform: uppercase; 
            }}
            
            .msg {{ font-size: 14px; line-height: 1.4; color: #fff; }}

            /* Colors per type */
            .card-buy {{ border-left: 4px solid var(--green); }}
            .card-buy .badge {{ background: var(--green); color: #fff; }}
            
            .card-sell {{ border-left: 4px solid var(--gold); }}
            .card-sell .badge {{ background: var(--gold); color: #000; }}
            
            .card-loss {{ border-left: 4px solid var(--red); }}
            
            /* Noise handling */
            .card-noise {{ background: transparent; border: none; border-bottom: 1px solid #1e293b; padding: 8px 0; }}
            .card-noise .msg {{ color: var(--text-dim); font-size: 13px; }}
            .card-noise .time {{ color: #475569; }} /* Müra kellaaeg on tumedam */

            /* Pagination */
            .nav {{ display: flex; justify-content: center; gap: 20px; margin-top: 40px; padding-bottom: 40px; }}
            .nav a {{ color: var(--accent); text-decoration: none; }}
        </style>
        <script>
            function filterFeed(type) {{
                const events = document.querySelectorAll('.event');
                const buttons = document.querySelectorAll('.filters button');
                buttons.forEach(b => b.classList.remove('active'));
                document.getElementById('btn-' + type).classList.add('active');

                events.forEach(el => {{
                    if (type === 'all') el.style.display = 'block';
                    else if (type === 'trades') {{
                        if (el.classList.contains('card-buy') || el.classList.contains('card-sell')) el.style.display = 'block';
                        else el.style.display = 'none';
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
                    <button id="btn-all" class="active" onclick="filterFeed('all')">Kõik</button>
                    <button id="btn-trades" onclick="filterFeed('trades')">Ainult Tehingud</button>
                </div>
            </div>
        </div>

        <div class="container">
            {feed_html}
            
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