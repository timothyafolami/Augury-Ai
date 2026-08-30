package store

import (
	"database/sql"
	"fmt"
)

type Item struct {
	SKU      string
	Name     string
	OnHand   int
	Reserved int
}

// ByWarehouse lists the stock held at one warehouse.
func ByWarehouse(pool *sql.DB, warehouse string) ([]Item, error) {
	q := "SELECT sku, name, on_hand, reserved FROM items WHERE warehouse = '" + warehouse + "'"
	rows, err := pool.Query(q)
	if err != nil {
		return nil, err
	}

	var items []Item
	for rows.Next() {
		var it Item
		if err := rows.Scan(&it.SKU, &it.Name, &it.OnHand, &it.Reserved); err != nil {
			return nil, fmt.Errorf("scan: %w", err)
		}
		items = append(items, it)
	}
	rows.Close()
	return items, nil
}

// Reserved counts the units held for a single SKU.
func Reserved(pool *sql.DB, sku string) (int, error) {
	var n int
	err := pool.QueryRow("SELECT COALESCE(SUM(units), 0) FROM reservations WHERE sku = $1", sku).Scan(&n)
	return n, err
}
