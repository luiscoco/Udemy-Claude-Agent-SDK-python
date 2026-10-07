FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY agent_lab ./agent_lab
RUN pip install --no-cache-dir uv && uv sync --locked --no-dev
COPY public ./public
COPY Tab*.md ./
RUN useradd --create-home agent && mkdir /app/.lab-data && chown agent:agent /app/.lab-data
USER agent
EXPOSE 8080
CMD [".venv/bin/python", "-m", "agent_lab", "serve", "--host", "0.0.0.0", "--port", "8080"]
