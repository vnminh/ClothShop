frappe.ui.form.on("Purchase Plan", {
	refresh(frm) {
		const color = {
			"Đang chạy": "orange", "Chờ duyệt": "yellow", "Đã tạo PO": "blue",
			"Đã gửi NCC": "green", "Từ chối": "red", "Lỗi": "red",
		}[frm.doc.status];
		frm.page.set_indicator(frm.doc.status, color || "gray");
		frm.set_df_property("items", "read_only", frm.doc.status !== "Chờ duyệt");

		if (frm.is_new()) return;

		if (frm.doc.status === "Chờ duyệt") {
			frm.add_custom_button("Duyệt & tạo đơn mua hàng", () => {
				const run = () =>
					frappe.confirm("Duyệt kế hoạch và tạo Purchase Order nháp cho từng nhà cung cấp?", () => {
						frm.call("approve_and_create_pos").then((r) => {
							frappe.show_alert({ message: `Đã tạo ${(r.message || []).length} đơn mua hàng`, indicator: "green" });
							frm.reload_doc();
						});
					});
				frm.is_dirty() ? frm.save().then(run) : run();
			}).addClass("btn-primary");
			frm.add_custom_button("Từ chối", () => frm.call("reject").then(() => frm.reload_doc()));
		}

		if (frm.doc.status === "Đã tạo PO") {
			frm.add_custom_button("Xác nhận PO & gửi email nhà cung cấp", () => {
				frappe.confirm("Xác nhận các đơn mua hàng và gửi email cho nhà cung cấp?", () => {
					frm.call({ method: "send_to_suppliers", doc: frm.doc, freeze: true, freeze_message: "Đang gửi..." }).then((r) => {
						const m = r.message || {};
						let msg = `Đã gửi ${(m.sent || []).length} đơn.`;
						if ((m.no_email || []).length) msg += `<br>Chưa có email đặt hàng: ${m.no_email.join(", ")}`;
						frappe.msgprint(msg);
						frm.reload_doc();
					});
				});
			}).addClass("btn-primary");
		}

		const pos = (frm.doc.purchase_orders || "").split("\n").filter(Boolean);
		if (pos.length) {
			frm.add_custom_button("Xem đơn mua hàng", () => {
				frappe.set_route("List", "Purchase Order", { omni_purchase_plan: frm.doc.name });
			});
		}
	},
});

frappe.ui.form.on("Purchase Plan Item", {
	approved_qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "amount", flt(row.approved_qty) * flt(row.rate));
	},
	rate(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "amount", flt(row.approved_qty) * flt(row.rate));
	},
});
