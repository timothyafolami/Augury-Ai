package reindex

import (
	"database/sql"
	"log"

	"example.com/inventory/internal/pricing"
	"example.com/inventory/internal/store"
)

type Result struct {
	SKU   string
	Cents int
}

// Run reprices every SKU in a warehouse, one goroutine per item.
func Run(pool *sql.DB, warehouse string) ([]Result, error) {
	items, err := store.ByWarehouse(pool, warehouse)
	if err != nil {
		return nil, err
	}

	results := make(chan Result)
	errs := make(chan error)

	for _, it := range items {
		go func(sku string) {
			q, err := pricing.Fetch(sku)
			if err != nil {
				errs <- err
				return
			}
			results <- Result{SKU: sku, Cents: q.Cents}
		}(it.SKU)
	}

	var out []Result
	for range items {
		select {
		case r := <-results:
			out = append(out, r)
		case err := <-errs:
			log.Printf("reindex: %v", err)
			return out, err
		}
	}
	return out, nil
}
