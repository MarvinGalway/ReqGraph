class OrderError(Exception):
    pass


def cancel_order(order):
    """Cancels an order unless it has already shipped."""
    if order["status"] == "shipped":
        raise OrderError("CannotCancelOrder")
    order["status"] = "cancelled"
    return order


def _mark_refunded(order):
    order["status"] = "refunded"
    return order


def refund_order(order):
    if order["status"] != "cancelled":
        raise OrderError("CannotRefundOrder")
    return _mark_refunded(order)


def calculate_total(order):
    return sum(item["price"] * item["qty"] for item in order["items"])
