import sqlite3
import pandas as pd
import streamlit as st

DB_PATH = "phones.db"

st.set_page_config(page_title="Encuentra tu Celular Ideal", page_icon="📱", layout="wide")
st.title("Encuentra tu Celular Ideal")

st.write("Completa los campos que necesites para filtrar tu búsqueda. Deja en blanco lo que no te interese.")

budget = st.number_input("Presupuesto máximo (COP)", min_value=0, value=0)
brand = st.text_input("Marca preferida (opcional)")
storage = st.number_input("Almacenamiento mínimo (GB)", min_value=0, value=0)
ram = st.number_input("RAM mínima (GB)", min_value=0, value=0)
camera = st.number_input("Resolución de cámara mínima (MP)", min_value=0, value=0)

if st.button("Buscar celulares"):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    query = "SELECT name, url, price_cop, storage_gb, ram_gb, camera_mp FROM phones WHERE 1=1"
    params = []
    if budget > 0:
        query += " AND price_cop <= ?"
        params.append(budget)
    if brand:
        query += " AND brand LIKE ?"
        params.append(f"%{brand}%")
    if storage > 0:
        query += " AND storage_gb >= ?"
        params.append(storage)
    if ram > 0:
        query += " AND ram_gb >= ?"
        params.append(ram)
    if camera > 0:
        query += " AND camera_mp >= ?"
        params.append(camera)
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    df = pd.DataFrame(rows)
    if not df.empty:
        st.dataframe(df)
    else:
        st.info("No se encontraron celulares que cumplan con los criterios.")
