import streamlit as st
import sqlite3, pandas as pd, json
import openai

# --- Configuración ---
openai.api_key = st.secrets["OPENAI_API_KEY"]
DB_PATH = "phones.db"

st.set_page_config(page_title="Celuloide · Asistente de compra", page_icon="📱")

st.markdown(
    '<div style="background:#004a99;padding:14px;border-radius:6px;">'
    '<span style="color:#fff;font-size:1.4rem;font-weight:700">'
    '📱  Encuentra tu Celular Ideal</span></div>',
    unsafe_allow_html=True)

QUESTIONS = [
    {"key": "budget",  "text": "¿Cuál es tu presupuesto máximo (COP)?", "widget": "number"},
    {"key": "brand",   "text": "¿Tienes una marca preferida? (opcional)", "widget": "text"},
    {"key": "usage",   "text": "¿Para qué usarás principalmente el celular?",
     "widget": "select",
     "options": ["Redes sociales", "Fotografía", "Juegos", "Trabajo/estudio", "Otro"]},
    {"key": "camera",  "text": "¿Qué tan importante es la cámara?", "widget": "select",
     "options": ["Poco", "Moderado", "Muy importante"]},
    {"key": "storage", "text": "¿Cuánta memoria interna prefieres?", "widget": "select",
     "options": ["64 GB o menos", "128 GB", "256 GB o más"]}
]
TOTAL_Q = len(QUESTIONS)

# ---------- Estado de sesión (robusto) ----------
if "chat" not in st.session_state:
    st.session_state.chat = [{"role": "assistant",
                              "content": "¡Hola 👋! Soy Celuloide. "
                                         "Te haré 5 preguntas para entender qué celular necesitas."}]
if "step" not in st.session_state:
    st.session_state.step = 0
if "answers" not in st.session_state:
    st.session_state.answers = {}

# ---------- Mostrar historial ----------
for msg in st.session_state.chat:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

step = st.session_state.step

# ---------- Flujo de preguntas ----------
if step < TOTAL_Q:
    q = QUESTIONS[step]
    with st.chat_message("assistant"):
        st.markdown(f"**Pregunta {step+1} de {TOTAL_Q}:** {q['text']}")

    if q["widget"] == "number":
        ans = st.number_input("Tu respuesta:", min_value=0, step=500000, key=f"inp_{step}")
    elif q["widget"] == "text":
        ans = st.text_input("Tu respuesta:", key=f"inp_{step}")
    elif q["widget"] == "select":
        ans = st.selectbox("Tu respuesta:", q["options"], key=f"inp_{step}")
    else:
        ans = ""

    if st.button("Enviar respuesta", key=f"btn_{step}"):
        st.session_state.answers[q["key"]] = ans
        st.session_state.chat.append({"role": "user", "content": str(ans)})
        st.session_state.step += 1
        st.experimental_rerun()

# ---------- Procesar todas las respuestas ----------
else:
    with st.chat_message("assistant"):
        st.markdown("¡Gracias! Procesando tus respuestas…")

    prompt = f"""
Convierte el siguiente JSON de respuestas en filtros para una base de datos
de celulares. Devuelve solo el objeto JSON con estas claves:
brand, max_price, min_storage, min_ram, min_camera_mp (usa null si no aplica).

{json.dumps(st.session_state.answers, ensure_ascii=False)}
"""
    try:
        rsp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0)
        filters = json.loads(rsp.choices[0].message.content)
    except Exception as e:
        with st.chat_message("assistant"):
            st.error(f"Error al usar la API: {e}")
        st.stop()

    # Construir la consulta
    q_sql, p = "SELECT name, url, price_cop, storage_gb, ram_gb, camera_mp FROM phones WHERE 1=1", []
    if filters.get("brand"):         q_sql += " AND brand LIKE ?";       p.append(f"%{filters['brand']}%")
    if filters.get("max_price"):     q_sql += " AND price_cop <= ?";     p.append(filters["max_price"])
    if filters.get("min_storage"):   q_sql += " AND storage_gb >= ?";    p.append(filters["min_storage"])
    if filters.get("min_ram"):       q_sql += " AND ram_gb >= ?";        p.append(filters["min_ram"])
    if filters.get("min_camera_mp"): q_sql += " AND camera_mp >= ?";     p.append(filters["min_camera_mp"])

    conn = sqlite3.connect(DB_PATH); conn.row_factory = sqlite3.Row
    rows = conn.execute(q_sql, p).fetchmany(5); conn.close()

    if rows:
        df = pd.DataFrame(rows)
        df["Enlace"] = df["url"].apply(lambda u: f"[Ver]({u})")
        with st.chat_message("assistant"):
            st.success(f"Encontré {len(df)} opciones para ti:")
            st.dataframe(df.drop(columns=["url"]), use_container_width=True)
    else:
        with st.chat_message("assistant"):
            st.info("No encontré celulares que cumplan esos criterios. "
                    "Pulsa *Reiniciar* para intentarlo de nuevo.")

    if st.button("🔄 Reiniciar chat"):
        for k in ("chat", "step", "answers"):
            st.session_state.pop(k, None)
        st.experimental_rerun()
