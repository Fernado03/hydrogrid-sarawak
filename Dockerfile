FROM python:3.11-slim

# System dependencies for C-extensions (DuckDB, LightGBM, Psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install build tooling
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install dependencies and local editable package
COPY pyproject.toml .
COPY src/ ./src/

# Install application and runtime dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    httpx \
    pydantic \
    sqlalchemy \
    psycopg2-binary \
    duckdb \
    pandas \
    numpy \
    scikit-learn \
    lightgbm \
    tabulate \
    python-dotenv \
    langgraph \
    langchain-core \
    langchain-openai \
    crewai \
    streamlit \
    plotly

# Install MLOps tracking runtime dependency (leverages previous cached layer)
RUN pip install --no-cache-dir mlflow

RUN pip install --no-cache-dir -e .

EXPOSE 8000 8501

CMD ["uvicorn", "hydrogrid.serving.app:app", "--host", "0.0.0.0", "--port", "8000"]