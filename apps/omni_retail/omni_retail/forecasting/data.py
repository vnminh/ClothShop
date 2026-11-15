"""Tổng hợp dữ liệu đầu vào cho dự báo từ ERPNext."""

import frappe
from frappe.utils import add_days, add_years, cint, flt, getdate


def weekly_sales(weeks, today=None):
	"""{item_code: [qty tuần 0 (cũ nhất) ... tuần weeks-1 (mới nhất)]}.
	Gồm Sales Invoice (trừ hóa đơn gộp từ POS để không đếm trùng) và POS Invoice; trả hàng được trừ ra."""
	today = getdate(today)
	start = add_days(today, -7 * weeks)
	rows = frappe.db.sql(
		"""
		select item_code, floor(datediff(posting_date, %(start)s) / 7) as wk, sum(qty) as qty from (
			select sii.item_code, si.posting_date, sii.stock_qty as qty
			from `tabSales Invoice Item` sii join `tabSales Invoice` si on si.name = sii.parent
			where si.docstatus = 1 and ifnull(si.is_consolidated, 0) = 0
				and si.posting_date >= %(start)s and si.posting_date < %(today)s
			union all
			select pii.item_code, pi.posting_date, pii.stock_qty as qty
			from `tabPOS Invoice Item` pii join `tabPOS Invoice` pi on pi.name = pii.parent
			where pi.docstatus = 1 and pi.posting_date >= %(start)s and pi.posting_date < %(today)s
		) t group by item_code, wk
		""",
		{"start": start, "today": today},
		as_dict=True,
	)
	out = {}
	for r in rows:
		wk = cint(r.wk)
		if 0 <= wk < weeks:
			out.setdefault(r.item_code, [0.0] * weeks)[wk] += flt(r.qty)
	for series in out.values():
		for i, v in enumerate(series):
			if v < 0:
				series[i] = 0.0
	return out


def stock_levels():
	"""{item_code: {"stock": tồn thực toàn hệ thống, "on_order": đang về theo PO}}"""
	rows = frappe.db.sql(
		"select item_code, sum(actual_qty) as stock, sum(ordered_qty) as on_order from `tabBin` group by item_code",
		as_dict=True,
	)
	return {r.item_code: {"stock": flt(r.stock), "on_order": flt(r.on_order)} for r in rows}


def purchasable_items():
	"""Các SKU (không phải template) có thể mua, kèm NCC mặc định, lead time, MOQ, giá mua."""
	items = frappe.get_all(
		"Item",
		filters={"disabled": 0, "is_stock_item": 1, "has_variants": 0, "is_purchase_item": 1},
		fields=[
			"name", "item_name", "item_group", "variant_of", "lead_time_days",
			"min_order_qty", "last_purchase_rate", "valuation_rate",
		],
	)
	default_supplier = {}
	for r in frappe.get_all(
		"Item Default", filters={"parenttype": "Item"}, fields=["parent", "default_supplier"]
	):
		if r.default_supplier:
			default_supplier.setdefault(r.parent, r.default_supplier)
	for r in frappe.get_all(
		"Item Supplier", filters={"parenttype": "Item"}, fields=["parent", "supplier"], order_by="idx"
	):
		default_supplier.setdefault(r.parent, r.supplier)
	buying_price = {}
	for r in frappe.get_all(
		"Item Price", filters={"buying": 1}, fields=["item_code", "price_list_rate"], order_by="modified asc"
	):
		buying_price[r.item_code] = flt(r.price_list_rate)

	out = {}
	for it in items:
		# biến thể kế thừa NCC / giá mua của sản phẩm mẫu nếu chưa khai báo riêng
		supplier = default_supplier.get(it.name) or default_supplier.get(it.variant_of)
		rate = (
			buying_price.get(it.name)
			or buying_price.get(it.variant_of)
			or flt(it.last_purchase_rate)
			or flt(it.valuation_rate)
		)
		out[it.name] = frappe._dict(
			item_code=it.name,
			item_name=it.item_name,
			item_group=it.item_group,
			template=it.variant_of or it.name,
			lead_time_days=cint(it.lead_time_days),
			min_order_qty=flt(it.min_order_qty),
			supplier=supplier,
			rate=rate,
		)
	return out


def upcoming_events(from_date, to_date):
	"""Sự kiện/mùa vụ giao với khoảng [from_date, to_date]; sự kiện lặp hằng năm được dời sang năm phù hợp."""
	from_date, to_date = getdate(from_date), getdate(to_date)
	out = []
	for ev in frappe.get_all(
		"Seasonal Event",
		filters={"is_active": 1},
		fields=["event_name", "event_type", "from_date", "to_date", "recurring_yearly", "affected_item_groups", "impact_note"],
	):
		start, end = getdate(ev.from_date), getdate(ev.to_date)
		candidates = [(start, end)]
		if cint(ev.recurring_yearly):
			candidates = []
			for year in range(from_date.year - 1, to_date.year + 1):
				shift = year - start.year
				candidates.append((getdate(add_years(start, shift)), getdate(add_years(end, shift))))
		for s, e in candidates:
			if s <= to_date and e >= from_date:
				out.append(
					{
						"ten": ev.event_name,
						"loai": ev.event_type,
						"tu_ngay": str(s),
						"den_ngay": str(e),
						"dong_san_pham": ev.affected_item_groups or "tất cả",
						"tac_dong": ev.impact_note or "",
					}
				)
				break
	out.sort(key=lambda d: d["tu_ngay"])
	return out


def upcoming_promotions(from_date, to_date):
	"""Chương trình khuyến mãi (Pricing Rule bán hàng) còn hiệu lực trong kỳ dự báo."""
	out = []
	for pr in frappe.get_all(
		"Pricing Rule",
		filters={"disable": 0, "selling": 1},
		fields=[
			"name", "title", "apply_on", "price_or_product_discount", "rate_or_discount",
			"discount_percentage", "discount_amount", "valid_from", "valid_upto", "coupon_code_based",
		],
	):
		if pr.valid_from and getdate(pr.valid_from) > getdate(to_date):
			continue
		if pr.valid_upto and getdate(pr.valid_upto) < getdate(from_date):
			continue
		targets = frappe.get_all(
			"Pricing Rule Item Group", filters={"parent": pr.name}, pluck="item_group"
		) or frappe.get_all("Pricing Rule Item Code", filters={"parent": pr.name}, pluck="item_code")
		if pr.price_or_product_discount == "Product":
			kind = "tặng sản phẩm"
		elif flt(pr.discount_percentage):
			kind = f"giảm {flt(pr.discount_percentage):g}%"
		elif flt(pr.discount_amount):
			kind = f"giảm {flt(pr.discount_amount):g}đ"
		else:
			kind = "ưu đãi giá"
		out.append(
			{
				"ten": pr.title or pr.name,
				"uu_dai": kind,
				"ap_dung_cho": ", ".join(targets[:8]) or "toàn bộ",
				"can_ma_coupon": bool(cint(pr.coupon_code_based)),
				"tu_ngay": str(pr.valid_from or ""),
				"den_ngay": str(pr.valid_upto or ""),
			}
		)
	return out
