# Guía: Protección de API Keys en Kiro

## Problema
Evitar que API keys, tokens o secretos queden hardcodeados en el código antes de hacer un PR a GitHub.

## Solución con Kiro

Kiro no tiene un evento nativo de "pre-PR", pero ofrece varias herramientas que combinadas logran el mismo resultado.

---

## 1. Steering File (prevención pasiva)

Crea `.kiro/steering/no-hardcoded-secrets.md`:

```markdown
---
inclusion: always
---

# No hardcodear secretos

Nunca incluir API keys, tokens, contraseñas o secretos directamente en el código.

## Reglas

- Usar variables de entorno: `os.environ["API_KEY"]` o `process.env.API_KEY`
- Usar archivos `.env` (nunca commitear `.env`, debe estar en `.gitignore`)
- Si se detecta un string que parece un secreto (empieza con `sk-`, `ghp_`, `AKIA`, etc.), reemplazarlo por una variable de entorno
- Patrones a detectar:
  - `sk-...` (OpenAI)
  - `ghp_...` (GitHub)
  - `AKIA...` (AWS)
  - Strings largos alfanuméricos asignados a variables con nombres como `key`, `token`, `secret`, `password`, `api_key`
```

Este archivo se carga automáticamente en cada interacción y Kiro lo respeta al generar código.

---

## 2. Hook: Revisión automática al editar archivos

Crea `.kiro/hooks/check-secrets-on-save.json`:

```json
{
  "name": "Check Secrets on Save",
  "version": "1.0.0",
  "description": "Revisa si hay API keys hardcodeadas al guardar un archivo",
  "when": {
    "type": "fileEdited",
    "patterns": ["*.py", "*.js", "*.ts", "*.tsx", "*.astro", "*.json", "*.yaml", "*.yml"]
  },
  "then": {
    "type": "askAgent",
    "prompt": "Revisa el archivo editado buscando API keys, tokens o secretos hardcodeados. Busca patrones como: strings asignados a variables llamadas 'key', 'token', 'secret', 'password', 'api_key'; strings que empiecen con 'sk-', 'ghp_', 'AKIA'; o cualquier string largo alfanumérico sospechoso. Si encontrás alguno, reemplazalo por una variable de entorno y avisame qué cambiaste."
  }
}
```

Este hook se ejecuta cada vez que guardás un archivo. Kiro revisa automáticamente y corrige si encuentra algo.

---

## 3. Hook: Revisión manual antes del PR (recomendado)

Crea `.kiro/hooks/pre-pr-secrets-check.json`:

```json
{
  "name": "Pre-PR Secrets Check",
  "version": "1.0.0",
  "description": "Revisión manual de secretos antes de hacer un PR",
  "when": {
    "type": "userTriggered"
  },
  "then": {
    "type": "askAgent",
    "prompt": "Hacé una revisión completa de todos los archivos del proyecto buscando API keys, tokens, contraseñas o secretos hardcodeados. Revisá especialmente: archivos .py, .js, .ts, .json, .yaml, .env (que no debería estar commiteado). Buscá patrones como 'sk-', 'ghp_', 'AKIA', strings largos asignados a variables con nombres sospechosos. Para cada hallazgo: 1) Reemplazá el valor por una variable de entorno, 2) Agregá la variable al archivo .env.example con un placeholder, 3) Verificá que .env esté en .gitignore. Mostrá un resumen de todo lo que encontraste y cambiaste."
  }
}
```

Este hook aparece como un botón en la sección "Agent Hooks" del panel de Kiro. Lo ejecutás manualmente antes de hacer el PR.

---

## 4. Hook: Comando automático con grep (detección rápida)

Crea `.kiro/hooks/grep-secrets.json`:

```json
{
  "name": "Grep Secrets",
  "version": "1.0.0",
  "description": "Busca patrones de secretos con grep antes de commitear",
  "when": {
    "type": "userTriggered"
  },
  "then": {
    "type": "runCommand",
    "command": "grep -rn --include='*.py' --include='*.js' --include='*.ts' --include='*.json' -E '(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36}|AKIA[A-Z0-9]{16}|password\\s*=\\s*[\"'\''][^\"'\\'']+[\"'\'']|api_key\\s*=\\s*[\"'\''][^\"'\\'']+[\"'\''])' . --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=.git"
  }
}
```

---

## Cómo aplicar

### Opción A: Solo steering (mínimo esfuerzo)
1. Crea el archivo `.kiro/steering/no-hardcoded-secrets.md`
2. Listo. Kiro lo respeta automáticamente al generar código.

### Opción B: Steering + hook automático
1. Crea el steering file
2. Crea el hook `check-secrets-on-save.json`
3. Cada vez que guardás un archivo, Kiro revisa

### Opción C: Steering + hook manual pre-PR (recomendado)
1. Crea el steering file
2. Crea el hook `pre-pr-secrets-check.json`
3. Antes de cada PR, ejecutá el hook desde el panel de Kiro

### Opción D: Todo combinado (máxima protección)
1. Steering file (prevención)
2. Hook on-save (detección temprana)
3. Hook manual pre-PR (revisión final)
4. Hook grep (verificación rápida)

---

## Complemento: .gitignore

Asegurate de tener esto en tu `.gitignore`:

```
.env
.env.local
.env.*.local
```

## Complemento: .env.example

Mantené un `.env.example` con los nombres de las variables pero sin valores:

```
API_KEY=
DATABASE_URL=
SECRET_TOKEN=
```
