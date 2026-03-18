PYTHON ?= python3

.PHONY: test compile ci docker-build

compile:
	$(PYTHON) -m compileall app.py gateway_server.py setup_ui.py superagent tasks mcp_servers

test:
	OPENAI_API_KEY=$${OPENAI_API_KEY:-test-openai-key} $(PYTHON) -m unittest discover -s tests -v

docker-build:
	docker build -t superagent-local .

ci: compile test docker-build
