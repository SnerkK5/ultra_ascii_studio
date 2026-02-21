# Hybrid Migration Bootstrap (QML + C++)

This folder contains the first migration stage from the current PySide app to a hybrid architecture:

- `src/ascii_engine.*`: C++ core object (timeline + typed node graph state)
- `qml/main.qml`: CapCut-like layout shell with smooth animations and a node workspace overlay
- `CMakeLists.txt`: Qt 6 build setup

## Build (Windows, Qt 6.5+)

1. Open `x64 Native Tools Command Prompt` or PowerShell with Qt in `PATH`.
2. Configure and build:

```powershell
cmake -S hybrid_nextgen -B hybrid_nextgen/build -G "Ninja"
cmake --build hybrid_nextgen/build --config Release
```

3. Run executable from build folder.

## Migration strategy (no feature loss)

1. Keep current Python app as production path.
2. Move rendering core to C++ module first (FFmpeg/OpenCV path).
3. Keep Python as scripting/plugin layer.
4. Move timeline/editor UI to QML in parts:
   - Media panel
   - Timeline tools (select/razor/trim/ripple)
   - Inspector
   - Node workspace
5. Bridge old state JSON <-> new C++ core to keep compatibility.

## Current status

- Project backup created before migration.
- Python editor upgraded with:
  - drag keyframes on timeline
  - tool modes (select/razor/trim/ripple)
  - typed node ports + compatibility validation
  - extra hotkeys and smoother UI entrance animations
  - runtime bridge launcher from main app: `Tools -> Hybrid UI (QML/C++)`

## Runtime bridge flow

1. In Python app choose `Tools -> Hybrid UI (QML/C++)`.
2. Current node/timeline state is exported to `hybrid_nextgen/bridge/runtime_state.json`.
3. Hybrid app starts with `--bridge-file`.
4. On close, hybrid app writes bridge state back.
5. Python app imports returned state automatically.

