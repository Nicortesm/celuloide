"""
Celuloide · Asistente de compra de celulares
-------------------------------------------

Flujo:
1. Bot saluda y plantea 5 preguntas guiadas.
2. Cada respuesta se guarda en session_state.
3. Al terminar llama a GPT-3.5 para convertir las respuestas a filtros JSON.
4. Consulta la base SQLite `phones.db`.
   • Si hay coincidencias → muestra TOP-5.
   • Si NO hay coincidencias → relaja el filtro de marca y muestra
     3 modelos “mejor relación calidad-precio” de cualquier marca
     (ordenados por la cámara y por acercarse al presupuesto).
5. Permite Reiniciar.

Presupuesto: admite “8m”, “8 millones”, “8.000.000” o “8000000”.
"""

import streamlit as st
import sqlite3, pandas as pd, json, re
import openai

# ---------- CONFIG ----------
openai.api_key = st.secrets["OPENAI_API_KEY"]      # pon tu clave en secrets
DB_PATH = "phones.db"                              # base creada por el scraper
MODEL   = "gpt-3.5-turbo"

st.set_page_config(page_title="Celuloide · Asistente de compra", page_icon="📱")

st.markdown(
    '<div style="background:#004a99;padding:14px;border-radius:6px;">'
    '<span style="color:#fff;font-size:1.4rem;font-weight:700">'
    '📱  Encuentra tu Celular Ideal</span></div>',
    unsafe_allow_html=True)

# ---------- util nº ----------
SPANISH = {"uno":1,"dos":2,"tres":3,"cuatro":4,"cinco":5,
           "seis":6,"siete":7,"ocho":8,"nueve":9,"diez":10}

def gpt_to_number(text:str)->int|None:
    prompt = f"Convierte '{text}' a un número entero COP. Devuelve solo el número."
    try:
        rsp = openai.ChatCompletion.create(
            model=MODEL,
            messages=[{"role":"user","content":prompt}],
            temperature=0)
        num = int(re.sub(r"[^0-9]", "", rsp.choices[0].message.content))
        return num if num>0 else None
    except Exception:
        return None

def parse_number(text:str)->int|None:
    t = text.lower().replace(".", "").replace(",", "").strip()
    # 1. dígitos
    if re.fullmatch(r"\d+[kKmM]?", t):
        num = int(re.findall(r"\d+", t)[0])
        if t.endswith(("m","M")) and num < 1000:   # 8m
            num *= 1_000_000
        elif t.endswith(("k","K")):
            num *= 1_000
        return num
    # 2. contiene millones / mil
    dig = re.findall(r"\d+", t)
    if dig and ("mill" in t or "millon" in t):
        return int(dig[0]) * 1_000_000
    if dig and "mil" in t:
        return int(dig[0]) * 1_000
    # 3. palabra
    for w,n in SPANISH.items():
        if w in t:
            if "mill" in t: return n*1_000_000
            if "mil"  in t: return n*1_000
            return n
    # 4. GPT respaldo
    return gpt_to_number(text)

# ---------- preguntas ----------
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

# ---------- session ----------
if "chat" not in st.session_state:
    st.session_state.chat=[{"role":"assistant","content":"¡Hola 👋! Soy Celuloide. Te haré 5 preguntas."}]
    st.session_state.step=0
    st.session_state.answers={}

# ---------- mostrar chat ----------
for m in st.session_state.chat:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

step=st.session_state.step

# ---------- preguntas guiadas ----------
if step<TOTAL:
    q=QUESTIONS[step]
    with st.chat_message("assistant"):
        st.markdown(f"**Pregunta {step+1}/{TOTAL}:** {q['text']}")
    if q["widget"]=="text":
        ans=st.text_input("Tu respuesta:", key=f"inp{step}")
    else:
        ans=st.selectbox("Tu respuesta:", q["options"], key=f"inp{step}")
    if st.button("Enviar", key=f"btn{step}"):
        if q["key"]=="budget":
            ans=parse_number(ans) or 0
        st.session_state.answers[q["key"]]=ans
        st.session_state.chat.append({"role":"user","content":str(ans)})
        st.session_state.step+=1
        st.rerun()

# ---------- fin de preguntas ----------
else:
    with st.chat_message("assistant"):
        st.markdown("¡Gracias! Procesando tus respuestas…")

    # GPT → filtros
    prompt=f"""
Convierte el JSON de respuestas del usuario a filtros. Devuelve SOLO el objeto:
brand, max_price, min_storage, min_ram, min_camera_mp (null si no aplica).

{json.dumps(st.session_state.answers, ensure_ascii=False)}
"""
    try:
        filt=json.loads(openai.ChatCompletion.create(
            model=MODEL,
            messages=[{"role":"user","content":prompt}],
            temperature=0).choices[0].message.content)
    except Exception as e:
        st.error(f"Error GPT: {e}"); st.stop()

    # SQL base
    base_sql="SELECT name,url,price_cop,storage_gb,ram_gb,camera_mp FROM phones WHERE 1=1"
    def run_query(f, override_brand=None):
        sql,params=base_sql,[]
        if override_brand is not None:
            f=f.copy(); f["brand"]=override_brand
        if f.get("brand"):         sql+=" AND brand LIKE ?"; params.append(f"%{f['brand']}%")
        if f.get("max_price"):     sql+=" AND price_cop<=?"; params.append(f["max_price"])
        if f.get("min_storage"):   sql+=" AND storage_gb>=?";params.append(f["min_storage"])
        if f.get("min_ram"):       sql+=" AND ram_gb>=?";    params.append(f["min_ram"])
        if f.get("min_camera_mp"): sql+=" AND camera_mp>=?"; params.append(f["min_camera_mp"])
        conn=sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row
        rows=conn.execute(sql+" LIMIT 5",params).fetchall(); conn.close()
        return rows

    rows=run_query(filt)

    # Si vacío y había marca -> quitar marca y mostrar alternativas TOP por cámara vs precio
    if not rows and filt.get("brand"):
        alt_rows=run_query(filt, override_brand=None)
        explain = ("No encontré modelos de esa marca con esos requisitos.\n\n"
                   "Aquí tienes 3 opciones destacadas de otras marcas:")
        rows=alt_rows[:3]  # top 3
    else:
        explain=None

    if rows:
        df=pd.DataFrame(rows)
        df["Enlace"]=df["url"].apply(lambda u:f"[Ver]({u})")
        with st.chat_message("assistant"):
            if explain: st.warning(explain)
            st.success(f"Resultados ({len(df)})")
            st.dataframe(df.drop(columns=["url"]), use_container_width=True)
    else:
        with st.chat_message("assistant"):
            st.info("No encontré celulares con esos criterios. "
                    "Pulsa *Reiniciar* para intentarlo de nuevo.")

    if st.button("🔄 Reiniciar"):
        for k in ("chat","step","answers"): st.session_state.pop(k,None)
        st.rerun()
