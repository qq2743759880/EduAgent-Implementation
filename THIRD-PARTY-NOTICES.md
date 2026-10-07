# Third-party components

Bili-Study's original source code is licensed under MIT (see LICENSE). Third-party components, model weights and educational media retain their own licenses; the project license does not grant rights to course videos.

- **BiliSum**: MIT prompt/media adaptation. Original attribution and provenance are retained in `bili-study-agent/app/domains/video_learning/vendor/bilisum/`.
- **shadcn**: the existing `4.16.2` stylesheet is preserved unchanged in `bili-study-frontend/src/styles/`. Its upstream MIT license and SHA-256 provenance are included there. The code-generation CLI is not shipped as an application dependency.
- **MinIO**: the portable image builds the official `RELEASE.2025-10-15T17-29-55Z` source, licensed under GNU AGPLv3. Source and release instructions: https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z . No modified MinIO source is embedded in Bili-Study.
- **MinerU 4.0.10**: installed in a separate runtime; its declared license is `LicenseRef-MinerU-Open-Source-License`, based on Apache 2.0 with additional terms. Review the upstream `LICENSE.md`, including service attribution and applicable commercial thresholds: https://github.com/opendatalab/MinerU/blob/master/LICENSE.md . It must not be described as unrestricted MIT software.
- **Model weights and educational media**: not included in the source release. Obtain weights from their publishers and follow their separate licenses. Import only educational material you are authorized to use; a Bilibili link does not grant redistribution permission.

Other dependencies retain their package licenses. This source package does not include the author's installed virtual environments, Docker images, private keys, Cookie files, media or database exports.
