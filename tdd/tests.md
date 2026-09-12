# 好测试与坏测试

## 好测试

**集成风格**：通过真实接口测试，而不是 mock 内部部件。

```typescript
// 好：测试可观察的行为
test("用户可以用有效购物车结账", async () => {
  const cart = createCart();
  cart.add(product);
  const result = await checkout(cart, paymentMethod);
  expect(result.status).toBe("confirmed");
});
```

特征：

- 测试用户/调用方关心的行为
- 只使用公共 API
- 在内部重构后依然有效
- 描述做什么，而不是怎么做
- 每个测试一个逻辑断言

## 坏测试

**实现细节测试**：与内部结构耦合。

```typescript
// 差：测试实现细节
test("checkout 调用了 paymentService.process", async () => {
  const mockPayment = jest.mock(paymentService);
  await checkout(cart, payment);
  expect(mockPayment.process).toHaveBeenCalledWith(cart.total);
});
```

危险信号：

- mock 内部协作者
- 测试私有方法
- 对调用次数/顺序做断言
- 重构但行为未变时测试就挂
- 测试名描述的是怎么做而不是做什么
- 通过外部手段而不是接口来验证

```typescript
// 差：绕过接口去验证
test("createUser 保存到数据库", async () => {
  await createUser({ name: "Alice" });
  const row = await db.query("SELECT * FROM users WHERE name = ?", ["Alice"]);
  expect(row).toBeDefined();
});

// 好：通过接口验证
test("createUser 让用户可以被取回", async () => {
  const user = await createUser({ name: "Alice" });
  const retrieved = await getUser(user.id);
  expect(retrieved.name).toBe("Alice");
});
```

**同义反复测试**：期望值只是把实现复述一遍，因此测试在构造上必然通过。

```typescript
// 差：期望值用与代码相同的方式重新计算
test("calculateTotal 对行项目求和", () => {
  const items = [{ price: 10 }, { price: 5 }];
  const expected = items.reduce((sum, i) => sum + i.price, 0);
  expect(calculateTotal(items)).toBe(expected);
});

// 好：期望值是独立、已知的字面量
test("calculateTotal 对行项目求和", () => {
  expect(calculateTotal([{ price: 10 }, { price: 5 }])).toBe(15);
});
```
