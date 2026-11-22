# AETHENTRA — Scientific Intelligence Platform

Antarctic climate & cryosphere data and models. Repository layout:

| Path | Content |
|---|---|
| `DATAS/` | User-collected raw Antarctic datasets (read-only) |
| `EXTERNAL APIs/` | Copernicus CDS ERA5 request scripts (`API.py`, `PRESSUREAPI.py`) |
| `data/src/preprocessing/antarctic/` | Stage 1: inventory / validation / preprocessing of `DATAS/` (`python -m data.src.preprocessing.antarctic.run_pipeline`) |
| `src/aethentra/` | **ML Task 01**: weekly Antarctic sea-ice concentration forecasting (data, preprocessing, features, baselines, models, training, evaluation, inference, visualization, reporting) |
| `configs/` | YAML configuration for Task 01 (data sources, preprocessing, features, training, evaluation) |
| `scripts/` | CLI entry points (download, preprocess, validate, train, analyze, figures, predict, docs) |
| `api/` | FastAPI forecast service |
| `models/` | `checkpoints/` (candidates), `final/` (frozen final model bundle), `artifacts/` (climatologies) |
| `experiments/` | logs and metrics (validation, tuning, selection record, single test evaluation) |
| `outputs/` | figures, data-validation reports, forecasts + frontend layers |
| `docs/ml_task_01/` | Task 01 documentation (start with `AETHENTRA_ML_TASK_01_FINAL_REPORT.md`) |
| `src/aethentra/temperature/` | **ML Task 02**: weekly Antarctic 2 m temperature & anomaly forecasting (configs `configs/ml02/`, scripts `scripts/ml02/`, API router `/temperature`) |
| `docs/ml_task_02/` | Task 02 documentation (start with `AETHENTRA_ML_TASK_02_FINAL_REPORT.md`) |
| `notebooks/` | `01_temperature_exploration.ipynb` (ML-02) |
| `metadata/`, `reports/` | Stage 1 manifests and Word report |

## Run and host the website anywhere

The platform has two processes:

| Process | What it is | Port | Who connects to it |
|---|---|---|---|
| **API** (`api/`, FastAPI + Uvicorn) | Serves model outputs, metrics and forecasts | `8000` | Only the website server (keep it on `127.0.0.1`) |
| **Website** (`web/`, Next.js 15) | The site, the 3D globe and the pre-built map layers in `web/public/data/` | `3000` | Browsers on any device |

The browser never calls the API directly: Next.js forwards `/backend/*` to the API on the server side. So **only port 3000
has to be reachable** from other devices, and the API can stay private. If the API is not running, the site still loads; the
globe layers and climate charts come from static files, and model panels show an "unavailable" message.

### 1. Requirements (download and install these first)

| Requirement | Version | Download / install | Check |
|---|---|---|---|
| Git | any recent | https://git-scm.com/downloads | `git --version` |
| Python | **3.11** (tested 3.11.9; 3.10–3.12 should work) | https://www.python.org/downloads/ — on Windows tick "Add python.exe to PATH" | `python --version` |
| Node.js | **20 LTS or newer** (tested 24.13; Next.js 15 needs ≥ 18.18) | https://nodejs.org/en/download (npm is included) | `node --version` · `npm --version` |
| Web browser | Chrome, Edge, Firefox or Safari with **WebGL 2** and hardware acceleration on | — | open https://get.webgl.org/webgl2/ |
| Disk / RAM | allow about 5 GB free for the repository, Python packages and `node_modules`; 8 GB RAM recommended | — | — |
| Internet | Needed at install time. While running, only the live NASA GIBS satellite layer and the optional Cesium terrain need it; everything else is served locally. | — | — |

Optional, only for re-downloading data or retraining (not needed to run the site):

| Optional | Used for | Install |
|---|---|---|
| CDS API key (`~/.cdsapirc`) | ERA5 downloads (`scripts/era5_bulk_download.py`) | https://cds.climate.copernicus.eu/how-to-api |
| Copernicus Marine account | CMEMS C1–C7 downloads (`scripts/cmems_download.py`) | `pip install copernicusmarine` then `copernicusmarine login` |
| PyTorch (CUDA) | Training or re-running the U-Net models | `pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124` |
| Cesium ion token | 3D terrain relief on the globe (the site works without it) | https://ion.cesium.com/tokens, put in `web/.env.local` |

Raw data (`data/raw/`) and some large derived products are **not** in git (see `.gitignore`). They are only needed to
retrain models or rebuild the map layers; the website runs from what is committed.

### 2. Get the code and install dependencies (once per machine)

```bash
git clone https://github.com/STEVENLYRAJ/Antarctic-Intelligence.git
cd Antarctic-Intelligence

# Python environment for the API
python -m venv .venv
# Windows (PowerShell):      .venv\Scripts\Activate.ps1
# macOS / Linux:             source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

# Website (npm install also copies the CesiumJS assets into web/public/cesium)
cd web
npm install
cp .env.example .env.local        # Windows PowerShell: Copy-Item .env.example .env.local
npm run build                     # production build, about 1 minute
cd ..
```

If PowerShell refuses to run `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

`web/.env.local` settings (no secrets are needed):

```ini
AETHENTRA_API_URL=http://127.0.0.1:8000     # where the website server finds the API
NEXT_PUBLIC_CESIUM_ION_TOKEN=               # optional, public Cesium ion token for terrain
```

### 3. Start it (every time)

Use two terminals, both started in the repository folder.

```bash
# Terminal 1: API, private to this machine
#   (activate .venv first, as above)
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2: website, reachable from this machine and the local network
cd web
npx next start -H 0.0.0.0 -p 3000
```

Open **http://localhost:3000**. Check: http://localhost:3000/backend/health returns `{"status":"ok",...}`.

For development with hot reload, use `npm run dev` instead of `npm run build` + `next start`.

Windows, start both hidden in the background from PowerShell:

```powershell
Start-Process -WindowStyle Hidden python -ArgumentList '-m','uvicorn','api.main:app','--host','127.0.0.1','--port','8000'
Start-Process -WindowStyle Hidden -WorkingDirectory web cmd.exe -ArgumentList '/c','npx next start -H 0.0.0.0 -p 3000'
```

Stop them: close the terminals, or on Windows run
`Get-NetTCPConnection -LocalPort 3000,8000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }`.

### 4. Open it on other devices (phone, tablet, laptop on the same Wi-Fi / LAN)

1. Find the host computer's IP address: Windows `ipconfig` (IPv4 Address), macOS `ipconfig getifaddr en0`, Linux `hostname -I`.
2. Allow incoming connections on port 3000 (once):
   - **Windows** (PowerShell as Administrator):
     `New-NetFirewallRule -DisplayName "AETHENTRA web 3000" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow -Profile Private`
     (and set the Wi-Fi network to *Private* in Windows Settings > Network)
   - **macOS**: allow "node" when the firewall prompt appears.
   - **Linux (ufw)**: `sudo ufw allow 3000/tcp`
3. On the other device open **http://\<host-IP\>:3000**, for example `http://192.168.1.20:3000`.

Port 8000 does not need to be opened; the API stays private.

### 5. Share a public link (anyone on the internet, temporary)

Cloudflare quick tunnel: no account and no router changes. The link works while the command runs.

```bash
# install once:  Windows: winget install --id Cloudflare.cloudflared   macOS: brew install cloudflared
#                Linux: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
cloudflared tunnel --url http://localhost:3000
# prints a https://<random-name>.trycloudflare.com address; share it
```

The API has no authentication and the website forwards every `/backend/*` request to it, so share public links only
for demos and stop the tunnel (Ctrl+C) afterwards.

### 6. Permanent hosting (server or cloud VM)

On any Linux server or VM (Ubuntu 22.04+, 2 vCPU / 4 GB RAM or more), follow steps 1–3, then keep both processes running and
put a web server with HTTPS in front of port 3000:

```bash
# keep both processes alive across logouts and reboots (example with pm2)
sudo npm install -g pm2
pm2 start "python -m uvicorn api.main:app --host 127.0.0.1 --port 8000" --name aethentra-api   # run inside the activated .venv
pm2 start "npx next start -H 127.0.0.1 -p 3000" --name aethentra-web --cwd web
pm2 save && pm2 startup

# HTTPS reverse proxy to the website (Caddy obtains the certificate automatically)
sudo apt install -y caddy
echo 'your-domain.example { reverse_proxy 127.0.0.1:3000 }' | sudo tee /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

The website alone can also be deployed to Vercel (root directory `web/`). Set `AETHENTRA_API_URL` to a publicly reachable API
URL in the Vercel project settings; without one, the static layers and charts work but the live model panels show "unavailable".

### 7. Update the data shown on the site

The map layers and series in `web/public/data/` are pre-built from the local archive (needs `data/raw/`):

```bash
python scripts/web/build_globe_products.py              # all products, about 16 min
python scripts/web/build_globe_products.py era5d era5d2 # only the ERA5 daily layers and records, about 2 min
```

The running site picks up the new files without a rebuild. Commit `web/public/data/` so other machines get them on `git pull`.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `/backend/health` fails | The API is not running or not on `127.0.0.1:8000`; start terminal 1, or set `AETHENTRA_API_URL` in `web/.env.local` and rebuild |
| Globe is black or missing | Enable hardware acceleration in the browser; check https://get.webgl.org/webgl2/ |
| `cesium not installed` during `npm install` | Delete `web/node_modules` and run `npm install` again |
| Other devices cannot connect | Firewall rule for port 3000, network set to *Private*, and both devices on the same network (guest Wi-Fi often blocks this) |
| Port already in use | Stop the old process (see step 3) or use another port: `npx next start -p 3001` |
| `pip install` fails on geopandas/rasterio | Use Python 3.11 (prebuilt wheels exist), or install them with `conda install -c conda-forge geopandas rasterio` |

## ML Task 01 quick start

```bash
pip install -r requirements.txt
python scripts/download_data.py --all       # public data only, MD5-verified, resumable
python scripts/preprocess.py
python scripts/validate_data.py
python scripts/train.py tables && python scripts/train.py candidates
python scripts/analyze.py features
python scripts/train.py tune && python scripts/train.py select && python scripts/train.py final
python scripts/train.py test                # single evaluation on 2021-2025
python scripts/analyze.py final && python scripts/make_figures.py
python scripts/predict.py                   # latest weekly forecast -> outputs/forecasts/
python scripts/build_docs.py
python -m pytest tests/
uvicorn api.main:app --port 8000
```

Full details: `docs/ml_task_01/REPRODUCIBILITY_GUIDE.md`. No credentials are required; see `.env.example` for optional ERA5 /
Copernicus Marine / Earthdata extensions. Never commit `.env`.

## ML Task 02 quick start (weekly 2 m temperature / anomaly)

```bash
python scripts/ml02/download_data.py --stations --ncep-interim   # anonymous; --era5 needs %USERPROFILE%\.cdsapirc
python scripts/ml02/preprocess.py --source ncep_r1
python scripts/ml02/validate_data.py --source ncep_r1
bash scripts/ml02/run_all.sh ncep_r1        # tables -> models -> Optuna -> select -> final -> single test -> analysis -> figures -> forecast
python scripts/ml02/build_docs.py
python -m pytest tests/test_ml02_temperature.py
```

ML-02 currently uses **NCEP/NCAR R1 as an interim substitute for ERA5** (no CDS key was available); see
`docs/ml_task_02/TEMPERATURE_DATA_SOURCES.md` for the switch to ERA5.

## Web viewer and local API

```bash
bash scripts/serve.sh                       # API + viewer on http://127.0.0.1:8000/  (loopback only)
```

`/viewer/` shows the latest sea-ice and 2 m temperature forecasts as polar-stereographic maps rendered from the native
EPSG:3412 GeoTIFFs, with every layer labelled as observation / reanalysis / model prediction / evaluation. API documentation
is at `/docs`. This is a local service, not a production deployment (no authentication, TLS or public hosting).

## Spatial deep-learning addendum (U-Net, both tasks)

```bash
python -m pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu124   # CUDA build, ~2.5 GB
bash scripts/ml02/run_cnn.sh ncep_r1        # stacks -> train -> validate -> frozen decision -> refit -> single test
bash scripts/run_ml01_cnn.sh
```

The U-Net runs after the tree-model selection and test were frozen. It replaces a tree model only if it is better on every
validation selection metric; that decision is written to `addendum_cnn_decision_record.json` before its single test evaluation.

## ML Task 03 quick start (Sentinel-1 SAR sea-ice detection)

```bash
pip install -r requirements.txt                                   # + torch (CUDA) for the U-Net
python scripts/ml03/download_data.py --land --charts --start 2018-01-01 --end 2026-11-09   # USNIC charts, anonymous
python scripts/ml03/download_data.py --catalogue --scenes         # Sentinel-1 EW HH via Planetary Computer, anonymous
python scripts/ml03/run_all.py                                    # prepare -> samples -> baselines -> tiles -> U-Nets -> validate -> select -> final -> test -> analysis/docs
python scripts/ml03/generate_weekly_map.py --week-start 2026-11-02
python scripts/ml03/predict.py --scene-id <S1 EW GRDM HH id>
python -m pytest tests/test_ml03_sar.py
```

Labels are USNIC Antarctic ice charts (expert, chart-scale), so every ML-03 metric is *agreement with the charts*, not pixel truth.
Results and limitations: `docs/ml_task_03/AETHENTRA_ML_TASK_03_FINAL_REPORT.md`. API under `/seaice-detection`; weekly layers in
the viewer's "SAR sea-ice detection" tab.

## ML Task 04 quick start (Antarctic climate anomaly detection)

Public data only (NCEP/NCAR R1 daily via NOAA PSL OPeNDAP, NOAA/NSIDC SIC CDR v6); no credentials needed.

```bash
python scripts/ml04/run_all.py                 # download -> preprocess -> baselines -> features -> fit -> validate (frozen)
                                               # -> test (once) -> score -> products -> export -> store
python scripts/ml04/run_all.py --from score    # rebuild products from the saved detectors
python scripts/ml04/update_pipeline.py --check # are newer source data available?
python -m pytest tests/test_ml04_anomaly.py
```

API under `/api/ml04` (health, model-info, detect, latest, anomalies, monthly-summary, seasonal-summary, spatial-data, metrics,
data-coverage, events, compound, sea-ice-extent); dashboard at `/viewer/#anom`. Documentation: `docs/ml_task_04/`
(progress tracker, audit, data inventory and documentation, model card, scientific limitations, test report).
Note: NOAA PSL's NCEP R1 daily record ends 2026-03-17, so multivariate anomalies stop at February 2026.
