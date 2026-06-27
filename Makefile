# BSTU-AI — Docker Compose shortcuts
# Requires: Docker Desktop / engine, .env (see `make env`)
#
# По умолчанию `up` без --build — образ подтягивается из кеша Docker; pip/npm не делаются заново
# при простом коде после первой сборки. После изменения requirements.txt или Dockerfile:
#     make build
# Полная принудительная пересборка:
#     make rebuild

COMPOSE_FULL := docker compose --profile platform --profile openwebui --profile bots

.PHONY: help env up up-build build stack-full stack-full-build down restart ps logs logs-all health \
	ui ui-reset-modules ui-nuke-volume ui-build webui webui-build bots bots-build rebuild clean shell-api shell-worker

.DEFAULT_GOAL := help

help:
	@echo "BSTU-AI — быстрые команды"
	@echo ""
	@echo "  make env              — скопировать .env.example → .env, если .env нет"
	@echo "  make up               — ядро: postgres, redis, qdrant, api, celery (-d, без сборки при каждом запуске)"
	@echo "  make up-build         — то же, но собрать образы ingestion/celery (после смены requirements.txt)"
	@echo "  make build            — только docker compose build (api + bots)"
	@echo "  make down             — остановить и убрать контейнеры"
	@echo "  make restart          — down + up"
	@echo "  make ps               — docker compose ps -a"
	@echo "  make logs             — follow: ingestion-service + celery-worker"
	@echo "  make logs-all         — follow: все сервисы"
	@echo "  make health           — GET /api/health"
	@echo "  make ui               — UI задач (:5173), профиль platform (без --build)"
	@echo "  make ui-reset-modules — очистить только содержимое node_modules в томе UI (не rm -rf точки монтирования)"
	@echo "  make ui-nuke-volume   — остановить UI и удалить docker-том platform_ui_node_modules (с нуля)"
	@echo "  make ui-build         — собрать/обновить образы перед ui"
	@echo "  make webui / webui-build — Open WebUI"
	@echo "  make bots / bots-build — telegram + upload боты"
	@echo "  make stack-full       — platform + openwebui + bots, без сборки каждый раз"
	@echo "  make stack-full-build — всё профили + сборка образов"
	@echo "  make rebuild          — compose build --no-cache (долго, с нуля)"
	@echo "  make clean            — down + удалить volumes (БД/Qdrant + node_modules UI)"
	@echo "  make shell-api        — sh внутри ingestion-service"
	@echo "  make shell-worker     — sh внутри celery-worker"

env:
	@test -f .env && echo ".env уже есть" || (cp .env.example .env && echo "Создан .env из .env.example — отредактируйте ключи")

up:
	docker compose up -d

up-build:
	docker compose up -d --build

build:
	docker compose build

down:
	docker compose down

restart: down up

ps:
	docker compose ps -a

logs:
	docker compose logs -f ingestion-service celery-worker

logs-all:
	docker compose logs -f

health:
	@curl -sfS http://localhost:8001/api/health | python3 -m json.tool 2>/dev/null || curl -sfS http://localhost:8001/api/health

ui:
	docker compose --profile platform up -d

ui-reset-modules:
	-docker compose --profile platform stop problem-platform-ui 2>/dev/null
	docker compose --profile platform run --rm problem-platform-ui sh -c '\
	  if [ -d node_modules ]; then \
	    chmod -R u+w node_modules 2>/dev/null || true; \
	    find node_modules -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || rm -rf node_modules/* 2>/dev/null || true; \
	  fi'
	@echo "Готово. Запустите: make ui"

# Удаляет именованный том (имя зависит от каталога проекта: см. docker volume ls | grep platform_ui)
ui-nuke-volume:
	-docker compose --profile platform stop problem-platform-ui 2>/dev/null || true
	docker compose --profile platform rm -sf problem-platform-ui 2>/dev/null || true
	@VOL=$$(docker volume ls -q --filter name=platform_ui_node_modules | head -n 1); \
	  if [ -z "$$VOL" ]; then echo "Том platform_ui_node_modules не найден — ок."; \
	  else echo "Удаляю: $$VOL"; docker volume rm -f "$$VOL"; fi
	@echo "Готово. Запустите: make ui"

ui-build:
	docker compose --profile platform up -d --build

webui:
	docker compose --profile openwebui up -d

webui-build:
	docker compose --profile openwebui up -d --build

bots:
	docker compose --profile bots up -d

bots-build:
	docker compose --profile bots up -d --build

stack-full:
	$(COMPOSE_FULL) up -d

stack-full-build:
	$(COMPOSE_FULL) up -d --build

rebuild:
	docker compose build --no-cache

clean:
	docker compose --profile platform --profile openwebui --profile bots down -v

shell-api:
	docker compose exec ingestion-service sh

shell-worker:
	docker compose exec celery-worker sh
