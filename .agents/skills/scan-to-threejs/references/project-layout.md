# Companion project layout

The 3d-model-anything repository provides a runnable viewer and iPhone app:

- `apps/house-capture/`: iPhone app source (display name: 3D Model Anything).
- `apps/room-viewer/`: viewer and matched-camera capture page.
- `packages/room-runtime/`: geometry helpers, wall builders, materials, lighting, rendering and types.
- `packages/room-physics/`: optional interactive physics.
- `demos/<id>/`: modeled room implementations; register in `demos/index.ts`.
- `data/demos/<id>/`: converted room measurements.
- `data/web-assets/`: browser assets, served at the URL root.
- `data/captures-in/`, `data/scans/`, `data/captures/`: ignored personal inputs and output evidence.

Run `npm ci`, then `npm run dev` from the project root. `npm run build` checks TypeScript and creates the viewer build; `npm run preview` serves it. The public demo contains only the detailed office. It intentionally excludes raw reference scans and photo collections. Add your own assets and room module to use Scan/Overlay and photo comparisons.

Capture is available at `/tools/capture.html`. `cap.sh`, `cmp.sh`, and `cmp_photo.sh` detect this repository layout from the working directory. `CAP_URL` defaults to the viewer's dev server (port 5188). Override `CAP_URL`, `CAP_OUT`, `PHOTO_DIR`, or `CAP_QUERY` as needed. Captures run through `capture.mjs` with Playwright (`npm ci`, then `npx playwright install chromium`). Outside this layout helpers default to `captures/` and `public/<room-id>/photos/`; they do not create a viewer application.

Use `assets/BRIEF.example.md` as a fictional modeling-brief outline. The old room-specific source templates are not distributed: use the maintained runtime types and example implementations instead.

Python dependencies are pinned in the repository's `pyproject.toml` and `uv.lock` (Python 3.12, the newest version Open3D supports): run `uv sync`, then the helpers with `uv run python3 …`. Conversion and house import only need the standard library; image preparation and comparisons need Pillow; mesh reconstruction needs NumPy/Open3D/Pillow. Measurement helpers resolve Node dependencies from the target project's installation. Install dependencies in a project environment rather than changing system Python.

The app export contract is documented in `apps/house-capture/README.md`; the Codable models are `HouseProject.swift` and `ScanBundle.swift`. Do not rename serialized keys or format IDs merely because the app's public name changed.
