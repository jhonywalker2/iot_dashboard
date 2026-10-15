import time
import streamlit as st
from influxdb_client import InfluxDBClient
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.colors import sample_colorscale

# ---------------------------
# CONFIG (usa st.secrets, ver nota abajo)
# ---------------------------
url = st.secrets["INFLUX_URL"]
token = st.secrets["INFLUX_TOKEN"]
org = st.secrets["INFLUX_ORG"]
bucket = "iot_telemetry_data"

# ---------------------------
# STREAMLIT UI
# ---------------------------
st.set_page_config(page_title="IoT Dashboard", layout="wide")

st.title("🌡️ IoT Telemetry Dashboard")
st.markdown("Monitoreo de temperatura y humedad en tiempo real")

st.sidebar.header("Configuración")

time_range = st.sidebar.selectbox(
    "Rango de tiempo",
    ["-1h", "-6h", "-12h", "-24h", "-7d"],
    index=3
)

refresh = st.sidebar.slider("Auto-refresh (segundos)", 0, 60, 10)

# ---------------------------
# COLORES DINÁMICOS
# ---------------------------
# Temperatura: azul (frío) -> verde -> amarillo -> rojo (caliente)
TEMP_MIN, TEMP_MAX = 0, 45
TEMP_SCALE = [
    [0.0, "#2b83ba"],
    [0.35, "#abdda4"],
    [0.55, "#ffffbf"],
    [0.75, "#fdae61"],
    [1.0, "#d7191c"],
]

# Humedad: amarillo/naranja (seco) -> azul claro -> azul oscuro (muy húmedo)
HUM_MIN, HUM_MAX = 0, 100
HUM_SCALE = [
    [0.0, "#f4a742"],
    [0.3, "#a6d8f0"],
    [0.6, "#4a90d9"],
    [1.0, "#08306b"],
]

def get_color(value, vmin, vmax, scale):
    """Devuelve un color según la posición del valor dentro del rango."""
    if pd.isna(value):
        return "#999999"
    pos = (value - vmin) / (vmax - vmin)
    pos = max(0.0, min(1.0, pos))
    return sample_colorscale(scale, pos)[0]

def vertical_bar(value, title, unit, vmin, vmax, scale):
    """Barra vertical tipo termómetro con color dinámico."""
    color = get_color(value, vmin, vmax, scale)

    fig = go.Figure()
    # Fondo (rango completo)
    fig.add_trace(go.Bar(
        x=[title],
        y=[vmax - vmin],
        marker_color="rgba(150,150,150,0.2)",
        hoverinfo="skip",
        width=0.5,
    ))
    # Valor actual
    fig.add_trace(go.Bar(
        x=[title],
        y=[value - vmin],
        marker_color=color,
        marker_line_color="rgba(0,0,0,0.3)",
        marker_line_width=1,
        text=[f"{value:.2f} {unit}"],
        textposition="outside",
        hovertemplate=f"{title}: {value:.2f} {unit}<extra></extra>",
        width=0.5,
    ))
    fig.update_layout(
        barmode="overlay",
        showlegend=False,
        height=350,
        margin=dict(l=10, r=10, t=30, b=10),
        yaxis=dict(
            range=[0, (vmax - vmin) * 1.12],
            tickmode="array",
            tickvals=[v - vmin for v in range(int(vmin), int(vmax) + 1, max(1, int((vmax - vmin) / 5)))],
            ticktext=[str(v) for v in range(int(vmin), int(vmax) + 1, max(1, int((vmax - vmin) / 5)))],
            title=unit,
        ),
        xaxis=dict(tickfont=dict(size=14)),
    )
    return fig

# ---------------------------
# DATA FUNCTION
# ---------------------------
@st.cache_data(ttl=10)
def load_data(time_range):
    client = InfluxDBClient(url=url, token=token, org=org)
    query_api = client.query_api()

    query = f'''
    from(bucket: "{bucket}")
      |> range(start: {time_range})
      |> filter(fn: (r) => r["_field"] == "temperature" or r["_field"] == "humidity")
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> keep(columns: ["_time", "temperature", "humidity"])
    '''

    result = query_api.query_data_frame(query)

    if isinstance(result, list):
        df = pd.concat(result)
    else:
        df = result

    if df.empty:
        return df

    df["_time"] = pd.to_datetime(df["_time"])
    df["temperature"] = pd.to_numeric(df["temperature"], errors="coerce")
    df["humidity"] = pd.to_numeric(df["humidity"], errors="coerce")
    df = df.sort_values("_time")

    return df

# ---------------------------
# LOAD DATA
# ---------------------------
df = load_data(time_range)

# ---------------------------
# METRICS (barras verticales, dispuestas horizontalmente)
# ---------------------------
if not df.empty:
    st.subheader("📊 Indicadores")

    col1, col2, col3, col4 = st.columns(4)

    temp_now = df["temperature"].iloc[-1]
    hum_now = df["humidity"].iloc[-1]
    temp_avg = df["temperature"].mean()
    hum_avg = df["humidity"].mean()

    col1.plotly_chart(
        vertical_bar(temp_now, "🌡️ Temp actual", "°C", TEMP_MIN, TEMP_MAX, TEMP_SCALE),
        use_container_width=True,
    )
    col2.plotly_chart(
        vertical_bar(hum_now, "💧 Humedad actual", "%", HUM_MIN, HUM_MAX, HUM_SCALE),
        use_container_width=True,
    )
    col3.plotly_chart(
        vertical_bar(temp_avg, "🌡️ Temp promedio", "°C", TEMP_MIN, TEMP_MAX, TEMP_SCALE),
        use_container_width=True,
    )
    col4.plotly_chart(
        vertical_bar(hum_avg, "💧 Humedad promedio", "%", HUM_MIN, HUM_MAX, HUM_SCALE),
        use_container_width=True,
    )

# ---------------------------
# CHARTS
# ---------------------------
if not df.empty:

    st.subheader("📈 Serie de tiempo")

    fig = px.line(
        df,
        x="_time",
        y=["temperature", "humidity"],
        title="Temperature & Humidity"
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("⏱️ Promedio cada 10 minutos")

    df_resampled = (
        df.set_index("_time")[["temperature", "humidity"]]
        .resample("10min")
        .mean()
        .dropna()
    )

    fig2 = px.line(
        df_resampled,
        x=df_resampled.index,
        y=["temperature", "humidity"],
        title="Smoothed Data (10min avg)"
    )
    st.plotly_chart(fig2, use_container_width=True)

else:
    st.warning("No hay datos disponibles en este rango de tiempo")

# ---------------------------
# AUTO REFRESH
# ---------------------------
if refresh > 0:
    time.sleep(refresh)
    st.rerun()
