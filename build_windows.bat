@echo off
echo Building FuzzyMatcher Studio (Windows)...

pip install pyinstaller fastapi uvicorn python-multipart scikit-learn

python -m pyinstaller --noconfirm --onefile --windowed ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "scorers;scorers" ^
  --hidden-import "sklearn.feature_extraction.text" ^
  --hidden-import "sklearn.metrics.pairwise" ^
  --hidden-import "sklearn.utils._cython_blas" ^
  --hidden-import "sklearn.neighbors.typedefs" ^
  --hidden-import "sklearn.neighbors._partition_nodes" ^
  --hidden-import "uvicorn.logging" ^
  --hidden-import "uvicorn.loops.auto" ^
  --hidden-import "uvicorn.protocols.http.auto" ^
  --hidden-import "uvicorn.protocols.websockets.auto" ^
  --hidden-import "uvicorn.lifespan.on" ^
  --hidden-import "anyio._backends._asyncio" ^
  --name "FuzzyMatcher_Windows" ^
  app.py

echo.
echo Build complete! Check the dist\ directory for FuzzyMatcher_Windows.exe
pause