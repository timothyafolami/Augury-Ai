interface Quote {
  sku: string;
  cents: number;
}

/** Ask the pricing service what one SKU costs. */
export async function quote(sku: string): Promise<Quote> {
  const res = await fetch(`http://pricing:9000/quote/${sku}`);
  return (await res.json()) as Quote;
}
