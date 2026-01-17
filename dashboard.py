from flask import Flask, request
import os
import math
import re

app = Flask(__name__)
LOG_FILE = "/root/vibe-trader/bot.log"
LINES_PER_PAGE = 100

def classify_log_line(line):
    lower = line.lower()
    if "võitja" in lower or "ostame" in lower or "tehtud! ostetud" in lower: return "card-buy", "🚀 OST"
    if "kasum" in lower or "müün" in lower or "tehtud! müüdud" in lower: return "card-sell", "💰 MÜÜK"
    if "kahjum" in lower: return "card-loss", "🔻 STOP"
    if "> uudis:" in lower: return "card-news", "📰 UUDIS"
    if "raha otsas" in lower: return "card-warning", "⚠️ RAHA"
    return "card-noise", ""

@app.route("/")
def view_log():
    lines = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f: lines = f.readlines()
        except:
            with open(LOG_FILE, "r", encoding="latin-1") as f: lines = f.readlines()
        lines = lines[::-1]

    total_pages = math.ceil(len(lines) / LINES_PER_PAGE) or 1
    page = request.args.get('page', 1, type=int)
    if page < 1: page = 1
    if page > total_pages: page = total_pages

    current_lines = lines[(page-1)*LINES_PER_PAGE : page*LINES_PER_PAGE]

    feed_html = ""
    for line in current_lines:
        clean = line.strip()
        if not clean: continue
        
        ts = ""
        msg = clean
        if clean.startswith("[") and "]" in clean:
            end = clean.find("]")
            ts = clean[1:end]
            msg = clean[end+1:].strip()

        css, badge = classify_log_line(msg)
        
        link_html = ""
        if css == "card-news":
            raw_content = msg.replace("> UUDIS:", "").strip()
            if "|||" in raw_content:
                parts = raw_content.split("|||")
                title = parts[0].strip()
                url = parts[1].strip()
                msg = title
                link_html = f'<a href="{url}" target="_blank" class="news-btn">Loe edasi ↗</a>'
            else:
                msg = raw_content

        feed_html += f"""
        <div class="event {css}">
            <div class="meta">
                <span class="time">{ts}</span>
                {f'<span class="badge">{badge}</span>' if badge else ''}
            </div>
            <div class="msg">{msg} {link_html}</div>
        </div>
        """

    prev_url = f'/?page={page-1}' if page > 1 else '#'
    next_url = f'/?page={page+1}' if page < total_pages else '#'

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Vibe Trader</title>
        <meta http-equiv="refresh" content="30">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ background: #0f172a; color: #e2e8f0; font-family: sans-serif; padding: 20px; max-width: 800px; margin: 0 auto; }}
            .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; margin-bottom: 20px; padding-bottom: 10px; }}
            .event {{ background: #1e293b; border: 1px solid #334155; padding: 12px; border-radius: 8px; margin-bottom: 10px; }}
            .meta {{ display: flex; gap: 10px; font-size: 12px; color: #94a3b8; margin-bottom: 5px; }}
            .time {{ color: #38bdf8; min-width: 130px; font-family: monospace; }}
            .badge {{ font-weight: bold; padding: 2px 6px; border-radius: 4px; }}
            
            .card-buy {{ border-left: 4px solid #10b981; }} .card-buy .badge {{ background: #10b981; color: #fff; }}
            .card-sell {{ border-left: 4px solid #f59e0b; }} .card-sell .badge {{ background: #f59e0b; color: #000; }}
            .card-news {{ border-left: 4px solid #fff; background: #262f40; }} .card-news .badge {{ background: #475569; color: #fff; }}
            
            .news-btn {{ display: inline-block; margin-top: 5px; background: #38bdf8; color: #000; padding: 4px 10px; border-radius: 4px; text-decoration: none; font-size: 12px; font-weight: bold; }}
            
            .card-noise {{ border: none; background: transparent; padding: 4px 0; border-bottom: 1px solid #1e293b; opacity: 0.7; }}
            .card-noise .time {{ display: none; }} 
            .card-noise .msg {{ font-size: 13px; color: #64748b; }}
            
            .nav {{ margin-top: 20px; text-align: center; }}
            a {{ color: #38bdf8; text-decoration: none; margin: 0 10px; }}
        </style>
    </head>
    <body>
        <div class="header"><h1>🤖 Vibe Trader</h1><span>LIVE</span></div>
        {feed_html}
        <div class="nav"><a href="{prev_url}">❮ Uuemad</a> <span>Leht {page}</span> <a href="{next_url}">Vanemad ❯</a></div>
    </body>
    </html>
    """

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)