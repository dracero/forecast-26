---
inclusion: always
---

# Convención de nombres por lenguaje

Seguir las buenas prácticas de naming de cada lenguaje.

## Python (PEP 8)

- Variables y funciones: `snake_case` → `ruta_archivo`, `datos_historicos`
- Funciones: `snake_case` → `procesar_excel()`, `ejecutar_forecast()`
- Constantes: `UPPER_SNAKE_CASE` → `BASE_DIR`, `MAX_RETRIES`
- Clases: `PascalCase` → `ForecastResult`, `DataProcessor`
- Módulos y paquetes: `snake_case` → `main.py`, `api.py`

## JavaScript / TypeScript

- Variables y funciones: `camelCase` → `equipoSelect`, `cargarEquipos()`
- Constantes: `UPPER_SNAKE_CASE` o `camelCase` → `API_URL` o `apiUrl`
- Clases y componentes: `PascalCase` → `ForecastChart`
- Archivos de componentes: `PascalCase` → `Layout.astro`

## CSS

- Clases: `kebab-case` → `chart-wrapper`, `upload-section`
- IDs: `camelCase` → `forecastChart`, `equipoSelect`

## General

- Nombres descriptivos, evitar abreviaciones ambiguas
- Esta convención aplica a código nuevo y a código existente cuando se modifica
