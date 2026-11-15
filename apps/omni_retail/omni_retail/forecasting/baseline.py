"""Dự báo nền bằng thống kê + công thức số lượng đặt hàng. Thuần Python, không phụ thuộc frappe.

Chuỗi đầu vào luôn là doanh số theo tuần, sắp từ cũ nhất -> mới nhất.
"""

import math

WEEKS_PER_YEAR = 52


def recent_daily_rate(weekly, recent_weeks=8):
	"""Tốc độ bán/ngày: trung bình có trọng số (tuần càng gần càng nặng) của N tuần gần nhất."""
	tail = [max(float(x or 0), 0.0) for x in list(weekly)[-recent_weeks:]]
	if not tail:
		return 0.0
	weights = list(range(1, len(tail) + 1))
	return sum(q * w for q, w in zip(tail, weights)) / sum(weights) / 7.0


def seasonal_factor(weekly, horizon_days, recent_weeks=8, lo=0.5, hi=2.5, min_base_qty=8):
	"""Hệ số mùa vụ kiểu seasonal-naive: cùng kỳ năm trước, nhu cầu trong kỳ dự báo
	gấp bao nhiêu lần giai đoạn ngay trước đó. Trả 1.0 nếu chưa đủ dữ liệu."""
	weekly = [max(float(x or 0), 0.0) for x in weekly]
	horizon_weeks = max(1, int(math.ceil(horizon_days / 7.0)))
	pivot = len(weekly) - WEEKS_PER_YEAR  # vị trí "hôm nay của năm trước"
	if pivot - recent_weeks < 0:
		return 1.0
	base = weekly[pivot - recent_weeks : pivot]
	forward = weekly[pivot : pivot + horizon_weeks]
	if len(forward) < horizon_weeks or sum(base) < min_base_qty:
		return 1.0
	# cùng cách tính trọng số với recent_daily_rate để hai đại lượng so sánh được với nhau
	weights = list(range(1, len(base) + 1))
	base_rate = sum(q * w for q, w in zip(base, weights)) / sum(weights)
	forward_rate = sum(forward) / len(forward)
	if base_rate <= 0:
		return 1.0
	return clamp(forward_rate / base_rate, lo, hi)


def clamp(value, lo, hi):
	try:
		value = float(value)
	except (TypeError, ValueError):
		return 1.0
	if math.isnan(value) or math.isinf(value):
		return 1.0
	return max(lo, min(hi, value))


def baseline_forecast(weekly, horizon_days, factor=None, recent_weeks=8):
	"""Nhu cầu dự báo trong `horizon_days` ngày tới."""
	rate = recent_daily_rate(weekly, recent_weeks)
	if factor is None:
		factor = seasonal_factor(weekly, horizon_days, recent_weeks)
	return {
		"daily_rate": rate,
		"seasonal_factor": factor,
		"forecast": rate * horizon_days * factor,
	}


def suggest_order_qty(
	daily_forecast, lead_time_days, cover_days, safety_days, stock, on_order, min_order_qty=0, multiple=1
):
	"""SL đề xuất = nhu cầu trong (lead time + kỳ phủ) + tồn an toàn - tồn hiện tại - hàng đang về.
	Làm tròn lên theo bội số đóng gói và số lượng đặt tối thiểu."""
	daily_forecast = max(float(daily_forecast or 0), 0.0)
	need = daily_forecast * (lead_time_days + cover_days + safety_days)
	qty = need - max(float(stock or 0), 0.0) - max(float(on_order or 0), 0.0)
	if qty <= 0:
		return 0
	multiple = max(int(multiple or 1), 1)
	qty = int(math.ceil(qty / multiple) * multiple)
	if min_order_qty and qty < min_order_qty:
		qty = int(math.ceil(float(min_order_qty) / multiple) * multiple)
	return qty


def bucketize(weekly, size=4):
	"""Gộp chuỗi tuần thành các kỳ `size` tuần (tính từ cuối về đầu) để gửi AI cho gọn."""
	weekly = list(weekly)
	out = []
	end = len(weekly)
	while end > 0:
		start = max(0, end - size)
		out.append(round(sum(weekly[start:end]), 2))
		end = start
	return list(reversed(out))
