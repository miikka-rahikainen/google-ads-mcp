FROM python:3.11-slim
RUN pip install --no-cache-dir uv==0.12.6
WORKDIR /app
COPY requirements.lock ./
RUN uv pip install --system --require-hashes -r requirements.lock
COPY pyproject.toml README.md LICENSE MANIFEST.in ./
COPY ads_mcp ./ads_mcp
RUN uv pip install --system --no-deps .
ENV GOOGLE_ADS_MCP_MODE=hosted
EXPOSE 8080
CMD ["google-ads-mcp"]
