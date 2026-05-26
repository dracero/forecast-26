# Implementation Plan: CSV Import Forecast

## Overview

The CSV BigQuery import feature already exists in the codebase. This implementation plan focuses on verifying the existing implementation against requirements, adding missing validations (e.g., empty CSV handling per Requirement 7.5), setting up the test infrastructure, and writing property-based tests to validate the correctness properties defined in the design document.

## Tasks

- [x] 1. Set up test infrastructure
  - [x] 1.1 Create pytest configuration and test directory structure
    - Create `pyproject.toml` with `[tool.pytest.ini_options]` section
    - Create `tests/` directory with `__init__.py` and `conftest.py`
    - Add `hypothesis` and `pytest` to dev dependencies
    - Add `httpx` for async test client (FastAPI TestClient)
    - Add `openpyxl` for Excel export verification
    - _Requirements: All (testing infrastructure)_

- [x] 2. Add missing validation for empty CSV (Requirement 7.5)
  - [x] 2.1 Implement empty CSV validation in `procesar_csv_bigquery`
    - After column validation and row filtering, check if 0 equipos are processable (0 successful + 0 errors)
    - Return `{"error": "No se encontraron datos válidos en el archivo"}` with appropriate structure for HTTP 400
    - _Requirements: 7.5_

  - [x] 2.2 Update `upload_bq_csv` endpoint to handle the empty CSV case
    - Ensure the endpoint returns HTTP 400 when `procesar_csv_bigquery` returns an error for empty/invalid data
    - Verify the existing error handling path covers this new case
    - _Requirements: 7.5_

- [x] 3. Checkpoint - Verify existing implementation
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Write property-based tests for column validation and mapping
  - [x] 4.1 Create shared test fixtures and helpers in `tests/conftest.py`
    - Create helper functions to generate valid CSV DataFrames with required columns
    - Create Hypothesis strategies for generating CSV data (valid and invalid)
    - Create a fixture for temporary test/listos directories using `tmp_path`
    - _Requirements: 2.1-2.8_

  - [x]* 4.2 Write property test for column validation (Property 2)
    - **Property 2: Column validation reports missing columns**
    - For any CSV missing one or more required columns, verify the error lists exactly the missing columns
    - **Validates: Requirements 2.1, 2.2**

  - [x]* 4.3 Write property test for column mapping (Property 3)
    - **Property 3: Column mapping preserves data correctly**
    - For any valid CSV row, verify Equipo = trimmed id_enlace with spaces→_ and /→-, Fecha = parsed timestamp, Valor = float conversion
    - **Validates: Requirements 2.3, 2.4, 2.5**

  - [x]* 4.4 Write property test for extra columns ignored (Property 4)
    - **Property 4: Extra columns do not affect processing**
    - For any valid CSV with additional arbitrary columns, verify output is identical to processing without them
    - **Validates: Requirements 2.7**

  - [x]* 4.5 Write property test for null row filtering (Property 5)
    - **Property 5: Null rows are filtered from output**
    - For any processed dataset, verify no output row has null ds, y, or tipo
    - **Validates: Requirements 2.8**

- [x] 5. Write property-based tests for processing logic
  - [x]* 5.1 Write property test for existing forecast passthrough (Property 6)
    - **Property 6: Existing forecast passthrough preserves all data points**
    - For any equipo with forecast dates ≥ 2028-03-01, verify all historical and forecast rows are preserved without y-value modification
    - **Validates: Requirements 3.1, 4.4**

  - [x]* 5.2 Write property test for insufficient data rejection (Property 7)
    - **Property 7: Insufficient historical data rejection**
    - For any equipo with 1 ≤ N < 6 historical points, verify it appears in errores with motivo containing N and 6
    - **Validates: Requirements 3.4, 4.5**

  - [x]* 5.3 Write property test for constant series rejection (Property 8)
    - **Property 8: Constant series rejection**
    - For any equipo with ≥ 6 identical y values, verify it appears in errores with motivo "Valores sin variación"
    - **Validates: Requirements 3.5, 4.5**

  - [x]* 5.4 Write property test for exception message truncation (Property 9)
    - **Property 9: Exception message truncation**
    - For any exception message of length L, verify recorded motivo has length ≤ 120 and is a prefix of the original
    - **Validates: Requirements 3.6**

- [x] 6. Write property-based tests for output format and naming
  - [x]* 6.1 Write property test for output file format (Property 10)
    - **Property 10: Output file format invariant**
    - For any successfully processed equipo, verify the CSV has exactly columns ds, y, tipo with correct value patterns
    - **Validates: Requirements 3.7, 4.1**

  - [x]* 6.2 Write property test for date deduplication (Property 11)
    - **Property 11: Historical date deduplication keeps last value**
    - For any historical series with duplicate dates, verify output has one row per date with the last occurrence's value
    - **Validates: Requirements 4.2**

  - [x]* 6.3 Write property test for equipment key name construction (Property 12)
    - **Property 12: Equipment key name construction**
    - For any id_enlace and rol strings, verify the key equals `{transformed_id}_{rol}_MAXIMO`
    - **Validates: Requirements 4.3**

- [x] 7. Checkpoint - Ensure all property tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Write property-based tests for export and response
  - [x]* 8.1 Write property test for export interval calculation (Property 13)
    - **Property 13: Export interval calculation**
    - For any forecast row with value V: without outliers → 0.9V/1.1V, with outliers → 0.8V/1.2V, historical → empty
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5**

  - [x]* 8.2 Write property test for response structure (Property 14)
    - **Property 14: Response structure completeness**
    - For any processing with ≥ 1 successful equipo, verify response has message with filename and count, equipos list, and errores with equipo+motivo fields
    - **Validates: Requirements 7.1, 7.2**

- [x] 9. Write integration tests for end-to-end flows
  - [x]* 9.1 Write integration test for full CSV upload flow
    - Upload a valid CSV with multiple equipos via TestClient
    - Verify files are created in test/ and listos/ directories
    - Verify response structure matches expected format
    - _Requirements: 2.1-2.8, 4.1-4.3, 7.1_

  - [x]* 9.2 Write integration test for CSV with pre-existing forecast (passthrough)
    - Upload CSV where equipos already have forecast dates ≥ 2028-03-01
    - Verify NeuralProphet is NOT called (mock it to raise if called)
    - Verify output files contain the original forecast data
    - _Requirements: 3.1, 4.4_

  - [x]* 9.3 Write integration test for error scenarios
    - Test: non-CSV file → 400 error
    - Test: CSV missing columns → 400 with column names
    - Test: CSV with all-null data → 400 empty data error
    - Test: equipo with < 6 points → appears in errores
    - Test: equipo with constant values → appears in errores
    - _Requirements: 2.2, 3.3, 3.4, 3.5, 7.4, 7.5_

  - [x]* 9.4 Write integration test for Excel export from CSV-originated data
    - Process a CSV, then call export endpoint for a processed equipo
    - Verify Excel has correct columns, sheet name, and interval calculations
    - Verify historical rows have empty intervals, forecast rows have ±10%
    - _Requirements: 6.1-6.6_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The existing implementation in `main.py` and `api.py` already covers most requirements; tasks focus on verification and gap-filling
- NeuralProphet should be mocked in property tests to avoid computational cost; integration tests may use it selectively
- Use `tmp_path` pytest fixture to isolate file system operations in tests

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "4.4", "4.5"] },
    { "id": 4, "tasks": ["5.1", "5.2", "5.3", "5.4"] },
    { "id": 5, "tasks": ["6.1", "6.2", "6.3"] },
    { "id": 6, "tasks": ["8.1", "8.2"] },
    { "id": 7, "tasks": ["9.1", "9.2", "9.3", "9.4"] }
  ]
}
```
