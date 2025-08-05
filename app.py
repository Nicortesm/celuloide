import sqlite3
import pandas as pd
import streamlit as st
import openai
import json

# --- Configuración de API ---
openai.api_key = st.secrets["OPENAI_API_KEY"]  # define esto en los secretos de Streamlit
DB_PATH = "phones.db"  # base de datos creada por el scraper

# --- Configurar página y estilos ---
st.set_page_config(page_title="Celuloide: Encuentra tu Celular Ideal",
                   page_icon="📱",
                   layout="wide")

st.markdown("""
    <style>
    body, .stApp { background-color: #ffffff; color: #003366; }
    input, select, textarea {
        background-color: #f0f8ff;
        border: 1px solid #003366;
        color: #003366;
    }
    button { background-color: #0066cc; color: #ffffff; border-radius: 4px; }
    button:hover { background-color: #004a99; }
    </style>
""", unsafe_allow_html=True)

# --- UI ---
st.title("📱 Encuentra tu Celular Ideal con IA")
st.write("Describe lo que buscas en un celular en lenguaje natural.")

user_input = st.text_area("¿Qué estás buscando?",
                          placeholder="Ej: Quiero un celular Samsung para fotos y redes sociales que cueste menos de 2 millones")

# --- Al hacer clic en Buscar ---
if st.button("Buscar celulares"):
    if not user_input.strip():
        st.warning("Por favor escribe al menos una frase con lo que estás buscando.")
        st.stop()

    # ---- Prompt para GPT ----
    prompt = f'''
Eres un asistente que ayuda a elegir celulares con base en una base de datos
que tiene estos campos: marca, precio (COP), almacenamiento en GB, RAM en GB
y cámara en megapíxeles.

Convierte la petición del usuario en un JSON con estas claves:
brand, max_price, min_storage, min_ram, min_camera_mp (todas opcionales).
Ejemplo esperado:
{{
  "brand": "Samsung",
  "max_price": 2000000,
  "min_storage": 128,
  "min_ram": 6,
  "min_camera_mp": 48
}}

Petición del usuario:
"{user_input}"
'''

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        # Convertir la respuesta en diccionario de filtros
        filters = json.loads(response.choices[0].message.content.strip())

        st.subheader("🎯 Filtros aplicados por la IA")
        st.json(filters)

        # ---- Construir consulta SQL dinámica ----
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

        # ---- Ejecutar consulta ----
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()

        # ---- Mostrar resultados ----
        df = pd.DataFrame(rows)
        if df.empty:
            st.info("No se encontraron celulares con los filtros detectados.")
        else:
            st.success(f"Se encontraron {len(df)} celulares")
            df["Ver producto"] = df["url"].apply(lambda u: f"[Enlace]({u})")
            st.dataframe(df.drop(columns=["url"]), use_container_width=True)

    except Exception as e:
        st.error(f"Hubo un error al consultar la API o procesar los datos: {e}")
