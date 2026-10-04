# 第三方元件與來源

本工具使用以下官方或本機既有套件，原有授權檔保留在 `runtime/` 與各套件的 `.dist-info` 資料夾。

- CPython 3.13.14：Python Software Foundation License，https://www.python.org/
- NumPy 2.5.1：BSD，https://numpy.org/
- Pillow 12.3.0：HPND，https://python-pillow.org/
- OpenCV 5.0.0：Apache 2.0，https://opencv.org/
- MediaPipe 1.0.1：Apache 2.0，https://github.com/google-ai-edge/mediapipe
- Matplotlib 3.11.1 及其依賴：授權資訊隨套件附上，https://matplotlib.org/

MediaPipe 從 PyPI 安裝；執行環境及部分已安裝套件從本機 Python 環境封裝進工具，工具執行時不依賴原安裝路徑。

## 本機模型

使用 Google 官方 MediaPipe 模型，功能依官方文件實作：

- Face Landmarker（478 個關鍵點）：https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker
- 多類別人像分割（背景、頭髮、身體皮膚、臉部皮膚、衣服、其他）：https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter
- 模型原始網址：
  - https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
  - https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/1/selfie_multiclass_256x256.tflite

模型已隨包附上，啟動或修圖時不會下載任何內容。模型 SHA-256 見 `MANIFEST.json`。
