import streamlit as st
import sqlite3, pandas as pd, json
import openai

# --- Configuración ---
openai.api_key = st.secrets["OPENAI_API_KEY"]        # define tu clave en secrets
DB_PATH = "phones.db"                                # base con los celulares

st.set_page_config("Celuloide · Asistente de compra", "📱", layout="wide")

# --- Estilos simples (fondo blanco, header azul) ---
st.markdown("""
<style>
.stApp {background:#ffffff;}
#header {background:#004a99;color:#fff;padding:14px;border-radius:6px;margin-bottom:1rem;}
.big {font-size:1.5rem;font-weight:700;}
.btn {background:#0066cc;color:#fff;padding:6px 12px;border:none;border-radius:4px;}
</style>""", unsafe_allow_html=True)
st.markdown('<div id="header"><span class="big">📱  Encuentra tu Celular Ideal</span></div>', unsafe_allow_html=True)

# --------- 1 · Mantener estado de la conversación -----------
if "step" not in st.session_state:
    st.session_state.step = 0
    st.session_state.answers = {}

questions = [
    {"key": "budget", "label": "¿Cuál es tu presupuesto máximo (COP)?", "widget": "number"},
    {"key": "brand", "label": "¿Tienes una marca preferida? (opcional)", "widget": "text"},
    {"key": "usage", "label": "¿Para qué usarás principalmente el celular?", "widget": "select",
     "options": ["Redes sociales", "Fotografía", "Juegos", "Trabajo/estudio", "Otro"]},
    {"key": "camera", "label": "¿Qué tan importante es la cámara?", "widget": "select",
     "options": ["Poco", "Moderado", "Muy importante"]},
    {"key": "storage", "label": "¿Cuánta memoria interna prefieres?", "widget": "select",
     "options": ["64 GB o menos", "128 GB", "256 GB o más"]},
]

step = st.session_state.step

# --------- 2 · Mostrar la pregunta actual -----------
if step < len(questions):
    q = questions[step]
    st.subheader(f"Pregunta {step+1} de {len(questions)}")

    # Renderizar el widget adecuado
    if q["widget"] == "number":
        val = st.number_input(q["label"], min_value=0, step=100000)
    elif q["widget"] == "text":
        val = st.text_input(q["label"])
    elif q["widget"] == "select":
        val = st.selectbox(q["label"], q["options"])
    else:
        val = ""

    if st.button("Siguiente", key=f"next_{step}", help="Guardar respuesta y continuar", type="primary"):
        st.session_state.answers[q["key"]] = val
        st.session_state.step += 1
        st.experimental_rerun()

# --------- 3 · Todas las respuestas capturadas -> llamar GPT -----------
else:
    st.subheader("🧠 Calculando la mejor recomendación…")

    # Prompt compacto para transformar respuestas en filtros numéricos
    prompt = f"""
Convierte el siguiente JSON de respuestas del usuario a filtros para una base de datos
de celulares. Devuelve solo el objeto JSON con las claves:
brand, max_price, min_storage, min_ram, min_camera_mp (usa None si no aplica).

Respuestas:
{json.dumps(st.session_state.answers, ensure_ascii=False)}
"""
    try:
        rsp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0)
        filters = json.loads(rsp.choices[0].message.content)

    except Exception as e:
        st.error(f"Error al usar la API de OpenAI: {e}")
        st.stop()

    st.write("**Filtros calculados por IA:**")
    st.json(filters)

    # --------- 4 · Ejecutar la consulta SQL ---------
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
    rows = conn.execute(query, params).fetchmany(5)   # top-5
    conn.close()

    if rows:
        st.success(f"Encontré {len(rows)} opciones para ti:")
        df = pd.DataFrame(rows)
        df["Enlace"] = df["url"].apply(lambda u: f"[Ver]({u})")
        st.dataframe(df.drop(columns=["url"]), use_container_width=True)
    else:
        st.info("No encontré celulares que cumplan con esos criterios. "
                "Pulsa “Reiniciar” para intentar con otras respuestas.")

    # Botón reiniciar
    if st.button("🔄 Reiniciar"):
        st.session_state.step = 0
        st.session_state.answers = {}
        st.experimental_rerun()
