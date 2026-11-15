SITE ?= clothshop.localhost
BENCH = docker compose exec backend bench --site $(SITE)

.PHONY: up down logs init seed-demo forecast test migrate restart shell clean image push

up:            ## Build và chạy toàn bộ hệ thống
	docker compose up -d --build

down:          ## Dừng hệ thống (giữ dữ liệu)
	docker compose down

logs:          ## Xem tiến trình khởi tạo site
	docker compose logs -f create-site

seed-demo:     ## Nạp dữ liệu demo (chạy lại an toàn)
	$(BENCH) execute omni_retail.setup.demo.seed

forecast:      ## Chạy AI dự báo + lập kế hoạch mua hàng ngay
	$(BENCH) execute omni_retail.forecasting.planner.run

test:          ## Unit test của omni_retail
	$(BENCH) set-config allow_tests true
	$(BENCH) run-tests --module omni_retail.tests.test_pure

migrate:       ## Áp dụng thay đổi DocType/custom field sau khi sửa code
	$(BENCH) migrate
	docker compose restart backend queue-short queue-long scheduler

restart:       ## Nạp lại code Python
	docker compose restart backend queue-short queue-long scheduler

shell:
	docker compose exec backend bash

clean:         ## XÓA toàn bộ dữ liệu (database, site)
	docker compose down -v

IMAGE ?= leevox/clothshop-omni
TAG ?= v15
REPO_URL ?= https://github.com/vnminh/ClothShop.git

image:         ## Build image từ commit mới nhất trên GitHub (nhánh main)
	$(eval SHA := $(shell git ls-remote $(REPO_URL) refs/heads/main | cut -c1-40))
	docker build --build-arg REPO_URL=$(REPO_URL) --build-arg REPO_REF=$(SHA) \
		-t $(IMAGE):$(TAG) -t $(IMAGE):latest -t $(IMAGE):$(shell echo $(SHA) | cut -c1-7) docker

push: image    ## Build rồi đẩy image lên Docker Hub
	docker push $(IMAGE):$(TAG)
	docker push $(IMAGE):latest
	docker push $(IMAGE):$(shell git ls-remote $(REPO_URL) refs/heads/main | cut -c1-7)
