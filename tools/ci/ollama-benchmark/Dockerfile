FROM ollama/ollama:0.34.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv python3-cairosvg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /source
COPY pyproject.toml README.md config.example.toml ./
COPY src/ src/
COPY tools/ci/ollama-benchmark/ benchmark/
RUN python3 -m venv /opt/benchmark \
    && /opt/benchmark/bin/pip install --no-cache-dir .
ENV OLLAMA_HOST=127.0.0.1:11434 \
    OLLAMA_NO_CLOUD=1 \
    OLLAMA_NUM_PARALLEL=1 \
    OLLAMA_MAX_LOADED_MODELS=1 \
    OLLAMA_LLM_LIBRARY=cpu \
    NVIDIA_VISIBLE_DEVICES=void \
    PATH=/opt/benchmark/bin:$PATH
ENTRYPOINT []
