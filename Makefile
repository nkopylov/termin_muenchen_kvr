.PHONY: update up down build logs restart

update:
	git pull && docker-compose down && docker-compose build && docker-compose up -d

up:
	docker-compose up -d

down:
	docker-compose down

build:
	docker-compose build

logs:
	docker-compose logs -f

restart:
	docker-compose restart
