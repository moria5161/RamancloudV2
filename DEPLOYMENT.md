# RamanCloud alpha deployment

Use the `alpha` branch of [the deployment repository](https://github.com/moria5161/RamancloudV2/tree/alpha). The public frontend is served at `/rc/`. The backend listens on `127.0.0.1:5001` and serves its API under `/alpha/api/`. Clone each release into its own directory and record its Git SHA so it can be restored.

## Prepare a release

1. Use a dedicated unprivileged Linux user and group named `ramancloud-alpha`. Create `/srv/ramancloud-alpha/releases` for the source and build, and `/var/lib/ramancloud-alpha` for persistent data. Give the service user ownership and restrict write access.
2. As that user, clone branch `alpha` into a new directory under `/srv/ramancloud-alpha/releases`, verify the intended commit, and run `bash scripts/prepare_alpha.sh` with Python 3.11, Node.js 24 or later and npm. This builds the frontend and installs the backend and the separate CPU SSnet runtime. For a smoke test of SSnet, upload a known reference spectrum, train with small settings, and verify extraction on a mixture covering the trained wave-number range.
3. Install the example environment file as `/etc/ramancloud-alpha.env` with mode `0600` and configure the models below. Symlink `/srv/ramancloud-alpha/current` to the prepared release. Install `deploy/alpha/ramancloud-alpha.service` under `/etc/systemd/system/`, run `systemctl daemon-reload`, and start `ramancloud-alpha`. Check `curl -fsS http://127.0.0.1:5001/alpha/api/health` before exposing the route.
4. For an `/alpha/` preview, include `deploy/alpha/nginx.conf` in the appropriate Nginx configuration. For the public `/rc/` deployment, follow the publishing section below. Verify the health check, a refresh on a nested page, and streaming AI responses. Enable `ramancloud-alpha` to start at boot after acceptance.

For a preview without system-level access, use `~/ramancloud-alpha/releases`, link the chosen release as `~/ramancloud-alpha/current`, and put the private environment at `~/ramancloud-alpha/alpha.env` with `RAMANCLOUD_DATA_DIR` set to the absolute path of `~/ramancloud-alpha/state`. Install `deploy/alpha/ramancloud-alpha.user.service` as `~/.config/systemd/user/ramancloud-alpha.service` and run `systemctl --user daemon-reload` and `systemctl --user enable --now ramancloud-alpha`. The server operator can enable lingering for the service account to keep it running after SSH logout. Use one service variant at a time.

## AI and algorithm models

SSnet training and mixture extraction run one job at a time in submission order. Keep the production service at one worker for the SSnet queue. Hyperspectral processing and AI requests run independently of SSnet jobs. The model server manages its own inference concurrency. Cap Ollama context with `RAMANCLOUD_OLLAMA_CONTEXT` and verify both chat and structured plan generation when changing it.

- Run Ollama on the server with a loopback listener and pull the model from the environment file. Verify `/api/tags` on the Ollama listener and send one real chat through the website. The model consumes server CPU/RAM or GPU. The application can also use its existing DeepSeek or SiliconFlow provider through the server environment when the group supplies credentials. Keep provider keys in the restricted environment file.
- Run `python3.11 scripts/setup_legacy_algorithms.py` for the preprocessing dependencies and public F2P checkpoint. Supply the compatible AirNet checkpoint from approved server storage and export `RAMANCLOUD_AIRNET_MODEL` pointing to it for the installer. Confirm F2P and AirNet availability and real inference before offering them to users.
- For library matching, provision the approved PeakNet package privately and pass its path to `python3.11 scripts/setup_peaknet.py /path/to/peaknet-package.zip`. For Spectrum to Structure, run `python3.11 scripts/setup_vib2mol.py` and verify generation with a reference input. The installers use the manifest and pinned checksums where available. When provisioning more than one runtime, install PeakNet and Vib2Mol before the preprocessing runtime and verify all of them together. Optional agent assets require separate approved provisioning.

## Data and administrative accounts

The hosted optimized edition uses MySQL for accounts, project metadata, analysis records and feedback. Self-hosted deployments can select MySQL using the [environment template](backend/.env.mysql.example). Set the application credentials in the service's private environment. The app creates its tables after the database has been provisioned.

The default self-hosted configuration uses SQLite. With the example service directories, the SQLite database is at `/var/lib/ramancloud-alpha/ramancloud.db` and uploaded files are at `/var/lib/ramancloud-alpha/stored_files`. SSnet job files live under the storage directory. The QA sidebar keeps chat in the current session.

Before migrating an existing site, identify and back up its database and storage as a pair. Check the schema and test a restored copy with alpha. For SQLite alpha backups, stop the alpha service briefly, archive the entire private state directory, and start the service again. Test restoration of accounts, files, and record links. If MySQL is already available, configure a dedicated database and credentials using `backend/.env.mysql.example` and take both a database backup and a matching file backup.

For a fresh SQLite installation, run the following in the active release as the service user. The script prompts for the initial administrator's own username and password.

~~~bash
cd /srv/ramancloud-alpha/current/backend
sudo -u ramancloud-alpha env RAMANCLOUD_DATA_DIR=/var/lib/ramancloud-alpha \
    ../.venv/bin/python bootstrap_admin.py
~~~

Ask the second maintainer to register individually. In **Personal Space → Account management**, the first administrator can promote that account. Administrators can see account profile information, status and roles and manage feedback. Passwords and session tokens are excluded from the account list. Verify that an ordinary account receives HTTP 403 for that list.

For code rollback, return the `current` symlink to the previous release and restart alpha. For schema changes, test the compatibility of the previous release first and use a coordinated data restore when needed.

## Publish the frontend at `/rc/`

~~~bash
cd frontend
RAMANCLOUD_BASE_PATH=/rc/ VITE_RAMANCLOUD_API_BASE=/rc/ramancloud-api npm run build
~~~

Copy the contents of `dist/` into the `rc/` subdirectory of a versioned Nginx document root. Serve `rc/index.html` for `/rc/` and registered frontend routes such as `/rc/login` and `/rc/projects` so direct visits and refreshes work. Serve `/rc/assets/` and `/rc/research/` from the build with HTTP 404 for missing files. Route `/rc/ramancloud-api/` separately to `http://127.0.0.1:5001/alpha/api/`, preserving the query string and the upstream error response. Redirect `/` and `/rc` to `/rc/`.

Back up the active Nginx configuration before switching the document root and routes. Run `nginx -t`, reload Nginx, and verify the homepage, a direct visit to a frontend route, JS and CSS, and `/rc/ramancloud-api/health`. Check that the health response is JSON and that a missing API route returns HTTP 404. Verify upload and download through the public gateway using a representative file, since the gateway and origin may have independent upload limits. To roll back, restore the backed-up Nginx configuration, test it, and reload Nginx. Keep both releases and their data directories available during the rollback period.

## Move V2 to a GPU host

Keep the public `/rc/` and `/rc/ramancloud-api/` paths. When an existing origin also serves the legacy site, forward the V2 paths from that origin to the GPU host while keeping the legacy site's specific routes on the existing origin. Allow the GPU host's web server to accept requests from the existing origin, keep streaming API response buffering disabled, and keep the application, MySQL and Ollama listeners on loopback. Frontend builds keep the same public paths.

Deploy and test the active V2 source and frontend build on the new machine with its own MySQL credentials. Copy the V2 database and persistent storage together, including the model checkpoints and approved model runtimes. After the test restore, pause writes on both instances while taking and importing the final snapshot. Compare table counts and check representative file references before switching traffic. Keep the original data and release for recovery, and keep the old V2 backend stopped after the new instance begins accepting writes.

Use Ollama's published GPU support guidance for the driver and accelerator. Verify a real inference and confirm GPU offload in `ollama ps`.

Install SSnet's CUDA environment with `python scripts/setup_ssnet.py --cuda`. Set `RAMANCLOUD_SSNET_DEVICE=cuda` in the V2 backend environment. If the CUDA environment lives outside `.venv-ssnet` in the checkout, set `RAMANCLOUD_SSNET_PYTHON` to its Python executable. Verify CUDA availability in that interpreter and run a small training and prediction job before serving production traffic.

To use CUDA for hyperspectral TSVD and the neural passes of F2P and AirNet, set `RAMANCLOUD_HYPERSPECTRAL_CUDA_PYTHON` to a CUDA-enabled Python with `numpy`, `scipy`, `PyWavelets`, `pybaselines`, and PyTorch. The original weights and parameters still apply. The upload API advertises the supported chunk size in `/api/health`, then parses the completed file through the same path as a single-part upload.
