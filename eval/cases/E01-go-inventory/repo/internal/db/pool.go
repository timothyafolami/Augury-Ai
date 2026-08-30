package db

import (
	"database/sql"
	"os"

	_ "github.com/lib/pq"
)

// Open returns the shared connection pool.
func Open() (*sql.DB, error) {
	dsn := os.Getenv("DATABASE_URL")
	if dsn == "" {
		dsn = "postgres://inventory:inventory@db:5432/inventory?sslmode=disable"
	}
	pool, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, err
	}
	pool.SetMaxOpenConns(4)
	return pool, nil
}
