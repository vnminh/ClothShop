"""State machine thuần (không phụ thuộc frappe) cho vòng đời đơn online.

Giao tại nhà:
  Chờ xác nhận -> Đang xử lý -> Sẵn sàng giao hàng -> Đang giao hàng -> Thành công -> (Đã trả hàng)
                                                        └-> Giao thất bại -> Sẵn sàng giao hàng | Đã hủy
Nhận tại điểm bán:
  Chờ xác nhận -> Đang xử lý -> Sẵn sàng nhận tại điểm bán -> Thành công -> (Đã trả hàng)
Hủy: khách chỉ hủy được khi "Chờ xác nhận"; nhân viên hủy được trước khi "Đang giao hàng".
"""

from omni_retail.constants import (
	ACTOR_CUSTOMER,
	ACTOR_SHIPPER,
	ACTOR_STAFF,
	ACTOR_SYSTEM,
	CANCELLED,
	DELIVERY_HOME,
	DELIVERY_PICKUP,
	DONE,
	FAILED,
	PENDING,
	PROCESSING,
	READY_PICKUP,
	READY_SHIP,
	RETURNED,
	SHIPPING,
)


class TransitionError(Exception):
	pass


_BOTH = (DELIVERY_HOME, DELIVERY_PICKUP)

# (from, to) -> (các actor được phép, các hình thức nhận hàng áp dụng)
TRANSITIONS = {
	(PENDING, PROCESSING): ((ACTOR_STAFF,), _BOTH),
	(PROCESSING, READY_SHIP): ((ACTOR_STAFF,), (DELIVERY_HOME,)),
	(PROCESSING, READY_PICKUP): ((ACTOR_STAFF,), (DELIVERY_PICKUP,)),
	(READY_SHIP, SHIPPING): ((ACTOR_SHIPPER,), (DELIVERY_HOME,)),
	(SHIPPING, DONE): ((ACTOR_SHIPPER,), (DELIVERY_HOME,)),
	(SHIPPING, FAILED): ((ACTOR_SHIPPER,), (DELIVERY_HOME,)),
	(FAILED, READY_SHIP): ((ACTOR_STAFF,), (DELIVERY_HOME,)),
	(READY_PICKUP, DONE): ((ACTOR_STAFF,), (DELIVERY_PICKUP,)),
	(DONE, RETURNED): ((ACTOR_STAFF,), _BOTH),
	# hủy đơn
	(PENDING, CANCELLED): ((ACTOR_CUSTOMER, ACTOR_STAFF, ACTOR_SYSTEM), _BOTH),
	(PROCESSING, CANCELLED): ((ACTOR_STAFF, ACTOR_SYSTEM), _BOTH),
	(READY_SHIP, CANCELLED): ((ACTOR_STAFF, ACTOR_SYSTEM), (DELIVERY_HOME,)),
	(READY_PICKUP, CANCELLED): ((ACTOR_STAFF, ACTOR_SYSTEM), (DELIVERY_PICKUP,)),
	(FAILED, CANCELLED): ((ACTOR_STAFF, ACTOR_SYSTEM), (DELIVERY_HOME,)),
}


def next_statuses(current, delivery_method, actors):
	"""Danh sách trạng thái mà một trong các `actors` được phép chuyển tới."""
	actors = set(actors or ())
	out = []
	for (src, dst), (allowed, methods) in TRANSITIONS.items():
		if src == current and delivery_method in methods and actors.intersection(allowed):
			out.append(dst)
	return out


def check_transition(current, target, delivery_method, actors):
	"""Ném TransitionError nếu không được phép chuyển current -> target."""
	rule = TRANSITIONS.get((current, target))
	if not rule:
		raise TransitionError(f"Không thể chuyển đơn từ «{current}» sang «{target}».")
	allowed, methods = rule
	if delivery_method not in methods:
		raise TransitionError(
			f"Trạng thái «{target}» không áp dụng cho đơn «{delivery_method}»."
		)
	if not set(actors or ()).intersection(allowed):
		raise TransitionError(f"Bạn không có quyền chuyển đơn sang «{target}».")
	return True
