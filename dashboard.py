from flask import Flask, request
import os
import math

app = Flask(__name__)

# SEADISTUS
LOG_FILE = "/root/vibe-trader/bot.log"
LINES_PER_PAGE = 50  # Mitu rida ühel lehel kuvame

@app.route("/")
def view_log():
    # 1. Loeme faili sisu
    lines = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            # Fallback kui utf-8 ei toimi (nt vanad logid)
            with open(LOG_FILE, "r", encoding="latin-1") as f:
                lines = f.readlines()
                
        # Pöörame ümber, et uusim oleks üleval
        lines = lines[::-1]
    
    # 2. Lehekülgede loogika (Pagination)
    total_lines = len(lines)
    total_pages = math.ceil(total_lines / LINES_PER_PAGE)
    if total_pages == 0: total_pages = 1
    
    # Küsime URL-ist, mitmendat lehte kasutaja tahab (vaikimisi 1)
    page = request.args.get('page', 1, type=int)
    if page < 1: page = 1
    if page > total_pages: page = total_pages

    # Arvutame, mis read tuleb näidata
    start = (page - 1) * LINES_PER_PAGE
    end = start + LINES_PER_PAGE
    current_page_lines = lines[start:end]

    # 3. HTML & CSS Disain
    rows_html = ""
    for line in current_page_lines:
        clean_line = line.strip()
        if not clean_line: continue
        
        row_class = ""
        
        # Värvikoodid
        if "VÕITJA" in clean_line:
            row_class = "winner"
            clean_line = "🚀 " + clean_line
        elif "TEHTUD" in clean_line:
            row_class = "success"
            clean_line = "✅ " + clean_line
        elif "KAHJUM" in clean_line:
            row_class = "danger"
            clean_line = "🔻 " + clean_line
        elif "KASUM" in clean_line:
            row_class = "success"
            clean_line = "💰 " + clean_line
        elif "AI HINNE" in clean_line:
            row_class = "info"
        
        # Kellaaja eraldamine
        timestamp = ""
        message = clean_line
        if clean_line.startswith("["):
            parts = clean_line.split("]", 1)
            if len(parts) > 1:
                timestamp = parts[0] + "]"
                message = parts[1].strip()

        rows_html += f"""
        <tr class="{row_class}">
            <td class="time">{timestamp}</td>
            <td class="msg">{message}</td>
        </tr>
        """

    # Navigatsiooni nupud
    prev_link = f'/?page={page-1}' if page > 1 else '#'
    next_link = f'/?page={page+1}' if page < total_pages else '#'
    prev_class = 'btn' if page > 1 else 'btn disabled'
    next_class = 'btn' if page < total_pages else 'btn disabled'

    prev_btn = f'<a href="{prev_link}" class="{prev_class}">❮ Eelmine</a>'
    next_btn = f'<a href="{next_link}" class="{next_class}">Järgmine ❯</a>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Vibe Trader Pro</title>
        <meta http-equiv="refresh" content="30">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            :root {{ --bg: #0f172a; --card: #1e293b; --text: #94a3b8; --green: #22c55e; --red: #ef4444; --gold: #eab308; --blue: #38bdf8; }}
            body {{ background-color: var(--bg); color: var(--text); font-family: monospace; margin: 0; padding: 20px; }}
            .header {{ display: flex; justify-content: space-between; border-bottom: 1px solid #334155; padding-bottom: 10px; margin-bottom: 20px; }}
            h1 {{ color: #f8fafc; margin: 0; font-size: 20px; }}
            .status {{ color: var(--green); font-weight: bold; }}
            .nav {{ display: flex; justify-content: space-between; background: var(--card); padding: 10px; border-radius: 8px; margin-bottom: 15px; }}
            .btn {{ text-decoration: none; color: #fff; background: #334155; padding: 5px 15px; border-radius: 4px; }}
            .btn.disabled {{ opacity: 0.3; pointer-events: none; }}
            table {{ width: 100%; border-collapse: collapse; background: var(--card); border-radius: 8px; }}
            td {{ padding: 10px; border-bottom: 1px solid #334155; vertical-align: top; }}
            .time {{ width: 160px; color: #64748b; font-size: 12px; white-space: nowrap; }}
            .msg {{ color: #e2e8f0; }}
            .winner .msg {{ color: var(--gold); font-weight: bold; }}
            .success .msg {{ color: var(--green); }}
            .danger .msg {{ color: var(--red); }}
            .info .msg {{ color: var(--blue); }}
            @media (max-width: 600px) {{ .time {{ display: none; }} }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🤖 VIBE TRADER PRO</h1>
            <span class="status">● LIVE</span>
        </div>
        <div class="nav">
            {prev_btn}
            <span>Leht {page} / {total_pages}</span>
            {next_btn}
        </div>
        <table>{rows_html}</table>
    </body>
    </html>
    """
    return html

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)