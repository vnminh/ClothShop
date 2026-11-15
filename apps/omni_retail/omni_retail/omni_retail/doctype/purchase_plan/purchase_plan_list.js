frappe.listview_settings["Purchase Plan"] = {
	get_indicator(doc) {
		const color = {
			"Đang chạy": "orange", "Chờ duyệt": "yellow", "Đã tạo PO": "blue",
			"Đã gửi NCC": "green", "Từ chối": "red", "Lỗi": "red",
		}[doc.status] || "gray";
		return [doc.status, color, "status,=," + doc.status];
	},
	onload(listview) {
		listview.page.add_inner_button("Chạy AI dự báo ngay", () => {
			frappe.call("omni_retail.forecasting.tasks.run_now").then(() => {
				frappe.show_alert({
					message: "Đã đưa vào hàng đợi. Kế hoạch sẽ xuất hiện trong danh sách sau ít phút.",
					indicator: "blue",
				}, 8);
			});
		});
	},
};
