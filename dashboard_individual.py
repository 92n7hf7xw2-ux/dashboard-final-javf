import json
import pandas as pd
import streamlit as st
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
import seaborn as sns

st.set_page_config(
    page_title="Dashboard geoespacial de ventas",
    layout="wide"
)

# -----------------------------
# Carga de datos
# -----------------------------
@st.cache_data
def cargar_datos():
    df = pd.read_excel("dataset_tarea_ind.xlsx")

    cols_convertir = ["lat", "lng", "lat_cd", "lng_cd", "venta_neta", "kms_dist"]
    for col in cols_convertir:
        df[col] = (
            df[col]
            .astype(str)
            .str.replace(",", ".", regex=False)
            .astype(float)
        )

    df["fecha_compra"] = pd.to_datetime(df["fecha_compra"], dayfirst=True, errors="coerce")
    return df


@st.cache_data
def cargar_geojson():
    with open("comunas_metropolitana-1.geojson", "r", encoding="utf-8") as f:
        return json.load(f)


df = cargar_datos()
geojson_data = cargar_geojson()

# -----------------------------
# Título
# -----------------------------
st.title("Dashboard geoespacial de ventas")
st.markdown(
    """
    Este dashboard integra visualizaciones estadísticas y geoespaciales para analizar la red logística,
    la distribución de ventas y los patrones territoriales de demanda de una cadena de tiendas.
    """
)

# -----------------------------
# Filtros
# -----------------------------
st.sidebar.header("Filtros de exploración")

canales = st.sidebar.multiselect(
    "Canal de venta",
    options=sorted(df["canal"].dropna().unique()),
    default=sorted(df["canal"].dropna().unique())
)

centros = st.sidebar.multiselect(
    "Centro de distribución",
    options=sorted(df["centro_dist"].dropna().unique()),
    default=sorted(df["centro_dist"].dropna().unique())
)

comunas = st.sidebar.multiselect(
    "Comuna",
    options=sorted(df["comuna"].dropna().unique()),
    default=sorted(df["comuna"].dropna().unique())
)

fecha_min = df["fecha_compra"].min()
fecha_max = df["fecha_compra"].max()

rango_fechas = st.sidebar.date_input(
    "Rango de fechas",
    value=(fecha_min, fecha_max),
    min_value=fecha_min,
    max_value=fecha_max
)

if isinstance(rango_fechas, tuple) and len(rango_fechas) == 2:
    fecha_inicio, fecha_fin = rango_fechas
else:
    fecha_inicio, fecha_fin = fecha_min, fecha_max

df_filtrado = df[
    (df["canal"].isin(canales)) &
    (df["centro_dist"].isin(centros)) &
    (df["comuna"].isin(comunas)) &
    (df["fecha_compra"] >= pd.to_datetime(fecha_inicio)) &
    (df["fecha_compra"] <= pd.to_datetime(fecha_fin))
].copy()

if df_filtrado.empty:
    st.warning("No existen datos para los filtros seleccionados.")
    st.stop()

# -----------------------------
# Indicadores
# -----------------------------
st.subheader("Indicadores generales")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Ventas netas", f"${df_filtrado['venta_neta'].sum():,.0f}")
col2.metric("Pedidos", f"{df_filtrado['orden'].nunique():,}")
col3.metric("Unidades", f"{df_filtrado['unidades'].sum():,}")
col4.metric("Comunas atendidas", f"{df_filtrado['comuna'].nunique()}")

# -----------------------------
# Gráficos generales
# -----------------------------
st.subheader("Panorama general del negocio")

col_a, col_b = st.columns(2)

with col_a:
    ventas_canal = df_filtrado.groupby("canal", as_index=False)["venta_neta"].sum()

    fig, ax = plt.subplots(figsize=(7, 4))
    sns.barplot(data=ventas_canal, x="canal", y="venta_neta", ax=ax)
    ax.set_title("Ventas netas por canal")
    ax.set_xlabel("Canal")
    ax.set_ylabel("Ventas netas")
    st.pyplot(fig)

with col_b:
    ventas_cd = (
        df_filtrado.groupby("centro_dist", as_index=False)["venta_neta"]
        .sum()
        .sort_values("venta_neta", ascending=False)
    )

    fig, ax = plt.subplots(figsize=(7, 4))
    sns.barplot(data=ventas_cd, x="venta_neta", y="centro_dist", ax=ax)
    ax.set_title("Ventas netas por centro de distribución")
    ax.set_xlabel("Ventas netas")
    ax.set_ylabel("Centro de distribución")
    st.pyplot(fig)

# -----------------------------
# Función: mapa red logística
# -----------------------------
def crear_mapa_red(data):
    mapa = folium.Map(
        location=[-33.45, -70.65],
        zoom_start=10,
        tiles="CartoDB positron"
    )

    folium.GeoJson(
        geojson_data,
        name="Comunas RM",
        style_function=lambda x: {
            "fillColor": "#f2f2f2",
            "color": "gray",
            "weight": 1,
            "fillOpacity": 0.15
        },
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Comuna:"])
    ).add_to(mapa)

    centros_unicos = data[["centro_dist", "lat_cd", "lng_cd"]].drop_duplicates()

    for _, row in centros_unicos.iterrows():
        folium.Marker(
            location=[row["lat_cd"], row["lng_cd"]],
            popup=f"<b>Centro:</b> {row['centro_dist']}",
            tooltip=row["centro_dist"],
            icon=folium.Icon(color="red", icon="home", prefix="fa")
        ).add_to(mapa)

    muestra = data.sample(n=min(1500, len(data)), random_state=42)
    cluster = MarkerCluster(name="Puntos de entrega").add_to(mapa)

    for _, row in muestra.iterrows():
        folium.CircleMarker(
            location=[row["lat"], row["lng"]],
            radius=3,
            color="blue",
            fill=True,
            fill_color="blue",
            fill_opacity=0.5,
            popup=(
                f"<b>Comuna:</b> {row['comuna']}<br>"
                f"<b>Canal:</b> {row['canal']}<br>"
                f"<b>Venta neta:</b> ${row['venta_neta']:,.0f}<br>"
                f"<b>Centro:</b> {row['centro_dist']}"
            ),
            tooltip=f"Entrega - {row['comuna']}"
        ).add_to(cluster)

    folium.LayerControl().add_to(mapa)
    return mapa


# -----------------------------
# Función: heatmap
# -----------------------------
def crear_heatmap(data, ponderar_venta=False):
    mapa = folium.Map(
        location=[-33.45, -70.65],
        zoom_start=10,
        tiles="CartoDB positron"
    )

    if ponderar_venta:
        heat_data = data[["lat", "lng", "venta_neta"]].dropna().values.tolist()
    else:
        heat_data = data[["lat", "lng"]].dropna().values.tolist()

    HeatMap(
        heat_data,
        radius=12,
        blur=18,
        min_opacity=0.35
    ).add_to(mapa)

    return mapa


# -----------------------------
# Función: coroplético
# -----------------------------
def crear_coropleta(data):
    ventas_comuna = (
        data.groupby("comuna", as_index=False)["venta_neta"]
        .sum()
    )

    mapa = folium.Map(
        location=[-33.45, -70.65],
        zoom_start=10,
        tiles="CartoDB positron"
    )

    folium.Choropleth(
        geo_data=geojson_data,
        name="Ventas por comuna",
        data=ventas_comuna,
        columns=["comuna", "venta_neta"],
        key_on="feature.properties.name",
        fill_color="YlOrRd",
        fill_opacity=0.7,
        line_opacity=0.3,
        legend_name="Ventas netas por comuna"
    ).add_to(mapa)

    folium.GeoJson(
        geojson_data,
        name="Comunas",
        style_function=lambda x: {
            "fillColor": "transparent",
            "color": "black",
            "weight": 0.5
        },
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Comuna:"])
    ).add_to(mapa)

    folium.LayerControl().add_to(mapa)
    return mapa


# -----------------------------
# Mapas
# -----------------------------
st.subheader("Visualizaciones geoespaciales")

tab1, tab2, tab3 = st.tabs([
    "Red logística",
    "Mapa de calor",
    "Mapa coroplético"
])

with tab1:
    st.markdown("Centros de distribución y muestra representativa de puntos de entrega.")
    st_folium(crear_mapa_red(df_filtrado), width=1100, height=600, returned_objects=[])

with tab2:
    tipo_heatmap = st.radio(
        "Seleccione tipo de HeatMap",
        ["Cantidad de pedidos", "Venta neta"],
        horizontal=True
    )

    if tipo_heatmap == "Cantidad de pedidos":
        st.markdown("Mapa de calor basado en densidad de pedidos.")
        st_folium(crear_heatmap(df_filtrado, ponderar_venta=False), width=1100, height=600, returned_objects=[])
    else:
        st.markdown("Mapa de calor ponderado por venta neta.")
        st_folium(crear_heatmap(df_filtrado, ponderar_venta=True), width=1100, height=600, returned_objects=[])

with tab3:
    st.markdown("Mapa coroplético de ventas netas totales por comuna.")
    st_folium(crear_coropleta(df_filtrado), width=1100, height=600, returned_objects=[])

# -----------------------------
# Visualización de síntesis
# -----------------------------
st.subheader("Hallazgo principal")

resumen_comuna = (
    df_filtrado.groupby("comuna")
    .agg(
        ventas_totales=("venta_neta", "sum"),
        cantidad_pedidos=("orden", "count")
    )
    .reset_index()
)

top_comunas = resumen_comuna.sort_values("ventas_totales", ascending=False).head(10)

fig, ax1 = plt.subplots(figsize=(12, 5))

sns.barplot(
    data=top_comunas,
    x="comuna",
    y="ventas_totales",
    ax=ax1
)

ax1.set_title("Las comunas con mayor venta no siempre concentran más pedidos")
ax1.set_xlabel("Comuna")
ax1.set_ylabel("Ventas netas totales")
ax1.tick_params(axis="x", rotation=45)

ax2 = ax1.twinx()

sns.lineplot(
    data=top_comunas,
    x="comuna",
    y="cantidad_pedidos",
    marker="o",
    ax=ax2
)

ax2.set_ylabel("Cantidad de pedidos")

plt.tight_layout()
st.pyplot(fig)

st.markdown(
    """
    **Lectura principal:** el dashboard permite observar que las comunas con mayor valor económico
    no siempre coinciden con aquellas que concentran mayor cantidad de pedidos. Esta diferencia
    permite distinguir territorios de alto volumen operativo y territorios de alto valor comercial.
    """
)

# -----------------------------
# Datos filtrados
# -----------------------------
with st.expander("Ver datos filtrados"):
    st.dataframe(df_filtrado)