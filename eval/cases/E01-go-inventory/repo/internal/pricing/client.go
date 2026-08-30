package pricing

import (
	"encoding/json"
	"fmt"
	"net/http"
)

type Quote struct {
	SKU   string  `json:"sku"`
	Cents int     `json:"cents"`
	Rate  float64 `json:"rate"`
}

// Fetch asks the pricing service what one SKU currently costs.
func Fetch(sku string) (*Quote, error) {
	resp, err := http.Get(fmt.Sprintf("http://pricing:9000/quote/%s", sku))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var q Quote
	if err := json.NewDecoder(resp.Body).Decode(&q); err != nil {
		return nil, err
	}
	return &q, nil
}
