# NVR-AI (Network Video Recorder AI)

Платформа интеллектуального видеонаблюдения на микросервисной архитектуре с использованием алгоритмов компьютерного зрения (CV) для анализа видеопотока в реальном времени.

## 🛠 Стек технологий
- **Backend:** FastAPI, SQLAlchemy (Async), Python 3.12
- **CV Engine:** PyTorch, YOLOv8 (детекция), InsightFace (распознавание лиц), EasyOCR (распознавание автономеров)
- **Frontend:** Next.js (React)
- **Базы данных и хранилище:** PostgreSQL + TimescaleDB (time-series), Redis (брокер/кэш), MinIO (S3 объектное хранилище)
- **Инфраструктура и DevOps:** Docker Compose, Kubernetes, Prometheus

## 🏗 Архитектура микросервисов
Проект разделен на изолированные компоненты для высокой отказоустойчивости:
- `auth_service` (8001) — Авторизация (JWT) и управление доступом.
- `camera_service` (8002) — Управление конфигурациями IP/RTSP камер.
- `stream_service` (8003) — Захват, транскодирование и раздача видеопотока.
- `event_service` (8004) — Прием метаданных от CV, хранение событий, умный поиск.
- `telegram_service` (8005) — Отправка алертов и видеофрагментов в Telegram-бота.
- `archive_service` (8006) — Долгосрочное архивирование записей в S3 (MinIO).
- `cv_engine` — Ядро нейросетевой аналитики (получает поток, генерирует события и клипы).

## 🚀 Быстрый старт

### Требования
- Docker и Docker Compose
- *Рекомендуется:* NVIDIA GPU + NVIDIA Container Toolkit для аппаратного ускорения инференса CV-моделей.

### Запуск (Docker Compose)
1. Склонируйте репозиторий:
   ```bash
   git clone https://github.com/boras-lab/NVR-AI.git
   cd NVR-AI
   ```

2. Запустите все сервисы:
   ```bash
   docker-compose up -d --build
   ```

### Точки входа
- **Web UI (Frontend):** `http://localhost:3000`
- **Swagger API (например, Auth):** `http://localhost:8001/docs`
- **MinIO Console:** `http://localhost:9001` (login/pass: `minioadmin` / `minioadminsecure`)
- **PostgreSQL:** `localhost:5433` (db: `ai_nvr`, user: `nvr_admin`, pass: `nvr_password_secure`)

## 📁 Структура репозитория
- `/backend/` — Исходный код микросервисов, общие модели (shared) и миграции (Alembic).
- `/cv_engine/` — Сервис видеоаналитики (детекторы, OCR, логика распознавания).
- `/frontend/` — Веб-интерфейс администратора и оператора.
- `/infrastructure/` — Конфиги для мониторинга (Prometheus).
- `/k8s/` — Kubernetes-манифесты для production-развертывания.
