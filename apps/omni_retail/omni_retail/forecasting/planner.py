"""Pipeline: tổng hợp dữ liệu -> dự báo nền -> AI điều chỉnh -> số lượng đề xuất -> Purchase Plan."""

import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from omni_retail.forecasting import baseline, data, llm

RECENT_WEEKS = 8
CHUNK = 25  # số sản phẩm mẫu gửi AI mỗi lần gọi


def get_config():
	s = frappe.get_single("Omni Retail Settings")
	api_key = s.get_password("openrouter_api_key", raise_exception=False) or frappe.conf.get("openrouter_api_key")
	return frappe._dict(
		ai_enabled=cint(s.ai_enabled),
		api_key=api_key,
		model=s.ai_model or frappe.conf.get("openrouter_model") or "deepseek/deepseek-chat",
		base_url=s.ai_base_url or "https://openrouter.ai/api/v1",
		min_factor=flt(s.min_ai_factor) or 0.3,
		max_factor=flt(s.max_ai_factor) or 3.0,
		history_weeks=max(cint(s.history_weeks) or 78, RECENT_WEEKS),
		cover_days=cint(s.cover_days) or 30,
		safety_days=cint(s.safety_days),
		default_lead_time=cint(s.default_lead_time_days) or 7,
		default_supplier=s.default_supplier,
	)


def build_forecast(cfg, today=None):
	"""Tính dự báo nền cho từng SKU và gom theo sản phẩm mẫu. Không gọi AI."""
	today = getdate(today or nowdate())
	items = data.purchasable_items()
	sales = data.weekly_sales(cfg.history_weeks, today)
	stock = data.stock_levels()
	horizon = cfg.default_lead_time + cfg.cover_days  # kỳ dự báo hiển thị

	templates = {}
	for code, it in items.items():
		series = sales.get(code) or [0.0] * cfg.history_weeks
		t = templates.setdefault(
			it.template,
			frappe._dict(code=it.template, group=it.item_group, weekly=[0.0] * cfg.history_weeks, skus=[], stock=0.0, on_order=0.0),
		)
		t.weekly = [a + b for a, b in zip(t.weekly, series)]
		t.skus.append(code)
		lv = stock.get(code, {})
		t.stock += flt(lv.get("stock"))
		t.on_order += flt(lv.get("on_order"))
		it.weekly = series
		it.stock = flt(lv.get("stock"))
		it.on_order = flt(lv.get("on_order"))

	for t in templates.values():
		# hệ số mùa vụ tính ở cấp sản phẩm mẫu (đủ sản lượng, ít nhiễu hơn từng size/màu)
		t.seasonal = baseline.seasonal_factor(t.weekly, horizon, RECENT_WEEKS)
		t.name = frappe.db.get_value("Item", t.code, "item_name") or t.code
		t.baseline = baseline.baseline_forecast(t.weekly, horizon, t.seasonal, RECENT_WEEKS)["forecast"]

	for it in items.values():
		t = templates[it.template]
		bf = baseline.baseline_forecast(it.weekly, horizon, t.seasonal, RECENT_WEEKS)
		it.daily_rate = bf["daily_rate"]
		it.seasonal = t.seasonal
		it.baseline = bf["forecast"]
	return items, templates, horizon


def ai_adjust(cfg, templates, horizon, today, events, promotions):
	"""Gọi AI theo từng lô sản phẩm mẫu. Trả (summary, {template: {factor, reason}}, errors)."""
	active = [t for t in templates.values() if sum(t.weekly) > 0]
	active.sort(key=lambda t: (t.group or "", t.code))
	period_ends = [str(add_days(today, -28 * i)) for i in range(12, -1, -1)]
	adjustments, summaries, errors = {}, [], []

	for i in range(0, len(active), CHUNK):
		chunk = active[i : i + CHUNK]
		payload = {
			"hom_nay": str(today),
			"ky_du_bao": {"tu_ngay": str(today), "den_ngay": str(add_days(today, horizon)), "so_ngay": horizon},
			"su_kien_mua_vu": events,
			"khuyen_mai": promotions,
			"ghi_chu_du_lieu": (
				"sales_4w: doanh số từng kỳ 4 tuần, kỳ cuối kết thúc hôm nay; ngày kết thúc mỗi kỳ ở ky_4_tuan_ket_thuc. "
				"same_period_last_year: doanh số cùng kỳ dự báo của năm trước (null nếu chưa có dữ liệu)."
			),
			"ky_4_tuan_ket_thuc": period_ends[-13:],
			"san_pham": [
				{
					"code": t.code,
					"name": t.name,
					"group": t.group,
					"sales_4w": baseline.bucketize(t.weekly[-52:], 4),
					"last_8_weeks": [round(x, 1) for x in t.weekly[-8:]],
					"same_period_last_year": _same_period_last_year(t.weekly, horizon),
					"stat_seasonal_factor": round(t.seasonal, 2),
					"baseline_forecast": round(t.baseline, 1),
					"stock": round(t.stock, 1),
					"on_order": round(t.on_order, 1),
				}
				for t in chunk
			],
		}
		try:
			content = llm.call_llm(llm.build_messages(payload), cfg.api_key, cfg.model, cfg.base_url)
			summary, adj = llm.normalize_adjustments(
				llm.parse_json_content(content), [t.code for t in chunk], cfg.min_factor, cfg.max_factor
			)
			adjustments.update(adj)
			if summary:
				summaries.append(summary)
		except Exception as e:
			frappe.log_error(title="omni_retail: lỗi gọi AI dự báo")
			errors.append(f"Lô {i // CHUNK + 1}: {str(e)[:200]}")
	return "\n\n".join(summaries), adjustments, errors


def _same_period_last_year(weekly, horizon_days):
	pivot = len(weekly) - baseline.WEEKS_PER_YEAR
	weeks = max(1, -(-horizon_days // 7))
	if pivot < 0 or pivot + weeks > len(weekly):
		return None
	return round(sum(weekly[pivot : pivot + weeks]), 1)


def run(triggered_by=None, use_ai=True, today=None):
	"""Tạo một Purchase Plan ở trạng thái 'Chờ duyệt'. Trả về tên chứng từ."""
	cfg = get_config()
	today = getdate(today or nowdate())
	plan = frappe.get_doc(
		{
			"doctype": "Purchase Plan",
			"title": f"Kế hoạch mua hàng {frappe.utils.formatdate(today, 'dd/MM/yyyy')}",
			"status": "Đang chạy",
			"company": frappe.defaults.get_global_default("company"),
			"run_date": today,
			"triggered_by": triggered_by or frappe.session.user,
		}
	).insert(ignore_permissions=True)
	frappe.db.commit()

	try:
		_fill_plan(plan, cfg, today, use_ai)
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(title="omni_retail: lập kế hoạch mua hàng thất bại")
		frappe.db.set_value("Purchase Plan", plan.name, {"status": "Lỗi", "ai_error": str(e)[:1000]})
		frappe.db.commit()
		raise
	frappe.db.commit()
	return plan.name


def _fill_plan(plan, cfg, today, use_ai):
	items, templates, horizon = build_forecast(cfg, today)
	events = data.upcoming_events(today, add_days(today, horizon))
	promotions = data.upcoming_promotions(today, add_days(today, horizon))

	summary, adjustments, errors, ai_used = "", {}, [], False
	if use_ai and cfg.ai_enabled:
		if cfg.api_key:
			summary, adjustments, errors = ai_adjust(cfg, templates, horizon, today, events, promotions)
			ai_used = bool(adjustments)
		else:
			errors.append("Chưa cấu hình OpenRouter API key: chỉ dùng dự báo thống kê.")

	rows = []
	for code, it in items.items():
		adj = adjustments.get(it.template) or {}
		factor = flt(adj.get("factor")) or 1.0
		ai_forecast = it.baseline * factor
		lead = it.lead_time_days or cfg.default_lead_time
		qty = baseline.suggest_order_qty(
			ai_forecast / horizon if horizon else 0,
			lead, cfg.cover_days, cfg.safety_days, it.stock, it.on_order, it.min_order_qty,
		)
		if qty <= 0:
			continue
		reason = adj.get("reason") or ""
		stat = f"Bán TB {it.daily_rate:.2f}/ngày; hệ số mùa vụ {it.seasonal:.2f}"
		rows.append(
			{
				"item_code": code,
				"item_name": it.item_name,
				"item_group": it.item_group,
				"supplier": it.supplier or cfg.default_supplier,
				"sold_recent": sum(it.weekly[-RECENT_WEEKS:]),
				"baseline_forecast": round(it.baseline, 2),
				"seasonal_factor": round(it.seasonal, 3),
				"ai_factor": factor,
				"ai_forecast": round(ai_forecast, 2),
				"current_stock": it.stock,
				"on_order": it.on_order,
				"lead_time_days": lead,
				"suggested_qty": qty,
				"approved_qty": qty,
				"rate": it.rate,
				"reason": f"{reason} ({stat})" if reason else stat,
			}
		)
	rows.sort(key=lambda r: (r["supplier"] or "", r["item_group"] or "", r["item_code"]))

	plan.reload()
	plan.update(
		{
			"status": "Chờ duyệt",
			"forecast_from": today,
			"forecast_to": add_days(today, horizon),
			"horizon_days": horizon,
			"ai_used": 1 if ai_used else 0,
			"ai_model": cfg.model if ai_used else None,
			"ai_summary": summary
			or (
				"Kế hoạch được lập từ dự báo thống kê (trung bình bán gần đây × hệ số mùa vụ cùng kỳ năm trước), "
				"chưa có điều chỉnh của AI."
			),
			"events_considered": "\n".join(
				[f"• {e['ten']} ({e['tu_ngay']} → {e['den_ngay']}): {e['tac_dong']}" for e in events]
				+ [f"• Khuyến mãi: {p['ten']} – {p['uu_dai']} ({p['ap_dung_cho']})" for p in promotions]
			),
			"ai_error": "\n".join(errors),
		}
	)
	plan.set("items", rows)
	plan.save(ignore_permissions=True)
