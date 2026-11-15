"""Dữ liệu demo: điểm bán, NCC, sản phẩm thời trang có biến thể, tồn theo lô, lịch sử bán 18 tháng,
khuyến mãi, tài khoản cho từng actor. Idempotent: chạy lại sẽ bỏ qua phần đã có.

Chạy: bench --site <site> execute omni_retail.setup.demo.seed
"""

import math
import random

import frappe
from frappe.utils import add_days, flt, getdate, nowdate

from omni_retail.constants import (
	DELIVERY_HOME,
	DELIVERY_PICKUP,
	PAY_COD,
	PAY_TRANSFER,
	PROCESSING,
	READY_PICKUP,
	READY_SHIP,
	ROLE_SALES_STAFF,
	ROLE_SHIPPER,
	ROLE_STORE_MANAGER,
	ROLE_WAREHOUSE_MANAGER,
)
from omni_retail.setup import masters
from omni_retail.setup.install import ROLE_PROFILES

PASSWORD = "ClothShop@2026"
HISTORY_WEEKS = 78
HISTORY_TAG = "DEMO-HISTORY"

STORES = [
	("ClothShop Quận 1", "12 Lê Lợi, P. Bến Nghé, Quận 1, TP. Hồ Chí Minh", "028 3822 0001"),
	("ClothShop Cầu Giấy", "88 Xuân Thủy, Q. Cầu Giấy, Hà Nội", "024 3766 0002"),
	("ClothShop Hải Châu", "45 Nguyễn Văn Linh, Q. Hải Châu, Đà Nẵng", "0236 365 0003"),
]

SUPPLIERS = {
	"Xưởng may An Phát": ("donhang@anphat.example", 7),
	"Dệt kim Hòa Bình": ("sales@hoabinhknit.example", 14),
	"Denim Sài Gòn": ("order@denimsg.example", 10),
}

GROUPS = ["Áo thun", "Áo sơ mi", "Áo khoác", "Áo len", "Quần dài", "Quần short", "Váy đầm"]

# (mã, tên, dòng SP, giá bán, giá vốn, NCC, màu, sức bán cơ sở/tuần/SKU, tồn mỗi SKU tại kho trung tâm)
PRODUCTS = [
	("ATN01", "Áo thun cotton basic", "Áo thun", 199000, 85000, "Xưởng may An Phát", ["Đen", "Trắng"], 5.0, 70),
	("ATN02", "Áo thun oversize in hình", "Áo thun", 259000, 110000, "Xưởng may An Phát", ["Đen", "Be"], 3.5, 60),
	("APL01", "Áo polo pique", "Áo thun", 329000, 150000, "Xưởng may An Phát", ["Xanh navy", "Trắng"], 3.0, 45),
	("ASM01", "Áo sơ mi oxford dài tay", "Áo sơ mi", 399000, 180000, "Xưởng may An Phát", ["Trắng", "Xanh navy"], 3.0, 40),
	("ASM02", "Áo sơ mi linen ngắn tay", "Áo sơ mi", 359000, 160000, "Xưởng may An Phát", ["Be", "Trắng"], 2.5, 40),
	("AKH01", "Áo khoác bomber", "Áo khoác", 699000, 330000, "Dệt kim Hòa Bình", ["Đen", "Xanh navy"], 2.5, 10),
	("AKH02", "Áo khoác phao lông vũ", "Áo khoác", 1190000, 590000, "Dệt kim Hòa Bình", ["Đen", "Đỏ"], 2.0, 6),
	("AKH03", "Áo khoác gió chống nước", "Áo khoác", 549000, 250000, "Dệt kim Hòa Bình", ["Xám", "Xanh navy"], 2.2, 14),
	("ALN01", "Áo len cổ tròn", "Áo len", 459000, 210000, "Dệt kim Hòa Bình", ["Be", "Xám"], 2.5, 8),
	("ALN02", "Áo len cổ lọ", "Áo len", 499000, 230000, "Dệt kim Hòa Bình", ["Đen", "Đỏ"], 2.0, 9),
	("QJN01", "Quần jeans slim fit", "Quần dài", 549000, 260000, "Denim Sài Gòn", ["Xanh navy", "Đen"], 3.2, 35),
	("QKK01", "Quần kaki ống đứng", "Quần dài", 459000, 210000, "Denim Sài Gòn", ["Be", "Xám"], 2.6, 30),
	("QSH01", "Quần short kaki", "Quần short", 289000, 125000, "Denim Sài Gòn", ["Be", "Xanh navy"], 3.0, 65),
	("QSH02", "Quần short thể thao", "Quần short", 229000, 95000, "Xưởng may An Phát", ["Đen", "Xám"], 3.2, 60),
	("VAY01", "Váy đầm suông công sở", "Váy đầm", 599000, 270000, "Denim Sài Gòn", ["Đen", "Be"], 2.2, 28),
	("VAY02", "Váy hoa nhí dáng xòe", "Váy đầm", 529000, 240000, "Denim Sài Gòn", ["Đỏ", "Trắng"], 2.4, 30),
]
SIZES = ["S", "M", "L", "XL"]
SIZE_SHARE = {"S": 0.7, "M": 1.3, "L": 1.2, "XL": 0.8}

# hệ số mùa vụ theo tháng (1..12) cho từng dòng sản phẩm
SEASON = {
	"Áo khoác": [2.2, 1.5, 0.7, 0.3, 0.15, 0.1, 0.1, 0.15, 0.4, 1.0, 2.0, 2.8],
	"Áo len": [2.0, 1.4, 0.6, 0.25, 0.1, 0.1, 0.1, 0.15, 0.4, 1.1, 2.1, 2.6],
	"Áo thun": [0.6, 0.7, 1.0, 1.3, 1.7, 1.9, 1.8, 1.5, 1.1, 0.8, 0.6, 0.5],
	"Quần short": [0.4, 0.5, 0.9, 1.4, 1.9, 2.1, 2.0, 1.6, 1.0, 0.6, 0.4, 0.35],
	"Váy đầm": [1.1, 1.0, 1.5, 1.3, 1.4, 1.4, 1.2, 1.0, 0.9, 0.9, 0.9, 1.2],
	"Áo sơ mi": [1.2, 0.9, 0.9, 1.0, 1.0, 1.0, 1.0, 1.5, 1.4, 1.0, 1.0, 1.1],
	"Quần dài": [1.3, 0.9, 0.9, 0.9, 0.8, 0.8, 0.8, 1.3, 1.3, 1.1, 1.2, 1.3],
}


def log(msg):
	print(f"[demo] {msg}", flush=True)


def seed():
	frappe.flags.mute_emails = True
	random.seed(20261114)
	make_users()
	stores = make_stores()
	make_suppliers()
	make_item_groups()
	skus = make_items()
	frappe.db.commit()
	make_stock(skus, stores)
	frappe.db.commit()
	publish_website_items(skus)
	make_customers()
	frappe.db.commit()
	make_promotions()
	frappe.db.commit()
	make_history(skus)
	frappe.db.commit()
	make_sample_orders(skus, stores)
	frappe.db.commit()
	make_first_plan()
	frappe.clear_cache()
	log("Hoàn tất dữ liệu demo.")


# ----------------------------------------------------------------------------
def make_user(email, full_name, roles, website_only=False):
	if frappe.db.exists("User", email):
		return email
	first, _, last = full_name.partition(" ")
	user = frappe.get_doc(
		{
			"doctype": "User", "email": email, "first_name": first, "last_name": last, "language": "vi",
			"send_welcome_email": 0, "enabled": 1, "new_password": PASSWORD,
			"user_type": "Website User" if website_only else "System User",
		}
	)
	user.flags.no_welcome_mail = True
	user.insert(ignore_permissions=True)
	user.add_roles(*[r for r in roles if frappe.db.exists("Role", r)])
	return email


def make_users():
	make_user("quanly@clothshop.local", "Trần Minh Quản", ROLE_PROFILES[ROLE_STORE_MANAGER])
	make_user("kho@clothshop.local", "Lê Thị Kho", ROLE_PROFILES[ROLE_WAREHOUSE_MANAGER])
	make_user("banhang@clothshop.local", "Phạm Thu Bán", ROLE_PROFILES[ROLE_SALES_STAFF])
	make_user("shipper@clothshop.local", "Võ Văn Giao", [ROLE_SHIPPER], website_only=True)
	make_user("khach@clothshop.local", "Nguyễn Văn An", ["Customer"], website_only=True)
	log("Đã tạo tài khoản demo.")


def make_stores():
	out = []
	for i, (name, address, phone) in enumerate(STORES):
		if not frappe.db.exists("Retail Store", name):
			frappe.get_doc(
				{
					"doctype": "Retail Store", "store_name": name, "address": address, "phone": phone,
					"manager": "quanly@clothshop.local" if i == 0 else None, "allow_pickup": 1, "is_active": 1,
				}
			).insert(ignore_permissions=True)
		store = frappe.get_doc("Retail Store", name)
		if i == 0 and store.pos_profile:
			prof = frappe.get_doc("POS Profile", store.pos_profile)
			users = [u.user for u in prof.applicable_for_users]
			for u in ("quanly@clothshop.local", "banhang@clothshop.local"):
				if u not in users:
					prof.append("applicable_for_users", {"user": u, "default": 1})
			prof.save(ignore_permissions=True)
		out.append(store)
	log(f"Đã tạo {len(out)} điểm bán lẻ.")
	return out


def make_suppliers():
	group = frappe.db.get_value("Supplier Group", {"is_group": 0, "name": "Local"}, "name") or frappe.db.get_value(
		"Supplier Group", {"is_group": 0}, "name"
	)
	for name, (email, _lead) in SUPPLIERS.items():
		if frappe.db.exists("Supplier", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Supplier", "supplier_name": name, "supplier_group": group, "supplier_type": "Company",
				"country": "Vietnam", "omni_order_email": email,
			}
		).insert(ignore_permissions=True)


def make_item_groups():
	root = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ["in", ["", None]]}, "name")
	if not frappe.db.exists("Item Group", "Thời trang"):
		frappe.get_doc(
			{"doctype": "Item Group", "item_group_name": "Thời trang", "parent_item_group": root, "is_group": 1}
		).insert(ignore_permissions=True)
	for g in GROUPS:
		if not frappe.db.exists("Item Group", g):
			frappe.get_doc(
				{"doctype": "Item Group", "item_group_name": g, "parent_item_group": "Thời trang", "is_group": 0}
			).insert(ignore_permissions=True)


def _price(item_code, price_list, rate):
	if not frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list}):
		frappe.get_doc(
			{"doctype": "Item Price", "item_code": item_code, "price_list": price_list, "price_list_rate": rate}
		).insert(ignore_permissions=True)


def make_items():
	"""Trả về list dict SKU: code, template, group, sell, cost, supplier, size, color, base, central_qty."""
	from erpnext.controllers.item_variant import create_variant

	central = frappe.db.get_single_value("Omni Retail Settings", "central_warehouse")
	c = masters.company()
	selling = masters.selling_price_list()
	buying = frappe.db.get_value("Price List", {"buying": 1, "enabled": 1}, "name")
	skus = []
	for code, name, group, sell, cost, supplier, colors, base, central_qty in PRODUCTS:
		lead = SUPPLIERS[supplier][1]
		common = {
			"item_group": group, "stock_uom": "Nos", "is_stock_item": 1, "is_purchase_item": 1, "is_sales_item": 1,
			"has_batch_no": 1, "create_new_batch": 1, "batch_number_series": "LO-.YY.MM.-.#####",
			"lead_time_days": lead, "min_order_qty": 10, "valuation_rate": cost, "standard_rate": sell,
		}
		if not frappe.db.exists("Item", code):
			frappe.get_doc(
				{
					"doctype": "Item", "item_code": code, "item_name": name, "has_variants": 1,
					"variant_based_on": "Item Attribute", "description": name,
					"attributes": [{"attribute": "Kích cỡ"}, {"attribute": "Màu"}],
					"item_defaults": [{"company": c, "default_warehouse": central, "default_supplier": supplier}],
					**{k: v for k, v in common.items() if k != "standard_rate"},
				}
			).insert(ignore_permissions=True)
		for color in colors:
			for size in SIZES:
				existing = frappe.db.sql(
					"""select i.name from `tabItem` i
					join `tabItem Variant Attribute` a on a.parent = i.name and a.attribute = 'Kích cỡ' and a.attribute_value = %s
					join `tabItem Variant Attribute` b on b.parent = i.name and b.attribute = 'Màu' and b.attribute_value = %s
					where i.variant_of = %s""",
					(size, color, code),
				)
				if existing:
					vcode = existing[0][0]
				else:
					variant = create_variant(code, {"Kích cỡ": size, "Màu": color})
					variant.update(common)
					variant.item_name = f"{name} - {color} - {size}"
					variant.description = variant.item_name
					variant.set("item_defaults", [{"company": c, "default_warehouse": central, "default_supplier": supplier}])
					variant.insert(ignore_permissions=True)
					vcode = variant.name
				_price(vcode, selling, sell)
				_price(vcode, buying, cost)
				skus.append(
					dict(code=vcode, template=code, group=group, sell=sell, cost=cost, supplier=supplier,
						size=size, color=color, base=base, central_qty=central_qty, name=f"{name} - {color} - {size}")
				)
	log(f"Đã tạo {len(PRODUCTS)} sản phẩm mẫu, {len(skus)} biến thể (SKU).")
	return skus


def make_stock(skus, stores):
	"""Nhập kho theo lô từ từng NCC (2 đợt để thấy FIFO), rồi chuyển một phần ra các điểm bán."""
	central = frappe.db.get_single_value("Omni Retail Settings", "central_warehouse")
	if frappe.db.exists("Purchase Receipt", {"remarks": ["like", "DEMO-STOCK%"], "docstatus": 1}):
		log("Tồn kho demo đã có, bỏ qua.")
		return
	c = masters.company()
	for supplier in SUPPLIERS:
		lines = [s for s in skus if s["supplier"] == supplier]
		# đợt 1 (cũ): 40% số lượng, đợt 2 (mới): 60% + phần chuyển cho cửa hàng
		for tag, days_ago, share in (("DEMO-STOCK-1", 45, 0.4), ("DEMO-STOCK-2", 12, 0.6)):
			per_store = 6
			pr = frappe.get_doc(
				{
					"doctype": "Purchase Receipt", "supplier": supplier, "company": c, "set_posting_time": 1,
					"posting_date": add_days(nowdate(), -days_ago), "set_warehouse": central, "remarks": tag,
					"items": [
						{
							"item_code": s["code"],
							"qty": math.ceil(s["central_qty"] * share) + (per_store * len(stores) if tag.endswith("2") else 0),
							"rate": s["cost"], "warehouse": central,
						}
						for s in lines
					],
				}
			)
			pr.insert(ignore_permissions=True)
			pr.submit()
		frappe.db.commit()
		log(f"Đã nhập kho 2 lô từ {supplier}.")

	for store in stores:
		se = frappe.get_doc(
			{
				"doctype": "Stock Entry", "stock_entry_type": "Material Transfer", "company": c,
				"from_warehouse": central, "to_warehouse": store.warehouse, "remarks": "DEMO-STOCK chuyển hàng ra điểm bán",
				"items": [
					{"item_code": s["code"], "qty": 6, "s_warehouse": central, "t_warehouse": store.warehouse}
					for s in skus
				],
			}
		)
		se.insert(ignore_permissions=True)
		se.submit()
		frappe.db.commit()
		log(f"Đã chuyển hàng ra {store.name}.")


def publish_website_items(skus):
	from webshop.webshop.doctype.website_item.website_item import make_website_item

	central = frappe.db.get_single_value("Omni Retail Settings", "central_warehouse")
	codes = [p[0] for p in PRODUCTS] + [s["code"] for s in skus]
	n = 0
	for code in codes:
		if frappe.db.exists("Website Item", {"item_code": code}):
			continue
		make_website_item(frappe.get_doc("Item", code), save=True)
		n += 1
	frappe.db.sql("update `tabWebsite Item` set website_warehouse = %s where ifnull(website_warehouse, '') = ''", central)
	log(f"Đã đưa {n} sản phẩm lên Webshop.")


def make_customers():
	group = frappe.db.get_value("Customer Group", {"name": "Individual"}, "name") or frappe.db.get_value(
		"Customer Group", {"is_group": 0}, "name"
	)
	territory = frappe.db.get_value("Territory", {"name": "Vietnam"}, "name") or frappe.db.get_value(
		"Territory", {"is_group": 0}, "name"
	)
	masters.walk_in_customer()
	for name in ("Khách online",):
		if not frappe.db.exists("Customer", name):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": name, "customer_type": "Individual",
					"customer_group": group, "territory": territory}
			).insert(ignore_permissions=True)

	email, cname = "khach@clothshop.local", "Nguyễn Văn An"
	if not frappe.db.exists("Customer", cname):
		frappe.get_doc(
			{"doctype": "Customer", "customer_name": cname, "customer_type": "Individual", "customer_group": group,
				"territory": territory, "loyalty_program": "Thành viên ClothShop"}
		).insert(ignore_permissions=True)
	# Frappe tự tạo Contact khi tạo User -> chỉ cần gắn Contact đó với Customer
	contact_name = frappe.db.get_value("Contact", {"user": email}, "name") or frappe.db.get_value(
		"Contact", {"email_id": email}, "name"
	)
	if contact_name:
		contact = frappe.get_doc("Contact", contact_name)
	else:
		contact = frappe.get_doc(
			{"doctype": "Contact", "first_name": "Nguyễn Văn", "last_name": "An", "user": email,
				"email_ids": [{"email_id": email, "is_primary": 1}]}
		)
	contact.user = email
	if not any(l.link_doctype == "Customer" and l.link_name == cname for l in contact.links):
		contact.append("links", {"link_doctype": "Customer", "link_name": cname})
	if not contact.phone_nos:
		contact.append("phone_nos", {"phone": "0901234567", "is_primary_mobile_no": 1, "is_primary_phone": 1})
	contact.save(ignore_permissions=True)
	if not frappe.db.exists("Dynamic Link", {"parenttype": "Address", "link_doctype": "Customer", "link_name": cname}):
		frappe.get_doc(
			{
				"doctype": "Address", "address_title": cname, "address_type": "Shipping",
				"address_line1": "25 Nguyễn Thị Minh Khai", "city": "Quận 3, TP. Hồ Chí Minh", "country": "Vietnam",
				"phone": "0901234567", "email_id": email, "is_primary_address": 1, "is_shipping_address": 1,
				"links": [{"link_doctype": "Customer", "link_name": cname}],
			}
		).insert(ignore_permissions=True)


def make_promotions():
	c = masters.company()
	today = getdate()

	def attempt(label, fn):
		try:
			fn()
			frappe.db.commit()
			log(f"Khuyến mãi: {label}")
		except Exception as e:
			frappe.db.rollback()
			log(f"KHÔNG tạo được khuyến mãi «{label}»: {e}")

	def winter_sale():
		name = "Ưu đãi mùa đông - Áo khoác giảm 10%"
		if frappe.db.exists("Promotional Scheme", name):
			return
		frappe.get_doc(
			{
				"doctype": "Promotional Scheme", "__newname": name, "apply_on": "Item Group",
				"item_groups": [{"item_group": "Áo khoác"}], "selling": 1, "applicable_for": "",
				"valid_from": add_days(today, -7), "valid_upto": add_days(today, 30), "company": c,
				"price_discount_slabs": [
					{"rule_description": "Giảm 10% áo khoác", "min_qty": 1, "rate_or_discount": "Discount Percentage",
						"discount_percentage": 10}
				],
			}
		).insert(ignore_permissions=True)

	def buy2get1():
		name = "Áo thun - Mua 2 tặng 1"
		if frappe.db.exists("Promotional Scheme", name):
			return
		frappe.get_doc(
			{
				"doctype": "Promotional Scheme", "__newname": name, "apply_on": "Item Group",
				"item_groups": [{"item_group": "Áo thun"}], "selling": 1,
				"valid_from": add_days(today, -7), "valid_upto": add_days(today, 60), "company": c,
				"product_discount_slabs": [
					{"rule_description": "Mua 2 áo thun tặng 1 cùng loại", "min_qty": 2, "same_item": 1, "free_qty": 1}
				],
			}
		).insert(ignore_permissions=True)

	def coupon():
		title = "Coupon CHAOMUNG giảm 50.000đ"
		pr = frappe.db.get_value("Pricing Rule", {"title": title}, "name")
		if not pr:
			pr = (
				frappe.get_doc(
					{
						"doctype": "Pricing Rule", "title": title, "apply_on": "Transaction", "selling": 1,
						"price_or_product_discount": "Price", "coupon_code_based": 1, "min_amt": 500000,
						"rate_or_discount": "Discount Amount", "discount_amount": 50000, "apply_discount_on": "Grand Total",
						"valid_from": add_days(today, -7), "valid_upto": add_days(today, 90), "company": c,
						"currency": frappe.get_cached_value("Company", c, "default_currency"),
					}
				)
				.insert(ignore_permissions=True)
				.name
			)
		if not frappe.db.exists("Coupon Code", {"coupon_code": "CHAOMUNG"}):
			frappe.get_doc(
				{
					"doctype": "Coupon Code", "coupon_name": "Chào mừng khách mới", "coupon_type": "Promotional",
					"coupon_code": "CHAOMUNG", "pricing_rule": pr, "maximum_use": 1000,
					"valid_from": add_days(today, -7), "valid_upto": add_days(today, 90),
				}
			).insert(ignore_permissions=True)

	attempt("Ưu đãi mùa đông áo khoác -10%", winter_sale)
	attempt("Áo thun mua 2 tặng 1", buy2get1)
	attempt("Coupon CHAOMUNG -50.000đ cho đơn từ 500.000đ", coupon)


def _demand_multiplier(group, day):
	"""Mùa vụ theo tháng (nội suy) × sự kiện × xu hướng tăng trưởng."""
	season = SEASON[group]
	m = day.month - 1
	frac = (day.day - 1) / 30.0
	mult = season[m] * (1 - frac) + season[(m + 1) % 12] * frac
	md = (day.month, day.day)
	if (11, 8) <= md <= (11, 14):
		mult *= 1.5  # 11.11
	if (11, 23) <= md <= (11, 30):
		mult *= 1.6  # Black Friday
	if (12, 18) <= md <= (12, 31):
		mult *= 1.25  # Noel
	if (1, 5) <= md <= (2, 5):
		mult *= 1.4  # trước Tết
	return mult


def make_history(skus):
	"""Mỗi tuần một hóa đơn bán hàng tổng hợp (không trừ kho) để làm dữ liệu lịch sử cho AI."""
	if frappe.db.exists("Sales Invoice", {"remarks": ["like", f"{HISTORY_TAG}%"], "docstatus": 1}):
		log("Lịch sử bán hàng demo đã có, bỏ qua.")
		return
	c = masters.company()
	comp = frappe.get_cached_doc("Company", c)
	today = getdate()
	customer = masters.walk_in_customer()
	selling = masters.selling_price_list()
	log(f"Đang tạo {HISTORY_WEEKS} tuần lịch sử bán hàng (mất vài phút)...")
	for w in range(HISTORY_WEEKS, 0, -1):
		day = add_days(today, -7 * w + 3)  # giữa tuần
		growth = 1.0 + 0.18 * (HISTORY_WEEKS - w) / 52.0
		items = []
		for s in skus:
			mean = s["base"] * SIZE_SHARE[s["size"]] * _demand_multiplier(s["group"], getdate(day)) * growth
			qty = int(round(max(0.0, random.gauss(mean, 0.35 * mean + 0.4))))
			if qty <= 0:
				continue
			items.append(
				{"item_code": s["code"], "qty": qty, "rate": s["sell"], "price_list_rate": s["sell"],
					"income_account": comp.default_income_account, "cost_center": comp.cost_center}
			)
		if not items:
			continue
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice", "customer": customer, "company": c, "set_posting_time": 1,
				"posting_date": day, "due_date": day, "update_stock": 0, "ignore_pricing_rule": 1,
				"selling_price_list": selling, "remarks": f"{HISTORY_TAG} tuần {day}", "items": items,
			}
		)
		si.flags.ignore_permissions = True
		si.insert()
		si.submit()
		if w % 6 == 0:
			frappe.db.commit()
			log(f"  ... còn {w} tuần")
	frappe.db.commit()
	# coi như đã thu tiền: ghi nhận một bút toán thu gộp cho gọn sổ công nợ
	try:
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		names = frappe.get_all(
			"Sales Invoice", filters={"remarks": ["like", f"{HISTORY_TAG}%"], "docstatus": 1, "outstanding_amount": [">", 0]},
			pluck="name", order_by="posting_date",
		)
		for name in names:
			pe = get_payment_entry("Sales Invoice", name)
			pe.posting_date = frappe.db.get_value("Sales Invoice", name, "posting_date")
			pe.reference_no = name
			pe.reference_date = pe.posting_date
			pe.insert(ignore_permissions=True)
			pe.submit()
		frappe.db.commit()
	except Exception as e:
		frappe.db.rollback()
		log(f"Không ghi nhận được thanh toán cho hóa đơn lịch sử: {e}")
	log("Đã tạo xong lịch sử bán hàng.")


def make_sample_orders(skus, stores):
	"""Vài đơn online ở các trạng thái khác nhau để demo ngay."""
	from omni_retail.orders import service

	if frappe.db.exists("Sales Order", {"omni_is_online": 1}):
		return
	c = masters.company()
	customer = "Nguyễn Văn An"
	address = frappe.db.get_value(
		"Dynamic Link", {"parenttype": "Address", "link_doctype": "Customer", "link_name": customer}, "parent"
	)
	by_group = {}
	for s in skus:
		if s["size"] == "M":
			by_group.setdefault(s["group"], s)

	def order(lines, method, pay, store=None):
		so = frappe.get_doc(
			{
				"doctype": "Sales Order", "customer": customer, "company": c, "order_type": "Shopping Cart",
				"transaction_date": nowdate(), "delivery_date": add_days(nowdate(), 3),
				"customer_address": address, "shipping_address_name": address,
				"omni_is_online": 1, "omni_delivery_method": method, "omni_payment_method": pay,
				"omni_pickup_store": store,
				"items": [{"item_code": by_group[g]["code"], "qty": q, "delivery_date": add_days(nowdate(), 3)} for g, q in lines],
			}
		)
		so.insert(ignore_permissions=True)
		so.submit()
		return so.name

	try:
		order([("Áo thun", 2), ("Quần short", 1)], DELIVERY_HOME, PAY_COD)  # chờ xác nhận
		n2 = order([("Áo sơ mi", 1), ("Quần dài", 1)], DELIVERY_HOME, PAY_TRANSFER)
		service.transition(n2, PROCESSING, "Đã gọi xác nhận với khách")
		n3 = order([("Váy đầm", 1)], DELIVERY_HOME, PAY_COD)
		service.transition(n3, PROCESSING)
		service.transition(n3, READY_SHIP, "Đã đóng gói")
		n4 = order([("Áo thun", 1), ("Quần dài", 1)], DELIVERY_PICKUP, PAY_COD, stores[0].name)
		service.transition(n4, PROCESSING)
		service.transition(n4, READY_PICKUP, "Hàng đã để tại quầy")
		frappe.db.commit()
		log("Đã tạo 4 đơn online mẫu.")
	except Exception as e:
		frappe.db.rollback()
		log(f"Không tạo được đơn online mẫu: {e}")


def make_first_plan():
	"""Chạy dự báo một lần để có sẵn Kế hoạch mua hàng chờ duyệt (dùng AI nếu đã cấu hình API key)."""
	if frappe.db.count("Purchase Plan"):
		return
	try:
		from omni_retail.forecasting import planner

		name = planner.run(triggered_by="Dữ liệu demo")
		log(f"Đã lập kế hoạch mua hàng đầu tiên: {name}")
	except Exception as e:
		log(f"Không lập được kế hoạch mua hàng: {e}")
