def test_overview_seeded(client):
    r = client.get("/api/overview")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3

    # Проверка данных по ТЗ:
    # SKU-101 Органайзер: Север 10, Юг 6
    # SKU-102 Контейнер: Север 5, Юг 0
    # SKU-103 Корзина: Север 0, Юг 4
    sku_map = {item["sku"]: item for item in data}
    assert sku_map["SKU-101"]["total_physical"] == 16
    assert sku_map["SKU-102"]["total_physical"] == 5
    assert sku_map["SKU-103"]["total_physical"] == 4


def test_shortage_detection(client):
    # Проверяем нехватку: на Юге для SKU-102 доступно 0, но на Севере есть 5
    # Пробуем зарезервировать FBS на Юге 2 шт
    warehouses = client.get("/api/warehouses").json()
    wh_south = next(w for w in warehouses if w["name"] == "Юг")
    products = client.get("/api/products").json()
    prod_102 = next(p for p in products if p["sku"] == "SKU-102")

    res = client.post("/api/shipments/fbs/reserve", json={
        "warehouse_id": wh_south["id"],
        "product_id": prod_102["id"],
        "quantity": 2
    })
    assert res.status_code == 400
    error_data = res.json()
    assert error_data["error_code"] == "STOCK_SHORTAGE"
    assert "Север" in error_data["message"]


def test_movement_and_idempotency(client):
    warehouses = client.get("/api/warehouses").json()
    wh_north = next(w for w in warehouses if w["name"] == "Север")
    wh_south = next(w for w in warehouses if w["name"] == "Юг")
    products = client.get("/api/products").json()
    prod_101 = next(p for p in products if p["sku"] == "SKU-101")

    # Перемещаем 3 шт Органайзера с Севера на Юг
    res_send = client.post("/api/movements", json={
        "from_warehouse_id": wh_north["id"],
        "to_warehouse_id": wh_south["id"],
        "product_id": prod_101["id"],
        "quantity": 3,
        "idempotency_key": "move-test-123"
    })
    assert res_send.status_code == 200
    mov_id = res_send.json()["movement_id"]

    # Повторная отправка с тем же ключом идемпотентности — не должна дублировать списание
    res_send_dup = client.post("/api/movements", json={
        "from_warehouse_id": wh_north["id"],
        "to_warehouse_id": wh_south["id"],
        "product_id": prod_101["id"],
        "quantity": 3,
        "idempotency_key": "move-test-123"
    })
    assert res_send_dup.status_code == 200
    assert res_send_dup.json()["movement_id"] == mov_id

    # Приёмка перемещения на Юге
    res_rec = client.post(f"/api/movements/{mov_id}/receive", params={"idempotency_key": "rec-123"})
    assert res_rec.status_code == 200

    # Повторная приёмка не должна увеличить остаток дважды
    res_rec_dup = client.post(f"/api/movements/{mov_id}/receive", params={"idempotency_key": "rec-123"})
    assert res_rec_dup.status_code == 200


def test_soft_delete_warehouse(client):
    # Создаем склад и удаляем его
    res_create = client.post("/api/warehouses", json={"name": "Восток"})
    assert res_create.status_code == 200
    wh_id = res_create.json()["id"]

    # Добавим приход
    products = client.get("/api/products").json()
    client.post("/api/stock/income", json={
        "warehouse_id": wh_id,
        "product_id": products[0]["id"],
        "quantity": 10
    })

    # Мягкое удаление склада
    res_del = client.delete(f"/api/warehouses/{wh_id}")
    assert res_del.status_code == 200
    del_data = res_del.json()
    assert del_data["has_remaining_stock"] is True
    assert del_data["remaining_items_count"] == 10


def test_fbs_flow_and_double_shipment(client):
    warehouses = client.get("/api/warehouses").json()
    wh_north = next(w for w in warehouses if w["name"] == "Север")
    products = client.get("/api/products").json()
    prod_101 = next(p for p in products if p["sku"] == "SKU-101")

    # 1. Резерв FBS на 2 шт
    res_resv = client.post("/api/shipments/fbs/reserve", json={
        "warehouse_id": wh_north["id"],
        "product_id": prod_101["id"],
        "quantity": 2,
        "idempotency_key": "fbs-resv-001"
    })
    assert res_resv.status_code == 200
    shipment_id = res_resv.json()["shipment_id"]

    # 2. Отправка клиенту (списание со склада)
    res_ship = client.post(f"/api/shipments/fbs/{shipment_id}/ship", params={"idempotency_key": "ship-fbs-001"})
    assert res_ship.status_code == 200
    assert res_ship.json()["shipment_status"] == "SHIPPED_TO_CLIENT"

    # 3. ПОВТОРНЫЙ КЛИК (защита от двойного списания)
    res_ship_dup = client.post(f"/api/shipments/fbs/{shipment_id}/ship", params={"idempotency_key": "ship-fbs-001"})
    assert res_ship_dup.status_code == 200
    assert res_ship_dup.json()["shipment_status"] == "SHIPPED_TO_CLIENT"

    # 4. Вручение клиенту
    res_deliv = client.post(f"/api/shipments/fbs/{shipment_id}/deliver")
    assert res_deliv.status_code == 200
    assert res_deliv.json()["shipment_status"] == "DELIVERED"


def test_fbo_flow_and_receiving(client):
    warehouses = client.get("/api/warehouses").json()
    wh_north = next(w for w in warehouses if w["name"] == "Север")
    products = client.get("/api/products").json()
    prod_102 = next(p for p in products if p["sku"] == "SKU-102")

    # 1. Отгрузка FBO (3 шт едут на маркетплейс)
    res_fbo = client.post("/api/shipments/fbo/ship", json={
        "warehouse_id": wh_north["id"],
        "product_id": prod_102["id"],
        "quantity": 3,
        "destination": "Склад WB Коледино",
        "idempotency_key": "fbo-ship-001"
    })
    assert res_fbo.status_code == 200
    shipment_id = res_fbo.json()["shipment_id"]

    # 2. Проверяем статус "в пути FBO"
    overview = client.get("/api/overview").json()
    prod_data = next(p for p in overview if p["sku"] == "SKU-102")
    assert prod_data["in_transit_fbo"] >= 3

    # 3. Приёмка маркетплейсом
    res_recv = client.post(f"/api/shipments/fbo/{shipment_id}/receive", params={"idempotency_key": "fbo-recv-001"})
    assert res_recv.status_code == 200
    assert res_recv.json()["shipment_status"] == "RECEIVED_BY_MP"

    # 4. Повторный клик приёмки FBO
    res_recv_dup = client.post(f"/api/shipments/fbo/{shipment_id}/receive", params={"idempotency_key": "fbo-recv-001"})
    assert res_recv_dup.status_code == 200
