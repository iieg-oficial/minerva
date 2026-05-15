.PHONY: help network up down restart logs ps secrets \
        test-up test-down test-logs test-ps

NETWORK_NAME := iieg-network
COMPOSE := docker compose
TEST_COMPOSE := docker compose -f test/docker-compose.test.yml

help:
	@echo ""
	@echo "  Minerva (Authentik IdP):"
	@echo "    up            Levantar el stack de Authentik (.env)"
	@echo "    down          Tumbar el stack"
	@echo "    restart       Reiniciar (aplica blueprints nuevos)"
	@echo "    logs          Logs del stack"
	@echo "    ps            Status de los contenedores"
	@echo "    secrets       Generar valores aleatorios para el .env"
	@echo ""
	@echo "  Ambiente de prueba (ver test/README.md):"
	@echo "    test-up       Levantar gateway-test + app dummy"
	@echo "    test-down     Tumbar el ambiente de prueba"
	@echo "    test-logs     Logs del ambiente de prueba"
	@echo ""

network:
	@docker network inspect $(NETWORK_NAME) >/dev/null 2>&1 || \
	    (echo "Creando red $(NETWORK_NAME)..."; docker network create $(NETWORK_NAME))

up: network
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart: down up

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

secrets:
	@echo "# Pegar en .env (valores recien generados):"
	@echo "AUTHENTIK_SECRET_KEY=$$(openssl rand -base64 60 | tr -d '\n')"
	@echo "POSTGRES_PASSWORD=$$(openssl rand -base64 36 | tr -d '\n')"
	@echo "AUTHENTIK_BOOTSTRAP_PASSWORD=$$(openssl rand -base64 24 | tr -d '\n')"
	@echo "AUTHENTIK_BOOTSTRAP_TOKEN=$$(openssl rand -hex 32)"

test-up:
	$(TEST_COMPOSE) up -d

test-down:
	$(TEST_COMPOSE) down

test-logs:
	$(TEST_COMPOSE) logs -f --tail=100

test-ps:
	$(TEST_COMPOSE) ps
