"""
Celuloide · Asistente de compra de celulares (versión robusta)
--------------------------------------------------------------
- Preguntas guiadas (5) → respuestas en session_state
- GPT transforma a filtros JSON (timeout 30 s, manejo de errores)
- Consulta SQLite phones.db
    · Si hay matches: TOP-5
    · Si no pero hay marca: quita marca y sugiere 3 opciones calidad-precio
- Presupuesto acepta: 8m, 8 millones, 8.000.000, 8000000, etc.
"""

import streamlit as st
import sqlite3, pandas as pd, json, re
import openai
from tenacity import retry, stop_after_delay   # para timeout seguro

# -------- CONFIG --------
openai.api_key = st.secrets["OPENAI_API_KEY"]        # añade tu clave en secrets
DB_PATH = "phones.db"
MODEL   = "gpt-3.5-turbo"

st.set_page_config(page_title="Celuloide · Asistente de compra", page_icon="📱")

st.markdown(
    '<div style="background:#004a99;padding:14px;border-radius:6px;">'
    '<span style="color:#fff;font-size:1.4rem;font-weight:700">'
    '📱 Encuentra tu Celular Ideal</span></div>',
    unsafe_allow_html=True,
)

# ---------- util ↳ presupuesto ----------
SPANISH = {"uno":1,"dos":2,"tres":3,"cuatro":4,"cinco":5,"seis":6,"siete":7,
           "ocho":8,"nueve":9,"diez":10}
def gpt_to_number(text:str)->int|None:
    prom = f"Convierte '{text}' a un número entero COP. Devuelve solo dígitos."
    try:
        rsp = openai.ChatCompletion.create(
            model=MODEL,
            messages=[{"role":"user","content":prom}],
            temperature=0)
        num = int(re.sub(r"[^0-9]", "", rsp.choices[0].message.content))
        return num if num>0 else None
    except Exception:
        return None

def parse_number(text:str)->int|None:
    t = text.lower().replace(".", "").replace(",", "").strip()
    # 1) dígitos + k/m
    if re.fullmatch(r"\d+[kKmM]?", t):
        n=int(re.findall(r"\d+", t)[0])
        if t.endswith(("m","M")) and n<1000: n*=1_000_000
        if t.endswith(("k","K")):            n*=1_000
        return n
    # 2) contiene millones / mil
    dig=re.findall(r"\d+", t)
    if dig and ("mill" in t): return int(dig[0])*1_000_000
    if dig and "mil" in t:    return int(dig[0])*1_000
    # 3) palabras
    for w,n in SPANISH.items():
        if w in t:
            if "mill" in t: return n*1_000_000
            if "mil"  in t: return n*1_000
            return n
    # 4) respaldo GPT
    return gpt_to_number(text)

# ---------- Preguntas ----------
QUESTIONS = [
    {"key":"budget","text":"¿Cuál es tu presupuesto máximo (COP)?","widget":"text"},
    {"key":"brand","text":"¿Tienes una marca preferida? (opcional)","widget":"text"},
    {"key":"usage","text":"¿Para qué usarás principalmente el celular?",
     "widget":"select","options":["Redes sociales","Fotografía","Juegos","Trabajo/estudio","Otro"]},
    {"key":"camera","text":"¿Qué tan importante es la cámara?",
     "widget":"select","options":["Poco","Moderado","Muy importante"]},
    {"key":"storage","text":"¿Cuánta memoria interna prefieres?",
     "widget":"select","options":["64 GB o menos","128 GB","256 GB o más"]},
]
TOTAL=len(QUESTIONS)

# ---------- Sesión ----------
if "chat" not in st.session_state:
    st.session_state.chat=[{"role":"assistant",
                            "content":"¡Hola 👋! Soy Celuloide. "
                                      "Responderé a 5 preguntas para encontrar tu celular ideal."}]
    st.session_state.step=0
    st.session_state.answers={}

# ---------- Mostrar historial ----------
for m in st.session_state.chat:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

step = st.session_state.step

# ---------- Flujo de preguntas ----------
if step < TOTAL:
    q=QUESTIONS[step]
    with st.chat_message("assistant"):
        st.markdown(f"**Pregunta {step+1}/{TOTAL}:** {q['text']}")
    if q["widget"]=="text":
        ans=st.text_input("Tu respuesta:", key=f"inp{step}")
    else:
        ans=st.selectbox("Tu respuesta:", q["options"], key=f"inp{step}")
    if st.button("Enviar", key=f"btn{step}"):
        if q["key"]=="budget":
            ans = parse_number(ans) or 0
        st.session_state.answers[q["key"]]=ans
        st.session_state.chat.append({"role":"user","content":str(ans)})
        st.session_state.step += 1
        st.rerun()

# ---------- Fin de preguntas ----------
else:
    with st.chat_message("assistant"): st.markdown("⌛ Procesando tus respuestas…")

    # --- GPT → filtros (máx 30 s) ---
    prompt = f"""
Convierte este JSON de respuestas a filtros:
brand, max_price, min_storage, min_ram, min_camera_mp (null si no aplica).

{json.dumps(st.session_state.answers, ensure_ascii=False)}
"""
    @retry(stop=stop_after_delay(30))
    def gpt_filters(prompt:str)->dict:
        rsp=openai.ChatCompletion.create(
            model=MODEL,
            messages=[{"role":"user","content":prompt}],
            temperature=0)
        return json.loads(rsp.choices[0].message.content)

    try:
        filt=gpt_filters(prompt)
    except Exception as e:
        with st.chat_message("assistant"):
            st.error(f"No pude interpretar tus respuestas (error: {e}). "
                     "Intenta reiniciar el chat.")
        st.stop()

    # --- Construir y ejecutar SQL ---
    base_sql="SELECT name,url,price_cop,storage_gb,ram_gb,camera_mp FROM phones WHERE 1=1"
    def query_rows(f, override_brand=None, limit=5):
        sql, p = base_sql, []
        f = f.copy()
        if override_brand is not None: f["brand"]=override_brand
        if f.get("brand"):         sql+=" AND brand LIKE ?";       p.append(f"%{f['brand']}%")
        if f.get("max_price"):     sql+=" AND price_cop<=?";       p.append(f["max_price"])
        if f.get("min_storage"):   sql+=" AND storage_gb>=?";      p.append(f["min_storage"])
        if f.get("min_ram"):       sql+=" AND ram_gb>=?";          p.append(f["min_ram"])
        if f.get("min_camera_mp"): sql+=" AND camera_mp>=?";       p.append(f["min_camera_mp"])
        conn=sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row
        rows=conn.execute(sql+" LIMIT ?", p+[limit]).fetchall(); conn.close()
        return rows

    rows=query_rows(filt)

    # --- plan B si vacío y había marca ---
    if not rows and filt.get("brand"):
        rows=query_rows(filt, override_brand=None, limit=3)
        explain=("No encontré modelos de esa marca con tus exigencias.\n\n"
                 "Estas son 3 opciones destacadas de otras marcas que se acercan:")

    # --- Mostrar resultado ---
    if rows:
        df=pd.DataFrame(rows)
        df["Enlace"]=df["url"].apply(lambda u:f"[Ver]({u})")
        with st.chat_message("assistant"):
            if 'explain' in locals(): st.warning(explain)
            else: st.success(f"Encontré {len(df)} opciones:")
            st.dataframe(df.drop(columns=["url"]), use_container_width=True)
    else:
        with st.chat_message("assistant"):
            st.info("No encontré celulares que cumplan tus criterios. "
                    "Pulsa Reiniciar y prueba con requisitos más flexibles.")

    # --- Botón Reiniciar ---
    if st.button("🔄 Reiniciar"):
        for k in ("chat","step","answers"): st.session_state.pop(k,None)
        st.rerun()
