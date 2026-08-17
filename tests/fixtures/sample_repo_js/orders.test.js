const { cancelOrder } = require("./orders");

test("cancel order sets status to cancelled", () => {
  const order = { status: "pending" };
  const result = cancelOrder(order);
  expect(result.status).toBe("cancelled");
});

test("cancel order raises when already shipped", () => {
  const order = { status: "shipped" };
  expect(() => cancelOrder(order)).toThrow();
});
