# Squish 9.2 InterOps Migration Checklist

## 1. Use the root Python environment
Preferred interpreter:
```powershell
C:\sys-verification-automation\py_venv_interops_1.5.0\Scripts\python.exe
```
Confirm with:
```powershell
C:\sys-verification-automation\py_venv_interops_1.5.0\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.prefix)"
```

## 2. Prefer root `site-packages` in the demo script
File:
- `my-test-scripts/demo-mosaiq-script.py`

Ensure it inserts:
- `C:\sys-verification-automation\py_venv_interops_1.5.0\Lib\site-packages`
before the current interpreter `site-packages`.

## 3. Keep compatibility shims
Files to keep:
- `Lib/site-packages/objectmaphelper.py`
- `Lib/site-packages/toplevelwindow.py`
- `Lib/site-packages/remotesystem.py`
- `Lib/site-packages/squishtest/__init__.py`

Purpose:
- satisfy missing module imports
- load the versioned `squishtest_310` extension from Squish 9.2

## 4. Keep guarded Squish API compatibility patches
Modified files:
- `Lib/site-packages/interops/libraries/desktop/application_aut.py`
- `Lib/site-packages/interops/libraries/squish_actions/common.py`

Purpose:
- avoid failures when Squish 9.2 APIs differ from old expectations
- provide fallback object lookup and input handling

## 5. Inspect the live AUT object tree
Run these scripts to discover what Squish exposes:
```powershell
C:\sys-verification-automation\py_venv_interops_1.5.0\Scripts\python.exe my-test-scripts\inspect_aut_objects.py
C:\sys-verification-automation\py_venv_interops_1.5.0\Scripts\python.exe my-test-scripts\start_and_inspect.py
```

## 6. Update Mosaiq login object mapping
- Use inspection results to patch the actual login control map
- Target the Mosaiq login object definitions in `interops`

## 7. Run the demo end-to-end
```powershell
C:\sys-verification-automation\py_venv_interops_1.5.0\Scripts\python.exe my-test-scripts\demo-mosaiq-script.py
```

Validate:
- `interops` imports successfully
- `squishtest` loads correctly
- AUT starts
- login works
- patient open flow works

## 8. Compatibility note
Current environment:
- Python 3.10.6 32-bit
- Squish 9.2 runtime with `squishtest_310.pyd`

If you need 64-bit app support later, use a matching 64-bit Python and Squish runtime together.
