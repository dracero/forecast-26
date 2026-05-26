# Requirements Document

## Introduction

Funcionalidad de importación de archivos CSV con formato BigQuery para el sistema Forecaster. Permite al usuario subir un CSV exportado desde BigQuery, mapear sus columnas al formato interno del sistema, ejecutar NeuralProphet cuando corresponda, visualizar y editar los resultados por equipo, y exportar el resultado final como archivo Excel.

## Glossary

- **Sistema**: La aplicación Forecaster (backend FastAPI + frontend Astro)
- **CSV_BigQuery**: Archivo CSV exportado desde BigQuery con columnas `id_enlace`, `time_series_timestamp`, `time_series_type`, `time_series_adjusted_data` y otras columnas que se ignoran
- **Frontend**: Interfaz web construida con Astro que permite la interacción del usuario
- **Backend**: Servidor FastAPI que procesa los datos y ejecuta los modelos
- **Equipo**: Identificador de un enlace/equipo de red, derivado de la columna `id_enlace` del CSV
- **Rol**: Categoría funcional del equipo (ej: CDN, CORE) que el usuario ingresa manualmente antes de subir el CSV
- **Capa**: Clasificación temporal de los datos: "HISTORICO MEDICION" para datos pasados o "PROYECCION ACTUAL" para datos futuros
- **NeuralProphet**: Modelo de forecasting basado en redes neuronales utilizado para generar proyecciones
- **Fecha_Limite**: Fecha objetivo hasta la cual se generan proyecciones (marzo 2028)
- **Excel_Salida**: Archivo .xlsx generado al exportar, con columnas Equipo, Rol, Metrica, Capa, Fecha, Valor, Intervalo Menor, Intervalo Mayor

## Requirements

### Requirement 1: Interfaz de carga de CSV BigQuery

**User Story:** Como usuario, quiero tener un formulario dedicado en el frontend para subir un archivo CSV de BigQuery e indicar el Rol, para poder importar datos de forecast desde esa fuente.

#### Acceptance Criteria

1. THE Frontend SHALL mostrar una sección "CSV BigQuery" con un campo de selección de archivo que acepte únicamente archivos con extensión `.csv`
2. THE Frontend SHALL mostrar un campo de texto para que el usuario ingrese el valor de Rol (máximo 50 caracteres) antes de subir el archivo
3. IF el usuario intenta subir sin haber ingresado un Rol (campo vacío o solo espacios en blanco), THEN THE Frontend SHALL mostrar el mensaje "⚠️ Ingresá un Rol antes de subir." y enfocar el campo de Rol sin enviar la solicitud al servidor
4. WHEN el usuario selecciona un archivo CSV, ingresa un Rol válido y presiona el botón de subida, THE Frontend SHALL enviar el archivo y el Rol al endpoint `/api/upload-bq-csv` mediante POST con FormData
5. WHILE el archivo se está procesando, THE Frontend SHALL deshabilitar el botón de subida y mostrar el texto "Procesando..." en el botón
6. WHEN el endpoint responde exitosamente, THE Frontend SHALL mostrar el mensaje de confirmación devuelto por el servidor y restaurar el botón a su estado original
7. IF el endpoint responde con un error, THEN THE Frontend SHALL mostrar el mensaje de error devuelto por el servidor, restaurar el botón a su estado original y no limpiar el formulario

### Requirement 2: Validación y mapeo de columnas del CSV

**User Story:** Como usuario, quiero que el sistema transforme automáticamente las columnas del CSV de BigQuery al formato interno, para no tener que hacer la conversión manualmente.

#### Acceptance Criteria

1. WHEN el Backend recibe un CSV, THE Backend SHALL validar que existan las columnas `id_enlace`, `time_series_timestamp`, `time_series_type` y `time_series_adjusted_data`
2. IF alguna columna requerida falta en el CSV, THEN THE Backend SHALL retornar un error HTTP 400 indicando las columnas faltantes
3. WHEN el CSV es válido, THE Backend SHALL mapear la columna `id_enlace` al campo Equipo, eliminando espacios en blanco al inicio y final del valor
4. WHEN el CSV es válido, THE Backend SHALL convertir la columna `time_series_timestamp` al campo Fecha en formato `YYYY-MM-DD`, tratando valores no parseables como fecha nula
5. WHEN el CSV es válido, THE Backend SHALL mapear la columna `time_series_adjusted_data` al campo Valor, convirtiendo el contenido a tipo numérico y tratando valores no convertibles como nulos
6. WHEN el CSV es válido, THE Backend SHALL mapear el valor `history` de `time_series_type` a "HISTORICO MEDICION" y el valor `forecast` a "PROYECCION ACTUAL", tratando cualquier otro valor como Capa nula
7. WHEN el CSV es válido, THE Backend SHALL ignorar todas las columnas del CSV que no sean las cuatro requeridas
8. THE Backend SHALL eliminar filas donde Fecha, Valor o Capa resulten nulos o no convertibles después del mapeo

### Requirement 3: Procesamiento condicional con NeuralProphet

**User Story:** Como usuario, quiero que el sistema detecte si el CSV ya contiene proyecciones hasta marzo 2028 y en ese caso use esos datos directamente sin recalcular, para ahorrar tiempo de procesamiento.

#### Acceptance Criteria

1. WHEN un equipo del CSV tiene filas de tipo `forecast` con fecha máxima igual o posterior a 2028-03-01, THE Backend SHALL usar los datos de proyección del CSV directamente sin ejecutar NeuralProphet y generar el archivo de salida con las columnas `ds`, `y` y `tipo` preservando todos los puntos de proyección existentes
2. WHEN un equipo del CSV tiene filas de tipo `forecast` con fecha máxima anterior a 2028-03-01 o no tiene filas de tipo `forecast`, THE Backend SHALL ejecutar NeuralProphet para generar proyecciones mensuales desde el último dato histórico hasta 2028-03-01, descartando cualquier proyección parcial preexistente en el CSV
3. WHEN un equipo no tiene filas con tipo `history` (o `HISTORICO MEDICION`), THE Backend SHALL registrar el equipo en la lista de errores con el motivo "Sin datos históricos" y no generar archivo de salida para ese equipo
4. WHEN un equipo tiene menos de 6 filas de datos históricos, THE Backend SHALL registrar el equipo en la lista de errores con un motivo que indique la cantidad encontrada y el mínimo requerido (por ejemplo "Solo N datos (mínimo 6)")
5. WHEN un equipo tiene todos sus valores históricos idénticos (un único valor distinto en la serie), THE Backend SHALL registrar el equipo en la lista de errores con el motivo "Valores sin variación"
6. IF NeuralProphet lanza una excepción durante el entrenamiento o la predicción, THEN THE Backend SHALL registrar el equipo en la lista de errores con el mensaje de la excepción truncado a un máximo de 120 caracteres
7. WHEN el Backend procesa un equipo exitosamente (por ruta CSV directo o por NeuralProphet), THE Backend SHALL generar un archivo CSV de salida con formato de tres columnas (`ds` en formato `YYYY-MM-DD`, `y` numérico, `tipo` con valores `historico` o `forecast`) conteniendo tanto los datos históricos como las proyecciones

### Requirement 4: Generación de archivos de forecast por equipo

**User Story:** Como usuario, quiero que cada equipo del CSV genere un archivo de forecast individual, para poder visualizar y editar cada uno por separado.

#### Acceptance Criteria

1. WHEN el procesamiento de un equipo es exitoso, THE Backend SHALL guardar un archivo `frcst_{equipo}_{rol}_MAXIMO.csv` en la carpeta `listos/` con columnas `ds` (fecha en formato `YYYY-MM-DD`), `y` (valor numérico) y `tipo` (valor `historico` o `forecast`)
2. WHEN el procesamiento de un equipo es exitoso, THE Backend SHALL guardar un archivo `{equipo}_{rol}_MAXIMO.csv` en la carpeta `test/` con los datos históricos en formato `ds` (fecha en formato `YYYY-MM-DD`), `y` (valor numérico), eliminando fechas duplicadas y conservando el último valor registrado para cada fecha
3. THE Backend SHALL construir el nombre de clave del equipo concatenando el nombre del equipo (con espacios reemplazados por guiones bajos y barras `/` reemplazadas por guiones `-`), el Rol proporcionado por el usuario y el literal `MAXIMO`, separados por guiones bajos
4. WHEN el equipo ya tiene datos de proyección cuya fecha máxima es igual o posterior a la fecha límite de forecast configurada, THE Backend SHALL incluir tanto los datos históricos (con tipo `historico`) como los de proyección existentes (con tipo `forecast`) en el archivo de salida sin ejecutar NeuralProphet
5. IF un equipo tiene menos de 6 registros históricos o sus valores no presentan variación (un único valor distinto), THEN THE Backend SHALL omitir el procesamiento de ese equipo y registrarlo en la lista de errores con el motivo específico de exclusión
6. IF la carpeta `listos/` o `test/` no existe al momento de guardar, THEN THE Backend SHALL crear la carpeta automáticamente antes de escribir el archivo

### Requirement 5: Visualización de equipos procesados desde CSV

**User Story:** Como usuario, quiero ver todos los equipos importados desde el CSV en el selector de equipos, incluyendo aquellos que ya tenían proyecciones completas, para poder revisar y editar sus datos.

#### Acceptance Criteria

1. WHEN el procesamiento del CSV finaliza exitosamente, THE Frontend SHALL recargar la lista completa de equipos disponibles en el selector dentro de los 2 segundos posteriores a recibir la respuesta del servidor, incluyendo tanto los equipos con forecast recién generado como aquellos que ya tenían proyecciones completas en el CSV
2. WHEN hay equipos con errores de procesamiento, THE Frontend SHALL mostrar una sección titulada con el conteo de equipos fallidos, listando para cada uno el nombre del equipo y el motivo específico del error retornado por el servidor
3. WHEN el procesamiento del CSV finaliza con 0 equipos procesados exitosamente, THE Frontend SHALL mantener el selector con los equipos previamente disponibles sin modificar su contenido y mostrar únicamente la sección de errores
4. WHEN un equipo procesado desde CSV es seleccionado en el selector, THE Frontend SHALL mostrar el gráfico con las series de histórico y forecast, y habilitar los controles de edición: arrastre de puntos de forecast, botones de ajuste de tendencia (más/menos pendiente), y botón de guardar cambios
5. IF el usuario selecciona un equipo cuyo forecast proviene de proyecciones preexistentes del CSV (no generadas por NeuralProphet), THEN THE Frontend SHALL mostrar los mismos controles de edición y visualización que para equipos con forecast generado

### Requirement 6: Exportación a Excel

**User Story:** Como usuario, quiero exportar los datos de un equipo importado desde CSV como archivo Excel, con el formato estándar del sistema incluyendo intervalos de confianza.

#### Acceptance Criteria

1. WHEN el usuario presiona el botón de exportar para un equipo originado desde CSV BigQuery, IF no existe un archivo .xlsx original en contenidos/, THEN THE Backend SHALL generar un Excel desde cero con las columnas Equipo, Rol, Metrica, Capa, Fecha, Valor, Intervalo Menor e Intervalo Mayor, en una hoja llamada "Datos Forecast"
2. WHEN se genera el Excel, THE Backend SHALL asignar "HISTORICO MEDICION" como Capa para filas de tipo historico y "PROYECCION ACTUAL" para filas de tipo forecast
3. WHEN se genera el Excel para filas de tipo forecast sin recálculo por outliers, THE Backend SHALL calcular Intervalo Menor como Valor × 0.9 e Intervalo Mayor como Valor × 1.1 (intervalo del 10%)
4. IF el forecast fue recalculado excluyendo outliers (el CSV contiene una columna "outlier" con al menos un valor "si"), THEN THE Backend SHALL usar un intervalo del 20% (Intervalo Menor como Valor × 0.8 e Intervalo Mayor como Valor × 1.2)
5. WHEN se genera el Excel para filas de tipo historico, THE Backend SHALL dejar los campos Intervalo Menor e Intervalo Mayor vacíos
6. THE Backend SHALL nombrar el archivo exportado como `forecast_{equipo}.xlsx` y servirlo como descarga con el tipo MIME `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
7. IF no existe un archivo de forecast (frcst_{equipo}.csv) en la carpeta de resultados cuando el usuario solicita la exportación, THEN THE Backend SHALL responder con un error indicando que no hay forecast disponible para ese equipo, sin generar archivo

### Requirement 7: Respuesta y feedback al usuario

**User Story:** Como usuario, quiero recibir feedback claro sobre el resultado del procesamiento del CSV, para saber cuántos equipos se procesaron correctamente y cuáles tuvieron problemas.

#### Acceptance Criteria

1. WHEN el procesamiento del CSV finaliza con al menos un equipo cargado exitosamente, THE Backend SHALL retornar una respuesta HTTP 200 que incluya el nombre del archivo subido, la cantidad de equipos cargados correctamente y la lista de equipos procesados
2. WHEN hay equipos con errores durante el procesamiento, THE Backend SHALL incluir en la respuesta un campo de errores con una lista donde cada entrada contenga el identificador del equipo y una descripción del motivo del fallo, hasta un máximo de 500 entradas
3. WHEN el procesamiento finaliza exitosamente, THE Frontend SHALL mostrar el mensaje de resultado en el elemento de estado de la sección CSV BigQuery dentro de los 2 segundos posteriores a recibir la respuesta del backend
4. IF el archivo subido no tiene extensión `.csv`, THEN THE Backend SHALL retornar un error HTTP 400 con un mensaje indicando que solo se aceptan archivos .csv
5. IF el CSV tiene extensión válida pero no contiene equipos procesables (0 equipos cargados y 0 errores de equipo), THEN THE Backend SHALL retornar un error HTTP 400 con un mensaje indicando que no se encontraron datos válidos en el archivo
6. WHEN el procesamiento finaliza con errores en uno o más equipos, THE Frontend SHALL mostrar la lista de errores en un contenedor visual diferenciado que incluya la cantidad total de equipos con problemas y, para cada uno, el identificador del equipo y el motivo del fallo
