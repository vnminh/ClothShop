"""Thiết lập hệ thống. Mọi hàm đều idempotent: chạy lại nhiều lần không sinh trùng dữ liệu."""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, getdate

from omni_retail.constants import (
	ALL_STATUSES,
	DELIVERY_HOME,
	DELIVERY_PICKUP,
	PAY_COD,
	PAY_TRANSFER,
	ROLE_SALES_STAFF,
	ROLE_SHIPPER,
	ROLE_STORE_MANAGER,
	ROLE_WAREHOUSE_MANAGER,
)
from omni_retail.setup import masters

COMPANY_NAME = "ClothShop"
COMPANY_ABBR = "CS"

ROLE_PROFILES = {
	ROLE_STORE_MANAGER: [ROLE_STORE_MANAGER, "Sales Manager", "Sales User", "Stock User", "Accounts User", "Item Manager"],
	ROLE_WAREHOUSE_MANAGER: [ROLE_WAREHOUSE_MANAGER, "Stock Manager", "Stock User", "Purchase Manager", "Purchase User", "Item Manager"],
	ROLE_SALES_STAFF: [ROLE_SALES_STAFF, "Sales User"],
	ROLE_SHIPPER: [ROLE_SHIPPER],
}


def after_install():
	ensure_base()


def after_migrate():
	ensure_base()


def ensure_base():
	ensure_roles()
	ensure_custom_fields()


def setup_all():
	"""Gọi từ docker/init-site.sh sau khi cài app."""
	ensure_base()
	ensure_company()
	ensure_fiscal_years()
	ensure_payment_modes()
	central = masters.ensure_warehouse("Kho trung tâm")
	masters.store_group_warehouse()
	ensure_settings(central)
	ensure_item_attributes()
	ensure_webshop()
	ensure_loyalty_program()
	ensure_seasonal_events()
	ensure_role_profiles()
	ensure_permissions()
	ensure_workspaces()
	ensure_email_account()
	ensure_language()
	frappe.db.commit()
	frappe.clear_cache()


# ----------------------------------------------------------------------------
def ensure_roles():
	for role in (ROLE_STORE_MANAGER, ROLE_WAREHOUSE_MANAGER, ROLE_SALES_STAFF):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
	if not frappe.db.exists("Role", ROLE_SHIPPER):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE_SHIPPER, "desk_access": 0}).insert(ignore_permissions=True)
	frappe.db.set_value("Role", ROLE_SHIPPER, {"desk_access": 0, "home_page": "/shipper"})


def ensure_custom_fields():
	ro = {"read_only": 1, "no_copy": 1, "allow_on_submit": 1}
	online = "eval:doc.omni_is_online"
	fields = {
		"Sales Order": [
			dict(fieldname="omni_section", label="Đơn online (Omnichannel)", fieldtype="Section Break", insert_after="amended_from"),
			dict(fieldname="omni_is_online", label="Là đơn online", fieldtype="Check", insert_after="omni_section", in_standard_filter=1),
			dict(fieldname="omni_status", label="Trạng thái xử lý", fieldtype="Select", options="\n" + "\n".join(ALL_STATUSES),
				insert_after="omni_is_online", in_list_view=1, in_standard_filter=1, depends_on=online, **ro),
			dict(fieldname="omni_delivery_method", label="Hình thức nhận hàng", fieldtype="Select",
				options="\n".join(["", DELIVERY_HOME, DELIVERY_PICKUP]), insert_after="omni_status", depends_on=online, in_standard_filter=1),
			dict(fieldname="omni_pickup_store", label="Nhận tại điểm bán", fieldtype="Link", options="Retail Store",
				insert_after="omni_delivery_method", depends_on=f"eval:doc.omni_delivery_method=='{DELIVERY_PICKUP}'", in_standard_filter=1),
			dict(fieldname="omni_cb1", fieldtype="Column Break", insert_after="omni_pickup_store"),
			dict(fieldname="omni_payment_method", label="Hình thức thanh toán", fieldtype="Select",
				options="\n".join(["", PAY_COD, PAY_TRANSFER]), insert_after="omni_cb1", depends_on=online),
			dict(fieldname="omni_payment_confirmed", label="Đã nhận thanh toán", fieldtype="Check", insert_after="omni_payment_method", depends_on=online, **ro),
			dict(fieldname="omni_refund_required", label="Cần hoàn tiền cho khách", fieldtype="Check", insert_after="omni_payment_confirmed", depends_on=online, **ro),
			dict(fieldname="omni_handled_by", label="Nhân viên tiếp nhận", fieldtype="Link", options="User", insert_after="omni_refund_required", depends_on=online, **ro),
			dict(fieldname="omni_cb2", fieldtype="Column Break", insert_after="omni_handled_by"),
			dict(fieldname="omni_shipper", label="Shipper", fieldtype="Link", options="User", insert_after="omni_cb2", depends_on=online, **ro),
			dict(fieldname="omni_delivery_attempts", label="Số lần giao", fieldtype="Int", insert_after="omni_shipper", depends_on=online, **ro),
			dict(fieldname="omni_ready_at", label="Sẵn sàng lúc", fieldtype="Datetime", insert_after="omni_delivery_attempts", depends_on=online, **ro),
			dict(fieldname="omni_delivered_at", label="Hoàn tất lúc", fieldtype="Datetime", insert_after="omni_ready_at", depends_on=online, **ro),
		],
		"Quotation": [
			dict(fieldname="omni_delivery_method", label="Hình thức nhận hàng", fieldtype="Select",
				options="\n".join(["", DELIVERY_HOME, DELIVERY_PICKUP]), insert_after="order_type", allow_on_submit=1),
			dict(fieldname="omni_pickup_store", label="Nhận tại điểm bán", fieldtype="Link", options="Retail Store",
				insert_after="omni_delivery_method", allow_on_submit=1),
			dict(fieldname="omni_payment_method", label="Hình thức thanh toán", fieldtype="Select",
				options="\n".join(["", PAY_COD, PAY_TRANSFER]), insert_after="omni_pickup_store", allow_on_submit=1),
		],
		"Supplier": [
			dict(fieldname="omni_order_email", label="Email nhận đơn đặt hàng", fieldtype="Data", options="Email", insert_after="supplier_name"),
		],
		"Purchase Order": [
			dict(fieldname="omni_purchase_plan", label="Kế hoạch mua hàng (AI)", fieldtype="Link", options="Purchase Plan",
				insert_after="supplier", read_only=1, no_copy=1, in_standard_filter=1),
		],
	}
	create_custom_fields(fields, update=True)


def ensure_company():
	if frappe.db.count("Company"):
		return
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	year = getdate().year
	frappe.flags.mute_emails = True
	result = setup_complete(
		{
			"currency": "VND",
			"full_name": "Quản trị hệ thống",
			"company_name": COMPANY_NAME,
			"timezone": "Asia/Ho_Chi_Minh",
			"company_abbr": COMPANY_ABBR,
			"industry": "Retail",
			"country": "Vietnam",
			"fy_start_date": f"{year}-01-01",
			"fy_end_date": f"{year}-12-31",
			"language": "english",
			"company_tagline": "Thời trang đa kênh",
			"email": "admin@clothshop.local",
			"password": "admin",
			"chart_of_accounts": "Standard",
		}
	)
	if not frappe.db.count("Company"):
		frappe.throw(f"Setup wizard thất bại: {result}")
	frappe.db.commit()


def ensure_fiscal_years():
	year = getdate().year
	for y in (year - 2, year - 1, year, year + 1):
		if frappe.db.exists("Fiscal Year", {"year_start_date": f"{y}-01-01"}):
			continue
		frappe.get_doc(
			{"doctype": "Fiscal Year", "year": str(y), "year_start_date": f"{y}-01-01", "year_end_date": f"{y}-12-31"}
		).insert(ignore_permissions=True)


def ensure_payment_modes():
	c = masters.company()
	comp = frappe.get_doc("Company", c)
	cash_account = comp.default_cash_account or frappe.db.get_value(
		"Account", {"company": c, "account_type": "Cash", "is_group": 0}, "name"
	)
	bank_account = comp.default_bank_account or frappe.db.get_value(
		"Account", {"company": c, "account_type": "Bank", "is_group": 0}, "name"
	)
	if not bank_account:
		parent = frappe.db.get_value("Account", {"company": c, "account_type": "Bank", "is_group": 1}, "name")
		bank_account = (
			frappe.get_doc(
				{
					"doctype": "Account",
					"account_name": "Tài khoản ngân hàng",
					"parent_account": parent,
					"company": c,
					"account_type": "Bank",
					"is_group": 0,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	if not comp.default_bank_account:
		frappe.db.set_value("Company", c, "default_bank_account", bank_account)

	for name, typ, account in (("Tiền mặt", "Cash", cash_account), ("Chuyển khoản", "Bank", bank_account)):
		if not frappe.db.exists("Mode of Payment", name):
			frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": name, "type": typ, "enabled": 1}).insert(
				ignore_permissions=True
			)
		mop = frappe.get_doc("Mode of Payment", name)
		if not any(a.company == c for a in mop.accounts):
			mop.append("accounts", {"company": c, "default_account": account})
			mop.save(ignore_permissions=True)


def _set_single(doctype, values):
	doc = frappe.get_single(doctype)
	changed = False
	for k, v in values.items():
		if doc.meta.has_field(k) and doc.get(k) != v:
			doc.set(k, v)
			changed = True
	if changed:
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)


def ensure_settings(central):
	_set_single(
		"Stock Settings",
		{
			"default_warehouse": central,
			"allow_negative_stock": 0,
			"enable_stock_reservation": 1,
			"auto_reserve_serial_and_batch": 1,
			"pick_serial_and_batch_based_on": "FIFO",
			"auto_create_serial_and_batch_bundle_for_outward": 1,
		},
	)
	_set_single("Accounts Settings", {"unlink_advance_payment_on_cancelation_of_order": 1})

	s = frappe.get_single("Omni Retail Settings")
	defaults = {
		"central_warehouse": central,
		"cod_mode_of_payment": "Tiền mặt",
		"transfer_mode_of_payment": "Chuyển khoản",
		"bank_transfer_info": "Ngân hàng ABC - STK 0123 456 789 - CTK: CONG TY CLOTHSHOP. Nội dung: mã đơn hàng.",
		"pickup_expiry_days": 5,
		"return_window_days": 7,
		"ai_enabled": 1,
		"ai_model": frappe.conf.get("openrouter_model") or "deepseek/deepseek-chat",
		"ai_base_url": "https://openrouter.ai/api/v1",
		"schedule": "Hằng tuần (thứ Hai)",
		"min_ai_factor": 0.3,
		"max_ai_factor": 3,
		"history_weeks": 78,
		"cover_days": 30,
		"safety_days": 7,
		"default_lead_time_days": 7,
	}
	changed = False
	for k, v in defaults.items():
		if not s.get(k):
			s.set(k, v)
			changed = True
	if changed:
		s.save(ignore_permissions=True)


def ensure_item_attributes():
	specs = {
		"Kích cỡ": [("S", "S"), ("M", "M"), ("L", "L"), ("XL", "XL")],
		"Màu": [("Đen", "DEN"), ("Trắng", "TRG"), ("Xanh navy", "NVY"), ("Be", "BE"), ("Đỏ", "DO"), ("Xám", "XAM")],
	}
	for attr, values in specs.items():
		if frappe.db.exists("Item Attribute", attr):
			doc = frappe.get_doc("Item Attribute", attr)
		else:
			doc = frappe.get_doc({"doctype": "Item Attribute", "attribute_name": attr})
		existing = {v.attribute_value for v in doc.item_attribute_values}
		abbrs = {v.abbr for v in doc.item_attribute_values}
		added = False
		for value, ab in values:
			if value not in existing and ab not in abbrs:
				doc.append("item_attribute_values", {"attribute_value": value, "abbr": ab})
				added = True
		if added or doc.is_new():
			doc.save(ignore_permissions=True)


def ensure_checkout_gateway():
	"""Webshop chỉ bật nút Đặt hàng khi có Payment Gateway Account. Hệ thống không dùng cổng thanh toán
	(COD / chuyển khoản xác nhận tay) nên khai báo một gateway hình thức."""
	c = masters.company()
	gateway = "COD - Chuyển khoản"
	if not frappe.db.exists("Payment Gateway", gateway):
		frappe.get_doc({"doctype": "Payment Gateway", "gateway": gateway}).insert(ignore_permissions=True)
	name = frappe.db.get_value("Payment Gateway Account", {"payment_gateway": gateway}, "name")
	if not name:
		account = frappe.get_cached_value("Company", c, "default_bank_account") or frappe.db.get_value(
			"Account", {"company": c, "account_type": "Bank", "is_group": 0}, "name"
		)
		name = (
			frappe.get_doc(
				{
					"doctype": "Payment Gateway Account",
					"payment_gateway": gateway,
					"payment_account": account,
					"currency": frappe.get_cached_value("Company", c, "default_currency"),
					"is_default": 1,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	return name


def ensure_webshop():
	c = masters.company()
	gateway_account = ensure_checkout_gateway()
	values = {
		"enabled": 1,
		"company": c,
		"price_list": masters.selling_price_list(),
		"default_customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
		"quotation_series": "SAL-QTN-.YYYY.-",
		"payment_gateway_account": gateway_account,
		"enable_checkout": 1,
		"payment_success_url": "Orders",
		"show_price": 1,
		"show_stock_availability": 1,
		"show_quantity_in_website": 0,
		"enable_variants": 1,
		"allow_items_not_in_stock": 0,
		"show_apply_coupon_code_in_website": 1,
		"enable_wishlist": 1,
		"products_per_page": 12,
	}
	_set_single("Webshop Settings", values)
	_set_single("Website Settings", {"home_page": "all-products", "app_name": COMPANY_NAME})
	_set_single("Portal Settings", {"default_portal_home": "/all-products"})


def ensure_loyalty_program():
	name = "Thành viên ClothShop"
	if frappe.db.exists("Loyalty Program", name):
		return
	c = masters.company()
	comp = frappe.get_cached_doc("Company", c)
	expense = frappe.db.get_value(
		"Account", {"company": c, "root_type": "Expense", "is_group": 0, "account_name": ["like", "%Marketing%"]}, "name"
	) or frappe.db.get_value("Account", {"company": c, "root_type": "Expense", "is_group": 0}, "name")
	frappe.get_doc(
		{
			"doctype": "Loyalty Program",
			"loyalty_program_name": name,
			"loyalty_program_type": "Multiple Tier Program",
			"from_date": f"{getdate().year - 2}-01-01",
			"auto_opt_in": 1,
			"company": c,
			"conversion_factor": 100,  # 1 điểm = 100đ khi đổi
			"expiry_duration": 365,
			"expense_account": expense,
			"cost_center": comp.cost_center,
			"collection_rules": [
				{"tier_name": "Bạc", "collection_factor": 10000, "min_spent": 0},
				{"tier_name": "Vàng", "collection_factor": 8000, "min_spent": 5000000},
				{"tier_name": "Kim cương", "collection_factor": 5000, "min_spent": 20000000},
			],
		}
	).insert(ignore_permissions=True)


def ensure_seasonal_events():
	y = getdate().year
	events = [
		("Mùa đông (miền Bắc lạnh)", "Mùa vụ", f"{y}-11-01", f"{y + 1}-02-15", 1, "Áo khoác, Áo len, Quần dài",
			"Thời tiết lạnh: nhu cầu áo khoác, áo len tăng mạnh; áo thun, quần short, váy giảm."),
		("Mùa hè", "Mùa vụ", f"{y}-04-15", f"{y}-08-31", 1, "Áo thun, Quần short, Váy đầm",
			"Nắng nóng: áo thun, quần short, váy đầm bán chạy; đồ giữ ấm gần như không bán."),
		("Tựu trường", "Sự kiện mua sắm", f"{y}-08-10", f"{y}-09-10", 1, "Áo sơ mi, Quần dài",
			"Học sinh, sinh viên mua sơ mi và quần dài."),
		("Quốc tế Phụ nữ 8/3", "Lễ tết", f"{y}-03-01", f"{y}-03-08", 1, "Váy đầm", "Nhu cầu quà tặng, váy đầm tăng."),
		("Sale 11.11", "Sự kiện mua sắm", f"{y}-11-08", f"{y}-11-12", 1, "", "Ngày hội mua sắm online, đơn online tăng mạnh."),
		("Black Friday", "Sự kiện mua sắm", f"{y}-11-23", f"{y}-11-30", 1, "", "Khuyến mãi lớn toàn ngành, nhu cầu tăng trên mọi dòng hàng."),
		("Giáng sinh & Năm mới", "Lễ tết", f"{y}-12-15", f"{y + 1}-01-02", 1, "Áo len, Áo khoác, Váy đầm", "Mua sắm đi chơi lễ, quà tặng."),
		# Tết âm lịch không trùng ngày dương hằng năm -> khai báo theo từng năm
		("Tết Nguyên đán 2027", "Lễ tết", "2027-01-10", "2027-02-05", 0, "",
			"Mua sắm quần áo mới trước Tết (mùng 1 là 06/02/2027): cao điểm 3-4 tuần trước Tết, sau Tết nhu cầu giảm sâu 2 tuần."),
	]
	for name, typ, start, end, recurring, groups, note in events:
		if frappe.db.exists("Seasonal Event", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Seasonal Event", "event_name": name, "event_type": typ, "from_date": start, "to_date": end,
				"recurring_yearly": recurring, "affected_item_groups": groups, "impact_note": note, "is_active": 1,
			}
		).insert(ignore_permissions=True)


def ensure_role_profiles():
	for name, roles in ROLE_PROFILES.items():
		roles = [r for r in roles if frappe.db.exists("Role", r)]
		if frappe.db.exists("Role Profile", name):
			doc = frappe.get_doc("Role Profile", name)
			if {r.role for r in doc.roles} == set(roles):
				continue
			doc.set("roles", [{"role": r} for r in roles])
		else:
			doc = frappe.get_doc({"doctype": "Role Profile", "role_profile": name, "roles": [{"role": r} for r in roles]})
			doc.name = name
		# Role Profile khóa chứng từ khi xếp hàng cập nhật user; gỡ khóa còn sót từ lần chạy dở
		try:
			doc.unlock()
		except Exception:
			pass
		doc.save(ignore_permissions=True) if frappe.db.exists("Role Profile", name) else doc.insert(ignore_permissions=True)
		frappe.db.commit()


def _grant(doctype, role, rights):
	from frappe.permissions import add_permission, update_permission_property

	if not frappe.db.exists("DocType", doctype):
		return
	if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0}):
		add_permission(doctype, role, 0)
	for right in rights:
		update_permission_property(doctype, role, 0, right, 1, validate=False)


def ensure_permissions():
	full = ("read", "write", "create", "submit", "cancel", "print", "report", "email")
	entry = ("read", "write", "create", "submit", "print", "report")
	read = ("read", "print", "report")
	# bán tại quầy
	# POS trừ kho theo lô -> người bán cần quyền tạo Serial and Batch Bundle
	for dt in ("POS Invoice", "POS Opening Entry", "POS Closing Entry", "Serial and Batch Bundle"):
		_grant(dt, ROLE_SALES_STAFF, entry)
		_grant(dt, ROLE_STORE_MANAGER, full)
	for dt in ("POS Profile", "Mode of Payment", "Loyalty Program", "Pricing Rule", "Coupon Code", "Sales Invoice",
			"Delivery Note", "Payment Entry", "Batch", "Warehouse", "Item Price", "Price List", "Company"):
		_grant(dt, ROLE_SALES_STAFF, read)
	# khuyến mãi do quản lý điểm bán phụ trách
	for dt in ("Pricing Rule", "Promotional Scheme", "Coupon Code", "Loyalty Program"):
		_grant(dt, ROLE_STORE_MANAGER, ("read", "write", "create", "delete", "print", "report"))
	_grant("Material Request", ROLE_STORE_MANAGER, entry)
	_grant("Material Request", ROLE_SALES_STAFF, read)
	# khách trên Webshop: chỉ đọc hồ sơ của chính mình (giới hạn trong omni_retail/permissions.py)
	if frappe.db.exists("Role", "Customer"):
		_grant("Customer", "Customer", ("read",))


def _workspace(name, icon, roles, shortcuts, cards):
	"""shortcuts: [(label, type, link_to, extra)]; cards: [(card label, [(label, link_type, link_to)])]"""
	content = [{"id": frappe.generate_hash(length=10), "type": "header", "data": {"text": f'<span class="h4"><b>{name}</b></span>', "col": 12}}]
	sc_rows, link_rows = [], []
	for label, typ, link_to, extra in shortcuts:
		if typ == "DocType" and not frappe.db.exists("DocType", link_to):
			continue
		row = {"label": label, "type": typ, "link_to": link_to, "color": "Grey"}
		row.update(extra or {})
		sc_rows.append(row)
		content.append({"id": frappe.generate_hash(length=10), "type": "shortcut", "data": {"shortcut_name": label, "col": 3}})
	content.append({"id": frappe.generate_hash(length=10), "type": "spacer", "data": {"col": 12}})
	for card, links in cards:
		links = [l for l in links if frappe.db.exists(l[1], l[2])]
		if not links:
			continue
		link_rows.append({"type": "Card Break", "label": card, "link_count": len(links)})
		for label, link_type, link_to in links:
			link_rows.append({"type": "Link", "label": label, "link_type": link_type, "link_to": link_to})
		content.append({"id": frappe.generate_hash(length=10), "type": "card", "data": {"card_name": card, "col": 4}})

	exists = frappe.db.exists("Workspace", name)
	if exists:
		doc = frappe.get_doc("Workspace", name)
	else:
		doc = frappe.get_doc({"doctype": "Workspace", "label": name, "title": name, "name": name})
	doc.update({"module": "Omni Retail", "icon": icon, "public": 1, "is_hidden": 0, "content": json.dumps(content, ensure_ascii=False)})
	doc.set("roles", [{"role": r} for r in roles])
	doc.set("shortcuts", sc_rows)
	doc.set("links", link_rows)
	doc.flags.ignore_links = True
	doc.save(ignore_permissions=True) if exists else doc.insert(ignore_permissions=True)


def ensure_workspaces():
	from omni_retail.constants import PENDING, PROCESSING, READY_PICKUP

	def so_filter(status):
		return {"stats_filter": json.dumps({"omni_is_online": 1, "omni_status": status, "docstatus": 1}, ensure_ascii=False)}

	_workspace(
		"Điểm bán lẻ", "retail", [ROLE_STORE_MANAGER, ROLE_SALES_STAFF, "System Manager"],
		[
			("Bán tại quầy (POS)", "Page", "point-of-sale", None),
			("Đơn chờ xác nhận", "DocType", "Sales Order", so_filter(PENDING)),
			("Đơn đang xử lý", "DocType", "Sales Order", so_filter(PROCESSING)),
			("Đơn chờ khách đến nhận", "DocType", "Sales Order", so_filter(READY_PICKUP)),
			("Khách hàng", "DocType", "Customer", None),
			("Yêu cầu chuyển hàng từ kho", "DocType", "Material Request", None),
			("Chương trình khuyến mãi", "DocType", "Promotional Scheme", None),
			("Mã coupon", "DocType", "Coupon Code", None),
		],
		[
			("Bán hàng", [("Đơn hàng", "DocType", "Sales Order"), ("Hóa đơn POS", "DocType", "POS Invoice"),
				("Mở ca POS", "DocType", "POS Opening Entry"), ("Đóng ca POS", "DocType", "POS Closing Entry"),
				("Khách hàng", "DocType", "Customer")]),
			("Ưu đãi", [("Chương trình khuyến mãi", "DocType", "Promotional Scheme"), ("Quy tắc giá", "DocType", "Pricing Rule"),
				("Mã coupon", "DocType", "Coupon Code"), ("Chương trình tích điểm", "DocType", "Loyalty Program")]),
			("Điểm bán & tồn kho", [("Điểm bán lẻ", "DocType", "Retail Store"), ("Tồn kho", "Report", "Stock Balance"),
				("Yêu cầu chuyển hàng", "DocType", "Material Request"), ("Doanh số theo sản phẩm", "Report", "Item-wise Sales Register")]),
		],
	)
	_workspace(
		"Kho & Mua hàng", "stock", [ROLE_WAREHOUSE_MANAGER, "System Manager"],
		[
			("Kế hoạch mua hàng (AI)", "DocType", "Purchase Plan", None),
			("Đơn nhập hàng (PO)", "DocType", "Purchase Order", None),
			("Phiếu nhập kho", "DocType", "Purchase Receipt", None),
			("Phiếu xuất/chuyển kho", "DocType", "Stock Entry", None),
			("Yêu cầu chuyển hàng", "DocType", "Material Request", None),
			("Sản phẩm", "DocType", "Item", None),
			("Lô sản phẩm", "DocType", "Batch", None),
			("Nhà cung cấp", "DocType", "Supplier", None),
		],
		[
			("Hàng hóa", [("Sản phẩm", "DocType", "Item"), ("Dòng sản phẩm", "DocType", "Item Group"),
				("Lô sản phẩm", "DocType", "Batch"), ("Bảng giá", "DocType", "Item Price")]),
			("Nhập - xuất kho", [("Đơn nhập hàng", "DocType", "Purchase Order"), ("Phiếu nhập kho", "DocType", "Purchase Receipt"),
				("Phiếu xuất/chuyển kho", "DocType", "Stock Entry"), ("Phiếu giao hàng", "DocType", "Delivery Note"),
				("Kho", "DocType", "Warehouse"), ("Tồn kho", "Report", "Stock Balance"), ("Sổ kho", "Report", "Stock Ledger")]),
			("AI dự báo & mua hàng", [("Kế hoạch mua hàng", "DocType", "Purchase Plan"), ("Sự kiện / mùa vụ", "DocType", "Seasonal Event"),
				("Nhà cung cấp", "DocType", "Supplier"), ("Cấu hình Omni Retail", "DocType", "Omni Retail Settings")]),
		],
	)


def ensure_language():
	_set_single("System Settings", {"language": "vi", "time_zone": "Asia/Ho_Chi_Minh", "enable_onboarding": 0})
	frappe.db.set_value("User", "Administrator", "language", "vi")


def ensure_email_account():
	"""Tài khoản email gửi đi mặc định (dev: Mailpit, không cần xác thực). Đổi sang SMTP thật trong Email Account."""
	if frappe.db.exists("Email Account", {"default_outgoing": 1, "enable_outgoing": 1}):
		return
	frappe.get_doc(
		{
			"doctype": "Email Account",
			"email_account_name": "Hệ thống ClothShop",
			"email_id": frappe.conf.get("omni_mail_from") or "noreply@clothshop.local",
			"enable_outgoing": 1,
			"default_outgoing": 1,
			"enable_incoming": 0,
			"smtp_server": frappe.conf.get("omni_mail_server") or "mailpit",
			"smtp_port": cint(frappe.conf.get("omni_mail_port")) or 1025,
			"no_smtp_authentication": 1,
			"use_tls": 0,
			"use_ssl_for_outgoing": 0,
			"always_use_account_email_id_as_sender": 1,
		}
	).insert(ignore_permissions=True)
