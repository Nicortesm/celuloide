# ---------- Celuloide Chat ---------- #
import streamlit as st
import sqlite3, pandas as pd, json, time
import openai

# --- Configuración ---
openai.api_key = st.secrets["OPENAI_API_KEY"]
DB_PATH = "phones.db"

st.set_page_config("Celuloide · Tu asesor de celulares", "📱", layout="wide")

HEADER_CSS = """
<style>
.stApp {background:#ffffff;color:#000;}
#header {background:#004a99;color:#fff;padding:16px;border-radius:6px;margin-bottom:1rem;}
.big {font-size:1.6rem;font-weight:700;}
.chat-row {margin-bottom:8px;}
.user-msg {background:#e6f0ff;padding:8px 12px;border-radius:8px;max-width:85%%;}
.bot-msg  {background:#f2f2f2;padding:8px 12px;border-radius:8px;max-width:85%%;}
</style>
"""
st.markdown(HEADER_CSS, unsafe_allow_html=True)
st.markdown('<div id="header"><span class="big">📱  Encuentra tu Celular Ideal con IA</span></div>', unsafe_allow_html=True)

# -- Sesión de chat --
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant",
         "content": "Hola 👋 Soy Celuloide, tu asesor de celulares. "
                    "Cuéntame en lenguaje natural qué necesitas (marca, uso, presupuesto, etc.)"}
    ]

# -- Mostrar historial --
for m in st.session_state.messages:
    align = "user-msg" if m["role"] == "user" else "bot-msg"
    st.markdown(f'<div class="chat-row {align}">{m["content"]}</div>', unsafe_allow_html=True)

# -- Entrada del usuario --
if user_msg := st.chat_input("Escribe tu mensaje…"):
    st.session_state.messages.append({"role": "user", "content": user_msg})
    st.markdown(f'<div class="chat-row user-msg">{user_msg}</div>', unsafe_allow_html=True)

    # --- Prompt a GPT ---
    system_prompt = """
Eres Celuloide, un asesor que ayuda a comprar celulares. Siempre respondes en español
con tono amistoso y profesional. Recibes un historial de la conversación y el último
mensaje del usuario. Devuelve un JSON con dos claves:

"reply": lo que le dices al usuario,
"filters": objeto con brand, max_price, min_storage, min_ram, min_camera_mp (opcional).

Ejemplo:
{
 "reply": "Entiendo, busquemos Samsung económicos con buena cámara…",
 "filters": {
   "brand":"Samsung",
   "max_price":2000000,
   "min_camera_mp":48
 }
}
"""

    chat_history = [{"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages]

    chat_history.insert(0, {"role": "system", "content": system_prompt})

    gpt = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=chat_history,
        temperature=0.4,
    )

    # -- Procesar respuesta --
    try:
        raw = gpt.choices[0].message.content.strip()
        data = json.loads(raw)
        reply = data["reply"]
        filters = data.get("filters", {})

    except Exception as e:
        reply = "Lo siento, hubo un problema al interpretar la respuesta de la IA."
        filters = {}

    # -- Buscar en BD si hay filtros --
    if filters:
        query = "SELECT name, url, price_cop, storage_gb, ram_gb, camera_mp FROM phones WHERE 1=1"
        params = []
        if filters.get("brand"):
            query += " AND brand LIKE ?"
            params.append(f"%{filters['brand']}%")
        if filters.get("max_price"):
            query += " AND price_cop <= ?"
            params.append(filters["max_price"])
        if filters.get("min_storage"):
            query += " AND storage_gb >= ?"
            params.append(filters["min_storage"])
        if filters.get("min_ram"):
            query += " AND ram_gb >= ?"
            params.append(filters["min_ram"])
        if filters.get("min_camera_mp"):
            query += " AND camera_mp >= ?"
            params.append(filters["min_camera_mp"])

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchmany(3)  # top-3
        conn.close()

        if rows:
            reply += f"<br><br><b>Te recomiendo estos modelos:</b>"
            for r in rows:
                reply += (f"<br>• <a href=\"{r['url']}\" target=\"_blank\">{r['name']}</a> – "
                          f"${r['price_cop']:,} COP, {r['storage_gb']} GB / {r['ram_gb']} GB, "
                          f"cámara {r['camera_mp']} MP")
        else:
            reply += "<br><br>No encontré modelos que cumplan exactamente esos criterios."

    # -- Mostrar respuesta del bot --
    st.session_state.messages.append({"role": "assistant", "content": reply})
    st.markdown(f'<div class="chat-row bot-msg">{reply}</div>', unsafe_allow_html=True)
