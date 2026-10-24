# 可选 Python 算法适配器

该组件保留 Python/Pillow/RapidOCR/rembg 算法能力，不承担商品、审核、发布或数据库业务。普通成品图工作流只需要 Java。

使用 Python 3.12+ 创建独立虚拟环境，安装 `requirements.txt`。设置至少32字符的 `COMPUTE_TOKEN`，用 `uvicorn app:app --host 127.0.0.1 --port 8100 --limit-concurrency 4 --timeout-keep-alive 5` 启动。容器部署只接内部网络。Java `COMPUTE_URL=http://compute:8100`、相同token，单任务超时180秒。

接口仅为 `POST /internal/compute/{jobId}`，multipart字段 `file`、JSON字符串`params`，Header `X-Internal-Token`。结果为含 `manifest.json` 和可选 `output.png` 的ZIP。最多2个任务并发；同jobId同输入复用，异输入409。请求不接收本机路径、SQL或回调URL。

`RESIZE`直接可用。OCR需要另装RapidOCR与ONNX Runtime，并配置已有本地模型 `OCR_DET_MODEL/OCR_REC_MODEL/OCR_CLS_MODEL`；抠图需要rembg与ONNX Runtime以及 `U2NET_HOME/birefnet-general.onnx`。缺模型时返回503，不自动下载模型、不伪造识别结果。原算法源码仍在 `apps/api/app/image_pipeline.py` 与 `scene_pipeline.py`，不是Java重写的算法。大型模型运行时间和实际模型输出仍需用受控素材验收。
