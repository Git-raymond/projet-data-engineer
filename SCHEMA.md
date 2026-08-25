# Schéma des données

```text
stores (1) --------< sales >-------- (1) products

stores
- PK store_id
- city
- employees

products
- PK product_ref
- name
- price
- stock

sales
- PK sale_id
- sale_date
- FK product_ref
- quantity
- FK store_id

analysis_results
- PK analysis_id
- analysis_type
- dimension
- metric_quantity
- metric_revenue
- created_at
```

Le fichier de ventes ne fournit pas d'identifiant de transaction.
`sale_id` est donc un SHA-256 de date + produit + quantité + magasin afin d'éviter
la réimportation d'une ligne strictement identique.
