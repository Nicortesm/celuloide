"""
Aplicación conversacional para recomendar celulares disponibles en Ktronix.
Incluye: scraping, limpieza y servidor web.
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
import re
import argparse
from flask import Flask, render_template_string, request

# ========== CONFIGURACIÓN ==========
DB_PATH = "phones.db"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
SITEMAP_URL = "https://www.ktronix.com/sitemap-productos.xml"

# ========== FUNCIONES DE EXTRACCIÓN ==========
def get_phone_urls():
    resp = requests.get(SITEMAP_URL, headers=HEADERS)
    soup = BeautifulSoup(resp.content, "xml")
    urls = [loc.text for loc in soup.find_all("loc") if "/celular-" in loc.text]
    return urls

def extract_phone_data(url):
    resp = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    data = {"url": url}
    try:
        data["name"] = soup.find("h1").text.strip()
        price = soup.select_one(".price-box .skuBestPrice")
        if price:
            data["price_cop"] = int(re.sub(r"[^0-9]", "", price.text))
    except:
        return None
    spec_map = {
        "Memoria Interna": "storage_gb",
        "Memoria RAM": "ram_gb",
        "Resolución cámara posterior": "camera_mp",
        "Capacidad de la batería": "battery_mah",
        "Tamaño de pantalla": "screen_size_in",
        "Procesador": "processor",
        "Sistema operativo": "os",
        "Marca": "brand"
    }
    specs = soup.select(".product-specs-list li")
    for li in specs:
        if " - " in li.text:
            k, v = map(str.strip, li.text.split(" - ", 1))
            if k in spec_map:
                field = spec_map[k]
                value = re.sub(r"[^0-9.,A-Za-z\s]", "", v)
                if field.endswith("_gb") or field.endswith("_mah") or field.endswith("_mp"):
                    nums = re.findall(r"\d+", value)
                    data[field] = int(nums[0]) if nums else None
                elif field == "screen_size_in":
                    match = re.search(r"\d+(\.\d+)?", value)
                    data[field] = float(match.group()) if match else None
                else:
                    data[field] = value.strip()
    return data

# ========== FUNCIONES DE BD ==========
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS phones (
            id INTEGER PRIMARY KEY,
            name TEXT, url TEXT, price_cop INTEGER,
            brand TEXT, storage_gb INTEGER, ram_gb INTEGER,
            camera_mp INTEGER, battery_mah INTEGER,
            screen_size_in REAL, processor TEXT, os TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_phone(data):
    if not data or "name" not in data:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    fields = [k for k in data.keys() if k in (
        "name", "url", "price_cop", "brand", "storage_gb", "ram_gb",
        "camera_mp", "battery_mah", "screen_size_in", "processor", "os")]
    values = [data.get(f) for f in fields]
    placeholders = ",".join(["?"] * len(fields))
    cur.execute(f"INSERT INTO phones ({','.join(fields)}) VALUES ({placeholders})", values)
    conn.commit()
    conn.close()

# ========== SERVIDOR FLASK ==========
HTML_TEMPLATE = """
<!doctype html>
<title>Encuentra tu Celular Ideal</title>
<h1>Encuentra tu Celular Ideal</h1>
<form method="post">
  Presupuesto máximo (COP): <input name="budget" type="number"><br>
  Almacenamiento mínimo (GB): <input name="storage" type="number"><br>
  RAM mínima (GB): <input name="ram" type="number"><br>
  Resolución de cámara mínima (MP): <input name="camera" type="number"><br>
  <input type="submit" value="Buscar">
</form>
{% if rows %}<table border="1" style="margin-top:20px">
<tr><th>Nombre</th><th>Precio</th><th>Almacenamiento</th><th>RAM</th><th>Cámara</th><th>Enlace</th></tr>
{% for r in rows %}<tr>
<td>{{r['name']}}</td><td>${{r['price_cop']}}</td><td>{{r['storage_gb']}}GB</td><td>{{r['ram_gb']}}GB</td><td>{{r['camera_mp']}}MP</td>
<td><a href="{{r['url']}}" target="_blank">Ver</a></td>
</tr>{% endfor %}</table>{% endif %}
"""

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    rows = []
    if request.method == "POST":
        q = "SELECT * FROM phones WHERE 1=1"
        params = []
        if request.form["budget"]:
            q += " AND price_cop <= ?"
            params.append(request.form["budget"])
        if request.form["storage"]:
            q += " AND storage_gb >= ?"
            params.append(request.form["storage"])
        if request.form["ram"]:
            q += " AND ram_gb >= ?"
            params.append(request.form["ram"])
        if request.form["camera"]:
            q += " AND camera_mp >= ?"
            params.append(request.form["camera"])
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(q, params).fetchall()
        conn.close()
    return render_template_string(HTML_TEMPLATE, rows=rows)

# ========== MAIN ==========
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--harvest", action="store_true")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    DB_PATH = args.db
    if args.harvest:
        init_db()
        urls = get_phone_urls()[:args.limit]
        for url in urls:
            data = extract_phone_data(url)
            save_phone(data)
    if args.serve:
        app.run(debug=True, port=8000)
