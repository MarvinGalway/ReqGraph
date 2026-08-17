import pytest
from orders import OrderError, calculate_total, cancel_order


def test_cancel_order_ok():
    order = {"status": "pending"}
    result = cancel_order(order)
    assert result["status"] == "cancelled"


def test_cancel_order_when_shipped_raises():
    order = {"status": "shipped"}
    with pytest.raises(OrderError):
        cancel_order(order)


def test_calculate_total():
    order = {"items": [{"price": 10, "qty": 2}, {"price": 5, "qty": 1}]}
    assert calculate_total(order) == 25
