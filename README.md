<div align="center">

<img src="frontend/public/logo-v1.png" alt="RamanCloud logo" width="96">

# RamanCloud

**Raman spectral preprocessing, in your browser.**

Cut, denoise, and correct baselines for spectra, time series, and hyperspectral images.

[Open RamanCloud](https://ramancloud.xmu.edu.cn/preprocessing/) · [Local Setup](LOCAL_SETUP.md) · [Report an Issue](https://github.com/moria5161/RamancloudV2/issues) · [Apache 2.0](LICENSE)

</div>

---

## Workspace

| Module | Work with | What you can do |
| :--- | :--- | :--- |
| **Spectral Processing** | Individual spectra and batches of up to 512 files | Build a pipeline, compare curves, and export results or baselines. |
| **Hyperspectral Processing** | Spectral images and time series | Compare heatmaps, inspect spatial pixels or time points, and export coordinate-preserving data. |
| **Extra Tools** | Spectral and mapping files | Split mappings, merge spectra, and convert supported instrument formats. |

**Your pipeline, your order.** Arrange cutting, denoising, and baseline correction to suit your data, then adjust the available parameters.

The workspace includes demo datasets, an in-app tutorial, English and Chinese interfaces, and light and dark themes.

## Getting Started

1. **Load** a demo or upload your files. For imaging and time series, select the matching instrument and data type.
2. **Build** your pipeline by adding and ordering processing steps.
3. **Compare** raw and processed data using interactive spectra and heatmaps.
4. **Export** results, separate baselines, or a ZIP with processing records.

Batch exports keep the original filenames. Imaging and time-series exports preserve source coordinates in Horiba-style text files; choose **Horiba** when importing them again.

<details>
<summary><strong>Available Algorithms</strong></summary>

| Task | Algorithms |
| :--- | :--- |
| Denoising | Savitzky-Golay, Wavelet (WTD), PEER, F2P, TSVD |
| Baseline correction | AirNet, airPLS, AABS, IModPoly, SNIP |

TSVD operates on multiple aligned spectra. AirNet and F2P use pretrained models; F2P is a masked self-supervised algorithm that has not yet been published.

Algorithm descriptions and references are available in the website's **Tutorial**.

</details>

## Run Locally

Use **Python 3.11** and **Node.js 22 or 24** to run your own copy.

The **[Local Setup Guide](LOCAL_SETUP.md)** covers installation, backend and frontend startup, optional model weights, and troubleshooting on Linux, macOS, and Windows.

| Layer | Stack |
| :--- | :--- |
| Browser workspace | React, Plotly |
| Processing API | FastAPI, NumPy, SciPy, PyWavelets, pybaselines |

AirNet and F2P weights are configured on the hosted website and are not included in this repository.

<details>
<summary><strong>Data Sharing on the Hosted Website</strong></summary>

Original-upload sharing is enabled by default to improve RamanCloud. Disable it in **Settings** before uploading confidential data.

Shared originals are retained until administrators delete them. Turning sharing off affects future uploads only. Demo datasets and processing results are not archived.

</details>

## Contact

Developed by **Ren Research Group, Xiamen University**.

[Website feedback and bug reports](https://github.com/moria5161/RamancloudV2/issues) · [Research inquiries](mailto:bren@xmu.edu.cn)

## License

RamanCloud source code is licensed under the **[Apache License 2.0](LICENSE)**.

Third-party components retain their original licenses. Model weights, datasets, and publication figures are not covered by this software license unless explicitly stated otherwise.
