class OrderError(Exception):
    pass


def cancel_order(order):
    if order["status"] == "shipped":
        raise OrderError("CannotCancelOrder")
    order["status"] = "cancelled"
    return order


def refund_order(order):
    if order["status"] != "cancelled":
        raise OrderError("CannotRefundOrder")
    order["status"] = "refunded"
    return order


def calculate_total(order):
    return sum(item["price"] * item["qty"] for item in order["items"])
