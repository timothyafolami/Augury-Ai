package api

import (
	"database/sql"
	"encoding/json"
	"net/http"

	"example.com/inventory/internal/reindex"
	"example.com/inventory/internal/store"
)

type view struct {
	SKU      string `json:"sku"`
	Name     string `json:"name"`
	OnHand   int    `json:"on_hand"`
	Reserved int    `json:"reserved"`
}

// Register wires the HTTP surface onto a mux.
func Register(mux *http.ServeMux, pool *sql.DB) {
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	mux.HandleFunc("/inventory", func(w http.ResponseWriter, r *http.Request) {
		warehouse := r.URL.Query().Get("warehouse")
		items, err := store.ByWarehouse(pool, warehouse)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		out := make([]view, 0, len(items))
		for _, it := range items {
			reserved, err := store.Reserved(pool, it.SKU)
			if err != nil {
				http.Error(w, err.Error(), http.StatusInternalServerError)
				return
			}
			out = append(out, view{SKU: it.SKU, Name: it.Name, OnHand: it.OnHand, Reserved: reserved})
		}
		json.NewEncoder(w).Encode(out)
	})

	mux.HandleFunc("/reindex", func(w http.ResponseWriter, r *http.Request) {
		results, err := reindex.Run(pool, r.URL.Query().Get("warehouse"))
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		json.NewEncoder(w).Encode(results)
	})
}
