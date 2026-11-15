"""Hàm tạo dữ liệu nền dùng chung (idempotent)."""

import frappe


def company():
	return frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")


def abbr(c=None):
	return frappe.get_cached_value("Company", c or company(), "abbr")


def root_warehouse(c=None):
	c = c or company()
	return frappe.db.get_value(
		"Warehouse", {"company": c, "is_group": 1, "parent_warehouse": ["in", ["", None]]}, "name"
	)


def ensure_warehouse(name, parent=None, is_group=0, c=None):
	c = c or company()
	full = f"{name} - {abbr(c)}"
	if frappe.db.exists("Warehouse", full):
		return full
	doc = frappe.get_doc(
		{
			"doctype": "Warehouse",
			"warehouse_name": name,
			"company": c,
			"is_group": is_group,
			"parent_warehouse": parent or root_warehouse(c),
		}
	).insert(ignore_permissions=True)
	return doc.name


def store_group_warehouse():
	return ensure_warehouse("Điểm bán lẻ", is_group=1)


def selling_price_list():
	return frappe.db.get_single_value("Selling Settings", "selling_price_list") or frappe.db.get_value(
		"Price List", {"selling": 1, "enabled": 1}, "name"
	)


def walk_in_customer():
	name = "Khách lẻ"
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": "Individual",
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			}
		).insert(ignore_permissions=True)
	return name


def ensure_pos_profile(store_name, warehouse):
	name = f"POS {store_name}"
	if frappe.db.exists("POS Profile", name):
		return name
	c = company()
	comp = frappe.get_cached_doc("Company", c)
	s = frappe.get_single("Omni Retail Settings")
	payments = []
	if s.cod_mode_of_payment:
		payments.append({"mode_of_payment": s.cod_mode_of_payment, "default": 1})
	if s.transfer_mode_of_payment:
		payments.append({"mode_of_payment": s.transfer_mode_of_payment, "default": 0})
	doc = frappe.get_doc(
		{
			"doctype": "POS Profile",
			"__newname": name,
			"company": c,
			"customer": walk_in_customer(),
			"warehouse": warehouse,
			"currency": comp.default_currency,
			"selling_price_list": selling_price_list(),
			"write_off_account": comp.write_off_account,
			"write_off_cost_center": comp.cost_center,
			"cost_center": comp.cost_center,
			"income_account": comp.default_income_account,
			"expense_account": comp.default_expense_account,
			"payments": payments,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name
