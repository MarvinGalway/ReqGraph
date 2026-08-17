class OrderError extends Error {}

function cancelOrder(order) {
  if (order.status === "shipped") {
    throw new OrderError("CannotCancelOrder");
  }
  order.status = "cancelled";
  return order;
}

function markRefunded(order) {
  order.status = "refunded";
  return order;
}

function refundOrder(order) {
  if (order.status !== "cancelled") {
    throw new OrderError("CannotRefundOrder");
  }
  return markRefunded(order);
}

module.exports = { OrderError, cancelOrder, refundOrder };
