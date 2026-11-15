app_name = "omni_retail"
app_title = "Omni Retail"
app_publisher = "ClothShop"
app_description = "Omnichannel Retail & Supply Chain on ERPNext"
app_email = "admin@clothshop.local"
app_license = "MIT"

required_apps = ["erpnext", "webshop"]

after_install = "omni_retail.setup.install.after_install"
after_migrate = "omni_retail.setup.install.after_migrate"

# Desk
doctype_js = {
	"Sales Order": "public/js/sales_order.js",
}

# Website (Webshop): checkout mở rộng + theo dõi đơn
web_include_js = ["/assets/omni_retail/js/omni_web.js"]
web_include_css = ["/assets/omni_retail/css/omni_web.css"]

doc_events = {
	"Sales Order": {
		"before_validate": "omni_retail.orders.events.sales_order_before_validate",
		"on_submit": "omni_retail.orders.events.sales_order_on_submit",
	},
}

scheduler_events = {
	"daily": [
		"omni_retail.orders.tasks.expire_pickup_orders",
		"omni_retail.forecasting.tasks.scheduled_run",
	],
}

permission_query_conditions = {
	"Customer": "omni_retail.permissions.customer_query_conditions",
}
has_permission = {
	"Customer": "omni_retail.permissions.customer_has_permission",
}
