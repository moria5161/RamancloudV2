# RamanCloud

An online workspace for Raman spectral preprocessing.

**[Open RamanCloud](https://ramancloud.xmu.edu.cn/preprocessing/)**

## Features

- Process individual spectra, time series, and hyperspectral images.
- Arrange spectral cutting, denoising, and baseline correction in your preferred order.
- Compare raw and processed data through spectra and heatmaps, and inspect individual spatial pixels or time points.
- Download processed data with optional processing records, split or merge spectral files, and convert between supported instrument formats.
- Switch between English and Chinese, with light and dark themes.

## Workflow

1. Choose **Spectral Processing** or **Hyperspectral Processing**.
2. Load a demo dataset or upload your data. For time series and imaging, select the matching instrument and data type.
3. Add processing steps, arrange their order, and adjust the parameters.
4. Run the pipeline, compare the results, and download the processed data.

Use **Extra Tools** for file operations and **Tutorial** for guidance.

To run your own copy, see the [local setup guide](LOCAL_SETUP.md).

## Architecture

React and Plotly provide the interactive workspace; FastAPI handles data loading and processing. Nginx serves the frontend and forwards API requests to the backend.

Developed by Ren Research Group, Xiamen University.
