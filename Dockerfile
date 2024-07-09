FROM mcr.microsoft.com/devcontainers/python:3.12

ENV PYTHONUNBUFFERED 1

WORKDIR /app
RUN pip install poetry==1.8.3
RUN poetry config virtualenvs.create false
COPY poetry.lock pyproject.toml /app/
RUN poetry install --no-root
