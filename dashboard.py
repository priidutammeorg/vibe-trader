from flask import Flask
import os

app = Flask(__name__)

LOG_FILE = "bot.log"

@app.route("/")
def view_log():
    # Loeme logifaili sisu
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        
        # Pöörame read ümber, et UUS INFO oleks ÜLEVAL (mugavam lugeda)
        lines = lines[::-1]
        content = "".join(lines)
    else:
        content = "Logifaili ei leitud. Oota, kuni bot tööle hakkab."

    # Lihtne HTML ja CSS disain
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Vibe Trader Log</title>
        <meta http-equiv="refresh" content="10"> <style>
            body {{
                background-color: #0d1117;
                color: #58a6ff;
                font-family: 'Courier New', Courier, monospace;
                padding: 20px;
                font-size: 14px;
            }}
            h1 {{ color: #ffffff; border-bottom: 1px solid #30363d; padding-bottom: 10px; }}
            pre {{
                white-space: pre-wrap;       /* Et tekst ei jookseks ekraanist välja */
                word-wrap: break-word;
            }}
            .timestamp {{ color: #8b949e; }}
        </style>
    </head>
    <body>
        <h1>🤖 Vibe Trader Live Log</h1>
        <p style="color: #8b949e;">Leht värskendab ennast ise iga 10 sekundi tagant.</p>
        <pre>{content}</pre>
    </body>
    </html>
    """
    return html

if __name__ == "__main__":
    # Paneme serveri käima pordil 5000 ja lubame ligipääsu väljast (host='0.0.0.0')
    app.run(host="0.0.0.0", port=5000)