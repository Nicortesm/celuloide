import sqlite3
import pandas as pd
import streamlit as st
import openai
import os

openai.api_key = st.secrets["OPENAI_API_KEY"]
DB_PATH = "phones.db"

st.set_page_config(page_title="Celuloide: Encuentra tu Celular Ideal", page_icon="📱", layout="wide")

st.markdown(\"\"\"<style>
body, .stApp { background-color: #ffffff; color: #003366; }
input, select, textarea { background-color: #f0f8ff; border: 1px solid #003366; color: #003366; }
button { background-color: #0066cc; color: #ffffff; border-radius: 4px; }
button:hover { background-color: #004a99; }
</style>\"\"\", unsafe_allow_html=True)

st.title("📱 Encuentra tu Celular Ideal con IA")
st.write("Describe lo que buscas en un celular como si estuvieras hablando con una persona:")

user_input = st.text_area("¿Qué estás buscando?", placeholder="Ej: Quiero un celular Samsung para fotos y redes sociales que cueste menos de 2 millones")

if st.button("Buscar celulares"):
    if not user_input.strip():
        st.warning("Por favor escribe al menos una frase con lo que estás buscando.")
    else:
        prompt = f"""
Eres un asistente que ayuda a elegir celulares con base en una base de datos que tiene estos campos: marca, precio (COP), almacenamiento en GB, RAM en GB y cámara en megapíxeles.

Tu tarea es convertir lo que diga el usuario en un filtro JSON con estas claves:

- brand (opcional)
- max_price (opcional)
- min_storage (en GB, opcional)
- min_ram (en GB, opcional)
- min_camera_mp (en megapíxeles, opcional)

Ejemplo de respuesta:

{{
  "brand": "Samsung",
  "max_price": 2000000,
  "min_storage": 128,
  "min_ram": 6,
  "min_camera_mp": 48
}}

Ahora convierte esta petición:

\"\"\"{user_input}\"\"\"
"""

        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            filters = eval(response.choices[0].message.content.strip())
            st.subheader("🎯 Filtros aplicados por la IA")
            st.json(filters)

            # Armar la consulta
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            query = "SELECT name, url, price_cop, storage_gb, ram_gb, camera_mp FROM phones WHERE 1=1"
            params = []

            if "brand" in filters:
                query += " AND brand LIKE ?"
                params.append(f"%{filters['brand']}%")
            if "max_price" in filters:
                query += " AND price_cop <= ?"
                params.append(filters["max_price"])
            if "min_storage" in filters:
                query += " AND storage_gb >= ?"
                params.append(filters["min_storage"])
            if "min_ram" in filters:
                query += " AND ram_gb >= ?"
                params.append(filters["min_ram"])
            if "min_camera_mp" in filters:
                query += " AND camera_mp >= ?"
                params.append(filters["min_camera_mp"])

            cur.execute(query, params)
            rows = cur.fetchall()
            conn.close()

            df = pd.DataFrame(rows)
            if not df.empty:
                st.success(f"Se encontraron {len(df)} celulares")
                df["Ver producto"] = df["url"].apply(lambda u: f"[Enlace]({u})")
                st.dataframe(df.drop(columns=["url"]), use_container_width=True)
            else:
                st.info("No se encontraron celulares con los filtros detectados.")

        except Exception as e:
            st.error(f"Hubo un error con la API: {e}")
