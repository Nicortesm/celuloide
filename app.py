import streamlit as st
import sqlite3, pandas as pd, json, re
import openai

openai.api_key = st.secrets["OPENAI_API_KEY"]
DB_PATH = "phones.db"

st.set_page_config(page_title="Celuloide · Asistente de compra", page_icon="📱")

st.markdown(
    '<div style="background:#004a99;padding:14px;border-radius:6px;"><span '
    'style="color:#fff;font-size:1.4rem;font-weight:700">📱 Encuentra tu Celular Ideal</span></div>',
    unsafe_allow_html=True,
)

# ---- util para convertir “dos millones” → 2000000
SPANISH = {"uno":1,"dos":2,"tres":3,"cuatro":4,"cinco":5,"seis":6,"siete":7,"ocho":8,"nueve":9,"diez":10}
def parse_number(text:str) -> int|None:
    t = text.lower().replace(".", "").replace(",", "").strip()
    digits = re.findall(r"\d+", t)
    if digits:
        return int("".join(digits))
    for word, n in SPANISH.items():
        if word in t:
            if "millón" in t or "millones" in t:
                return n * 1_000_000
            if "mil" in t:
                return n * 1_000
    return None

QUESTIONS = [
    {"key":"budget","text":"¿Cuál es tu presupuesto máximo (COP)?",
     "widget":"text"},
    {"key":"brand","text":"¿Tienes una marca preferida? (opcional)",
     "widget":"text"},
    {"key":"usage","text":"¿Para qué usarás principalmente el celular?",
     "widget":"select","options":["Redes sociales","Fotografía","Juegos","Trabajo/estudio","Otro"]},
    {"key":"camera","text":"¿Qué tan importante es la cámara?",
     "widget":"select","options":["Poco","Moderado","Muy importante"]},
    {"key":"storage","text":"¿Cuánta memoria interna prefieres?",
     "widget":"select","options":["64 GB o menos","128 GB","256 GB o más"]},
]
TOTAL = len(QUESTIONS)

# ---------- estado ----------
if "chat" not in st.session_state:
    st.session_state.chat  = [{"role":"assistant","content":"¡Hola 👋! Soy Celuloide. Te haré 5 preguntas."}]
    st.session_state.step   = 0
    st.session_state.answers= {}

# ---------- historial ----------
for m in st.session_state.chat:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

step = st.session_state.step

# ---------- preguntas ----------
if step < TOTAL:
    q = QUESTIONS[step]
    with st.chat_message("assistant"):
        st.markdown(f"**Pregunta {step+1} de {TOTAL}:** {q['text']}")
    if q["widget"]=="text":
        ans = st.text_input("Tu respuesta:", key=f"inp{step}")
    elif q["widget"]=="select":
        ans = st.selectbox("Tu respuesta:", q["options"], key=f"inp{step}")
    else:
        ans = ""
    if st.button("Enviar", key=f"btn{step}"):
        # convertir presupuesto si es necesario
        if q["key"]=="budget":
            num = parse_number(ans)
            ans = num if num is not None else 0
        st.session_state.answers[q["key"]] = ans
        st.session_state.chat.append({"role":"user","content":str(ans)})
        st.session_state.step += 1
        if hasattr(st, "rerun"): st.rerun()
        elif hasattr(st, "experimental_rerun"): st.experimental_rerun()

# ---------- procesar ----------
else:
    with st.chat_message("assistant"):
        st.markdown("¡Gracias! Procesando tus respuestas…")

    prompt = f"""
Convierte el siguiente JSON de respuestas en filtros para una base de datos
de celulares. Devuelve solo el objeto JSON con las claves:
brand, max_price, min_storage, min_ram, min_camera_mp (null si no aplica).

{json.dumps(st.session_state.answers, ensure_ascii=False)}
"""
    try:
        filt = json.loads(openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role":"user","content":prompt}],
            temperature=0
        ).choices[0].message.content)
    except Exception as e:
        st.error(f"GPT error: {e}"); st.stop()

    # consulta SQL
    sql = "SELECT name,url,price_cop,storage_gb,ram_gb,camera_mp FROM phones WHERE 1=1"
    p=[]
    if filt.get("brand"):         sql+=" AND brand LIKE ?";         p.append(f"%{filt['brand']}%")
    if filt.get("max_price"):     sql+=" AND price_cop<=?";         p.append(filt["max_price"])
    if filt.get("min_storage"):   sql+=" AND storage_gb>=?";        p.append(filt["min_storage"])
    if filt.get("min_ram"):       sql+=" AND ram_gb>=?";            p.append(filt["min_ram"])
    if filt.get("min_camera_mp"): sql+=" AND camera_mp>=?";         p.append(filt["min_camera_mp"])

    conn=sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row
    rows=conn.execute(sql,p).fetchmany(5); conn.close()

    if rows:
        df=pd.DataFrame(rows)
        df["Enlace"]=df["url"].apply(lambda u:f"[Ver]({u})")
        with st.chat_message("assistant"):
            st.success(f"Aquí tienes {len(df)} opciones:")
            st.dataframe(df.drop(columns=["url"]), use_container_width=True)
    else:
        with st.chat_message("assistant"):
            st.info("No encontré modelos con esos criterios. Pulsa Reiniciar para intentarlo de nuevo.")
    if st.button("🔄 Reiniciar"):
        for k in ("chat","step","answers"): st.session_state.pop(k,None)
        if hasattr(st, "rerun"): st.rerun()
        elif hasattr(st, "experimental_rerun"): st.experimental_rerun()
