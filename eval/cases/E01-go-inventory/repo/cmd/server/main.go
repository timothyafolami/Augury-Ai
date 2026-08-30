package main

import (
	"log"
	"net/http"

	"example.com/inventory/internal/api"
	"example.com/inventory/internal/db"
)

func main() {
	pool, err := db.Open()
	if err != nil {
		log.Fatalf("open: %v", err)
	}
	defer pool.Close()

	mux := http.NewServeMux()
	api.Register(mux, pool)

	log.Println("listening on :8080")
	if err := http.ListenAndServe(":8080", mux); err != nil {
		log.Fatal(err)
	}
}
