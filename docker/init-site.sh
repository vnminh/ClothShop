#!/bin/bash
# Chạy một lần mỗi lần `docker compose up`: tạo site nếu chưa có, migrate, chạy setup nghiệp vụ.
set -euo pipefail
cd /home/frappe/frappe-bench

SITE="${SITE_NAME:-clothshop.localhost}"

wait-for-it -t 180 db:3306
wait-for-it -t 60 redis-cache:6379
wait-for-it -t 60 redis-queue:6379

# chờ configurator ghi xong common_site_config.json
for i in $(seq 1 60); do
  if grep -q '"redis_queue"' sites/common_site_config.json 2>/dev/null; then break; fi
  echo "Đang chờ common_site_config.json..."; sleep 2
done

printf 'frappe\nerpnext\npayments\nwebshop\nomni_retail\n' > sites/apps.txt
# container này không chạy entrypoint gốc -> tự trỏ sites/assets về assets đã build trong image
rm -rf sites/assets && ln -s /home/frappe/frappe-bench/assets sites/assets

MARKER="sites/${SITE}/.omni_installed"
if [ ! -f "${MARKER}" ]; then
  FORCE=""
  if [ -d "sites/${SITE}" ]; then
    echo ">>> Phát hiện site tạo dở, tạo lại từ đầu"
    FORCE="--force"
  fi
  echo ">>> Tạo site ${SITE}"
  bench new-site "${SITE}" ${FORCE} \
    --mariadb-user-host-login-scope='%' \
    --admin-password "${ADMIN_PASSWORD:-admin}" \
    --db-root-username root \
    --db-root-password "${DB_ROOT_PASSWORD:-admin}" \
    --install-app erpnext \
    --install-app payments \
    --install-app webshop \
    --install-app omni_retail \
    --set-default
  touch "${MARKER}"
else
  echo ">>> Site đã tồn tại, chạy migrate"
  bench --site "${SITE}" migrate
fi

# Email gửi ra (mặc định: Mailpit trong compose)
bench --site "${SITE}" set-config omni_mail_server "${MAIL_SERVER:-mailpit}"
bench --site "${SITE}" set-config -p omni_mail_port "${MAIL_PORT:-1025}"
bench --site "${SITE}" set-config omni_mail_from "${MAIL_FROM:-noreply@clothshop.local}"
bench --site "${SITE}" set-config host_name "${HOST_NAME:-http://clothshop.localhost:8080}"

# AI (OpenRouter / DeepSeek)
if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  bench --site "${SITE}" set-config openrouter_api_key "${OPENROUTER_API_KEY}"
fi
bench --site "${SITE}" set-config openrouter_model "${OPENROUTER_MODEL:-deepseek/deepseek-chat}"

echo ">>> Thiết lập nghiệp vụ (idempotent)"
bench --site "${SITE}" execute omni_retail.setup.install.setup_all

if [ "${SEED_DEMO:-0}" = "1" ]; then
  echo ">>> Nạp dữ liệu demo"
  bench --site "${SITE}" execute omni_retail.setup.demo.seed
fi

bench --site "${SITE}" enable-scheduler
bench --site "${SITE}" clear-cache
echo ">>> Hoàn tất. Mở http://${SITE}:${HTTP_PORT:-8080}"
