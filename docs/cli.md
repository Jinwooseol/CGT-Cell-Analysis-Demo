# Command-line interface (`cgt-cli`)

The headless runner drives the same worker classes as the desktop GUI, with no display required. It
is installed as the `cgt-cli` console script (`pip install -e .`) and can also be invoked as a
module:

```bash
cgt-cli <command> [options]
# or
python -m cgt_cell_analysis_demo.cli <command> [options]
```

Global options: `-v/--verbose` (DEBUG logging), `--version`.

## Commands

### `run` — full pipeline

Runs all four stages for one sample, writing each stage into `work/<sample>/0N_*`.

```bash
cgt-cli run --sample S001 \
    --optical-tiles data/S001/optical \
    --pcr data/S001/pcr \
    --out-root work
```

| Option | Required | Description |
|--------|----------|-------------|
| `--sample` | yes | Sample identifier (becomes the output sub-folder). |
| `--optical-tiles` | yes | Folder of optical tile images (stage 1 input). |
| `--pcr` | yes | Folder with the PCR image and `rawData_{G,R}.csv` (stage 3 input). |
| `--out-root` | no | Output root (default `work`). |
| `--config` | no | Path to a JSON config (default: project `config.json`). |

Output layout:

```
work/S001/
├── 01_optical_indexing/   (+ Well_Image/ crops)
├── 02_cell_counting/      (Predicted_Cell_Count.csv)
├── 03_pcr_indexing/       (Labeled_rawData_{G,R}.csv)
└── 04_merge_results/      (rawCellData_{G,R}.csv)
```

### Single-stage commands

| Command | Key options | Purpose |
|---------|-------------|---------|
| `optical` | `--tiles --out` | Stage 1: optical well indexing. |
| `count` | `--images --out [--sample]` | Stage 2: AI cell counting (needs model weights). |
| `pcr` | `--pcr --out` | Stage 3: PCR well indexing. |
| `merge` | `--count-dir --pcr-dir --out [--sample]` | Stage 4: merge counts with PCR data. |

### `validate` — check configuration

```bash
cgt-cli validate                 # reference files must exist
cgt-cli validate --require-model # also require the model weights file
```

Exits `0` when valid, `1` (with a list of problems) otherwise.

### `info` — show resolved configuration

```bash
cgt-cli info
```

Prints the version and every configuration key after path resolution.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success. |
| `1` | A worker reported an error, a file was missing, or validation failed. |
| `130` | Interrupted (Ctrl-C). |
