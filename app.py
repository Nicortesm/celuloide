"""
Celuloide – Asistente de compra de celulares  (versión estable)
- Flujo guiado de 5 preguntas.
- Parser flexible de presupuesto (8m, ocho millones, etc.).
- Llamada a OpenAI 1.x con response_format="json_object" → garantiza JSON válido.
- Timeout 30 s con tenacity.
- Si no hay coincidencias exactas pero hay marca, sugiere 3 modelos de otras marcas.
- Mensajes claros si la IA no devuelve JSON o si no hay resultados.
"""

import streamlit as st
import sqlite3, pandas as pd, json, re
from json import JSONDecodeError
from tenacity import retry, stop_after_delay
from openai import OpenAI

# ---------------- CONFIG ----------------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])     # secrets.toml
DB_PATH = "phones.db"                                     # base SQLite
MODEL   = "gpt-3.5-turbo"

st.set_page_config(page_title="Celuloide · Asistente de compra", page_icon="📱")
st.markdown(
    '<div style="background:#004a99;padding:14px;border-radius:6px;">'
    '<span style="color:#fff;font-size:1.4rem;font-weight:700">'
    '📱 Encuentra tu Celular Ideal</span></div>',
    unsafe_allow_html=True,
)

# ---------------- Util presupuesto ----------------
SPANISH = {"uno":1,"dos":2,"tres":3,"cuatro":4,"cinco":5,"seis":6,"siete":7,
           "ocho":8,"nueve":9,"diez":10}

def gpt_to_number(text:str)->int|None:
    """Si el parser local falla, consulta GPT para convertir a entero."""
    p = f"Convierte '{text}' a número entero COP. Devuelve solo dígitos."
    try:
        rsp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role":"user","content":p}],
            response_format={"type":"json_object"},
            temperature=0)
        num = int(json.loads(rsp.choices[0].message.content)["number"])
        return num if num > 0 else None
    except Exception:
        return None

def parse_number(text:str)->int|None:
    t = text.lower().replace(".", "").replace(",", "").strip()
    # dígitos con k/m
    if re.fullmatch(r"\d+[kKmM]?", t):
        n=int(re.findall(r"\d+", t)[0])
        if t.endswith(("m","M")) and n<1000: n*=1_000_000
        if t.endswith(("k","K")):            n*=1_000
        return n
    # contiene millones / mil
    dig=re.findall(r"\d+", t)
    if dig and ("mill" in t): return int(dig[0])*1_000_000
    if dig and "mil"  in t:  return int(dig[0])*1_000
    # palabras
    for w,n in SPANISH.items():
        if w in t:
            if "mill" in t: return n*1_000_000
            if "mil"  in t: return n*1_000
            return n
    # GPT respaldo
    return gpt_to_number(text)

# ---------------- Preguntas ----------------
Q = [
 {"key":"budget","text":"¿Cuál es tu presupuesto máximo (COP)?","widget":"text"},
 {"key":"brand","text":"¿Tienes una marca preferida? (opcional)","widget":"text"},
 {"key":"usage","text":"¿Para qué usarás principalmente el celular?",
  "widget":"select","options":["Redes sociales","Fotografía","Juegos","Trabajo/estudio","Otro"]},
 {"key":"camera","text":"¿Qué tan importante es la cámara?",
  "widget":"select","options":["Poco","Moderado","Muy importante"]},
 {"key":"storage","text":"¿Cuánta memoria interna prefieres?",
  "widget":"select","options":["64 GB o menos","128 GB","256 GB o más"]},
]
TOTAL=len(Q)

# ---------------- Estado de sesión ----------------
if "chat" not in st.session_state:
    st.session_state.chat=[{"role":"assistant",
                            "content":"¡Hola 👋! Soy Celuloide. Te haré 5 preguntas."}]
    st.session_state.step=0
    st.session_state.answers={}

S=st.session_state  # alias corto

# ---------------- Mostrar historial ----------------
for m in S.chat:
    with st.chat_message(m["role"]): st.markdown(m["content"])

step=S.step

# ---------------- Preguntas guiadas ----------------
if step<TOTAL:
    q=Q[step]
    with st.chat_message("assistant"):
        st.markdown(f"**Pregunta {step+1}/{TOTAL}:** {q['text']}")
    ans = st.text_input("Tu respuesta:") if q["widget"]=="text" else \
          st.selectbox("Tu respuesta:", q["options"])
    if st.button("Enviar"):
        if q["key"]=="budget": ans=parse_number(ans) or 0
        S.answers[q["key"]]=ans
        S.chat.append({"role":"user","content":str(ans)})
        S.step += 1
        st.rerun()

# ---------------- Procesar respuestas ----------------
else:
    with st.chat_message("assistant"): st.markdown("⌛ Procesando tus respuestas…")

    prompt=f"""
Devuelve SOLO un objeto JSON válido (sin texto extra) con:
brand, max_price, min_storage, min_ram, min_camera_mp (null si no aplica).

Respuestas del usuario:
{json.dumps(S.answers, ensure_ascii=False)}
"""
    @retry(stop=stop_after_delay(30))
    def gpt_filters(p:str)->dict:
        rsp=client.chat.completions.create(
            model=MODEL,
            messages=[{"role":"user","content":p}],
            response_format={"type":"json_object"},
            temperature=0)
        return json.loads(rsp.choices[0].message.content)

    try:
        filt=gpt_filters(prompt)
    except Exception as e:
        with st.chat_message("assistant"):
            st.error(f"No pude interpretar tus respuestas (error: {e}). "
                     "Pulsa Reiniciar para intentarlo de nuevo.")
        st.stop()

    # -------- Consulta SQL --------
    def run_query(f, override_brand=None, limit=5):
        sql="SELECT name,url,price_cop,storage_gb,ram_gb,camera_mp FROM phones WHERE 1=1"
        p=[]; f=f.copy()
        if override_brand is not None: f["brand"]=override_brand
        if f.get("brand"):         sql+=" AND brand LIKE ?"; p.append(f"%{f['brand']}%")
        if f.get("max_price"):     sql+=" AND price_cop<=?"; p.append(f["max_price"])
        if f.get("min_storage"):   sql+=" AND storage_gb>=?";p.append(f["min_storage"])
        if f.get("min_ram"):       sql+=" AND ram_gb>=?";   p.append(f["min_ram"])
        if f.get("min_camera_mp"): sql+=" AND camera_mp>=?";p.append(f["min_camera_mp"])
        conn=sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row
        rows=conn.execute(sql+" LIMIT ?", p+[limit]).fetchall(); conn.close()
        return rows

    rows=run_query(filt)

    explain=None
    if not rows and filt.get("brand"):
        rows=run_query(filt, override_brand=None, limit=3)
        explain=("No encontré modelos de esa marca con tus requisitos.\n\n"
                 "Aquí tienes 3 opciones competitivas de otras marcas:")

    if rows:
        df=pd.DataFrame(rows)
        df["Enlace"]=df["url"].apply(lambda u:f"[Ver]({u})")
        with st.chat_message("assistant"):
            if explain: st.warning(explain)
            else: st.success(f"Encontré {len(df)} opciones:")
            st.dataframe(df.drop(columns=["url"]), use_container_width=True)
    else:
        with st.chat_message("assistant"):
            st.info("No se encontraron modelos con esos criterios. "
                    "Pulsa Reiniciar para intentarlo de nuevo.")

    if st.button("🔄 Reiniciar"):
        st.session_state.clear(); st.rerun()
