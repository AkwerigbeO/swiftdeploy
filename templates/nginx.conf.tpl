events {}

pid /tmp/nginx.pid;

http {
    resolver 127.0.0.11 ipv6=off valid=10s;
    client_body_temp_path /tmp/client_temp;
    proxy_temp_path /tmp/proxy_temp;
    fastcgi_temp_path /tmp/fastcgi_temp;
    uwsgi_temp_path /tmp/uwsgi_temp;
    scgi_temp_path /tmp/scgi_temp;

    log_format swiftdeploy '$time_iso8601 | $status | ${request_time}s | $upstream_addr | $request';

    access_log /var/log/nginx/access.log swiftdeploy;

    server {
        listen 8080;

        proxy_connect_timeout {{PROXY_TIMEOUT}};
        proxy_send_timeout {{PROXY_TIMEOUT}};
        proxy_read_timeout {{PROXY_TIMEOUT}};
        send_timeout {{PROXY_TIMEOUT}};

        add_header X-Deployed-By "swiftdeploy" always;

        location / {
            set $service_upstream http://app:{{APP_PORT}};
            proxy_pass $service_upstream;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_pass_header X-Mode;
        }

        error_page 502 = /502.json;
        error_page 503 = /503.json;
        error_page 504 = /504.json;

        location = /502.json {
            internal;
            default_type application/json;
            return 502 '{"error":"bad gateway","code":502,"service":"swiftdeploy-api","contact":"{{CONTACT}}"}';
        }

        location = /503.json {
            internal;
            default_type application/json;
            return 503 '{"error":"service unavailable","code":503,"service":"swiftdeploy-api","contact":"{{CONTACT}}"}';
        }

        location = /504.json {
            internal;
            default_type application/json;
            return 504 '{"error":"gateway timeout","code":504,"service":"swiftdeploy-api","contact":"{{CONTACT}}"}';
        }
    }
}
