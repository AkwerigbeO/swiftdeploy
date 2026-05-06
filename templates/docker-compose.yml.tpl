services:
  app:
    image: {{SERVICE_IMAGE}}
    container_name: swift_app
    user: "1000:1000"
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    environment:
      - MODE={{MODE}}
      - APP_VERSION={{VERSION}}
      - APP_PORT={{PORT}}
    expose:
      - "{{PORT}}"
    networks:
      - {{NETWORK}}
    restart: {{RESTART_POLICY}}
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import json, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:{{PORT}}/healthz', timeout=2)); raise SystemExit(0 if data.get('status') == 'ok' else 1)\""]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 5s

  nginx:
    image: {{NGINX_IMAGE}}
    container_name: swift_nginx
    user: "101:101"
    ports:
      - "{{NGINX_PORT}}:8080"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - nginx_logs:/var/log/nginx
    networks:
      - {{NETWORK}}
    restart: {{RESTART_POLICY}}
    depends_on:
      app:
        condition: service_healthy
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true

  opa:
    image: openpolicyagent/opa:latest
    container_name: swift_opa
    command: ["run", "--server", "--addr=0.0.0.0:8181", "/policies"]
    volumes:
      - ./policies:/policies
    ports:
      - "127.0.0.1:8181:8181"
    networks:
      - {{NETWORK}}
    restart: {{RESTART_POLICY}}

networks:
  {{NETWORK}}:
    driver: {{DRIVER}}

volumes:
  nginx_logs: