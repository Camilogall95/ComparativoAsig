import streamlit as st
import pandas as pd
import pyodbc
import os
import streamlit as st
import plotly.express as px

# ---------------------------
# CONFIGURACIÓN DE LA PÁGINA
# ---------------------------
st.set_page_config(page_title="Comparativo de Asignaciones", layout="wide")
st.title("📊 Comparativo de Asignaciones AXA")
st.write("Selecciona dos asignaciones para comparar los valores de cartera.")

# ---------------------------
# CONEXIÓN A SQL SERVER
# ---------------------------

def conectar_sql():
    try:
        # Leer las variables de entorno configuradas en Render
        server = os.getenv("DATABASE_SERVER")
        database = os.getenv("DATABASE_NAME")
        username = os.getenv("DATABASE_USER")
        password = os.getenv("DATABASE_PASSWORD")

        # Cadena de conexión
        conn_str = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            "TrustServerCertificate=yes;"
        )

        conn = pyodbc.connect(conn_str)
        return conn

    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")
        return None
# ---------------------------
# CARGAR LISTA DE ASIGNACIONES
# ---------------------------
def obtener_asignaciones(conn):
    query = "SELECT DISTINCT asignacion FROM [dbo].[Historico_Asignaciones] ORDER BY asignacion DESC"
    df = pd.read_sql(query, conn)
    return df["asignacion"].tolist()

# ---------------------------
# FUNCIÓN DE COMPARATIVO (llave corregida)
# ---------------------------
def comparativo_completo(conn, asignacion1, asignacion2):
    query = f"""
        WITH base1 AS (
            SELECT 
                afiliacion,
                periodo_mora,
                TRY_CAST(vlr_cartera AS FLOAT) AS valor_cartera,
                tipo_cartera
            FROM [dbo].[Historico_Asignaciones]
            WHERE asignacion = '{asignacion1}'
        ),
        base2 AS (
            SELECT 
                afiliacion,
                periodo_mora,
                TRY_CAST(vlr_cartera AS FLOAT) AS valor_cartera,
                tipo_cartera
            FROM [dbo].[Historico_Asignaciones]
            WHERE asignacion = '{asignacion2}'
        ),
        comparacion AS (
            SELECT 
                COALESCE(A1.afiliacion, A2.afiliacion) AS afiliacion,
                COALESCE(A1.periodo_mora, A2.periodo_mora) AS periodo_mora,
                COALESCE(A1.tipo_cartera, A2.tipo_cartera) AS tipo_cartera,
                ISNULL(A1.valor_cartera,0) AS valor_anterior,
                ISNULL(A2.valor_cartera,0) AS valor_actual,
                ISNULL(A2.valor_cartera,0) - ISNULL(A1.valor_cartera,0) AS diferencia,
                CASE 
                    WHEN A1.valor_cartera IS NULL THEN 'NUEVO'
                    WHEN A2.valor_cartera IS NULL THEN 'ELIMINADO'
                    WHEN A1.valor_cartera < A2.valor_cartera THEN 'AUMENTÓ'
                    WHEN A1.valor_cartera > A2.valor_cartera THEN 'DISMINUYÓ'
                    ELSE 'SE MANTIENE'
                END AS estado
            FROM base1 A1
            FULL JOIN base2 A2
                ON A1.afiliacion = A2.afiliacion 
                AND A1.periodo_mora = A2.periodo_mora
        )
        SELECT * FROM comparacion
    """
    df = pd.read_sql(query, conn)
    return df

# ---------------------------
# INTERFAZ STREAMLIT
# ---------------------------
conn = conectar_sql()
if conn:
    asignaciones = obtener_asignaciones(conn)
    col1, col2 = st.columns(2)

    with col1:
        asignacion1 = st.selectbox("📁 Asignación base (anterior)", asignaciones)
    with col2:
        asignacion2 = st.selectbox("📂 Asignación a comparar (actual)", asignaciones)

    # ---------------------------
    # Ejecutar comparación
    # ---------------------------
    if st.button("🔍 Ejecutar comparación"):
        with st.spinner("Calculando comparativo completo..."):
            try:
                df_completo = comparativo_completo(conn, asignacion1, asignacion2)
                st.session_state["df_completo"] = df_completo
                st.success("✅ Comparativo completo generado. Usa los filtros de abajo para analizar.")
            except Exception as e:
                st.error(f"❌ Error al generar el comparativo: {e}")

    # ---------------------------
    # Mostrar resultados si existen
    # ---------------------------
    if "df_completo" in st.session_state:
        df_completo = st.session_state["df_completo"]

        st.divider()
        st.subheader("🏷️ Tipo de Cartera")

        # Filtro tipo mosaico
        tipos_disponibles = sorted(df_completo["tipo_cartera"].dropna().unique())
        seleccionados = st.session_state.get("tipos_seleccionados", tipos_disponibles)
        cols = st.columns(4)
        nuevos_seleccionados = []

        for i, tipo in enumerate(tipos_disponibles):
            col = cols[i % 4]
            activo = tipo in seleccionados
            if col.button(f"{'✅' if activo else '⬜'} {tipo}"):
                if activo:
                    nuevos_seleccionados = [t for t in seleccionados if t != tipo]
                else:
                    nuevos_seleccionados = seleccionados + [tipo]
                st.session_state["tipos_seleccionados"] = nuevos_seleccionados
                st.rerun()

        tipos_seleccionados = st.session_state.get("tipos_seleccionados", tipos_disponibles)
        df_filtrado = df_completo[df_completo["tipo_cartera"].isin(tipos_seleccionados)]

         # --- Asegurar que el campo periodo_mora sea numérico ---
        df_filtrado["periodo_mora"] = pd.to_numeric(df_filtrado["periodo_mora"], errors="coerce")

        # --- Clasificación de periodos ---
        def clasificar_periodo(periodo):
            if pd.isna(periodo):
                return "Sin dato"
            elif periodo <= 201812:
                return "≤ 2018"
            elif 201901 <= periodo <= 202412:
                return "2019 – 2024"
            else:
                return "> 2024"

        df_filtrado["rango_periodo"] = df_filtrado["periodo_mora"].apply(clasificar_periodo)

        # --- Filtro multiselección con toggles ---
        rangos_disponibles = ["≤ 2018", "2019 – 2024", "> 2024"]

        if "periodos_seleccionados" not in st.session_state:
            st.session_state["periodos_seleccionados"] = rangos_disponibles.copy()

        cols = st.columns(len(rangos_disponibles))
        seleccionados = []

        for i, rango in enumerate(rangos_disponibles):
            activo = rango in st.session_state["periodos_seleccionados"]
            nuevo_estado = cols[i].toggle(rango, value=activo, key=f"tgl_{rango}")
            if nuevo_estado:
                seleccionados.append(rango)

        st.session_state["periodos_seleccionados"] = seleccionados

        # --- Aplicar filtro ---
        df_filtrado = df_filtrado[df_filtrado["rango_periodo"].isin(seleccionados)]


        # ---------------------------
        # Tarjetas de totales
        # ---------------------------
        total_anterior = df_filtrado["valor_anterior"].sum()
        total_actual = df_filtrado["valor_actual"].sum()
        total_diferencia = df_filtrado["diferencia"].sum()

        col_anterior, col_actual, col_diferencia = st.columns(3)
        col_anterior.metric("Valor Total Anterior", f"${total_anterior/1_000_000_000:,.0f} Mil M")
        col_actual.metric("Valor Total Actual", f"${total_actual/1_000_000_000:,.0f} Mil M")
        col_diferencia.metric("Diferencia Total", f"${total_diferencia/1_000_000_000:,.0f} Mil M")

        # ---------------------------
        # Resumen por estado
        # ---------------------------
        resumen = df_filtrado.groupby("estado").agg(
            valor_anterior_total=("valor_anterior", "sum"),
            valor_actual_total=("valor_actual", "sum"),
            diferencia_total=("diferencia", "sum"),
            cantidad_afiliaciones=("afiliacion", "nunique")
        ).reset_index()

        orden = ['NUEVO', 'ELIMINADO', 'AUMENTÓ', 'DISMINUYÓ', 'SE MANTIENE']
        resumen["orden"] = resumen["estado"].apply(lambda x: orden.index(x) if x in orden else 99)
        resumen = resumen.sort_values("orden").drop(columns="orden")

        # Convertir valores a miles de millones
        for col in ["valor_anterior_total", "valor_actual_total", "diferencia_total"]:
            resumen[col] = resumen[col] / 1_000_000

        # Formato pesos en tabla
        resumen_formateado = resumen.copy()
        for col in ["valor_anterior_total", "valor_actual_total", "diferencia_total"]:
            resumen_formateado[col] = resumen_formateado[col].apply(lambda x: f"${x:,.0f} Mill")

        st.subheader("📊 Resumen por estado")
        st.table(resumen_formateado)

        # ---------------------------
        # GRÁFICOS INTERACTIVOS
        # ---------------------------
        st.markdown("### 📈 Visualización gráfica del comparativo")

      # --- Gráfico 1: Comparativo anterior vs actual ---
        df_melt = resumen.melt(
            id_vars=["estado"],
            value_vars=["valor_anterior_total", "valor_actual_total"],
            var_name="Tipo Valor",
            value_name="Valor"
        )

        fig1 = px.bar(
            df_melt,
            x="estado",
            y="Valor",
            color="Tipo Valor",
            barmode="group",
            text=df_melt["Valor"].apply(lambda x: f"${x:,.0f} Mill"),
            title="Comparativo de Valor Total por Estado",
            labels={"estado": "Estado", "Valor": "Valor (Mill)"},
            color_discrete_map={
                "valor_anterior_total": "#1F77B4",
                "valor_actual_total": "#2ECC71"
            }
        )

        fig1.update_traces(textposition='outside')
        fig1.update_layout(
            xaxis_title=None,
            yaxis_title="Valor ($ Mill)",
            legend_title="Tipo de valor",
            title_x=0.3,
            yaxis_tickformat=',',
        )
        fig1.update_yaxes(range=[df_melt["Valor"].min() * 1.1, df_melt["Valor"].max() * 1.4])
        st.plotly_chart(fig1, use_container_width=True)

        # Crear columna de texto personalizada para cada estado
        resumen["texto_label"] = resumen["diferencia_total"].apply(
                lambda x: f"-${abs(x):,.1f} Mill" if x < 0 else f"${x:,.0f} Mill"
            )

        # --- Gráfico 2: Diferencia total (en Millones) ---
        fig2 = px.bar(
            resumen,
            x="estado",
            y="diferencia_total",
            color="estado",
            text="texto_label",  # ✅ aquí usamos la nueva columna
            title="Diferencia Total por Estado (en Millones)",
            labels={"diferencia_total": "Diferencia ($ Mill)", "estado": "Estado"},
            color_discrete_map={
                "NUEVO": "#27AE60",
                "ELIMINADO": "#E74C3C",
                "AUMENTÓ": "#3498DB",
                "DISMINUYÓ": "#F39C12",
                "SE MANTIENE": "#95A5A6"
            }
        )

        # 👉 Ajustar rango dinámico del eje Y
        fig2.update_yaxes(range=[
            resumen["diferencia_total"].min() * 1.3 if resumen["diferencia_total"].min() < 0 else 0,
            resumen["diferencia_total"].max() * 1.3
        ])

        # 👉 Ajustar detalles visuales
        fig2.update_traces(
            textposition="outside",
            cliponaxis=False
        )
        fig2.update_layout(
            showlegend=False,
            xaxis_title=None,
            yaxis_title="Diferencia ($ Mill)",
            title_x=0.3
        )

        st.plotly_chart(fig2, use_container_width=True)



        # --- Gráfico 3: Cantidad de afiliaciones ---
        fig3 = px.pie(
            resumen,
            names="estado",
            values="cantidad_afiliaciones",
            title="Distribución de Afiliaciones por Estado",
            color="estado",
            color_discrete_map={
                "NUEVO": "#27AE60",
                "ELIMINADO": "#E74C3C",
                "AUMENTÓ": "#3498DB",
                "DISMINUYÓ": "#F39C12",
                "SE MANTIENE": "#95A5A6"
            }
        )
        st.plotly_chart(fig3, use_container_width=True)

    conn.close()
else:
    st.stop()