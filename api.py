from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import os
import glob
import shutil
import pandas as pd
from openpyxl import load_workbook

from main import procesar_excel, convertir_a_prophet, ejecutar_forecast, recalcular_equipo, detectar_outliers, recalcular_sin_outliers, procesar_csv_bigquery, procesar_csv_historico, forecast_iterativo, ejecutar_forecast_pycaret

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTENIDOS = os.path.join(BASE_DIR, "contenidos")
TMP = os.path.join(BASE_DIR, "_tmp")
TEST = os.path.join(BASE_DIR, "test")
LISTOS = os.path.join(BASE_DIR, "listos")

for d in [CONTENIDOS, TMP, TEST, LISTOS]:
    os.makedirs(d, exist_ok=True)


def parsear_nombre_equipo(equipo: str):
    """Parsea un nombre clave de equipo en (equipo_nombre, rol_nombre, metrica_nombre).
    Soporta separador '__' (nuevo) y fallback a '_' (viejo).
    """
    if '__' in equipo:
        partes = equipo.split('__')
        if len(partes) == 3:
            return partes[0].replace('_', ' '), partes[1].replace('_', ' '), partes[2]
        elif len(partes) == 2:
            return partes[0].replace('_', ' '), '', partes[1]
        else:
            return equipo.replace('_', ' '), '', 'MAXIMO'
    else:
        # Fallback viejo con rsplit
        partes = equipo.rsplit('_', 2)
        if len(partes) == 3:
            return partes[0].replace('_', ' '), partes[1].replace('_', ' '), partes[2]
        elif len(partes) == 2:
            return partes[0].replace('_', ' '), '', partes[1]
        else:
            return equipo.replace('_', ' '), '', 'MAXIMO'

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), modelo: str = Form("neuralprophet")):
    """Sube un archivo .xlsx a contenidos/ y ejecuta el pipeline completo."""
    if not file.filename.endswith(".xlsx"):
        return JSONResponse(status_code=400, content={"error": "Solo se aceptan archivos .xlsx"})

    # Guardar archivo en contenidos/
    ruta = os.path.join(CONTENIDOS, file.filename)
    with open(ruta, "wb") as f:
        f.write(await file.read())

    # Paso 1: Procesar Excel -> _tmp
    nombre_csv = os.path.splitext(file.filename)[0] + ".csv"
    ruta_tmp = os.path.join(TMP, nombre_csv)
    procesar_excel(ruta, ruta_tmp)

    # Paso 2: Convertir a formato Prophet -> test/
    convertir_a_prophet(ruta, TEST)

    # Paso 3: Forecast -> listos/
    if modelo == 'neuralprophet':
        errores = ejecutar_forecast(TEST, LISTOS, fecha_limite="2028-03-01")
    else:
        errores = ejecutar_forecast_pycaret(TEST, LISTOS, fecha_limite="2028-03-01", modelo=modelo)

    return {
        "message": f"Archivo '{file.filename}' procesado con {modelo}.",
        "errores": errores or [],
    }


@app.get("/api/equipos")
def listar_equipos():
    """Lista todos los equipos con forecast disponible."""
    archivos = glob.glob(os.path.join(LISTOS, "frcst_*.csv"))
    equipos = [os.path.basename(f).replace("frcst_", "").replace(".csv", "") for f in archivos]
    equipos.sort()
    return {"equipos": equipos}


@app.post("/api/upload-bq-csv")
async def upload_bq_csv(file: UploadFile = File(...), rol: str = Form("CDN"), modelo: str = Form("neuralprophet")):
    """
    Sube un CSV con formato BigQuery y lo procesa.
    Columnas esperadas: id_enlace, time_series_timestamp, time_series_type, time_series_adjusted_data
    """
    if not file.filename.endswith(".csv"):
        return JSONResponse(status_code=400, content={"error": "Solo se aceptan archivos .csv"})

    # Guardar CSV temporalmente
    ruta_csv = os.path.join(CONTENIDOS, file.filename)
    with open(ruta_csv, "wb") as f:
        f.write(await file.read())

    # Procesar
    resultado = procesar_csv_bigquery(ruta_csv, rol, TEST, LISTOS, fecha_limite="2028-03-01")

    if "error" in resultado:
        return JSONResponse(status_code=400, content=resultado)

    return {
        "message": f"CSV '{file.filename}' procesado. {len(resultado['equipos'])} equipo(s) cargados.",
        "equipos": resultado["equipos"],
        "errores": resultado.get("errores", []),
    }


@app.post("/api/reimportar-excel")
async def reimportar_excel(file: UploadFile = File(...)):
    """
    Reimporta un Excel ya forecasteado para editar en el visualizador.
    Lee las filas, separa HISTORICO MEDICION y PROYECCION ACTUAL,
    y genera los frcst_*.csv en listos/ para cada equipo.
    """
    if not file.filename.endswith(".xlsx"):
        return JSONResponse(status_code=400, content={"error": "Solo se aceptan archivos .xlsx"})

    # Guardar temporalmente
    ruta = os.path.join(CONTENIDOS, file.filename)
    with open(ruta, "wb") as f:
        f.write(await file.read())

    # Leer Excel
    try:
        df = pd.read_excel(ruta, sheet_name="Datos Forecast")
    except ValueError:
        df = pd.read_excel(ruta)

    if 'Equipo' not in df.columns or 'Capa' not in df.columns:
        return JSONResponse(status_code=400, content={"error": "El Excel no tiene las columnas esperadas (Equipo, Capa, Fecha, Valor)"})

    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
    df = df.dropna(subset=['Fecha'])

    # Determinar columnas de agrupación
    cols_grupo = ['Equipo']
    if 'Rol' in df.columns:
        cols_grupo.append('Rol')
    if 'Metrica' in df.columns:
        cols_grupo.append('Metrica')

    equipos_procesados = []

    for clave, grupo in df.groupby(cols_grupo):
        if not isinstance(clave, tuple):
            clave = (clave,)
        partes = [str(c).replace(' ', '_').replace('/', '-').replace('|', '-').replace(':', '-').replace('*', '-').replace('?', '-').replace('"', '-').replace('<', '-').replace('>', '-').replace('\\', '-') for c in clave]
        nombre_clave = '__'.join(partes)

        # Separar histórico y forecast
        historico = grupo[grupo['Capa'].astype(str).str.strip() == 'HISTORICO MEDICION'].copy()
        forecast = grupo[grupo['Capa'].astype(str).str.strip() == 'PROYECCION ACTUAL'].copy()

        if historico.empty and forecast.empty:
            continue

        filas = []
        for _, row in historico.iterrows():
            filas.append({
                'ds': row['Fecha'].strftime('%Y-%m-%d %H:%M:%S'),
                'y': float(row['Valor']) if pd.notna(row.get('Valor')) else 0.0,
                'tipo': 'historico',
            })
        for _, row in forecast.iterrows():
            filas.append({
                'ds': row['Fecha'].strftime('%Y-%m-%d %H:%M:%S'),
                'y': float(row['Valor']) if pd.notna(row.get('Valor')) else 0.0,
                'tipo': 'forecast',
            })

        df_frcst = pd.DataFrame(filas)
        df_frcst = df_frcst.sort_values('ds').reset_index(drop=True)
        df_frcst['origen'] = 'reimportado'

        nombre_salida = f"frcst_{nombre_clave}.csv"
        ruta_salida = os.path.join(LISTOS, nombre_salida)
        df_frcst.to_csv(ruta_salida, index=False)

        # También guardar histórico en test/ para outliers y recálculos
        if not historico.empty:
            prophet_df = pd.DataFrame({
                'ds': historico['Fecha'].dt.strftime('%Y-%m-%d %H:%M:%S'),
                'y': historico['Valor'].astype(float),
            }).sort_values('ds').drop_duplicates(subset='ds', keep='last').reset_index(drop=True)
            ruta_test = os.path.join(TEST, f"{nombre_clave}.csv")
            prophet_df.to_csv(ruta_test, index=False)

        equipos_procesados.append(nombre_clave)

    return {
        "message": f"Excel reimportado. {len(equipos_procesados)} equipo(s) cargados para edición.",
        "equipos": equipos_procesados,
    }


@app.delete("/api/borrar-todo")
def borrar_todo():
    """Borra todos los archivos de contenidos/, test/, listos/ y _tmp/."""
    for carpeta in [CONTENIDOS, TMP, TEST, LISTOS]:
        for f in glob.glob(os.path.join(carpeta, "*")):
            try:
                os.remove(f)
            except Exception:
                pass
    return {"message": "Todo borrado correctamente."}


@app.post("/api/completar-forecast")
async def completar_forecast(file: UploadFile = File(...), equipos: str = Form("")):
    """
    Recibe un Excel con formato final y una lista de equipos fallidos.
    Para cada equipo, busca sus filas HISTORICO MEDICION dentro del Excel,
    ejecuta forecast iterativo con NeuralProphet y agrega PROYECCION ACTUAL.
    Retorna el Excel completado.
    """
    if not file.filename.endswith(".xlsx"):
        return JSONResponse(status_code=400, content={"error": "Solo se aceptan archivos .xlsx"})

    # Guardar Excel temporalmente
    ruta_excel = os.path.join(LISTOS, f"_completar_{file.filename}")
    with open(ruta_excel, "wb") as f:
        f.write(await file.read())

    # Leer Excel
    try:
        df_excel = pd.read_excel(ruta_excel, sheet_name="Datos Forecast")
    except ValueError:
        df_excel = pd.read_excel(ruta_excel)

    COLUMNAS = ['Fecha', 'Equipo', 'Rol', 'Geo 1', 'Geo 2', 'Geo 3',
                'Capa', 'Metrica', 'Valor', 'Intervalo Menor', 'Intervalo Mayor',
                'Capacidad', 'Fecha Menor', 'Fecha Valor', 'Fecha Mayor']

    for col in COLUMNAS:
        if col not in df_excel.columns:
            df_excel[col] = ''

    df_excel['Fecha'] = pd.to_datetime(df_excel['Fecha'], errors='coerce')

    # Parsear lista de equipos - formato: "Equipo, Rol, Metrica" uno por línea
    lineas = [l.strip() for l in equipos.replace('\r', '').split('\n') if l.strip()]
    lista_equipos = []
    for linea in lineas:
        partes = [p.strip() for p in linea.split(',')]
        if len(partes) >= 2:
            equipo_nombre = partes[0].strip().upper()
            rol = partes[1].strip().upper()
            metrica = partes[2].strip().upper() if len(partes) >= 3 else 'MAXIMO'
            lista_equipos.append((equipo_nombre, rol, metrica))
        elif len(partes) == 1 and partes[0]:
            # Formato clave directa: EQUIPO__ROL__METRICA o EQUIPO_ROL_METRICA
            clave = partes[0].strip().upper()
            eq, rl, mt = parsear_nombre_equipo(clave)
            lista_equipos.append((eq, rl, mt))

    if not lista_equipos:
        os.remove(ruta_excel)
        return JSONResponse(status_code=400, content={"error": "No se proporcionaron equipos. Formato: Equipo, Rol, Metrica (uno por línea)"})

    # Procesar cada equipo
    equipos_completados = []
    errores = []

    for (equipo_nombre, rol, metrica) in lista_equipos:
        # Buscar filas HISTORICO MEDICION de este equipo en el Excel
        mask = (
            (df_excel['Equipo'].astype(str).str.strip().str.upper() == equipo_nombre) &
            (df_excel['Rol'].astype(str).str.strip().str.upper() == rol) &
            (df_excel['Metrica'].astype(str).str.strip().str.upper() == metrica) &
            (df_excel['Capa'].astype(str).str.strip() == 'HISTORICO MEDICION')
        )
        historico = df_excel[mask].copy()

        if historico.empty:
            errores.append({"equipo": f"{equipo_nombre} {rol} {metrica}", "motivo": "Sin datos históricos en el Excel"})
            continue

        historico = historico.dropna(subset=['Fecha', 'Valor'])
        historico = historico.sort_values('Fecha').reset_index(drop=True)

        if historico.empty:
            errores.append({"equipo": f"{equipo_nombre} {rol} {metrica}", "motivo": "Fechas o valores inválidos"})
            continue

        # Crear df para NeuralProphet
        df_train = pd.DataFrame({
            'ds': historico['Fecha'].dt.to_period('M').dt.to_timestamp(),
            'y': historico['Valor'].astype(float),
        }).drop_duplicates(subset='ds', keep='last').reset_index(drop=True)

        # Guardar en test/ para que forecast_iterativo lo encuentre
        equipo_safe = equipo_nombre.replace(' ', '_')
        nombre_clave = f"{equipo_safe}__{rol}__{metrica}"
        ruta_test = os.path.join(TEST, f"{nombre_clave}.csv")
        df_train.to_csv(ruta_test, index=False)

        # Ejecutar forecast iterativo
        resultado = forecast_iterativo(TEST, LISTOS, nombre_clave, fecha_limite="2028-03-01")
        if "error" in resultado:
            errores.append({"equipo": f"{equipo_nombre} {rol} {metrica}", "motivo": resultado["error"]})
            continue

        # Leer el frcst generado y agregar solo PROYECCION ACTUAL al Excel
        ruta_frcst = os.path.join(LISTOS, f"frcst_{nombre_clave}.csv")
        if not os.path.exists(ruta_frcst):
            errores.append({"equipo": f"{equipo_nombre} {rol} {metrica}", "motivo": "No se generó forecast"})
            continue

        df_frcst = pd.read_csv(ruta_frcst)
        df_frcst['ds'] = pd.to_datetime(df_frcst['ds'])

        # Solo agregar filas de forecast (el histórico ya está en el Excel)
        df_forecast_only = df_frcst[df_frcst['tipo'] == 'forecast'].copy()

        nuevas_filas = []
        for _, row in df_forecast_only.iterrows():
            fila = {col: '' for col in COLUMNAS}
            fila['Fecha'] = row['ds']
            fila['Equipo'] = equipo_nombre
            fila['Rol'] = rol
            fila['Metrica'] = metrica
            fila['Capa'] = 'PROYECCION ACTUAL'
            fila['Valor'] = round(float(row['y']), 2)
            fila['Intervalo Menor'] = round(float(row['y']) * 0.9, 2)
            fila['Intervalo Mayor'] = round(float(row['y']) * 1.1, 2)
            nuevas_filas.append(fila)

        df_nuevas = pd.DataFrame(nuevas_filas, columns=COLUMNAS)
        df_excel = pd.concat([df_excel, df_nuevas], ignore_index=True)
        equipos_completados.append(f"{equipo_nombre} {rol} {metrica}")
        print(f"  Completado: {equipo_nombre} {rol} {metrica} ({len(df_forecast_only)} meses)")

    # Ordenar por Equipo, Rol, Metrica, Capa, Fecha
    cols_orden = [c for c in ['Equipo', 'Rol', 'Metrica', 'Capa', 'Fecha'] if c in df_excel.columns]
    if cols_orden:
        df_excel = df_excel.sort_values(cols_orden).reset_index(drop=True)

    # Guardar Excel completado
    nombre_export = "forecast_completado.xlsx"
    ruta_export = os.path.join(LISTOS, nombre_export)
    df_excel[COLUMNAS].to_excel(ruta_export, index=False, sheet_name="Datos Forecast")

    # Limpiar temporal
    if os.path.exists(ruta_excel):
        os.remove(ruta_excel)

    return FileResponse(
        ruta_export,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=nombre_export,
    )


@app.post("/api/upload-historico-csv")
async def upload_historico_csv(file: UploadFile = File(...), modelo: str = Form("neuralprophet")):
    """
    Sube un CSV con formato de histórico de proveedores y ejecuta forecast.
    Columnas esperadas: mes, proveedor, capa, max_mbps
    """
    if not file.filename.endswith(".csv"):
        return JSONResponse(status_code=400, content={"error": "Solo se aceptan archivos .csv"})

    ruta_csv = os.path.join(CONTENIDOS, file.filename)
    with open(ruta_csv, "wb") as f:
        f.write(await file.read())

    resultado = procesar_csv_historico(ruta_csv, TEST, LISTOS, fecha_limite="2028-03-01", modelo=modelo)

    if "error" in resultado:
        return JSONResponse(status_code=400, content=resultado)

    return {
        "message": f"CSV '{file.filename}' procesado con {modelo}. {len(resultado['equipos'])} equipo(s) cargados.",
        "equipos": resultado["equipos"],
        "errores": resultado.get("errores", []),
    }


@app.get("/api/csv-archivos")
def listar_csv_archivos():
    """Lista los archivos .csv subidos en contenidos/."""
    archivos = glob.glob(os.path.join(CONTENIDOS, "*.csv"))
    nombres = [os.path.basename(f) for f in archivos]
    nombres.sort()
    return {"archivos": nombres}


@app.delete("/api/csv-archivos/{nombre}")
def borrar_csv_archivo(nombre: str):
    """Borra un archivo CSV de contenidos/ y limpia todos los forecasts derivados de CSVs."""
    ruta = os.path.join(CONTENIDOS, nombre)
    if not os.path.exists(ruta):
        return JSONResponse(status_code=404, content={"error": "Archivo no encontrado"})

    os.remove(ruta)

    # Borrar TODOS los frcst de listos/ y archivos de test/
    # (mismo enfoque que borrar_archivo para Excel)
    for carpeta in [TEST, LISTOS]:
        for f in glob.glob(os.path.join(carpeta, "*")):
            try:
                os.remove(f)
            except Exception:
                pass

    # Si quedan archivos xlsx en contenidos, reprocesarlos
    otros_xlsx = glob.glob(os.path.join(CONTENIDOS, "*.xlsx"))
    for xlsx in otros_xlsx:
        nombre_csv = os.path.splitext(os.path.basename(xlsx))[0] + ".csv"
        procesar_excel(xlsx, os.path.join(TMP, nombre_csv))
        convertir_a_prophet(xlsx, TEST)
    if otros_xlsx:
        ejecutar_forecast(TEST, LISTOS, fecha_limite="2028-03-01")

    # Si quedan otros CSVs en contenidos, reprocesarlos
    otros_csv = glob.glob(os.path.join(CONTENIDOS, "*.csv"))
    for csv_file in otros_csv:
        # Intentar como BigQuery primero, luego como histórico
        try:
            df_check = pd.read_csv(csv_file, nrows=1, sep=None, engine='python', encoding='utf-8-sig')
            if 'id_enlace' in df_check.columns:
                procesar_csv_bigquery(csv_file, "CDN", TEST, LISTOS, fecha_limite="2028-03-01")
            elif 'proveedor' in df_check.columns:
                procesar_csv_historico(csv_file, TEST, LISTOS, fecha_limite="2028-03-01")
        except Exception:
            pass

    return {"message": f"'{nombre}' eliminado y forecasts actualizados."}


@app.get("/api/archivos")
def listar_archivos():
    """Lista los archivos .xlsx subidos en contenidos/."""
    archivos = glob.glob(os.path.join(CONTENIDOS, "*.xlsx"))
    nombres = [os.path.basename(f) for f in archivos]
    nombres.sort()
    return {"archivos": nombres}


@app.delete("/api/archivos/{nombre}")
def borrar_archivo(nombre: str):
    """Borra un archivo de contenidos/ y todos los forecasts asociados."""
    ruta = os.path.join(CONTENIDOS, nombre)
    if not os.path.exists(ruta):
        return JSONResponse(status_code=404, content={"error": "Archivo no encontrado"})

    os.remove(ruta)

    # Limpiar carpetas derivadas
    for carpeta in [TMP, TEST, LISTOS]:
        for f in glob.glob(os.path.join(carpeta, "*")):
            os.remove(f)

    # Si quedan otros xlsx en contenidos, reprocesar
    otros = glob.glob(os.path.join(CONTENIDOS, "*.xlsx"))
    for xlsx in otros:
        nombre_csv = os.path.splitext(os.path.basename(xlsx))[0] + ".csv"
        procesar_excel(xlsx, os.path.join(TMP, nombre_csv))
        convertir_a_prophet(xlsx, TEST)
    if otros:
        ejecutar_forecast(TEST, LISTOS, fecha_limite="2028-03-01")

    return {"message": f"'{nombre}' eliminado y forecasts actualizados."}


@app.get("/api/forecast/{equipo}")
def obtener_forecast(equipo: str):
    """Devuelve los datos de forecast de un equipo (histórico + predicción)."""
    ruta = os.path.join(LISTOS, f"frcst_{equipo}.csv")
    if not os.path.exists(ruta):
        return JSONResponse(status_code=404, content={"error": f"No se encontró forecast para '{equipo}'"})

    df = pd.read_csv(ruta)
    return {
        "equipo": equipo,
        "datos": df.to_dict(orient="records"),
    }


@app.post("/api/recalcular/{equipo}")
def recalcular(equipo: str, ajuste: str = "mas_baja"):
    """
    Recalcula el forecast de un equipo con tendencia ajustada.
    ajuste: 'mas_alta' o 'mas_baja'
    """
    resultado = recalcular_equipo(TEST, LISTOS, equipo, ajuste, fecha_limite="2028-03-01")
    if "error" in resultado:
        return JSONResponse(status_code=400, content=resultado)
    return resultado


@app.get("/api/outliers/{equipo}")
def obtener_outliers(equipo: str):
    """Detecta outliers en la serie histórica de un equipo."""
    fechas = detectar_outliers(TEST, equipo)
    return {"equipo": equipo, "outliers": fechas}


@app.post("/api/recalcular-sin-outliers/{equipo}")
async def recalcular_sin_outliers_endpoint(equipo: str, request_body: dict = None):
    """
    Recalcula el forecast excluyendo las fechas marcadas como incidentes.
    Body: {"fechas_excluidas": ["2024-11-01", "2024-07-01"]}
    """
    from fastapi import Request
    fechas = request_body.get("fechas_excluidas", []) if request_body else []
    resultado = recalcular_sin_outliers(TEST, LISTOS, equipo, fechas, fecha_limite="2028-03-01")
    if "error" in resultado:
        return JSONResponse(status_code=400, content=resultado)
    return resultado


@app.get("/api/exportar/{equipo}")
def exportar_forecast(equipo: str):
    """
    Genera un .xlsx con formato estándar para todos los orígenes.
    Columnas: (vacía), Equipo, Rol, Metrica, Capa, Fecha, Valor, Intervalo Menor, Intervalo Mayor
    """
    ruta_forecast = os.path.join(LISTOS, f"frcst_{equipo}.csv")

    if not os.path.exists(ruta_forecast):
        return JSONResponse(status_code=404, content={"error": f"No hay forecast para '{equipo}'"})

    # Leer forecast
    df_frcst = pd.read_csv(ruta_forecast)
    df_frcst['ds'] = pd.to_datetime(df_frcst['ds'])

    # Detectar intervalo: 20% si hay outliers, 10% si no
    tiene_outliers = 'outlier' in df_frcst.columns and (df_frcst['outlier'] == 'si').any()
    pct_intervalo = 0.20 if tiene_outliers else 0.10

    # Parsear el nombre del equipo para encontrar Equipo, Rol y Metrica
    equipo_nombre, rol_nombre, metrica_nombre = parsear_nombre_equipo(equipo)

    # Si viene de Excel original, intentar obtener el Rol real del archivo fuente
    es_bq_csv = 'origen' in df_frcst.columns and (df_frcst['origen'] == 'bq_csv').any()
    if not es_bq_csv:
        originales = glob.glob(os.path.join(CONTENIDOS, "*.xlsx"))
        if originales:
            try:
                try:
                    df_orig = pd.read_excel(originales[0], sheet_name="Datos Forecast")
                except ValueError:
                    df_orig = pd.read_excel(originales[0])
                mask = df_orig['Equipo'].astype(str).str.strip() == equipo_nombre
                filas_eq = df_orig[mask]
                if not filas_eq.empty and 'Rol' in df_orig.columns:
                    rol_nombre = str(filas_eq['Rol'].iloc[0]).strip()
            except Exception:
                pass

    # Construir el DataFrame de salida con formato estándar
    COLUMNAS = ['Fecha', 'Equipo', 'Rol', 'Geo 1', 'Geo 2', 'Geo 3',
                'Capa', 'Metrica', 'Valor', 'Intervalo Menor', 'Intervalo Mayor',
                'Capacidad', 'Fecha Menor', 'Fecha Valor', 'Fecha Mayor']

    filas = []
    for _, row in df_frcst.iterrows():
        es_forecast = row['tipo'] == 'forecast'
        capa = 'PROYECCION ACTUAL' if es_forecast else 'HISTORICO MEDICION'
        fila = {col: '' for col in COLUMNAS}
        fila['Fecha'] = row['ds']
        fila['Equipo'] = equipo_nombre
        fila['Rol'] = rol_nombre
        fila['Capa'] = capa
        fila['Metrica'] = metrica_nombre
        fila['Valor'] = round(float(row['y']), 2)
        if es_forecast:
            fila['Intervalo Menor'] = round(float(row['y']) * (1 - pct_intervalo), 2)
            fila['Intervalo Mayor'] = round(float(row['y']) * (1 + pct_intervalo), 2)
        filas.append(fila)

    df_export = pd.DataFrame(filas, columns=COLUMNAS)

    # Guardar como xlsx
    nombre_export = f"forecast_{equipo}.xlsx"
    ruta_export = os.path.join(LISTOS, nombre_export)
    df_export.to_excel(ruta_export, index=False, sheet_name="Datos Forecast")

    return FileResponse(
        ruta_export,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=nombre_export,
    )


@app.get("/api/exportar-todo")
def exportar_todo():
    """
    Genera un único .xlsx con todos los equipos forecasteados.
    Si hay un Excel original en contenidos/:
      - Copia todo el contenido original EXCEPTO las filas de PROYECCION ACTUAL
      - Agrega las nuevas filas de PROYECCION ACTUAL de cada frcst_*.csv (abril 2026 - marzo 2028)
    Si no hay Excel original (solo CSV BigQuery):
      - Genera desde cero con histórico + forecast filtrado
    """
    COLUMNAS = ['Fecha', 'Equipo', 'Rol', 'Geo 1', 'Geo 2', 'Geo 3',
                'Capa', 'Metrica', 'Valor', 'Intervalo Menor', 'Intervalo Mayor',
                'Capacidad', 'Fecha Menor', 'Fecha Valor', 'Fecha Mayor']

    FECHA_INICIO_FORECAST = pd.Timestamp('2026-05-01')
    FECHA_FIN_FORECAST = pd.Timestamp('2028-03-01')

    archivos_frcst = glob.glob(os.path.join(LISTOS, "frcst_*.csv"))
    if not archivos_frcst:
        return JSONResponse(status_code=400, content={"error": "No hay forecasts para exportar"})

    # Construir dict de forecasts por equipo: {equipo_nombre_metrica: df_forecast_filas}
    nuevas_proyecciones = []

    for ruta_frcst in sorted(archivos_frcst):
        nombre_archivo = os.path.basename(ruta_frcst)
        if not nombre_archivo.endswith('.csv'):
            continue

        equipo = nombre_archivo.replace("frcst_", "").replace(".csv", "")
        df_frcst = pd.read_csv(ruta_frcst)
        df_frcst['ds'] = pd.to_datetime(df_frcst['ds'])

        tiene_outliers = 'outlier' in df_frcst.columns and (df_frcst['outlier'] == 'si').any()
        pct_intervalo = 0.20 if tiene_outliers else 0.10

        equipo_nombre, rol_nombre, metrica_nombre = parsear_nombre_equipo(equipo)

        # Solo filas de forecast dentro del rango
        df_forecast = df_frcst[
            (df_frcst['tipo'] == 'forecast') &
            (df_frcst['ds'] >= FECHA_INICIO_FORECAST) &
            (df_frcst['ds'] <= FECHA_FIN_FORECAST)
        ].copy()

        # Siempre incluir mayo 2026 como PROYECCION ACTUAL si existe en el archivo
        mayo_2026 = FECHA_INICIO_FORECAST
        ya_tiene_mayo = not df_forecast[df_forecast['ds'] == mayo_2026].empty
        if not ya_tiene_mayo:
            # Buscar mayo en cualquier tipo (historico o forecast)
            fila_mayo = df_frcst[df_frcst['ds'] == mayo_2026]
            if not fila_mayo.empty:
                fila_add = fila_mayo.iloc[[0]].copy()
                fila_add['tipo'] = 'forecast'
                df_forecast = pd.concat([fila_add, df_forecast], ignore_index=True)
            else:
                # Interpolar mayo con abril y junio
                abril_2026 = pd.Timestamp('2026-04-01')
                junio_2026 = pd.Timestamp('2026-06-01')
                fila_abril = df_frcst[df_frcst['ds'] == abril_2026]
                fila_junio = df_forecast[df_forecast['ds'] == junio_2026]
                if fila_abril.empty:
                    fila_abril = df_frcst[df_frcst['ds'] <= abril_2026].tail(1)
                if not fila_abril.empty and not fila_junio.empty:
                    val_abril = float(fila_abril['y'].iloc[0])
                    val_junio = float(fila_junio['y'].iloc[0])
                    val_mayo = round((val_abril + val_junio) / 2, 2)
                    fila_add = pd.DataFrame([{'ds': mayo_2026, 'y': val_mayo, 'tipo': 'forecast'}])
                    df_forecast = pd.concat([fila_add, df_forecast], ignore_index=True)

        for _, row in df_forecast.iterrows():
            fila = {col: '' for col in COLUMNAS}
            fila['Fecha'] = row['ds']
            fila['Equipo'] = equipo_nombre
            fila['Rol'] = rol_nombre
            fila['Metrica'] = metrica_nombre
            fila['Capa'] = 'PROYECCION ACTUAL'
            fila['Valor'] = round(float(row['y']), 2)
            fila['Intervalo Menor'] = round(float(row['y']) * (1 - pct_intervalo), 2)
            fila['Intervalo Mayor'] = round(float(row['y']) * (1 + pct_intervalo), 2)
            nuevas_proyecciones.append(fila)

    # Verificar si hay Excel original
    originales = glob.glob(os.path.join(CONTENIDOS, "*.xlsx"))

    if originales:
        # Leer Excel original
        try:
            df_original = pd.read_excel(originales[0], sheet_name="Datos Forecast")
        except ValueError:
            df_original = pd.read_excel(originales[0])

        # Asegurar que tiene todas las columnas del formato estándar
        for col in COLUMNAS:
            if col not in df_original.columns:
                df_original[col] = ''

        # Filtrar el original con reglas exactas:
        # - HISTORICO MEDICION: solo hasta abril 2026 inclusive
        # - PROYECCION ACTUAL: se elimina toda (reemplazada por los forecasts calculados)
        # - PROYECCION LTE: solo desde abril 2028 en adelante
        # - Cualquier otra capa: se descarta
        if 'Capa' in df_original.columns:
            df_original['Fecha'] = pd.to_datetime(df_original['Fecha'], errors='coerce')
            capa = df_original['Capa'].astype(str).str.strip()
            fecha = df_original['Fecha']

            mask_conservar = (
                ((capa == 'HISTORICO MEDICION') & (fecha <= pd.Timestamp('2026-05-01'))) |
                ((capa == 'PROYECCION LTE') & (fecha >= pd.Timestamp('2028-04-01')))
            )
            df_base = df_original[mask_conservar].copy()
        else:
            df_base = df_original.copy()

        # Reordenar columnas al formato estándar
        cols_presentes = [c for c in COLUMNAS if c in df_base.columns]
        cols_extra = [c for c in df_base.columns if c not in COLUMNAS]
        df_base = df_base[cols_presentes + cols_extra]

        # Agregar nuevas proyecciones
        df_nuevas = pd.DataFrame(nuevas_proyecciones, columns=COLUMNAS)
        df_export = pd.concat([df_base, df_nuevas], ignore_index=True)

        # Ordenar por Equipo, Rol, Metrica, Capa, Fecha para agrupar CDN y PEER
        cols_orden = [c for c in ['Equipo', 'Rol', 'Metrica', 'Capa', 'Fecha'] if c in df_export.columns]
        if cols_orden:
            df_export = df_export.sort_values(cols_orden).reset_index(drop=True)
    else:
        # Sin Excel original: generar desde cero con histórico + forecast
        todas_las_filas = []
        for ruta_frcst in sorted(archivos_frcst):
            nombre_archivo = os.path.basename(ruta_frcst)
            if not nombre_archivo.endswith('.csv'):
                continue
            equipo = nombre_archivo.replace("frcst_", "").replace(".csv", "")
            df_frcst = pd.read_csv(ruta_frcst)
            df_frcst['ds'] = pd.to_datetime(df_frcst['ds'])
            tiene_outliers = 'outlier' in df_frcst.columns and (df_frcst['outlier'] == 'si').any()
            pct_intervalo = 0.20 if tiene_outliers else 0.10
            equipo_nombre, rol_nombre, metrica_nombre = parsear_nombre_equipo(equipo)
            for _, row in df_frcst.iterrows():
                es_forecast = row['tipo'] == 'forecast'
                fecha = row['ds']
                if es_forecast and (fecha < FECHA_INICIO_FORECAST or fecha > FECHA_FIN_FORECAST):
                    continue
                capa = 'PROYECCION ACTUAL' if es_forecast else 'HISTORICO MEDICION'
                fila = {col: '' for col in COLUMNAS}
                fila['Fecha'] = fecha
                fila['Equipo'] = equipo_nombre
                fila['Rol'] = rol_nombre
                fila['Metrica'] = metrica_nombre
                fila['Capa'] = capa
                fila['Valor'] = round(float(row['y']), 2)
                if es_forecast:
                    fila['Intervalo Menor'] = round(float(row['y']) * (1 - pct_intervalo), 2)
                    fila['Intervalo Mayor'] = round(float(row['y']) * (1 + pct_intervalo), 2)
                todas_las_filas.append(fila)
        df_export = pd.DataFrame(todas_las_filas, columns=COLUMNAS)

    nombre_export = "forecast_completo.xlsx"
    ruta_export = os.path.join(LISTOS, nombre_export)
    df_export.to_excel(ruta_export, index=False, sheet_name="Datos Forecast")

    return FileResponse(
        ruta_export,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=nombre_export,
    )


@app.post("/api/corregir-p95-todos")
def corregir_p95_todos():
    """
    Corrige todos los equipos donde P95 >= MAXIMO.
    Para cada fecha problemática, pone P95 = MAXIMO × 0.85.
    """
    archivos = glob.glob(os.path.join(LISTOS, "frcst_*_MAXIMO.csv"))
    corregidos = []

    for ruta_maximo in archivos:
        equipo_maximo = os.path.basename(ruta_maximo).replace("frcst_", "").replace(".csv", "")
        equipo_p95 = equipo_maximo.replace('_MAXIMO', '_P95')
        ruta_p95 = os.path.join(LISTOS, f"frcst_{equipo_p95}.csv")

        if not os.path.exists(ruta_p95):
            continue

        df_max = pd.read_csv(ruta_maximo)
        df_p95 = pd.read_csv(ruta_p95)

        df_max_frcst = df_max[df_max['tipo'] == 'forecast'][['ds', 'y']].copy()
        df_p95_frcst = df_p95[df_p95['tipo'] == 'forecast'][['ds', 'y']].copy()

        if df_max_frcst.empty or df_p95_frcst.empty:
            continue

        # Buscar fechas problemáticas y corregir
        fechas_corregidas = 0
        for idx, row_p95 in df_p95.iterrows():
            if row_p95['tipo'] != 'forecast':
                continue
            # Buscar el valor MAXIMO para esa fecha
            max_row = df_max_frcst[df_max_frcst['ds'] == row_p95['ds']]
            if max_row.empty:
                continue
            valor_max = max_row['y'].iloc[0]
            if row_p95['y'] >= valor_max:
                df_p95.at[idx, 'y'] = round(valor_max * 0.85, 2)
                fechas_corregidas += 1

        if fechas_corregidas > 0:
            df_p95.to_csv(ruta_p95, index=False)
            nombre_base = equipo_maximo.replace('_MAXIMO', '').replace('_', ' ')
            corregidos.append({"equipo": nombre_base, "fechas_corregidas": fechas_corregidas})

    return {
        "equipos_corregidos": len(corregidos),
        "detalle": corregidos,
        "message": f"{len(corregidos)} equipo(s) corregidos (P95 = MAXIMO × 0.85)" if corregidos else "No había nada que corregir",
    }


@app.get("/api/validar-p95-todos")
def validar_p95_todos():
    """
    Valida P95 vs MAXIMO para todos los equipos que tengan ambas métricas.
    Retorna lista de equipos con alertas.
    """
    archivos = glob.glob(os.path.join(LISTOS, "frcst_*_MAXIMO.csv"))
    resultados = []

    for ruta_maximo in archivos:
        equipo_maximo = os.path.basename(ruta_maximo).replace("frcst_", "").replace(".csv", "")
        equipo_p95 = equipo_maximo.replace('_MAXIMO', '_P95')
        ruta_p95 = os.path.join(LISTOS, f"frcst_{equipo_p95}.csv")

        if not os.path.exists(ruta_p95):
            continue

        df_max = pd.read_csv(ruta_maximo)
        df_p95 = pd.read_csv(ruta_p95)

        df_max_frcst = df_max[df_max['tipo'] == 'forecast'][['ds', 'y']].copy()
        df_p95_frcst = df_p95[df_p95['tipo'] == 'forecast'][['ds', 'y']].copy()

        if df_max_frcst.empty or df_p95_frcst.empty:
            continue

        merged = df_max_frcst.merge(df_p95_frcst, on='ds', suffixes=('_max', '_p95'))
        problemas = merged[merged['y_p95'] >= merged['y_max']]

        if not problemas.empty:
            # Nombre legible del equipo (sin _MAXIMO)
            nombre_base = equipo_maximo.replace('_MAXIMO', '').replace('_', ' ')
            alertas = []
            for _, row in problemas.iterrows():
                alertas.append({
                    "fecha": row['ds'],
                    "valor_p95": round(row['y_p95'], 2),
                    "valor_maximo": round(row['y_max'], 2),
                })
            resultados.append({
                "equipo": nombre_base,
                "equipo_maximo": equipo_maximo,
                "equipo_p95": equipo_p95,
                "alertas": alertas,
            })

    return {
        "total_equipos_validados": len(archivos),
        "equipos_con_problemas": len(resultados),
        "resultados": resultados,
    }


@app.get("/api/validar-p95/{equipo}")
def validar_p95_vs_maximo(equipo: str):
    """
    Valida que el forecast de P95 no supere al forecast de MAXIMO para el mismo enlace.
    Busca el equipo par (MAXIMO↔P95) y compara fecha a fecha.
    Retorna las fechas donde P95 >= MAXIMO.
    """
    # Determinar si este equipo es MAXIMO o P95 y buscar su par
    if '_MAXIMO' in equipo:
        equipo_maximo = equipo
        equipo_p95 = equipo.replace('_MAXIMO', '_P95')
    elif '_P95' in equipo:
        equipo_p95 = equipo
        equipo_maximo = equipo.replace('_P95', '_MAXIMO')
    else:
        return {"alertas": [], "message": "No se puede determinar la métrica del equipo"}

    ruta_maximo = os.path.join(LISTOS, f"frcst_{equipo_maximo}.csv")
    ruta_p95 = os.path.join(LISTOS, f"frcst_{equipo_p95}.csv")

    if not os.path.exists(ruta_maximo):
        return {"alertas": [], "message": f"No existe forecast MAXIMO: {equipo_maximo}"}
    if not os.path.exists(ruta_p95):
        return {"alertas": [], "message": f"No existe forecast P95: {equipo_p95}"}

    df_max = pd.read_csv(ruta_maximo)
    df_p95 = pd.read_csv(ruta_p95)

    # Filtrar solo forecast
    df_max_frcst = df_max[df_max['tipo'] == 'forecast'][['ds', 'y']].copy()
    df_p95_frcst = df_p95[df_p95['tipo'] == 'forecast'][['ds', 'y']].copy()

    if df_max_frcst.empty or df_p95_frcst.empty:
        return {"alertas": [], "message": "No hay datos de forecast para comparar"}

    # Merge por fecha
    merged = df_max_frcst.merge(df_p95_frcst, on='ds', suffixes=('_max', '_p95'))

    # Encontrar fechas donde P95 >= MAXIMO
    alertas = []
    for _, row in merged.iterrows():
        if row['y_p95'] >= row['y_max']:
            alertas.append({
                "fecha": row['ds'],
                "valor_p95": round(row['y_p95'], 2),
                "valor_maximo": round(row['y_max'], 2),
            })

    return {
        "equipo_maximo": equipo_maximo,
        "equipo_p95": equipo_p95,
        "alertas": alertas,
        "message": f"{len(alertas)} fecha(s) donde P95 supera o iguala a MAXIMO" if alertas else "OK: P95 siempre por debajo de MAXIMO",
    }


@app.post("/api/guardar-forecast/{equipo}")
async def guardar_forecast(equipo: str, request_body: dict):
    """
    Guarda los valores editados manualmente del forecast.
    Body: {"datos": [{"ds": "2026-03-01", "y": 123456, "tipo": "forecast"}, ...]}
    """
    datos = request_body.get("datos", [])
    if not datos:
        return JSONResponse(status_code=400, content={"error": "No hay datos para guardar"})

    ruta = os.path.join(LISTOS, f"frcst_{equipo}.csv")
    if not os.path.exists(ruta):
        return JSONResponse(status_code=404, content={"error": f"No se encontró forecast para '{equipo}'"})

    df = pd.DataFrame(datos)
    df.to_csv(ruta, index=False)

    return {"message": f"Forecast de {equipo} guardado correctamente."}
