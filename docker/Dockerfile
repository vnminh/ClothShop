# ERPNext v15 + Webshop + custom app omni_retail.
# Mã nguồn omni_retail và script khởi tạo được clone từ GitHub (không copy từ máy build),
# nên image luôn khớp với một commit cụ thể của repo.
FROM frappe/erpnext:version-15

USER frappe
WORKDIR /home/frappe/frappe-bench

# Storefront (kênh online). Webshop yêu cầu app payments.
RUN bench get-app --branch version-15 --skip-assets payments https://github.com/frappe/payments \
    && bench get-app --branch version-15 --skip-assets webshop https://github.com/frappe/webshop

ARG REPO_URL=https://github.com/vnminh/ClothShop.git
# nhánh, tag hoặc mã commit; truyền mã commit để Docker không dùng lại cache của lần clone trước
ARG REPO_REF=main

RUN git init -q /tmp/src \
    && git -C /tmp/src remote add origin "${REPO_URL}" \
    && git -C /tmp/src fetch -q --depth 1 origin "${REPO_REF}" \
    && git -C /tmp/src checkout -q FETCH_HEAD \
    && git -C /tmp/src rev-parse HEAD > /home/frappe/frappe-bench/CLOTHSHOP_COMMIT \
    && cp -r /tmp/src/apps/omni_retail apps/omni_retail \
    && cp /tmp/src/docker/init-site.sh /home/frappe/init-site.sh \
    && rm -rf /tmp/src

USER root
RUN install -m 755 /home/frappe/init-site.sh /usr/local/bin/init-site.sh && rm /home/frappe/init-site.sh
USER frappe

# Image gốc giữ assets đã build ở /home/frappe/frappe-bench/assets và entrypoint sẽ trỏ
# sites/assets về đó mỗi lần container khởi động -> phải build assets của app mới vào đúng chỗ này.
RUN ./env/bin/pip install --no-cache-dir -e apps/omni_retail \
    && printf 'frappe\nerpnext\npayments\nwebshop\nomni_retail\n' > sites/apps.txt \
    && rm -rf sites/assets && ln -s /home/frappe/frappe-bench/assets sites/assets \
    && bench build --production --app payments \
    && bench build --production --app webshop \
    && ln -sfn /home/frappe/frappe-bench/apps/omni_retail/omni_retail/public assets/omni_retail

LABEL org.opencontainers.image.source="https://github.com/vnminh/ClothShop" \
      org.opencontainers.image.title="ClothShop Omnichannel Retail (ERPNext v15)"
