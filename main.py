#Convierte a fechas y ordena
import pandas as pd
import numpy as np
import os
import glob
from datetime import datetime

# Cargar el archivo Excel
def procesar_excel(ruta_archivo, ruta_salida):
    print(f"Cargando archivo: {ruta_archivo}")

    # Leer el archivo Excel
    df = pd.read_excel(ruta_archivo)

    # Mostrar las primeras filas para verificar la estructura
    print("Primeras filas del archivo original:")
    print(df.head())
    print("\nInformación de los datos originales:")
    print(df.info())

    # Identificar todas las columnas que contienen 'Fecha' en su nombre
    columnas_fecha = [col for col in df.columns if 'Fecha' in col]
    print(f"\nColumnas de fecha identificadas: {columnas_fecha}")

    # Convertir todas las columnas de fecha al formato datetime
    for col in columnas_fecha:
        # Guardar los valores originales para comparación
        valores_originales = df[col].copy()

        # Intentar convertir a datetime con manejo de errores
        try:
            df[col] = pd.to_datetime(df[col], errors='coerce')

            # Si hay NaT (fechas no convertidas), intentar formatos adicionales
            if df[col].isna().any():
                print(f"Algunas fechas en '{col}' no se pudieron convertir automáticamente.")

                # Para los valores que siguen siendo NaT, intentar formatos específicos
                mask_nat = df[col].isna()
                valores_problematicos = valores_originales[mask_nat]

                # Intentar algunos formatos comunes en español
                formatos = ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d.%m.%Y', '%d %b %Y', '%d %B %Y']

                for valor_idx in valores_problematicos.index:
                    valor = valores_originales[valor_idx]
                    if isinstance(valor, str):
                        for formato in formatos:
                            try:
                                fecha = datetime.strptime(valor, formato)
                                df.at[valor_idx, col] = fecha
                                print(f"  - Convertido '{valor}' usando formato '{formato}'")
                                break
                            except ValueError:
                                continue

            print(f"Columna '{col}' convertida a formato fecha.")
        except Exception as e:
            print(f"Error al convertir columna '{col}': {str(e)}")

    # Verificar el resultado de la conversión
    print("\nVerificando conversión de fechas:")
    for col in columnas_fecha:
        print(f"  - '{col}': {df[col].dtype}")

    # Ordenar los datos para que los valores de Metrica (MAXIMO y P95) aparezcan agrupados completamente
    # sin ordenar por Capa, como solicitado
    print("\nOrdenando datos por Equipo, Rol, Metrica y Fecha (sin ordenar por Capa)...")

    columnas_ordenamiento = []
    orden_ascendente = []

    # Primero por Equipo (descendente)
    if 'Equipo' in df.columns:
        columnas_ordenamiento.append('Equipo')
        orden_ascendente.append(False)  # False para orden descendente

    # Luego por Rol (descendente)
    if 'Rol' in df.columns:
        columnas_ordenamiento.append('Rol')
        orden_ascendente.append(False)  # False para orden descendente

    # Luego por Metrica para agrupar todos los MAXIMO y P95
    if 'Metrica' in df.columns:
        columnas_ordenamiento.append('Metrica')
        orden_ascendente.append(True)  # True para orden ascendente

    # Finalmente por Fecha (ascendente)
    if 'Fecha' in df.columns:
        columnas_ordenamiento.append('Fecha')
        orden_ascendente.append(True)  # True para orden ascendente

    if columnas_ordenamiento:
        df = df.sort_values(by=columnas_ordenamiento, ascending=orden_ascendente)
        print(f"Datos ordenados por: {', '.join(columnas_ordenamiento)}")
        print("Esto garantiza que todas las métricas del mismo tipo (MAXIMO o P95) aparezcan agrupadas.")
    else:
        print("¡Advertencia! No se encontraron columnas adecuadas para ordenar.")

    # Calcular los intervalos de confianza para filas donde Capa = "PROYECCION ACTUAL"
    print("\nCalculando intervalos de confianza para PROYECCION ACTUAL...")
    if 'Capa' in df.columns and 'Valor' in df.columns:
        # Aplica el cálculo solo para las filas donde Capa = "PROYECCION ACTUAL"
        mask_proyeccion = df['Capa'] == "PROYECCION ACTUAL"

        # Calcula el 90% del valor para Intervalo Menor
        df.loc[mask_proyeccion, 'Intervalo Menor'] = df.loc[mask_proyeccion, 'Valor'] * 0.9

        # Calcula el 110% del valor para Intervalo Mayor
        df.loc[mask_proyeccion, 'Intervalo Mayor'] = df.loc[mask_proyeccion, 'Valor'] * 1.1

        print(f"Intervalos calculados para {mask_proyeccion.sum()} filas con Capa = 'PROYECCION ACTUAL'")
    else:
        print("¡Advertencia! No se encontraron las columnas 'Capa' o 'Valor' para calcular los intervalos.")

    # Guardar el resultado en CSV
    print(f"\nGuardando resultado en: {ruta_salida}")
    df.to_csv(ruta_salida, index=False)
    print("¡Proceso completado!")

    # Mostrar las primeras filas del resultado
    print("\nPrimeras filas del archivo procesado:")
    print(df.head())

    return df

def convertir_a_prophet(ruta_archivo, carpeta_prophet):
    """
    Lee directamente el archivo Excel original,
    filtra todas las filas con Capa = 'HISTORICO MEDICION',
    y genera un CSV por cada Equipo con columnas ds y y para NeuralProphet.
    """
    print(f"Convirtiendo a formato Prophet: {ruta_archivo}")

    try:
        df = pd.read_excel(ruta_archivo, sheet_name="Datos Forecast")
    except ValueError:
        df = pd.read_excel(ruta_archivo)
    except Exception as e:
        print(f"  Error leyendo {ruta_archivo}: {e}")
        return

    # Filtrar solo HISTORICO MEDICION
    if 'Capa' not in df.columns:
        print(f"  ¡Advertencia! No se encontró columna 'Capa'. Saltando.")
        return

    df = df[df['Capa'].str.strip() == 'HISTORICO MEDICION'].copy()

    if df.empty:
        print(f"  No hay filas con HISTORICO MEDICION.")
        return

    # Convertir Fecha a datetime
    df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
    df = df.dropna(subset=['Fecha', 'Valor'])

    print(f"  Total filas HISTORICO MEDICION: {len(df)}")

    # Agrupar por Equipo + Rol + Metrica (un CSV por combinación)
    cols_grupo = ['Equipo']
    if 'Rol' in df.columns:
        cols_grupo.append('Rol')
    if 'Metrica' in df.columns:
        cols_grupo.append('Metrica')

    grupos = df.groupby(cols_grupo)
    archivos_generados = 0

    for clave, grupo in grupos:
        if not isinstance(clave, tuple):
            clave = (clave,)
        partes = [str(c).replace(' ', '_').replace('/', '-') for c in clave]
        nombre_csv = '__'.join(partes) + '.csv'

        prophet_df = pd.DataFrame({
            'ds': grupo['Fecha'].dt.strftime('%Y-%m-%d'),
            'y': grupo['Valor'].astype(float)
        }).sort_values('ds', kind='stable').drop_duplicates(subset='ds', keep='last').reset_index(drop=True)

        ruta_csv = os.path.join(carpeta_prophet, nombre_csv)
        prophet_df.to_csv(ruta_csv, index=False)
        archivos_generados += 1
        print(f"  Generado: {nombre_csv} ({len(prophet_df)} registros)")

    print(f"  Total archivos Prophet generados: {archivos_generados}")


def ejecutar_forecast(carpeta_test, carpeta_listos, fecha_limite='2028-03-01'):
    """
    Lee cada CSV de la carpeta test (formato ds, y),
    entrena NeuralProphet y guarda el forecast en carpeta_listos como frcst_EQUIPO.csv.
    Retorna lista de equipos que no se pudieron forecastear con el motivo.
    """
    from neuralprophet import NeuralProphet, set_log_level
    set_log_level("ERROR")

    fecha_limite = pd.Timestamp(fecha_limite)
    archivos = glob.glob(os.path.join(carpeta_test, "*.csv"))
    errores = []

    if not archivos:
        print("No se encontraron archivos CSV en la carpeta 'test'.")
        return errores

    print(f"Ejecutando forecast para {len(archivos)} equipo(s) hasta {fecha_limite.strftime('%Y-%m-%d')}...\n")

    for ruta_csv in archivos:
        nombre = os.path.basename(ruta_csv)
        equipo = nombre.replace('.csv', '')
        print(f"--- {equipo} ---")

        df = pd.read_csv(ruta_csv)
        df['ds'] = pd.to_datetime(df['ds'])
        df = df.sort_values('ds').reset_index(drop=True)

        # Calcular meses hasta fecha_limite
        ultima = df['ds'].max()
        meses = (fecha_limite.year - ultima.year) * 12 + (fecha_limite.month - ultima.month)
        if meses <= 0:
            msg = f"Ya tiene datos hasta {ultima.strftime('%Y-%m-%d')}"
            print(f"  {msg}, saltando.")
            errores.append({"equipo": equipo, "motivo": msg})
            continue

        if len(df) < 6:
            msg = f"Solo {len(df)} datos (mínimo 6)"
            print(f"  Saltando: {msg}.")
            errores.append({"equipo": equipo, "motivo": msg})
            continue

        if df['y'].nunique() <= 1:
            msg = "Valores sin variación"
            print(f"  Saltando: {msg}.")
            errores.append({"equipo": equipo, "motivo": msg})
            continue

        try:
            m = NeuralProphet(
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
                learning_rate=0.1,
            )

            m.fit(df, freq='MS')

            future = m.make_future_dataframe(df, periods=meses)
            forecast = m.predict(future)
        except Exception as e:
            msg = str(e)[:120]
            print(f"  Error: {msg}. Saltando.")
            errores.append({"equipo": equipo, "motivo": msg})
            continue

        historico = df.copy()
        historico['tipo'] = 'historico'

        forecast_futuro = forecast[forecast['ds'] > ultima][['ds', 'yhat1']].copy()
        forecast_futuro.columns = ['ds', 'y']
        forecast_futuro['tipo'] = 'forecast'

        resultado = pd.concat([historico, forecast_futuro], ignore_index=True)
        resultado['ds'] = pd.to_datetime(resultado['ds']).dt.strftime('%Y-%m-%d')

        nombre_salida = f"frcst_{equipo}.csv"
        ruta_salida = os.path.join(carpeta_listos, nombre_salida)
        resultado.to_csv(ruta_salida, index=False)
        print(f"  Guardado: {nombre_salida} ({meses} meses)")

    print(f"\nForecasts completados. {len(errores)} equipo(s) con problemas.")
    return errores


def recalcular_equipo(carpeta_test, carpeta_listos, equipo, ajuste, fecha_limite='2028-03-01'):
    """
    Ajusta la pendiente del forecast existente escalando los valores futuros.
    ajuste: 'mas_alta' o 'mas_baja'
      - mas_baja: reduce la pendiente un 30%
      - mas_alta: aumenta la pendiente un 30%
    """
    ruta_frcst = os.path.join(carpeta_listos, f"frcst_{equipo}.csv")
    if not os.path.exists(ruta_frcst):
        return {"error": f"No se encontró forecast para '{equipo}'"}

    df = pd.read_csv(ruta_frcst)

    historico = df[df['tipo'] == 'historico'].copy()
    futuro = df[df['tipo'] == 'forecast'].copy()

    if futuro.empty:
        return {"error": "No hay datos de forecast para ajustar"}

    # Valor base: último punto histórico
    ultimo_valor = historico['y'].iloc[-1]

    # Calcular la diferencia (pendiente) de cada punto futuro respecto al base
    # y escalarla
    factor = 0.7 if ajuste == 'mas_baja' else 1.3

    futuro['y'] = ultimo_valor + (futuro['y'] - ultimo_valor) * factor

    resultado = pd.concat([historico, futuro], ignore_index=True)
    resultado.to_csv(ruta_frcst, index=False)

    return {"message": f"Pendiente ajustada ({ajuste}) para {equipo}"}


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    carpeta_entrada = os.path.join(base_dir, "contenidos")
    carpeta_tmp = os.path.join(base_dir, "_tmp")
    carpeta_test = os.path.join(base_dir, "test")
    carpeta_salida = os.path.join(base_dir, "listos")
    os.makedirs(carpeta_tmp, exist_ok=True)
    os.makedirs(carpeta_test, exist_ok=True)
    os.makedirs(carpeta_salida, exist_ok=True)

    # Paso 1: Procesar archivos de contenidos -> _tmp (CSV intermedio)
    archivos = glob.glob(os.path.join(carpeta_entrada, "*.xlsx"))

    if not archivos:
        print("No se encontraron archivos .xlsx en la carpeta 'contenidos'.")
    else:
        print(f"=== PASO 1: Procesando {len(archivos)} archivo(s) .xlsx ===\n")
        for ruta in archivos:
            nombre = os.path.basename(ruta)
            nombre_csv = os.path.splitext(nombre)[0] + '.csv'
            ruta_out = os.path.join(carpeta_tmp, nombre_csv)
            print(f"--- Procesando: {nombre} ---")
            procesar_excel(ruta, ruta_out)
            print()

    # Paso 2: Convertir xlsx originales -> test (formato ds, y por equipo)
    archivos_xlsx = glob.glob(os.path.join(carpeta_entrada, "*.xlsx"))

    if not archivos_xlsx:
        print("\nNo se encontraron archivos .xlsx en la carpeta 'contenidos'.")
    else:
        print(f"\n=== PASO 2: Convirtiendo {len(archivos_xlsx)} archivo(s) a formato Prophet ===\n")
        for ruta in archivos_xlsx:
            convertir_a_prophet(ruta, carpeta_test)
            print()

    # Paso 3: Ejecutar NeuralProphet forecast (test -> listos)
    print(f"\n=== PASO 3: Ejecutando NeuralProphet forecast hasta 2028-03 ===\n")
    ejecutar_forecast(carpeta_test, carpeta_salida, fecha_limite='2028-03-01')


def procesar_csv_bigquery(ruta_csv, rol, carpeta_test, carpeta_listos, fecha_limite='2028-03-01'):
    """
    Procesa un CSV con formato BigQuery:
      - id_enlace → Equipo
      - time_series_timestamp → Fecha
      - time_series_type: 'history' → HISTORICO MEDICION, 'forecast' → PROYECCION ACTUAL
      - time_series_adjusted_data → Valor
    Si ya tiene proyecciones hasta marzo 2028, no ejecuta NeuralProphet
    pero genera los archivos frcst_*.csv para visualización y edición.
    Retorna lista de equipos procesados y errores.
    """
    from neuralprophet import NeuralProphet, set_log_level
    set_log_level("ERROR")

    fecha_limite_ts = pd.Timestamp(fecha_limite)

    # Detectar separador leyendo la primera línea del archivo
    with open(ruta_csv, 'r', encoding='utf-8-sig', errors='replace') as f:
        primera_linea = f.readline()
    separador = ';' if primera_linea.count(';') > primera_linea.count(',') else ','

    df = pd.read_csv(ruta_csv, sep=separador, encoding='utf-8-sig', dtype={'id_enlace': str}, keep_default_na=False, na_values=[])
    print(f"CSV BigQuery cargado: {len(df)} filas")
    print(f"Columnas: {list(df.columns)}")

    # Validar columnas requeridas
    columnas_requeridas = ['id_enlace', 'time_series_timestamp', 'time_series_type', 'time_series_adjusted_data']
    faltantes = [c for c in columnas_requeridas if c not in df.columns]
    if faltantes:
        return {"error": f"Faltan columnas: {', '.join(faltantes)}", "equipos": [], "errores": []}

    # Mapear columnas
    df['Equipo'] = df['id_enlace'].astype(str).str.strip()
    df['Fecha'] = pd.to_datetime(df['time_series_timestamp'], errors='coerce', utc=True).dt.tz_localize(None)
    def parsear_numero(valor):
        """Parsea números con separador de miles (.) y decimal (,) o (.)."""
        s = str(valor).strip()
        # Contar puntos y comas
        puntos = s.count('.')
        comas = s.count(',')
        if comas == 1 and puntos >= 1:
            # Formato europeo: 1.234.567,89 → quitar puntos, coma→punto
            s = s.replace('.', '').replace(',', '.')
        elif puntos > 1:
            # Múltiples puntos = separadores de miles: 1.234.567 → quitar puntos
            s = s.replace('.', '')
        # Si hay un solo punto, es decimal normal: 101278.0 → no tocar
        try:
            return float(s)
        except ValueError:
            return float('nan')

    df['Valor'] = df['time_series_adjusted_data'].apply(parsear_numero)
    df['Capa'] = df['time_series_type'].map({
        'history': 'HISTORICO MEDICION',
        'forecast': 'PROYECCION ACTUAL',
    })

    # Limpiar filas sin fecha o valor
    df = df.dropna(subset=['Fecha', 'Valor', 'Capa'])
    df = df.sort_values(['Equipo', 'Fecha']).reset_index(drop=True)

    print(f"Filas válidas: {len(df)}")

    # Validar que haya datos procesables después del filtrado
    if df.empty:
        return {"error": "No se encontraron datos válidos en el archivo", "equipos": [], "errores": []}

    # Agrupar por equipo
    equipos_procesados = []
    errores = []

    for equipo_nombre, grupo in df.groupby('Equipo'):
        equipo_safe = str(equipo_nombre).replace(' ', '_').replace('/', '-').replace('|', '-').replace(':', '-').replace('*', '-').replace('?', '-').replace('"', '-').replace('<', '-').replace('>', '-').replace('\\', '-')
        # Usar Rol proporcionado por el usuario y Metrica genérica
        nombre_clave = f"{equipo_safe}__{rol}__MAXIMO"
        print(f"\n--- {nombre_clave} ---")

        historico = grupo[grupo['Capa'] == 'HISTORICO MEDICION'].copy()
        proyeccion = grupo[grupo['Capa'] == 'PROYECCION ACTUAL'].copy()

        if historico.empty:
            msg = "Sin datos históricos"
            print(f"  Saltando: {msg}")
            errores.append({"equipo": nombre_clave, "motivo": msg})
            continue

        # Guardar CSV en test/ (solo histórico, formato ds,y)
        prophet_df = pd.DataFrame({
            'ds': historico['Fecha'].dt.strftime('%Y-%m-%d %H:%M:%S'),
            'y': historico['Valor'].astype(float)
        }).sort_values('ds', kind='stable').drop_duplicates(subset='ds', keep='last').reset_index(drop=True)

        ruta_test = os.path.join(carpeta_test, f"{nombre_clave}.csv")
        prophet_df.to_csv(ruta_test, index=False)
        print(f"  Histórico guardado: {len(prophet_df)} registros")

        # Verificar si ya tiene proyecciones hasta marzo 2028
        tiene_forecast_completo = False
        if not proyeccion.empty:
            ultima_proyeccion = proyeccion['Fecha'].max()
            if ultima_proyeccion >= fecha_limite_ts:
                tiene_forecast_completo = True
                print(f"  Ya tiene proyección hasta {ultima_proyeccion.strftime('%Y-%m-%d')}, usando datos existentes")

        if tiene_forecast_completo:
            # Usar los datos de forecast del CSV directamente
            hist_out = prophet_df.copy()
            hist_out['tipo'] = 'historico'

            frcst_out = pd.DataFrame({
                'ds': proyeccion['Fecha'].dt.strftime('%Y-%m-%d %H:%M:%S'),
                'y': proyeccion['Valor'].astype(float),
            }).sort_values('ds', kind='stable').drop_duplicates(subset='ds', keep='last').reset_index(drop=True)
            frcst_out['tipo'] = 'forecast'

            resultado = pd.concat([hist_out, frcst_out], ignore_index=True)
        else:
            # Ejecutar NeuralProphet solo para los meses que faltan
            df_train = prophet_df.copy()
            # NeuralProphet con freq='MS' necesita fechas al inicio del mes
            df_train['ds'] = pd.to_datetime(df_train['ds']).dt.to_period('M').dt.to_timestamp()

            ultima_historico = df_train['ds'].max()

            # Si hay forecast parcial en el CSV, usarlo y completar desde ahí
            frcst_csv_out = None
            if not proyeccion.empty:
                frcst_csv_out = pd.DataFrame({
                    'ds': proyeccion['Fecha'].dt.strftime('%Y-%m-%d %H:%M:%S'),
                    'y': proyeccion['Valor'].astype(float),
                }).sort_values('ds', kind='stable').drop_duplicates(subset='ds', keep='last').reset_index(drop=True)
                frcst_csv_out['tipo'] = 'forecast'
                ultima_forecast_csv = proyeccion['Fecha'].max().to_period('M').to_timestamp()
            else:
                ultima_forecast_csv = ultima_historico

            # Calcular meses que faltan desde el último forecast del CSV
            meses = (fecha_limite_ts.year - ultima_forecast_csv.year) * 12 + (fecha_limite_ts.month - ultima_forecast_csv.month)

            if meses <= 0 and frcst_csv_out is not None:
                # El forecast del CSV llega exactamente a la fecha límite
                hist_out = df_train.copy()
                hist_out['ds'] = hist_out['ds'].dt.strftime('%Y-%m-%d %H:%M:%S')
                hist_out['tipo'] = 'historico'
                resultado = pd.concat([hist_out, frcst_csv_out], ignore_index=True)
                print(f"  Forecast del CSV completo hasta fecha límite")
            elif meses <= 0:
                msg = f"Ya tiene datos hasta {ultima_historico.strftime('%Y-%m-%d')}"
                print(f"  {msg}")
                errores.append({"equipo": nombre_clave, "motivo": msg})
                continue
            else:
                if len(df_train) < 6:
                    msg = f"Solo {len(df_train)} datos (mínimo 6)"
                    print(f"  Saltando: {msg}")
                    errores.append({"equipo": nombre_clave, "motivo": msg})
                    continue

                if df_train['y'].nunique() <= 1:
                    msg = "Valores sin variación"
                    print(f"  Saltando: {msg}. Valores únicos: {df_train['y'].unique()[:5]}")
                    errores.append({"equipo": nombre_clave, "motivo": msg})
                    continue

                try:
                    m = NeuralProphet(
                        yearly_seasonality=True,
                        weekly_seasonality=False,
                        daily_seasonality=False,
                        learning_rate=0.1,
                    )
                    m.fit(df_train, freq='MS')
                    # Generar desde el último histórico hasta la fecha límite
                    meses_desde_historico = (fecha_limite_ts.year - ultima_historico.year) * 12 + (fecha_limite_ts.month - ultima_historico.month)
                    future = m.make_future_dataframe(df_train, periods=meses_desde_historico)
                    forecast = m.predict(future)
                except Exception as e:
                    msg = str(e)[:120]
                    print(f"  Error NeuralProphet: {msg}")
                    errores.append({"equipo": nombre_clave, "motivo": msg})
                    continue

                hist_out = df_train.copy()
                hist_out['ds'] = hist_out['ds'].dt.strftime('%Y-%m-%d %H:%M:%S')
                hist_out['tipo'] = 'historico'

                # Solo los meses que el CSV no cubre (después del último forecast del CSV)
                forecast_nuevos = forecast[forecast['ds'] > ultima_forecast_csv][['ds', 'yhat1']].copy()
                forecast_nuevos.columns = ['ds', 'y']
                forecast_nuevos['ds'] = forecast_nuevos['ds'].dt.strftime('%Y-%m-%d %H:%M:%S')
                forecast_nuevos['tipo'] = 'forecast'

                partes_resultado = [hist_out]
                if frcst_csv_out is not None and len(frcst_csv_out) > 0:
                    partes_resultado.append(frcst_csv_out)
                    print(f"  Forecast del CSV: {len(frcst_csv_out)} meses, NeuralProphet completa: {len(forecast_nuevos)} meses")
                else:
                    print(f"  Forecast generado: {len(forecast_nuevos)} meses")
                partes_resultado.append(forecast_nuevos)
                resultado = pd.concat(partes_resultado, ignore_index=True)

        # Guardar en listos/
        nombre_salida = f"frcst_{nombre_clave}.csv"
        ruta_salida = os.path.join(carpeta_listos, nombre_salida)
        resultado['origen'] = 'bq_csv'
        resultado.to_csv(ruta_salida, index=False)
        equipos_procesados.append(nombre_clave)
        print(f"  Guardado: {nombre_salida}")

    # Si no se procesó ningún equipo y no hubo errores, no hay datos válidos
    if not equipos_procesados and not errores:
        return {"error": "No se encontraron datos válidos en el archivo", "equipos": [], "errores": []}

    return {
        "equipos": equipos_procesados,
        "errores": errores,
    }


def detectar_outliers(carpeta_test, equipo):
    """
    Detecta outliers en la serie histórica usando IQR.
    Retorna lista de fechas que son picos anómalos.
    """
    ruta_csv = os.path.join(carpeta_test, f"{equipo}.csv")
    if not os.path.exists(ruta_csv):
        return []

    df = pd.read_csv(ruta_csv)
    df['ds'] = pd.to_datetime(df['ds'])

    # Calcular IQR
    q1 = df['y'].quantile(0.25)
    q3 = df['y'].quantile(0.75)
    iqr = q3 - q1
    limite_superior = q3 + 1.5 * iqr
    limite_inferior = q1 - 1.5 * iqr

    # Detectar outliers
    outliers = df[(df['y'] > limite_superior) | (df['y'] < limite_inferior)]

    return outliers['ds'].dt.strftime('%Y-%m-%d').tolist()


def recalcular_sin_outliers(carpeta_test, carpeta_listos, equipo, fechas_excluidas, fecha_limite='2028-03-01'):
    """
    Recalcula el forecast excluyendo las fechas marcadas como incidentes.
    Los valores forecasteados usan intervalo de confianza del 20% si hay outliers.
    """
    from neuralprophet import NeuralProphet, set_log_level
    set_log_level("ERROR")

    ruta_csv = os.path.join(carpeta_test, f"{equipo}.csv")
    if not os.path.exists(ruta_csv):
        return {"error": f"No se encontró {equipo}.csv en test/"}

    df = pd.read_csv(ruta_csv)
    df['ds'] = pd.to_datetime(df['ds'])
    df = df.sort_values('ds').reset_index(drop=True)

    # Excluir las fechas marcadas como incidentes
    fechas_dt = pd.to_datetime(fechas_excluidas)
    df_limpio = df[~df['ds'].isin(fechas_dt)].copy().reset_index(drop=True)

    tiene_outliers = len(fechas_excluidas) > 0
    intervalo = 0.20 if tiene_outliers else 0.10

    fecha_limite = pd.Timestamp(fecha_limite)
    # Usar la última fecha del dataset ORIGINAL para calcular meses
    ultima_original = df['ds'].max()
    ultima_limpio = df_limpio['ds'].max()
    meses = (fecha_limite.year - ultima_limpio.year) * 12 + (fecha_limite.month - ultima_limpio.month)

    if meses <= 0:
        return {"error": "No hay meses futuros para forecastear"}

    if len(df_limpio) < 6:
        return {"error": f"Solo quedan {len(df_limpio)} datos después de excluir (mínimo 6)"}

    if df_limpio['y'].nunique() <= 1:
        return {"error": "Valores sin variación después de excluir outliers"}

    try:
        m = NeuralProphet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            learning_rate=0.1,
        )

        m.fit(df_limpio, freq='MS')
        future = m.make_future_dataframe(df_limpio, periods=meses)
        forecast = m.predict(future)
    except Exception as e:
        return {"error": str(e)[:200]}

    # Histórico: usar datos originales (con outliers) para que se vean en el gráfico
    historico = df.copy()
    historico['tipo'] = 'historico'
    historico['outlier'] = historico['ds'].isin(fechas_dt).map({True: 'si', False: 'no'})

    # Forecast futuro con intervalos (después de la última fecha original)
    forecast_futuro = forecast[forecast['ds'] > ultima_original][['ds', 'yhat1']].copy()
    forecast_futuro.columns = ['ds', 'y']
    forecast_futuro['tipo'] = 'forecast'
    forecast_futuro['outlier'] = 'no'

    resultado = pd.concat([historico, forecast_futuro], ignore_index=True)
    resultado['ds'] = pd.to_datetime(resultado['ds']).dt.strftime('%Y-%m-%d')

    # Guardar intervalo usado en el CSV
    resultado['intervalo'] = intervalo

    nombre_salida = f"frcst_{equipo}.csv"
    ruta_salida = os.path.join(carpeta_listos, nombre_salida)
    resultado.to_csv(ruta_salida, index=False)

    return {
        "message": f"Recalculado {equipo} sin {len(fechas_excluidas)} outlier(s), intervalo {int(intervalo*100)}%",
        "intervalo": intervalo,
    }


def procesar_csv_historico(ruta_csv, carpeta_test, carpeta_listos, fecha_limite='2028-03-01'):
    """
    Procesa un CSV con formato de histórico de proveedores:
      - mes → Fecha (primer día del mes)
      - ProovedorNombre → Equipo (en mayúsculas)
      - Capa → Rol (CDN, PEER)
      - max_mbps → Valor
      - Todos los datos son HISTORICO MEDICION, Metrica = MAXIMO
    Ejecuta NeuralProphet para generar forecast hasta fecha_limite.
    """
    from neuralprophet import NeuralProphet, set_log_level
    set_log_level("ERROR")

    fecha_limite_ts = pd.Timestamp(fecha_limite)

    # Detectar separador
    with open(ruta_csv, 'r', encoding='utf-8-sig', errors='replace') as f:
        primera_linea = f.readline()
    separador = ';' if primera_linea.count(';') > primera_linea.count(',') else ','

    df = pd.read_csv(ruta_csv, sep=separador, encoding='utf-8-sig')
    print(f"CSV Histórico cargado: {len(df)} filas")
    print(f"Columnas: {list(df.columns)}")

    # Normalizar nombres de columnas (quitar espacios)
    df.columns = df.columns.str.strip()

    # Validar columnas requeridas
    columnas_requeridas = ['mes', 'proveedor', 'capa', 'max_mbps']
    faltantes = [c for c in columnas_requeridas if c not in df.columns]
    if faltantes:
        return {"error": f"Faltan columnas: {', '.join(faltantes)}", "equipos": [], "errores": []}

    # Mapear columnas
    df['Equipo'] = df['proveedor'].astype(str).str.strip().str.upper()
    df['Rol'] = df['capa'].astype(str).str.strip().str.upper()
    df['Fecha'] = pd.to_datetime(df['mes'], errors='coerce').dt.to_period('M').dt.to_timestamp()
    df['Valor'] = pd.to_numeric(df['max_mbps'], errors='coerce')

    # Limpiar filas sin fecha o valor
    df = df.dropna(subset=['Fecha', 'Valor'])
    df = df.sort_values(['Equipo', 'Rol', 'Fecha']).reset_index(drop=True)

    print(f"Filas válidas: {len(df)}")

    if df.empty:
        return {"error": "No se encontraron datos válidos en el archivo", "equipos": [], "errores": []}

    # Agrupar por Equipo + Rol
    equipos_procesados = []
    errores = []

    for (equipo_nombre, rol), grupo in df.groupby(['Equipo', 'Rol']):
        equipo_safe = str(equipo_nombre).replace(' ', '_').replace('/', '-').replace('|', '-').replace(':', '-').replace('*', '-').replace('?', '-').replace('"', '-').replace('<', '-').replace('>', '-').replace('\\', '-')
        nombre_clave = f"{equipo_safe}__{rol}__MAXIMO"
        print(f"\n--- {nombre_clave} ---")

        # Guardar CSV en test/ (formato ds, y)
        prophet_df = pd.DataFrame({
            'ds': grupo['Fecha'].dt.strftime('%Y-%m-%d %H:%M:%S'),
            'y': grupo['Valor'].astype(float)
        }).sort_values('ds', kind='stable').drop_duplicates(subset='ds', keep='last').reset_index(drop=True)

        ruta_test = os.path.join(carpeta_test, f"{nombre_clave}.csv")
        prophet_df.to_csv(ruta_test, index=False)
        print(f"  Histórico guardado: {len(prophet_df)} registros")

        # Ejecutar NeuralProphet
        df_train = prophet_df.copy()
        df_train['ds'] = pd.to_datetime(df_train['ds']).dt.to_period('M').dt.to_timestamp()

        ultima = df_train['ds'].max()
        meses = (fecha_limite_ts.year - ultima.year) * 12 + (fecha_limite_ts.month - ultima.month)

        if meses <= 0:
            msg = f"Ya tiene datos hasta {ultima.strftime('%Y-%m-%d')}"
            print(f"  {msg}")
            errores.append({"equipo": nombre_clave, "motivo": msg})
            continue

        if len(df_train) < 6:
            msg = f"Solo {len(df_train)} datos (mínimo 6)"
            print(f"  Sin forecast: {msg}. Guardando solo histórico.")
            errores.append({"equipo": nombre_clave, "motivo": msg})
            # Guardar solo histórico en listos/ para que aparezca en el Excel
            hist_only = df_train.copy()
            hist_only['ds'] = hist_only['ds'].dt.strftime('%Y-%m-%d %H:%M:%S')
            hist_only['tipo'] = 'historico'
            hist_only['origen'] = 'historico_csv'
            nombre_salida = f"frcst_{nombre_clave}.csv"
            ruta_salida = os.path.join(carpeta_listos, nombre_salida)
            hist_only.to_csv(ruta_salida, index=False)
            equipos_procesados.append(nombre_clave)
            continue

        if df_train['y'].nunique() <= 1:
            msg = "Valores sin variación"
            print(f"  Sin forecast: {msg}. Guardando solo histórico.")
            errores.append({"equipo": nombre_clave, "motivo": msg})
            # Guardar solo histórico en listos/
            hist_only = df_train.copy()
            hist_only['ds'] = hist_only['ds'].dt.strftime('%Y-%m-%d %H:%M:%S')
            hist_only['tipo'] = 'historico'
            hist_only['origen'] = 'historico_csv'
            nombre_salida = f"frcst_{nombre_clave}.csv"
            ruta_salida = os.path.join(carpeta_listos, nombre_salida)
            hist_only.to_csv(ruta_salida, index=False)
            equipos_procesados.append(nombre_clave)
            continue

        try:
            m = NeuralProphet(
                yearly_seasonality=True,
                weekly_seasonality=False,
                daily_seasonality=False,
                learning_rate=0.1,
            )
            m.fit(df_train, freq='MS')
            future = m.make_future_dataframe(df_train, periods=meses)
            forecast = m.predict(future)
        except Exception as e:
            msg = str(e)[:120]
            print(f"  Error NeuralProphet: {msg}")
            errores.append({"equipo": nombre_clave, "motivo": msg})
            continue

        hist_out = df_train.copy()
        hist_out['ds'] = hist_out['ds'].dt.strftime('%Y-%m-%d %H:%M:%S')
        hist_out['tipo'] = 'historico'

        # El forecast incluye desde el último mes histórico (inclusive)
        # El último mes aparece como historico Y como forecast con el mismo valor
        forecast_futuro = forecast[forecast['ds'] >= ultima][['ds', 'yhat1']].copy()
        forecast_futuro.columns = ['ds', 'y']
        # Reemplazar el valor del último mes con el valor real histórico
        ultimo_valor_real = df_train[df_train['ds'] == ultima]['y'].iloc[0]
        forecast_futuro.loc[forecast_futuro['ds'] == ultima, 'y'] = ultimo_valor_real
        forecast_futuro['ds'] = forecast_futuro['ds'].dt.strftime('%Y-%m-%d %H:%M:%S')
        forecast_futuro['tipo'] = 'forecast'

        resultado = pd.concat([hist_out, forecast_futuro], ignore_index=True)
        resultado['origen'] = 'historico_csv'
        print(f"  Forecast generado: {len(forecast_futuro)} meses")

        # Guardar en listos/
        nombre_salida = f"frcst_{nombre_clave}.csv"
        ruta_salida = os.path.join(carpeta_listos, nombre_salida)
        resultado.to_csv(ruta_salida, index=False)
        equipos_procesados.append(nombre_clave)
        print(f"  Guardado: {nombre_salida}")

    return {
        "equipos": equipos_procesados,
        "errores": errores,
    }


def forecast_iterativo(carpeta_test, carpeta_listos, equipo, fecha_limite='2028-03-01'):
    """
    Forecast iterativo con NeuralProphet para equipos con pocos datos.
    Con 2 datos predice 1, con 3 predice 1, y así hasta llegar a fecha_limite.
    Si solo hay 1 dato, lo duplica con leve variación para tener 2 y arrancar.
    """
    from neuralprophet import NeuralProphet, set_log_level
    set_log_level("ERROR")

    fecha_limite_ts = pd.Timestamp(fecha_limite)

    ruta_csv = os.path.join(carpeta_test, f"{equipo}.csv")
    if not os.path.exists(ruta_csv):
        return {"error": f"No se encontró {equipo}.csv en test/"}

    df = pd.read_csv(ruta_csv)
    df['ds'] = pd.to_datetime(df['ds'])
    df = df.sort_values('ds').reset_index(drop=True)

    if df.empty:
        return {"error": "Sin datos"}

    # Normalizar al primer día del mes
    df['ds'] = df['ds'].dt.to_period('M').dt.to_timestamp()

    ultima = df['ds'].max()
    meses_necesarios = (fecha_limite_ts.year - ultima.year) * 12 + (fecha_limite_ts.month - ultima.month)

    if meses_necesarios <= 0:
        return {"error": f"Ya tiene datos hasta {ultima.strftime('%Y-%m-%d')}"}

    # Si solo hay 1 dato, duplicar con leve variación para tener 2
    if len(df) == 1:
        fecha_anterior = df['ds'].iloc[0] - pd.DateOffset(months=1)
        valor_original = df['y'].iloc[0]
        fila_extra = pd.DataFrame([{'ds': fecha_anterior, 'y': valor_original * 0.98}])
        df = pd.concat([fila_extra, df], ignore_index=True).sort_values('ds').reset_index(drop=True)

    # Guardar datos originales para el histórico
    df_historico_original = df.copy()

    # Forecast iterativo: predecir 1 mes, agregar al dataset, repetir
    datos_trabajo = df[['ds', 'y']].copy()
    print(f"  Forecast iterativo: {len(datos_trabajo)} datos iniciales, {meses_necesarios} meses a generar")

    for i in range(meses_necesarios):
        try:
            m = NeuralProphet(
                yearly_seasonality=False,
                weekly_seasonality=False,
                daily_seasonality=False,
                learning_rate=0.1,
                epochs=100,
            )
            m.fit(datos_trabajo, freq='MS')
            future = m.make_future_dataframe(datos_trabajo, periods=1)
            forecast = m.predict(future)

            # Obtener el valor predicho
            ultima_actual = datos_trabajo['ds'].max()
            nuevo = forecast[forecast['ds'] > ultima_actual][['ds', 'yhat1']].copy()
            if nuevo.empty:
                break
            nuevo.columns = ['ds', 'y']
            nuevo['y'] = nuevo['y'].clip(lower=0).round(2)  # No negativos

            datos_trabajo = pd.concat([datos_trabajo, nuevo], ignore_index=True)
        except Exception as e:
            print(f"  Error en iteración {i+1}: {str(e)[:80]}")
            # Fallback: usar último valor
            ultima_fecha = datos_trabajo['ds'].max()
            nueva_fecha = ultima_fecha + pd.DateOffset(months=1)
            nueva_fecha = nueva_fecha.to_period('M').to_timestamp()
            ultimo_valor = datos_trabajo['y'].iloc[-1]
            fila_fb = pd.DataFrame([{'ds': nueva_fecha, 'y': round(ultimo_valor, 2)}])
            datos_trabajo = pd.concat([datos_trabajo, fila_fb], ignore_index=True)

    # Separar histórico y forecast
    hist_out = df_historico_original.copy()
    hist_out['ds'] = hist_out['ds'].dt.strftime('%Y-%m-%d %H:%M:%S')
    hist_out['tipo'] = 'historico'

    ultima_hist = df_historico_original['ds'].max()
    forecast_out = datos_trabajo[datos_trabajo['ds'] > ultima_hist].copy()
    forecast_out['ds'] = forecast_out['ds'].dt.strftime('%Y-%m-%d %H:%M:%S')
    forecast_out['tipo'] = 'forecast'

    resultado = pd.concat([hist_out, forecast_out], ignore_index=True)
    resultado['origen'] = 'forecast_iterativo'

    nombre_salida = f"frcst_{equipo}.csv"
    ruta_salida = os.path.join(carpeta_listos, nombre_salida)
    resultado.to_csv(ruta_salida, index=False)

    print(f"  Forecast iterativo completado: {len(forecast_out)} meses generados")

    return {
        "message": f"Forecast iterativo generado para {equipo}: {len(forecast_out)} meses",
        "equipo": equipo,
    }
